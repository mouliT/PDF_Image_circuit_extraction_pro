"""Schematic PDF circuit-island extraction (layout-aware, raster density).

Goal
-----
Extract functional "circuit islands" from schematic PDFs where blocks are
placed arbitrarily and may be connected by long nets (power rails, labels,
inter-block wires). These islands are closer to human-drawn contours than to
electrical connected components.

Approach (Beta)
--------------
Vector-only connectivity tends to either:
  - merge the whole page (global nets), or
  - fragment into tiny pieces if you cut bridges aggressively.

This beta implementation uses a layout-density segmentation:
  - render page to grayscale at the requested DPI
  - compute a local ink density map (Gaussian blur of an ink mask)
  - threshold to get coarse "block" regions
  - connected components on the coarse regions
  - dilate/close to get a smooth arbitrary-shaped mask per block

The output is a per-island RGBA PNG with an arbitrary-shaped alpha mask.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import fitz  # PyMuPDF
import numpy as np
from PIL import Image, ImageDraw, ImageFilter


@dataclass(frozen=True)
class Island:
    """One extracted island on a single page."""

    page_index: int  # 0-based
    island_index: int  # 1-based within page
    dpi: int
    bbox: tuple[int, int, int, int]  # (x0, y0, x1, y1) in rendered pixels
    mask: Image.Image  # 'L' alpha mask, same size as bbox


def _connected_components_4(mask: np.ndarray) -> list[tuple[int, int, int, int, np.ndarray]]:
    """Return (x0,y0,x1,y1,comp_mask) for 4-connected components.

    mask: bool/uint8 array, True/1 indicates foreground.
    comp_mask is a bool array cropped to the bbox.
    """
    H, W = mask.shape
    seen = np.zeros((H, W), dtype=np.uint8)
    comps: list[tuple[int, int, int, int, np.ndarray]] = []

    from collections import deque

    for y in range(H):
        row = mask[y]
        for x in range(W):
            if not row[x] or seen[y, x]:
                continue
            q = deque([(y, x)])
            seen[y, x] = 1
            xs: list[int] = [x]
            ys: list[int] = [y]
            pts: list[tuple[int, int]] = [(y, x)]
            while q:
                cy, cx = q.popleft()
                for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                    if 0 <= ny < H and 0 <= nx < W and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = 1
                        q.append((ny, nx))
                        xs.append(nx)
                        ys.append(ny)
                        pts.append((ny, nx))

            x0, x1 = min(xs), max(xs) + 1
            y0, y1 = min(ys), max(ys) + 1
            cm = np.zeros((y1 - y0, x1 - x0), dtype=bool)
            for py, px in pts:
                cm[py - y0, px - x0] = True
            comps.append((x0, y0, x1, y1, cm))

    return comps


def _iter_segments_from_drawings(drawings: list[dict]) -> Iterable[tuple[tuple[float, float], tuple[float, float], float]]:
    """Yield (p0, p1, width_pt) segments from PyMuPDF drawings."""
    for d in drawings:
        w = float(d.get("width") or 0.5)
        for it in d.get("items", []) or []:
            t = it[0]
            if t == "l":
                p0 = it[1]
                p1 = it[2]
                yield (float(p0.x), float(p0.y)), (float(p1.x), float(p1.y)), w
            elif t == "re":
                r = it[1]
                x0, y0, x1, y1 = float(r.x0), float(r.y0), float(r.x1), float(r.y1)
                yield (x0, y0), (x1, y0), w
                yield (x1, y0), (x1, y1), w
                yield (x1, y1), (x0, y1), w
                yield (x0, y1), (x0, y0), w
            elif t == "qu":
                q = it[1]
                pts = [(float(q.ul.x), float(q.ul.y)), (float(q.ur.x), float(q.ur.y)),
                       (float(q.lr.x), float(q.lr.y)), (float(q.ll.x), float(q.ll.y))]
                for a, b in zip(pts, pts[1:] + pts[:1]):
                    yield a, b, w
            elif t == "c":
                # cubic Bezier: flatten to segments (PyMuPDF exposes control points)
                p0, p1, p2, p3 = it[1], it[2], it[3], it[4]
                P0 = (float(p0.x), float(p0.y))
                P1 = (float(p1.x), float(p1.y))
                P2 = (float(p2.x), float(p2.y))
                P3 = (float(p3.x), float(p3.y))

                def bez(t: float) -> tuple[float, float]:
                    u = 1.0 - t
                    x = (
                        u * u * u * P0[0]
                        + 3.0 * u * u * t * P1[0]
                        + 3.0 * u * t * t * P2[0]
                        + t * t * t * P3[0]
                    )
                    y = (
                        u * u * u * P0[1]
                        + 3.0 * u * u * t * P1[1]
                        + 3.0 * u * t * t * P2[1]
                        + t * t * t * P3[1]
                    )
                    return x, y

                steps = 12
                pts = [bez(i / steps) for i in range(steps + 1)]
                for a, b in zip(pts, pts[1:]):
                    yield a, b, w


def _filter_frame_segments(
    segments: list[tuple[tuple[float, float], tuple[float, float], float]],
    page_rect: fitz.Rect,
    border_margin_pt: float = 6.0,
) -> list[tuple[tuple[float, float], tuple[float, float], float]]:
    """Remove obvious page-border frame segments to avoid mega-island merges."""
    W = float(page_rect.width)
    H = float(page_rect.height)
    keep: list[tuple[tuple[float, float], tuple[float, float], float]] = []
    for (x0, y0), (x1, y1), w in segments:
        dx = x1 - x0
        dy = y1 - y0
        L = (dx * dx + dy * dy) ** 0.5
        if L < 0.5:
            continue
        # Page border: any segment that lies entirely within the border band.
        near_left = x0 < border_margin_pt and x1 < border_margin_pt
        near_right = x0 > W - border_margin_pt and x1 > W - border_margin_pt
        near_top = y0 < border_margin_pt and y1 < border_margin_pt
        near_bot = y0 > H - border_margin_pt and y1 > H - border_margin_pt
        if near_left or near_right or near_top or near_bot:
            continue

        # Title block region: bottom-right area.
        mx = 0.5 * (x0 + x1)
        my = 0.5 * (y0 + y1)
        if mx > 0.45 * W and my > 0.70 * H:
            continue
        keep.append(((x0, y0), (x1, y1), w))
    return keep


def find_islands_on_page(
    page: fitz.Page,
    *,
    min_bbox_px: int = 120,
    output_dpi: int = 300,
    ds: int = 4,
    blur_small_px: int | None = None,
    density_thr: int | None = None,
) -> list[Island]:
    """Find circuit islands on a page using a raster density segmentation."""
    dpi = int(output_dpi)
    scale = dpi / 72.0

    # Render grayscale
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False, colorspace=fitz.csGRAY)
    gray = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    a = np.array(gray, dtype=np.uint8)

    # Ink mask (conservative)
    ink = (a < 245).astype(np.uint8) * 255
    W, H = pix.width, pix.height

    # Downsample for segmentation
    ds = max(2, int(ds))
    Ws = max(1, W // ds)
    Hs = max(1, H // ds)
    ink_small = Image.fromarray(ink).resize((Ws, Hs), resample=Image.Resampling.BILINEAR)

    # Density map via Gaussian blur
    if blur_small_px is None:
        blur_small_px = max(8, int(0.03 * min(Ws, Hs)))
    blurred = ink_small.filter(ImageFilter.GaussianBlur(radius=int(blur_small_px)))
    b = np.array(blurred, dtype=np.uint8)

    if density_thr is None:
        density_thr = 22
    seeds = (b > int(density_thr)).astype(np.uint8) * 255

    seeds_img = Image.fromarray(seeds)
    # Smooth small holes / spurs
    seeds_img = seeds_img.filter(ImageFilter.MaxFilter(size=5)).filter(ImageFilter.MinFilter(size=5))

    # Remove furniture regions at low-res
    border = max(2, int(round(22 / ds)))
    if border * 2 < Ws and border * 2 < Hs:
        s = np.array(seeds_img, dtype=np.uint8)
        s[:border, :] = 0
        s[-border:, :] = 0
        s[:, :border] = 0
        s[:, -border:] = 0
        # Title block area (bottom-right)
        x0 = int(0.45 * Ws)
        y0 = int(0.70 * Hs)
        s[y0:, x0:] = 0
        seeds_img = Image.fromarray(s)

    seeds_mask = (np.array(seeds_img, dtype=np.uint8) > 0)

    comps = _connected_components_4(seeds_mask)

    out: list[Island] = []
    for x0s, y0s, x1s, y1s, cm in comps:
        # Expand bbox in small space
        pad_s = 6
        x0s2 = max(0, x0s - pad_s)
        y0s2 = max(0, y0s - pad_s)
        x1s2 = min(Ws, x1s + pad_s)
        y1s2 = min(Hs, y1s + pad_s)

        cm_crop = seeds_mask[y0s2:y1s2, x0s2:x1s2].astype(np.uint8) * 255
        cm_img = Image.fromarray(cm_crop)

        # Grow to include whitespace around the block; then close to smooth.
        grow = 17
        cm_img = cm_img.filter(ImageFilter.MaxFilter(size=grow))
        cm_img = cm_img.filter(ImageFilter.MaxFilter(size=5)).filter(ImageFilter.MinFilter(size=5))

        # Upscale to full resolution
        w_full = (x1s2 - x0s2) * ds
        h_full = (y1s2 - y0s2) * ds
        if w_full < min_bbox_px or h_full < min_bbox_px:
            continue
        mask_full = cm_img.resize((w_full, h_full), resample=Image.Resampling.NEAREST)

        x0 = x0s2 * ds
        y0 = y0s2 * ds
        x1 = min(W, x0 + w_full)
        y1 = min(H, y0 + h_full)
        # Clamp mask to actual crop if we hit image edge
        mask_full = mask_full.crop((0, 0, x1 - x0, y1 - y0))

        out.append(Island(page.number, 0, dpi, (x0, y0, x1, y1), mask_full))

    # Stable ordering: top-to-bottom, left-to-right
    out.sort(key=lambda isl: (isl.bbox[1], isl.bbox[0]))
    out = [Island(i.page_index, n + 1, i.dpi, i.bbox, i.mask) for n, i in enumerate(out)]
    return out


def render_island_png(
    page: fitz.Page,
    island: Island,
    out_path: Path,
    *,
    dpi: int | None = None,
) -> tuple[int, int]:
    """Render one island to RGBA PNG using the precomputed mask."""
    dpi = island.dpi if dpi is None else int(dpi)
    scale = dpi / 72.0
    x0, y0, x1, y1 = island.bbox
    clip = fitz.Rect(x0 / scale, y0 / scale, x1 / scale, y1 / scale).intersect(page.rect)
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=clip, alpha=False)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    mask = island.mask
    if mask.size != img.size:
        mask = mask.resize(img.size, resample=Image.Resampling.NEAREST)
    img.putalpha(mask)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return img.size[0], img.size[1]


def render_islands_overlay(
    page: fitz.Page,
    islands: list[Island],
    out_path: Path,
    *,
    dpi: int = 200,
) -> None:
    """Render page with island bounding boxes for debugging."""
    scale = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    draw = ImageDraw.Draw(img)

    for isl in islands:
        x0, y0, x1, y1 = isl.bbox
        r = [x0 * (dpi / isl.dpi), y0 * (dpi / isl.dpi), x1 * (dpi / isl.dpi), y1 * (dpi / isl.dpi)]
        draw.rectangle(r, outline=(255, 0, 0), width=3)
        draw.text((r[0] + 6, r[1] + 6), str(isl.island_index), fill=(255, 0, 0))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
