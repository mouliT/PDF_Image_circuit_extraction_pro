"""Schematic PDF circuit-island extraction (vector-first).

This module is intentionally conservative: it segments a schematic page into
connected "ink" islands based on vector strokes, without using captions.

It is a foundation for later graph- and net-aware partitioning.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import fitz  # PyMuPDF
import numpy as np
from PIL import Image, ImageDraw
from shapely.geometry import LineString, MultiLineString, Polygon
from shapely.ops import unary_union


@dataclass(frozen=True)
class Island:
    """One extracted island on a single page."""

    page_index: int  # 0-based
    island_index: int  # 1-based within page
    polygon: Polygon  # PDF coordinate space (points)


class _UnionFind:
    def __init__(self, n: int):
        self.p = list(range(n))
        self.r = [0] * n

    def find(self, a: int) -> int:
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a: int, b: int) -> None:
        ra = self.find(a)
        rb = self.find(b)
        if ra == rb:
            return
        if self.r[ra] < self.r[rb]:
            ra, rb = rb, ra
        self.p[rb] = ra
        if self.r[ra] == self.r[rb]:
            self.r[ra] += 1


def _find_bridges(n_nodes: int, adj: list[list[tuple[int, int]]]) -> set[int]:
    """Tarjan bridge-finding on an undirected graph.

    adj[u] contains (v, edge_index) entries.
    Returns a set of edge_index values that are bridges.
    """
    timer = 0
    tin = [-1] * n_nodes
    low = [-1] * n_nodes
    bridges: set[int] = set()

    def dfs(u: int, pe: int) -> None:
        nonlocal timer
        tin[u] = timer
        low[u] = timer
        timer += 1
        for v, ei in adj[u]:
            if ei == pe:
                continue
            if tin[v] != -1:
                low[u] = min(low[u], tin[v])
            else:
                dfs(v, ei)
                low[u] = min(low[u], low[v])
                if low[v] > tin[u]:
                    bridges.add(ei)

    for i in range(n_nodes):
        if tin[i] == -1:
            dfs(i, -1)

    return bridges


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
    merge_margin_pt: float = 1.2,
    split_long_bridges: bool = True,
    bridge_len_pt: float = 60.0,
    snap_pt: float = 0.8,
    min_bbox_px: int = 120,
    output_dpi: int = 300,
) -> list[Island]:
    """Find circuit islands on a page using vector strokes.

    Strategy
    - Convert drawings to line segments
    - Buffer segments by a small margin and union them
    - Each resulting polygon is an "ink island"

    Parameters
    - merge_margin_pt: connectivity margin in PDF points
    - min_bbox_px: discard tiny islands based on rendered bbox size
    - output_dpi: used only for min_bbox_px conversion
    """
    drawings = page.get_drawings()
    segs = list(_iter_segments_from_drawings(drawings))
    segs = _filter_frame_segments(segs, page.rect)
    if not segs:
        return []

    widths = np.array([w for _, _, w in segs], dtype=float)
    med_w = float(np.median(widths)) if widths.size else 0.5
    buf = max(0.6, 0.5 * med_w) + float(merge_margin_pt)

    # Optional: split a physically-connected page into spatial blocks by removing
    # long bridge wires. This approximates the "island" notion in schematics where
    # long nets connect functional blocks but should not force a single region.
    components: list[list[int]] = [list(range(len(segs)))]
    if split_long_bridges and len(segs) >= 50:
        # Build a snapped endpoint graph over segments.
        node_id: dict[tuple[int, int], int] = {}

        def nid(x: float, y: float) -> int:
            key = (int(round(x / snap_pt)), int(round(y / snap_pt)))
            if key not in node_id:
                node_id[key] = len(node_id)
            return node_id[key]

        edges: list[tuple[int, int, float]] = []
        for (x0, y0), (x1, y1), _w in segs:
            u = nid(x0, y0)
            v = nid(x1, y1)
            L = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
            edges.append((u, v, L))

        adj: list[list[tuple[int, int]]] = [[] for _ in range(len(node_id))]
        for ei, (u, v, _L) in enumerate(edges):
            if u == v:
                continue
            adj[u].append((v, ei))
            adj[v].append((u, ei))

        bridges = _find_bridges(len(node_id), adj)
        cut = {ei for ei in bridges if edges[ei][2] >= bridge_len_pt}

        if cut:
            uf = _UnionFind(len(node_id))
            for ei, (u, v, _L) in enumerate(edges):
                if ei in cut:
                    continue
                if u != v:
                    uf.union(u, v)

            comp_map: dict[int, list[int]] = {}
            for si, (u, v, _L) in enumerate(edges):
                if si in cut:
                    continue
                root = uf.find(u)
                comp_map.setdefault(root, []).append(si)
            # Only use split if it meaningfully partitions.
            if len(comp_map) > 1:
                components = list(comp_map.values())

    polys: list[Polygon] = []
    for seg_idx_list in components:
        lines = [LineString([segs[i][0], segs[i][1]]) for i in seg_idx_list]
        if not lines:
            continue
        mls = MultiLineString(lines)
        region = unary_union(mls.buffer(buf, cap_style="flat", join_style="mitre"))
        if isinstance(region, Polygon):
            polys.append(region)
        else:
            geoms = getattr(region, "geoms", None)
            if geoms is not None:
                polys.extend([g for g in geoms if isinstance(g, Polygon)])

    # Filter small / non-circuit islands
    scale = output_dpi / 72.0
    W = float(page.rect.width)
    H = float(page.rect.height)
    page_area = max(W * H, 1.0)

    def is_furniture(poly: Polygon) -> bool:
        minx, miny, maxx, maxy = poly.bounds
        bw = maxx - minx
        bh = maxy - miny

        # Full-page frame / border ring (very large bbox)
        if bw > 0.95 * W and bh > 0.95 * H:
            # Border rings have small area relative to page area.
            if (poly.area / page_area) < 0.25:
                return True

        # Title block region: bottom-right, rectangular-ish area
        if miny > 0.70 * H and minx > 0.45 * W and bw > 0.25 * W and bh > 0.12 * H:
            return True

        return False

    out: list[Island] = []
    idx = 1
    for poly in polys:
        if poly.is_empty:
            continue
        if is_furniture(poly):
            continue
        minx, miny, maxx, maxy = poly.bounds
        w_px = (maxx - minx) * scale
        h_px = (maxy - miny) * scale
        if w_px < min_bbox_px or h_px < min_bbox_px:
            continue
        out.append(Island(page.number, idx, poly))
        idx += 1

    # Stable order: top-to-bottom, left-to-right
    out.sort(key=lambda isl: (isl.polygon.bounds[1], isl.polygon.bounds[0]))
    # Re-number after sort
    out = [Island(i.page_index, n + 1, i.polygon) for n, i in enumerate(out)]
    return out


def render_island_png(
    page: fitz.Page,
    island: Island,
    out_path: Path,
    *,
    dpi: int = 300,
    pad_pt: float = 6.0,
) -> tuple[int, int]:
    """Render one island to RGBA PNG using polygon mask."""
    poly = island.polygon
    minx, miny, maxx, maxy = poly.bounds
    clip = fitz.Rect(minx - pad_pt, miny - pad_pt, maxx + pad_pt, maxy + pad_pt).intersect(page.rect)
    scale = dpi / 72.0
    mat = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat, clip=clip, alpha=False)

    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    mask = Image.new("L", (pix.width, pix.height), 0)
    draw = ImageDraw.Draw(mask)

    ext = list(poly.exterior.coords)
    pts = [((x - clip.x0) * scale, (y - clip.y0) * scale) for x, y in ext]
    draw.polygon(pts, fill=255)
    for interior in poly.interiors:
        hole = [((x - clip.x0) * scale, (y - clip.y0) * scale) for x, y in list(interior.coords)]
        draw.polygon(hole, fill=0)

    img.putalpha(mask)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return pix.width, pix.height


def render_islands_overlay(
    page: fitz.Page,
    islands: list[Island],
    out_path: Path,
    *,
    dpi: int = 200,
) -> None:
    """Render page with island outlines for debugging."""
    scale = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    draw = ImageDraw.Draw(img)

    for isl in islands:
        poly = isl.polygon
        ext = list(poly.exterior.coords)
        pts = [(x * scale, y * scale) for x, y in ext]
        draw.line(pts, fill=(255, 0, 0), width=3, joint="curve")
        # label
        minx, miny, _, _ = poly.bounds
        draw.text((minx * scale + 6, miny * scale + 6), str(isl.island_index), fill=(255, 0, 0))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
