#!/usr/bin/env python3
"""
figure_extractor_app.py
PDF Figure Extractor — Desktop App (PyQt6)

Entry point:  python figure_extractor_app.py

Architecture (single file):
    MainWindow(QMainWindow)
      |- ControlPanel(QWidget)          Stage 1  [done]
      |- QProgressBar                   Stage 2  [done]
      |- QSplitter
      |    |- ThumbnailGallery(QWidget) Stage 3
      |    |- PreviewPanel(QWidget)     Stage 4
      |- QStatusBar

    ExtractionWorker(QThread)           Stage 2  [done]
    FigureCard(QFrame)                  Stage 3
"""

import os
import re
import sys
from datetime import date as _date
from pathlib import Path

import fitz  # PyMuPDF
import numpy as np

try:
    from figure_quality import FigureQualityStandard, FigureMetrics, QualityEvaluator
    _QUALITY_AVAILABLE = True
except ImportError:
    _QUALITY_AVAILABLE = False

from PyQt6.QtCore import QRect, QSize, Qt, QThread, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QPixmapCache,
    QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)


# ---------------------------------------------------------------------------
# Dark stylesheet
# ---------------------------------------------------------------------------

DARK_STYLE = """
QMainWindow, QWidget {
    background-color: #1e1e1e;
    color: #d4d4d4;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 13px;
}

QSplitter::handle {
    background-color: #3c3c3c;
    width: 3px;
}

/* Buttons */
QPushButton {
    background-color: #2d2d2d;
    color: #d4d4d4;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    padding: 5px 14px;
    min-height: 28px;
}
QPushButton:hover {
    background-color: #3c3c3c;
    border-color: #569cd6;
}
QPushButton:pressed {
    background-color: #569cd6;
    color: #ffffff;
}
QPushButton:disabled {
    color: #555555;
    border-color: #2d2d2d;
}

/* Primary action button */
QPushButton#extractBtn {
    background-color: #0e639c;
    color: #ffffff;
    border: 1px solid #1177bb;
    font-weight: bold;
    font-size: 14px;
    min-height: 36px;
    border-radius: 5px;
}
QPushButton#extractBtn:hover {
    background-color: #1177bb;
}
QPushButton#extractBtn:pressed {
    background-color: #0a4d7a;
}
QPushButton#extractBtn:disabled {
    background-color: #2d2d2d;
    color: #555555;
    border-color: #3c3c3c;
}

/* Danger / stop button */
QPushButton#clearBtn, QPushButton#stopBtn {
    background-color: #2d2d2d;
    color: #f48771;
    border: 1px solid #3c3c3c;
}
QPushButton#clearBtn:hover, QPushButton#stopBtn:hover {
    background-color: #5a1d1d;
    border-color: #f48771;
    color: #ffffff;
}

/* Inputs */
QLineEdit {
    background-color: #2d2d2d;
    color: #d4d4d4;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 26px;
}
QLineEdit:focus {
    border-color: #569cd6;
}

QSpinBox, QDoubleSpinBox {
    background-color: #2d2d2d;
    color: #d4d4d4;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    padding: 3px 6px;
    min-height: 26px;
    min-width: 72px;
}
QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: #569cd6;
}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    background-color: #3c3c3c;
    border: none;
    width: 16px;
}
QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {
    background-color: #569cd6;
}

/* Labels */
QLabel#sectionLabel {
    color: #9cdcfe;
    font-weight: bold;
}
QLabel#queueLabel {
    color: #555555;
    padding: 4px 8px;
}
QScrollArea#queueScroll {
    background-color: #252526;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    max-height: 110px;
}
QWidget#queueContainer {
    background-color: #252526;
}
QLabel#queueRowName {
    color: #9cdcfe;
    font-size: 11px;
}
QLineEdit#queueRowCode {
    background-color: #1e1e1e;
    color: #ce9178;
    border: 1px solid #3c3c3c;
    border-radius: 3px;
    padding: 1px 5px;
    min-height: 20px;
    max-height: 20px;
    max-width: 110px;
    font-weight: bold;
    font-size: 11px;
}
QLineEdit#queueRowCode:focus {
    border-color: #569cd6;
}
QPushButton#queueRowRemove {
    background-color: transparent;
    color: #666666;
    border: none;
    font-size: 12px;
    min-width: 18px;
    max-width: 18px;
    padding: 0px;
}
QPushButton#queueRowRemove:hover {
    color: #f44747;
}

/* Separator line */
QFrame#hLine {
    color: #3c3c3c;
    background-color: #3c3c3c;
    max-height: 1px;
}

/* Placeholder panels */
QWidget#leftPlaceholder, QWidget#rightPlaceholder {
    background-color: #252526;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
}

/* Progress bar */
QProgressBar {
    background-color: #2d2d2d;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    text-align: center;
    color: #d4d4d4;
    min-height: 18px;
    max-height: 18px;
}
QProgressBar::chunk {
    background-color: #0e639c;
    border-radius: 3px;
}

/* Status bar */
QStatusBar {
    background-color: #007acc;
    color: #ffffff;
    font-size: 12px;
    padding: 2px 8px;
}
QStatusBar::item {
    border: none;
}

/* Figure cards */
QFrame#figureCard {
    background-color: #252526;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
}
/* Quality-based card borders — MARGINAL/REJECT flagged visually */
QFrame#figureCard[quality="MARGINAL"] {
    border: 2px solid #d7ba7d;
    background-color: #272200;
}
QFrame#figureCard[quality="REJECT"] {
    border: 2px solid #f48771;
    background-color: #271515;
}
/* Selected always shows blue, regardless of quality classification */
QFrame#figureCard[selected="true"] {
    border: 2px solid #569cd6;
    background-color: #1a2a3a;
}

/* Confidence score badge inside each card */
QLabel#confidenceLabel {
    font-size: 10px;
    text-align: center;
    padding: 1px 3px;
    border-radius: 2px;
}
QLabel#confidenceLabel[quality="GOOD"]     { color: #4ec9b0; }
QLabel#confidenceLabel[quality="MARGINAL"] { color: #d7ba7d; }
QLabel#confidenceLabel[quality="REJECT"]   { color: #f48771; }
QLabel#confidenceLabel[quality="UNKNOWN"]  { color: #555555; }

QPushButton#removeCardBtn {
    background-color: transparent;
    color: #888888;
    border: none;
    font-size: 14px;
    font-weight: bold;
    padding: 0px;
    min-height: 18px;
}
QPushButton#removeCardBtn:hover {
    color: #f48771;
}

/* ── Preview Panel ──────────────────────────────────────── */
QWidget#previewPanel {
    background: #1e1e1e;
}
QLabel#previewImage {
    background: #111111;
    border: 1px solid #3c3c3c;
    color: #555555;
}
QFrame#metaPanel {
    background: #252526;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
}

/* ── Crop widget drag hint ──────────────────────────────── */
QLabel#cropHint {
    color: #555555;
    font-size: 11px;
    padding: 2px 0px;
}

/* ── Preview inner splitter handle ─────────────────────── */
QSplitter#previewSplitter::handle {
    background-color: #3c3c3c;
    height: 5px;
}
QSplitter#previewSplitter::handle:hover {
    background-color: #569cd6;
}

/* ── Info scroll area ───────────────────────────────────── */
QScrollArea#infoScroll {
    border: none;
    background: transparent;
}
QScrollArea#infoScroll > QWidget {
    background: transparent;
}

/* ── Generate Context button ────────────────────────────── */
QPushButton#ctxBtn {
    background-color: #1a3a2a;
    color: #4ec9b0;
    border: 1px solid #4ec9b0;
    font-weight: bold;
    min-height: 28px;
    border-radius: 4px;
}
QPushButton#ctxBtn:hover  { background-color: #1e5c3a; border-color: #4ec9b0; }
QPushButton#ctxBtn:pressed { background-color: #155c37; }
QPushButton#ctxBtn:disabled {
    background-color: #2d2d2d;
    color: #555555;
    border-color: #3c3c3c;
}

/* ── Crop Correction Panel ──────────────────────────────── */
QFrame#cropPanel {
    background: #252526;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
}
QPushButton#reextractBtn {
    background-color: #0e639c;
    color: #ffffff;
    border: 1px solid #1177bb;
    font-weight: bold;
    min-height: 28px;
    border-radius: 4px;
}
QPushButton#reextractBtn:hover  { background-color: #1177bb; }
QPushButton#reextractBtn:pressed { background-color: #0a4d7a; }
QPushButton#reextractBtn:disabled {
    background-color: #2d2d2d;
    color: #555555;
    border-color: #3c3c3c;
}
QPushButton#subfigBtn {
    background-color: #2a3d2a;
    color: #89d185;
    border: 1px solid #4d9a4d;
    font-weight: bold;
    min-height: 28px;
    border-radius: 4px;
}
QPushButton#subfigBtn:hover   { background-color: #3a5a3a; border-color: #6ab86a; }
QPushButton#subfigBtn:pressed  { background-color: #1e2e1e; }
QPushButton#subfigBtn:disabled {
    background-color: #2d2d2d;
    color: #555555;
    border-color: #3c3c3c;
}
/* ── Sub-figure badge overlay on FigureCard ─────────────────────────── */
QLabel#subfigBadge {
    background-color: #3a2e10;
    color: #d7ba7d;
    font-size: 10px;
    font-weight: bold;
    border-top: 1px solid #d7ba7d;
}
"""


# ---------------------------------------------------------------------------
# Extraction utilities  (ported from extract_figures.py — kept inline so the
# app is self-contained and ExtractionWorker can call them from a QThread)
# ---------------------------------------------------------------------------

def _find_captions_on_page(page) -> dict:
    """
    Return {fig_id (str): caption_rect (fitz.Rect)} for every caption block.

    Supports common numbering styles:
      - Fig. 3
      - Figure 2.1
      - Fig 4-2
      - Fig S1

    Only matches blocks whose text *starts* with the caption prefix.
    """
    captions: dict = {}
    for block in page.get_text("blocks"):
        if block[6] != 0:          # skip image blocks
            continue
        text = block[4].strip()
        if not text:
            continue
        if text.count('\n') > 4:   # paragraph blocks are not captions
            continue

        # Capture ids like 2.1 / 4-2 / S1
        m = re.match(
            r'^\s*(?:Fig(?:ure)?\.?|FIG\.?)\s*([A-Za-z]?\d+(?:[.\-]\d+)*)\b',
            text,
            re.IGNORECASE,
        )
        if not m:
            continue
        fig_id = m.group(1)
        rect = fitz.Rect(block[:4])
        captions[fig_id] = captions[fig_id] | rect if fig_id in captions else rect
    return captions


def _fig_sort_key(fig_id: object) -> tuple:
    """Natural-ish sort key for figure ids (e.g. 1.10 after 1.9)."""
    s = str(fig_id)
    parts = re.split(r"[.\-]", s)
    numeric: list[int] = []
    head = parts[0]
    prefix = ""
    if head and head[0].isalpha():
        prefix = head[0].upper()
        head = head[1:]
        parts[0] = head
    for p in parts:
        try:
            numeric.append(int(p))
        except Exception:
            numeric.append(0)
    return (prefix, tuple(numeric), s)


def _fig_id_for_filename(fig_id: object) -> str:
    """Sanitise a figure id for use in filenames (e.g. 2.1 -> 2_1)."""
    safe = re.sub(r"[^0-9A-Za-z]+", "_", str(fig_id)).strip("_")
    return safe or "X"


# ---------------------------------------------------------------------------
# Pixel-based whitespace-gap constants  (tune these if needed)
# ---------------------------------------------------------------------------
_ANALYSIS_DPI  = 150    # render DPI for whitespace scan — fast, sufficient resolution
_DARK_THRESH   = 230    # pixel values below this are "ink" (0 = black, 255 = white)
_CONTENT_FRAC  = 0.003  # a row needs > 0.3 % dark pixels to count as a content row
_GAP_MIN_PT    = 15     # minimum whitespace gap height in PDF points to count as
                         # the figure boundary (separates figure from surrounding text).
                         # Must be large enough to skip intra-figure whitespace (axis
                         # tick gaps, inter-panel spacing ~5-10 pt) but still find the
                         # gap between the figure and the body text above (~12-24 pt).
                          # Stacked figures are separated by preceding_cap_y1, not this.
_GAP_HARD_PT   = 40     # a very large gap is treated as a hard boundary even if
                        # there is no detectable text in the gap (e.g. scanned PDFs).

# Embedded-image fallback tuning
_EMBED_MIN_AREA_FRAC = 0.02   # on-page area fraction threshold (skip tiny logos/icons)
_EMBED_MAX_PER_PAGE  = 40     # safety cap for pathological PDFs


def _find_figure_rect(
    page,
    caption_rect,
    page_captions: dict,
    max_search_height: int = 800,
    *,
    output_dpi: int | None = None,
    min_size_px: int | None = None,
):
    """
    Locate the figure above caption_rect using pixel-based whitespace-gap detection.

    Why pixels, not PDF metadata
    ----------------------------
    get_images() / get_drawings() only read PDF structural metadata — bounding
    boxes of embedded objects.  This fails for pure-vector figures (no image
    xref), multi-element figures whose bounding boxes don't align, and pages
    where a single image xref covers the whole page.  Rendering to pixels and
    reading the actual visual content is reliable for all figure types.

    Algorithm
    ---------
    1. Define the search zone: column x-range above the caption, upper-bounded
       by the nearest preceding caption on the same page (prevents merging
       stacked figures) or max_search_height, whichever is tighter.
    2. Render the search zone to a greyscale pixel image at _ANALYSIS_DPI.
    3. Compute the dark-pixel fraction per row (horizontal projection profile).
    4. Scan upward from the caption:
         a. Find fig_bottom — the last row that contains any ink, working up
            from the caption edge (skips any whitespace between caption and
            figure).
         b. Continue upward through figure content until _GAP_MIN_PT points
            of consecutive whitespace rows are found — that gap is the
            boundary between the figure and the text above it.
         c. fig_top is the first content row after that gap.
    5. Convert pixel rows back to PDF coordinates, pad, clip to page.

    Notes
    -----
    Some documents (theses, printed-to-PDF, vendor reports) place captions ABOVE
    figures. If the above-caption search yields no usable crop, this function
    also tries a mirrored search BELOW the caption.
    """
    page_rect = page.rect
    margin    = 8

    def _gap_has_body_text(gap_rect: fitz.Rect, width_ref: float) -> bool:
        """Heuristic: detect paragraph-like text blocks in a region.

        We intentionally avoid treating small figure-internal labels/legends as
        body text. In narrow columns, a simple width threshold can be too
        permissive, so we also require a minimum text length.
        """
        threshold = 0.60 * width_ref
        for block in page.get_text("blocks"):
            if block[6] != 0:
                continue
            br = fitz.Rect(block[:4])
            if br.width < threshold or not br.intersects(gap_rect):
                continue
            txt = (block[4] or "").strip()
            if not txt:
                continue
            words = len(txt.split())
            if words >= 12:
                return True
            if txt.count("\n") >= 2 and words >= 6:
                return True
            if len(txt) >= 80:
                return True
        return False

    def _body_text_blocks_in_rect(rect: fitz.Rect, width_ref: float) -> list[fitz.Rect]:
        """Return paragraph-like text block rects intersecting `rect`."""
        threshold = 0.60 * width_ref
        blocks: list[fitz.Rect] = []
        for block in page.get_text("blocks"):
            if block[6] != 0:
                continue
            br = fitz.Rect(block[:4])
            if br.width < threshold or not br.intersects(rect):
                continue
            txt = (block[4] or "").strip()
            if not txt:
                continue
            words = len(txt.split())
            if words >= 12 or (txt.count("\n") >= 2 and words >= 6) or len(txt) >= 80:
                blocks.append(br)
        blocks.sort(key=lambda r: r.y0)
        return blocks

    def _min_crop_ok(rect: fitz.Rect | None) -> bool:
        if rect is None:
            return False
        if not output_dpi or not min_size_px:
            return True
        w_px = rect.width * output_dpi / 72.0
        h_px = rect.height * output_dpi / 72.0
        return w_px >= min_size_px and h_px >= min_size_px

    def _rect_from_rows(zone: fitz.Rect, scale: float, top_px: int, bot_px: int, x0: float, x1: float) -> fitz.Rect | None:
        fig_y0 = zone.y0 + top_px / scale
        fig_y1 = zone.y0 + (bot_px + 1) / scale
        if fig_y1 - fig_y0 < 5:
            return None
        pad = 4
        return fitz.Rect(
            x0 - pad,
            fig_y0 - pad,
            x1 + pad,
            fig_y1 + pad,
        ).intersect(page_rect)

    def _content_bands(content_mask: "np.ndarray", from_bottom: bool) -> list[tuple[int, int]]:
        """Return contiguous (start,end) bands where mask is True."""
        bands: list[tuple[int, int]] = []
        H = int(content_mask.shape[0])
        if from_bottom:
            i = H - 1
            while i >= 0:
                if not bool(content_mask[i]):
                    i -= 1
                    continue
                end = i
                while i >= 0 and bool(content_mask[i]):
                    i -= 1
                start = i + 1
                bands.append((start, end))
        else:
            i = 0
            while i < H:
                if not bool(content_mask[i]):
                    i += 1
                    continue
                start = i
                while i < H and bool(content_mask[i]):
                    i += 1
                end = i - 1
                bands.append((start, end))
        return bands

    def _scan_above(zone: fitz.Rect, x0: float, x1: float) -> fitz.Rect | None:
        if zone.is_empty or zone.height < 5:
            return None

        scale = _ANALYSIS_DPI / 72.0
        pix = page.get_pixmap(
            matrix=fitz.Matrix(scale, scale),
            clip=zone,
            alpha=False,
            colorspace=fitz.csGRAY,
        )
        if pix.height < 2 or pix.width < 2:
            return None

        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
        dark_frac = (arr < _DARK_THRESH).sum(axis=1) / arr.shape[1]
        content = dark_frac > _CONTENT_FRAC

        # Exclude obvious body-text blocks above the figure, if present.
        min_row = 0
        body_blocks = _body_text_blocks_in_rect(zone, zone.width)
        if body_blocks:
            text_floor_y = max((r.y1 for r in body_blocks), default=zone.y0)
            if text_floor_y > zone.y0 + 2:
                min_row = int((text_floor_y - zone.y0) * scale)
                min_row = max(0, min(min_row, pix.height - 1))
                if min_row > 0:
                    content[:min_row] = False

        gap_min = max(4, int(_GAP_MIN_PT * scale))
        hard_gap = max(gap_min + 1, int(_GAP_HARD_PT * scale))
        bands = _content_bands(content, from_bottom=True)
        if not bands:
            return None

        first_rect: fitz.Rect | None = None

        # Build a crop by merging multiple content bands separated by whitespace.
        # Stop merging when the gap likely indicates surrounding body text.
        for base_i, (base_start, base_end) in enumerate(bands):
            if base_end < min_row:
                continue
            merged_top = base_start
            merged_bottom = base_end

            for upper_start, upper_end in bands[base_i + 1:]:
                if upper_end < min_row:
                    break
                gap_px = merged_top - upper_end - 1
                if gap_px <= 0:
                    merged_top = min(merged_top, upper_start)
                    continue

                # Large gaps are almost never intra-figure — stop.
                if gap_px >= hard_gap:
                    break

                # If the whitespace gap contains paragraph-like text, treat it as a boundary.
                if gap_px >= gap_min:
                    gap_rect = fitz.Rect(
                        x0,
                        zone.y0 + (upper_end + 1) / scale,
                        x1,
                        zone.y0 + merged_top / scale,
                    )
                    if _gap_has_body_text(gap_rect, zone.width):
                        break

                merged_top = upper_start

            rect = _rect_from_rows(zone, scale, merged_top, merged_bottom, x0, x1)
            if first_rect is None:
                first_rect = rect
            if _min_crop_ok(rect):
                return rect

        return first_rect

    def _scan_below(zone: fitz.Rect, x0: float, x1: float) -> fitz.Rect | None:
        if zone.is_empty or zone.height < 5:
            return None

        scale = _ANALYSIS_DPI / 72.0
        pix = page.get_pixmap(
            matrix=fitz.Matrix(scale, scale),
            clip=zone,
            alpha=False,
            colorspace=fitz.csGRAY,
        )
        if pix.height < 2 or pix.width < 2:
            return None

        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
        dark_frac = (arr < _DARK_THRESH).sum(axis=1) / arr.shape[1]
        content = dark_frac > _CONTENT_FRAC

        # Exclude obvious body-text blocks below the figure, if present.
        max_row = pix.height - 1
        body_blocks = _body_text_blocks_in_rect(zone, zone.width)
        if body_blocks:
            text_ceiling_y = min((r.y0 for r in body_blocks), default=zone.y1)
            if text_ceiling_y < zone.y1 - 2:
                max_row = int((text_ceiling_y - zone.y0) * scale)
                max_row = max(0, min(max_row, pix.height - 1))
                if max_row < pix.height - 1:
                    content[max_row + 1:] = False

        gap_min = max(4, int(_GAP_MIN_PT * scale))
        hard_gap = max(gap_min + 1, int(_GAP_HARD_PT * scale))
        bands = _content_bands(content, from_bottom=False)
        if not bands:
            return None

        first_rect: fitz.Rect | None = None

        for base_i, (base_start, base_end) in enumerate(bands):
            if base_start > max_row:
                break
            if base_end > max_row:
                base_end = max_row
            merged_top = base_start
            merged_bottom = base_end

            for lower_start, lower_end in bands[base_i + 1:]:
                if lower_start > max_row:
                    break
                if lower_end > max_row:
                    lower_end = max_row
                gap_px = lower_start - merged_bottom - 1
                if gap_px <= 0:
                    merged_bottom = max(merged_bottom, lower_end)
                    continue

                if gap_px >= hard_gap:
                    break

                if gap_px >= gap_min:
                    gap_rect = fitz.Rect(
                        x0,
                        zone.y0 + (merged_bottom + 1) / scale,
                        x1,
                        zone.y0 + lower_start / scale,
                    )
                    if _gap_has_body_text(gap_rect, zone.width):
                        break

                merged_bottom = lower_end

            rect = _rect_from_rows(zone, scale, merged_top, merged_bottom, x0, x1)
            if first_rect is None:
                first_rect = rect
            if _min_crop_ok(rect):
                return rect

        return first_rect

    # --- Column x-bounds ---
    # Captions are sometimes centered and narrow even for full-width figures.
    # If the caption is near the page center, widen the column bounds so we
    # don't crop out left/right sub-panels.
    cap_mid = 0.5 * (caption_rect.x0 + caption_rect.x1)
    page_mid = 0.5 * page_rect.width
    if caption_rect.width > 0.60 * page_rect.width:
        col_x0, col_x1 = margin, page_rect.width - margin
    elif abs(cap_mid - page_mid) < 0.12 * page_rect.width and caption_rect.width < 0.55 * page_rect.width:
        col_x0, col_x1 = margin, page_rect.width - margin
    else:
        col_x0 = caption_rect.x0 - margin
        col_x1 = caption_rect.x1 + margin

    # --- Upper bound: nearest preceding caption in the SAME column is the ceiling ---
    # Only captions whose x-range overlaps our column are in the same column.
    # Cross-column captions (e.g. a left-column fig caption constraining a
    # right-column figure) must be ignored or they produce a falsely tiny zone.
    preceding_cap_y1 = max(
        (r.y1 for r in page_captions.values()
         if r.y1 <= caption_rect.y0 - 2          # must be above us
         and r.x1 > col_x0 and r.x0 < col_x1),   # must overlap our column
        default=0.0,
    )
    search_top  = max(max(0.0, caption_rect.y0 - max_search_height), preceding_cap_y1)
    zone_above  = fitz.Rect(col_x0, search_top, col_x1, caption_rect.y0)

    rect_above = _scan_above(zone_above, col_x0, col_x1)
    if _min_crop_ok(rect_above):
        return rect_above

    # Mirrored below-caption search: used when captions are above the figure.
    following_cap_y0 = min(
        (
            r.y0
            for r in page_captions.values()
            if r.y0 >= caption_rect.y1 + 2
            and r.x1 > col_x0
            and r.x0 < col_x1
        ),
        default=page_rect.height,
    )
    search_bottom = min(page_rect.height, caption_rect.y1 + max_search_height, following_cap_y0)
    zone_below = fitz.Rect(col_x0, caption_rect.y1, col_x1, search_bottom)
    rect_below = _scan_below(zone_below, col_x0, col_x1)
    if _min_crop_ok(rect_below):
        return rect_below

    # Last resort: return whichever side found something (even if tiny)
    return rect_above if rect_above is not None else rect_below


def _find_text_paragraphs_in_rect(page, rect: fitz.Rect, zone_width: float) -> list:
    """Return text blocks inside rect wider than 60% of zone_width, top-to-bottom."""
    threshold = 0.60 * zone_width
    result = []
    for block in page.get_text("blocks"):
        if block[6] != 0:
            continue
        br = fitz.Rect(block[:4])
        if br.width >= threshold and br.intersects(rect):
            result.append(br)
    result.sort(key=lambda r: r.y0)
    return result


def _make_unique_path(output_dir: Path, base_name: str) -> Path:
    """
    Return output_dir/base_name if it does not exist; otherwise append
    _1, _2, ... until a free path is found.
    """
    candidate = output_dir / base_name
    if not candidate.exists():
        return candidate
    stem   = Path(base_name).stem
    suffix = Path(base_name).suffix
    counter = 1
    while True:
        candidate = output_dir / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


_STOP_WORDS = {
    'a', 'an', 'the', 'of', 'for', 'in', 'on', 'at', 'to', 'by', 'with',
    'and', 'or', 'from', 'into', 'using', 'under', 'based', 'via', 'as',
    'its', 'is', 'are', 'be', 'been', 'within', 'about', 'between',
}


def _make_short_code(pdf_path: Path) -> str:
    """
    Auto-suggest a short code from a PDF filename.
    Strips stop words, takes the first letter of each remaining word,
    returns uppercase, max 10 chars.  Falls back to first 8 chars of stem.
    Example: DC-Link_Voltage_Balancing_Modulation_for_Cascaded_H-Bridge_Converters
             → D V B M C H B C  →  DVBMCHBC
    """
    import re
    words = re.split(r'[_\-\s]+', pdf_path.stem)
    initials = [w[0].upper() for w in words
                if w and w.lower() not in _STOP_WORDS and w[0].isalpha()]
    code = ''.join(initials[:10])
    return code if code else pdf_path.stem[:8].upper()


def _reextract_figure(
    data: dict,
    expand_top: float,
    expand_bottom: float,
    expand_left: float,
    expand_right: float,
    dpi_override: int,
    out_path: "str | None" = None,
) -> tuple[str, tuple]:
    """
    Re-render a single figure with an adjusted crop rect.

    Parameters (all in PDF points, 1 pt = 1/72 inch):
        expand_top    -- positive = pull top edge UP (show more above)
        expand_bottom -- positive = pull bottom edge DOWN (show more below)
        expand_left   -- positive = pull left edge LEFT (wider left margin)
        expand_right  -- positive = pull right edge RIGHT (wider right margin)
        Negative values trim that edge inward.
        out_path      -- if given, save to this new path instead of overwriting
                         data["path"] (used for sub-figure extraction).

    Returns (dims_str, new_crop_rect_tuple) on success. Raises on failure.
    """
    x0, y0, x1, y1 = data["crop_rect"]
    new_rect = fitz.Rect(
        x0 - expand_left,
        y0 - expand_top,
        x1 + expand_right,
        y1 + expand_bottom,
    )
    doc  = fitz.open(data["pdf_path"])
    page = doc[data["page_num"]]
    new_rect = new_rect.intersect(page.rect)   # clamp to page bounds
    mat  = fitz.Matrix(dpi_override / 72, dpi_override / 72)
    pix  = page.get_pixmap(matrix=mat, clip=new_rect, alpha=False)
    doc.close()
    save_to = out_path if out_path else data["path"]
    pix.save(save_to)
    dims = f"{pix.width} x {pix.height}"
    rect_tuple = (new_rect.x0, new_rect.y0, new_rect.x1, new_rect.y1)
    return dims, rect_tuple


# ---------------------------------------------------------------------------
# Context-file helpers  (Stage 7)
# ---------------------------------------------------------------------------

def _extract_intro_text(doc, max_words: int = 450) -> str:
    """
    Return the first ~max_words words of the document (abstract + introduction),
    preserving paragraph breaks and skipping very short lines (headers, numbers).
    Searches the first 5 pages only.
    """
    paragraphs = []
    word_count = 0
    for page_num in range(min(len(doc), 5)):
        page = doc[page_num]
        for block in page.get_text("blocks"):
            if block[6] != 0:                          # skip image blocks
                continue
            text = block[4].strip().replace("\n", " ")
            if not text or len(text.split()) < 5:       # skip headers / page nums
                continue
            block_words = text.split()
            remaining = max_words - word_count
            if remaining <= 0:
                break
            if len(block_words) > remaining:
                paragraphs.append(" ".join(block_words[:remaining]) + " …")
                word_count = max_words
            else:
                paragraphs.append(text)
                word_count += len(block_words)
        if word_count >= max_words:
            break
    return "\n\n".join(paragraphs)


def _find_section_heading(page, caption_rect) -> str:
    """
    Return the nearest section/subsection heading above caption_rect on this page.
    Headings are identified as short text blocks that match common academic
    numbering patterns (I., II., A., 1., or ALL-CAPS short lines).
    """
    heading_pat = re.compile(
        r"^([IVXLC]+\.|[A-Z]\.|[0-9]+\.)\s+\S",   # I. INTRO  or  A. Method  or  1. Intro
    )
    best_text = "—"
    best_y1   = -1.0
    for block in page.get_text("blocks"):
        if block[6] != 0:
            continue
        bx0, by0, bx1, by1 = block[0], block[1], block[2], block[3]
        text = block[4].strip()
        if not text or by1 > caption_rect.y0:
            continue                               # must be above the caption
        first_line = text.split("\n")[0].strip()
        is_heading = (
            heading_pat.match(first_line) is not None
            or (len(first_line) < 90 and first_line == first_line.upper()
                and len(first_line.split()) >= 2)
        )
        if is_heading and by1 > best_y1:
            best_y1   = by1
            best_text = first_line
    return best_text


def _get_full_caption(page, caption_rect) -> str:
    """
    Return the full text of the caption block that overlaps caption_rect.
    Falls back to '—' if the block cannot be found.
    """
    cap_re = re.compile(
        r"^\s*(?:Fig(?:ure)?\.?|FIG\.?)\s*[A-Za-z]?\d+(?:[.\-]\d+)*",
        re.IGNORECASE,
    )
    for block in page.get_text("blocks"):
        if block[6] != 0:
            continue
        br = fitz.Rect(block[:4])
        if not br.intersects(caption_rect):
            continue
        text = block[4].strip().replace("\n", " ")
        if cap_re.match(text):
            return text
    return "—"


def _find_figure_references(doc, fig_id: object, caption_page: int) -> list[str]:
    """
    Return every sentence across the document that explicitly mentions Fig/Figure N.
    The caption line itself (on caption_page) is excluded to avoid duplication.
    Limited to 8 unique references.
    """
    fig_esc = re.escape(str(fig_id))
    pat = re.compile(
        rf"\b(?:Fig(?:ure)?\.?\s*{fig_esc}|FIG\.?\s*{fig_esc})\b",
        re.IGNORECASE,
    )
    cap_re = re.compile(
        r"^\s*(?:Fig(?:ure)?\.?|FIG\.?)\s*[A-Za-z]?\d+(?:[.\-]\d+)*",
        re.IGNORECASE,
    )
    refs: list[str] = []
    seen: set[str]  = set()

    for page_num in range(len(doc)):
        page = doc[page_num]
        for block in page.get_text("blocks"):
            if block[6] != 0:
                continue
            raw = block[4].replace("\n", " ").strip()
            if not pat.search(raw):
                continue
            # Exclude the caption block itself
            if page_num == caption_page and cap_re.match(raw):
                continue
            # Split into sentences and collect matches
            for sent in re.split(r"(?<=[.!?])\s+", raw):
                sent = sent.strip()
                if pat.search(sent) and len(sent) > 20 and sent not in seen:
                    seen.add(sent)
                    refs.append(sent)
                    if len(refs) >= 8:
                        return refs
    return refs


def _generate_paper_context_md(
    pdf_path: Path,
    short_code: str,
    fig_data_list: list,
    output_dir: Path,
    date_str: str,
) -> Path:
    """
    Auto-generate a structured Markdown context file for one paper.
    The file is written to output_dir/{short_code}_context.md.
    """
    doc = fitz.open(str(pdf_path))

    # --- First pass: build caption-rect map for all pages ---------
    page_caption_map: dict[int, dict] = {}
    for pn in range(len(doc)):
        page_caption_map[pn] = _find_captions_on_page(doc[pn])

    # --- Sort figures by figure number ----------------------------
    figs = sorted(fig_data_list, key=lambda d: _fig_sort_key(d.get("fig_id", d.get("fig_num", ""))))

    # --- Section headings per figure ------------------------------
    fig_sections: dict[int, str] = {}
    fig_captions: dict[int, str] = {}
    for fdata in figs:
        fn      = fdata.get("fig_id", fdata.get("fig_num", "—"))
        pn      = fdata.get("page_num", fdata["page"] - 1)
        page    = doc[pn]
        cap_map = page_caption_map.get(pn, {})
        cr      = cap_map.get(fn)
        fig_sections[fn] = _find_section_heading(page, cr) if cr else "—"
        fig_captions[fn] = _get_full_caption(page, cr)     if cr else "—"

    # ==============================================================
    # Build Markdown
    # ==============================================================
    L: list[str] = []

    L.append("<!--")
    L.append("  PAPER CONTEXT FILE  —  for use with Claude")
    L.append("  ─────────────────────────────────────────────")
    L.append("  How to use:")
    L.append("  1. Attach this file and the PNG images to a Claude conversation.")
    L.append("  2. Say: \"Using the context file below, explain [topic] as Feynman")
    L.append("     would — starting from [basic concept] and building up step by step.\"")
    L.append("  3. The 'Referenced in paper' sentences are the authors' own words")
    L.append("     about each figure — the most reliable guide to its meaning.")
    L.append("-->")
    L.append("")
    L.append(f"# Paper Context: {short_code} — {pdf_path.name}")
    L.append("")
    L.append(
        f"*Generated: {date_str}  |  "
        f"Figures: {len(figs)}  |  "
        f"Pages: {len(doc)}*"
    )
    L.append("")
    L.append("---")
    L.append("")

    # Overview
    L.append("## Paper Overview")
    L.append("")
    L.append("*(Auto-extracted from the first pages — edit for accuracy)*")
    L.append("")
    intro = _extract_intro_text(doc)
    L.append(intro if intro else "*(Could not extract text — scanned PDF?)*")
    L.append("")
    L.append("---")
    L.append("")

    # Figure index table
    L.append("## Figure Index")
    L.append("")
    L.append("| Figure | Page | File | Section |")
    L.append("|--------|------|------|---------|")
    for fdata in figs:
        fn  = fdata.get("fig_id", fdata.get("fig_num", "—"))
        sec = fig_sections.get(fn, "—")
        L.append(
            f"| Fig. {fn} | {fdata['page']} "
            f"| `{fdata['fname']}` | {sec} |"
        )
    L.append("")
    L.append("---")
    L.append("")

    # Detailed section per figure
    for fdata in figs:
        fn   = fdata.get("fig_id", fdata.get("fig_num", "—"))
        pn   = fdata.get("page_num", fdata["page"] - 1)
        sec  = fig_sections.get(fn, "—")
        cap  = fig_captions.get(fn, "—")
        refs = _find_figure_references(doc, fn, pn)

        L.append(f"## Figure {fn} — Page {fdata['page']}")
        L.append("")
        L.append(f"**File:** `{fdata['fname']}`  ")
        L.append(f"**Dimensions:** {fdata.get('dims', '—')} px  ")
        L.append(f"**Section:** {sec}")
        L.append("")
        L.append("**Caption:**")
        L.append(f"> {cap}")
        L.append("")
        if refs:
            L.append("**Referenced in paper:**")
            for ref in refs:
                L.append(f"> {ref}")
            L.append("")
        else:
            L.append("**Referenced in paper:** *(none found — may be a scanned PDF)*")
            L.append("")
        L.append("**Feynman entry point:** *(Claude: fill in)*")
        L.append("> What is the simplest real-world analogy for what this figure shows?")
        L.append("> What single concept does it primarily illustrate,")
        L.append("> and what prerequisite knowledge does a reader need?")
        L.append("")
        L.append("---")
        L.append("")

    doc.close()

    out_path = output_dir / f"{short_code}_context.md"
    out_path.write_text("\n".join(L), encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# ExtractionWorker  (Stage 2)
# ---------------------------------------------------------------------------

class ExtractionWorker(QThread):
    """
    Background thread that extracts figures from a list of PDF jobs.

    Signals
    -------
    progress(current, total)  -- emitted after every figure attempt
    figure_ready(data_dict)   -- emitted for every successfully saved figure
    log(message)              -- emitted for warnings / skips
    finished()                -- emitted when all jobs are done (or stopped)
    error(message)            -- emitted on an unrecoverable exception
    """

    progress     = pyqtSignal(int, int)   # current, total
    figure_ready = pyqtSignal(dict)        # FigureData dict
    log          = pyqtSignal(str)
    finished     = pyqtSignal()
    error        = pyqtSignal(str)

    def __init__(
        self,
        jobs: list,          # list of (pdf_path: Path, short_code: str)
        output_dir: Path,
        dpi: int,
        min_size: int,
        page_range: "tuple[int, int] | None" = None,   # 1-indexed inclusive
        parent=None,
    ):
        super().__init__(parent)
        self._jobs       = jobs
        self._output_dir = output_dir
        self._dpi        = dpi
        self._min_size   = min_size
        self._page_range = page_range
        self._evaluator  = QualityEvaluator() if _QUALITY_AVAILABLE else None

    # ------------------------------------------------------------------
    # QThread.run  — executed in the worker thread
    # ------------------------------------------------------------------

    def run(self):
        try:
            self._output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            self.error.emit(f"Cannot create output directory:\n{exc}")
            return

        # First pass: count total expected figures across all PDFs so the
        # progress bar has an accurate denominator before extraction starts.
        total_figs = self._count_total_figures()
        done = 0

        mat = fitz.Matrix(self._dpi / 72, self._dpi / 72)

        for pdf_path, short_code in self._jobs:
            if self.isInterruptionRequested():
                break

            self.log.emit(f"Opening  [{short_code}]: {pdf_path.name}")
            try:
                doc = fitz.open(str(pdf_path))
            except Exception as exc:
                self.log.emit(f"ERROR opening {pdf_path.name}: {exc}")
                continue

            # Apply optional page filter (1-indexed inclusive from UI)
            start_idx = 0
            end_idx   = len(doc) - 1
            if self._page_range:
                start_page, end_page = self._page_range
                start_idx = max(0, start_page - 1)
                end_idx   = min(len(doc) - 1, end_page - 1)
                if start_idx > end_idx:
                    self.log.emit(
                        f"  WARN  [{short_code}] page range {start_page}-{end_page} "
                        f"is outside this PDF ({len(doc)} pages)"
                    )
                    doc.close()
                    continue

            # Per-PDF quality metrics collected during extraction
            pdf_metrics: list = []

            # Collect captions across all pages
            all_captions: dict = {}
            page_caption_map: dict = {}
            for page_num in range(start_idx, end_idx + 1):
                if self.isInterruptionRequested():
                    break
                page = doc[page_num]
                found = _find_captions_on_page(page)
                page_caption_map[page_num] = found
                for fig_id, cap_rect in found.items():
                    if fig_id not in all_captions:
                        all_captions[fig_id] = (page_num, cap_rect)

            cap_count = len(all_captions)
            if cap_count == 0:
                self.log.emit(
                    f"  WARN  {pdf_path.name}: no figure captions found in pages {start_idx+1}-{end_idx+1}"
                )

            # Extract each figure
            for fig_id in sorted(all_captions, key=_fig_sort_key):
                if self.isInterruptionRequested():
                    break

                page_num, cap_rect = all_captions[fig_id]
                page = doc[page_num]

                this_page_captions = page_caption_map.get(page_num, {})
                fig_rect = _find_figure_rect(
                    page,
                    cap_rect,
                    this_page_captions,
                    output_dpi=self._dpi,
                    min_size_px=self._min_size,
                )
                done += 1
                self.progress.emit(done, total_figs)

                if fig_rect is None:
                    self.log.emit(
                        f"  skip  [{short_code}] Fig.{fig_id} "
                        f"page {page_num+1}: no content above caption"
                    )
                    continue

                try:
                    pix = page.get_pixmap(matrix=mat, clip=fig_rect, alpha=False)
                except Exception as exc:
                    self.log.emit(f"  WARN  render failed Fig.{fig_id}: {exc}")
                    continue

                w, h = pix.width, pix.height
                if w < self._min_size or h < self._min_size:
                    self.log.emit(
                        f"  skip  [{short_code}] Fig.{fig_id}: "
                        f"too small ({w}x{h}px)"
                    )
                    continue

                fig_safe = _fig_id_for_filename(fig_id)
                base_name = f"{short_code}_Fig{fig_safe}_page{page_num+1:02d}.png"
                out_path  = _make_unique_path(self._output_dir, base_name)

                try:
                    pix.save(str(out_path))
                except Exception as exc:
                    self.log.emit(f"  WARN  save failed {base_name}: {exc}")
                    continue

                # --- Maxwell measurement layer ---
                confidence     = 0.0
                classification = "UNKNOWN"
                if self._evaluator is not None:
                    try:
                        qm = self._evaluator.measure(
                            out_path,
                            fig_num=fig_id,
                            page=page_num + 1,
                            paper_num=short_code,
                        )
                        pdf_metrics.append(qm)
                        confidence     = qm.confidence_score
                        classification = qm.classification
                    except Exception as qex:
                        self.log.emit(f"  WARN  quality measure failed: {qex}")

                self.log.emit(
                    f"  saved  {out_path.name}  {w}x{h}px  "
                    f"page {page_num+1}  [{classification}  {confidence:.2f}]"
                )
                self.figure_ready.emit({
                    "path"          : str(out_path),
                    "fname"         : out_path.name,
                    "page"          : page_num + 1,
                    "dims"          : f"{w} x {h}",
                    "paper_num"     : short_code,
                    "paper_name"    : pdf_path.name,
                    "fig_num"       : fig_id,
                    "fig_id"        : fig_id,
                    "confidence"    : confidence,
                    "classification": classification,
                    "pdf_path"      : str(pdf_path),
                    "page_num"      : page_num,
                    "crop_rect"     : (fig_rect.x0, fig_rect.y0, fig_rect.x1, fig_rect.y1),
                    "dpi"           : self._dpi,
                    "source"        : "caption",
                })

            # Fallback: if captions are missing/unreliable, extract embedded images
            if cap_count < 2 and not self.isInterruptionRequested():
                self.log.emit(
                    f"  WARN  [{short_code}] <2 captions in pages {start_idx+1}-{end_idx+1} — extracting embedded images"
                )
                for page_num in range(start_idx, end_idx + 1):
                    if self.isInterruptionRequested():
                        break
                    page = doc[page_num]
                    try:
                        images = page.get_images(full=True)
                    except Exception:
                        images = []
                    if not images:
                        continue

                    page_area = float(page.rect.get_area()) if page.rect else 0.0
                    page_area = page_area if page_area > 0 else 1.0
                    saved_on_page = 0

                    for img in images:
                        if self.isInterruptionRequested():
                            break
                        if saved_on_page >= _EMBED_MAX_PER_PAGE:
                            self.log.emit(
                                f"  WARN  [{short_code}] page {page_num+1}: too many embedded images — capped at {_EMBED_MAX_PER_PAGE}"
                            )
                            break

                        xref = img[0]

                        # Skip tiny on-page placements (logos, icons)
                        try:
                            rects = page.get_image_rects(xref)
                        except Exception:
                            rects = []
                        if rects:
                            max_frac = max((float(r.get_area()) / page_area) for r in rects)
                            if max_frac < _EMBED_MIN_AREA_FRAC:
                                continue

                        # Filter tiny raw images cheaply before counting progress
                        try:
                            info = doc.extract_image(xref)
                            rw = int(info.get("width", 0) or 0)
                            rh = int(info.get("height", 0) or 0)
                            if rw and rh and (rw < self._min_size or rh < self._min_size):
                                continue
                        except Exception:
                            pass

                        done += 1
                        self.progress.emit(done, total_figs)

                        try:
                            pix = fitz.Pixmap(doc, xref)
                            if pix.alpha:
                                pix = fitz.Pixmap(pix, 0)
                            if pix.n == 1:
                                pix = fitz.Pixmap(fitz.csRGB, pix)
                            elif pix.n > 4:
                                pix = fitz.Pixmap(fitz.csRGB, pix)
                        except Exception as exc:
                            self.log.emit(f"  WARN  embedded image load failed p{page_num+1} xref={xref}: {exc}")
                            continue

                        w, h = pix.width, pix.height
                        if w < self._min_size or h < self._min_size:
                            continue

                        saved_on_page += 1
                        base_name = f"{short_code}_Img_page{page_num+1:02d}_{saved_on_page:02d}.png"
                        out_path = _make_unique_path(self._output_dir, base_name)
                        try:
                            pix.save(str(out_path))
                        except Exception as exc:
                            self.log.emit(f"  WARN  save failed {base_name}: {exc}")
                            continue

                        confidence = 0.0
                        classification = "UNKNOWN"
                        if self._evaluator is not None:
                            try:
                                qm = self._evaluator.measure(
                                    out_path,
                                    fig_num=0,
                                    page=page_num + 1,
                                    paper_num=short_code,
                                )
                                pdf_metrics.append(qm)
                                confidence = qm.confidence_score
                                classification = qm.classification
                            except Exception as qex:
                                self.log.emit(f"  WARN  quality measure failed: {qex}")

                        fig_id = f"img:{page_num+1}:{saved_on_page}"
                        self.figure_ready.emit({
                            "path"          : str(out_path),
                            "fname"         : out_path.name,
                            "page"          : page_num + 1,
                            "dims"          : f"{w} x {h}",
                            "paper_num"     : short_code,
                            "paper_name"    : pdf_path.name,
                            "fig_num"       : 0,
                            "fig_id"        : fig_id,
                            "confidence"    : confidence,
                            "classification": classification,
                            "pdf_path"      : str(pdf_path),
                            "page_num"      : page_num,
                            "dpi"           : self._dpi,
                            "source"        : "embedded_image",
                        })

            doc.close()

            # Write per-PDF quality report
            if self._evaluator is not None and pdf_metrics:
                try:
                    log_path = self._evaluator.log_session(
                        pdf_path.name, pdf_metrics, self._output_dir
                    )
                    self.log.emit(f"  metrics → {log_path.name}")
                except Exception as exc:
                    self.log.emit(f"  WARN  metrics log failed: {exc}")

        self.finished.emit()

    # ------------------------------------------------------------------
    # Helper: quick pass to count total figures (for progress bar total)
    # ------------------------------------------------------------------

    def _count_total_figures(self) -> int:
        total = 0
        for pdf_path, _ in self._jobs:
            try:
                doc = fitz.open(str(pdf_path))
                captions: set = set()

                start_idx = 0
                end_idx   = len(doc) - 1
                if self._page_range:
                    start_page, end_page = self._page_range
                    start_idx = max(0, start_page - 1)
                    end_idx   = min(len(doc) - 1, end_page - 1)
                    if start_idx > end_idx:
                        doc.close()
                        continue

                for page_num in range(start_idx, end_idx + 1):
                    for fig_id in _find_captions_on_page(doc[page_num]):
                        captions.add(fig_id)

                cap_count = len(captions)
                total += cap_count

                # Fallback count: embedded images when captions are missing/unreliable
                if cap_count < 2:
                    embed_count = 0
                    for page_num in range(start_idx, end_idx + 1):
                        page = doc[page_num]
                        try:
                            images = page.get_images(full=True)
                        except Exception:
                            images = []
                        if not images:
                            continue
                        page_area = float(page.rect.get_area()) if page.rect else 0.0
                        page_area = page_area if page_area > 0 else 1.0
                        per_page = 0
                        for img in images:
                            if per_page >= _EMBED_MAX_PER_PAGE:
                                break
                            xref = img[0]
                            try:
                                rects = page.get_image_rects(xref)
                            except Exception:
                                rects = []
                            if rects:
                                max_frac = max((float(r.get_area()) / page_area) for r in rects)
                                if max_frac < _EMBED_MIN_AREA_FRAC:
                                    continue
                            # Filter tiny raw images quickly
                            try:
                                info = doc.extract_image(xref)
                                w = int(info.get("width", 0) or 0)
                                h = int(info.get("height", 0) or 0)
                                if w and h and (w < self._min_size or h < self._min_size):
                                    continue
                            except Exception:
                                pass
                            embed_count += 1
                            per_page += 1
                    total += embed_count
                doc.close()
            except Exception:
                pass
        return max(total, 1)   # avoid division-by-zero in progress bar


# ---------------------------------------------------------------------------
# SingleFigureWorker  (Stage 5) — re-extract one figure in background
# ---------------------------------------------------------------------------

class SingleFigureWorker(QThread):
    done   = pyqtSignal(str, object)   # (dims_str, new_crop_rect tuple)
    failed = pyqtSignal(str)

    def __init__(self, data, exp_top, exp_bot, exp_lft, exp_rgt, dpi, parent=None):
        super().__init__(parent)
        self._data = data
        self._args = (exp_top, exp_bot, exp_lft, exp_rgt, dpi)

    def run(self):
        try:
            dims, rect_tuple = _reextract_figure(self._data, *self._args)
            self.done.emit(dims, rect_tuple)
        except Exception as exc:
            self.failed.emit(str(exc))


# ---------------------------------------------------------------------------
# SubFigureWorker  (Stage 8) — extract a sub-figure to a NEW file
# ---------------------------------------------------------------------------

class SubFigureWorker(QThread):
    """
    Like SingleFigureWorker but saves to a new path instead of overwriting,
    and emits the complete data dict for the new card.
    """
    done   = pyqtSignal(dict)   # new figure data dict
    failed = pyqtSignal(str)

    def __init__(self, parent_data, exp_top, exp_bot, exp_lft, exp_rgt, dpi, out_path, parent=None):
        super().__init__(parent)
        self._parent_data = parent_data
        self._args        = (exp_top, exp_bot, exp_lft, exp_rgt, dpi)
        self._out_path    = out_path

    def run(self):
        try:
            dims, rect_tuple = _reextract_figure(
                self._parent_data, *self._args, out_path=self._out_path
            )
            data = dict(self._parent_data)          # inherit all parent fields
            data["path"]      = self._out_path
            data["fname"]     = Path(self._out_path).name
            data["dims"]      = dims
            data["crop_rect"] = rect_tuple
            self.done.emit(data)
        except Exception as exc:
            self.failed.emit(str(exc))


# ---------------------------------------------------------------------------
# ContextWorker  (Stage 7) — generate context .md files in background
# ---------------------------------------------------------------------------

class ContextWorker(QThread):
    """
    Generates one {short_code}_context.md per paper using _generate_paper_context_md.

    Signals
    -------
    progress(current, total)  -- after each paper
    file_done(path_str)       -- path of the .md file just written
    log(message)              -- warnings / skips
    finished()                -- all papers done
    """

    progress  = pyqtSignal(int, int)
    file_done = pyqtSignal(str)
    log       = pyqtSignal(str)
    finished  = pyqtSignal()

    def __init__(
        self,
        jobs: list,                      # [(pdf_path, short_code), …]
        figures_by_paper: dict,          # {short_code: [fig_dict, …]}
        output_dir: Path,
        parent=None,
    ):
        super().__init__(parent)
        self._jobs             = jobs
        self._figures_by_paper = figures_by_paper
        self._output_dir       = output_dir

    def run(self):
        date_str = _date.today().isoformat()
        total    = len(self._jobs)
        for i, (pdf_path, short_code) in enumerate(self._jobs, 1):
            figs = self._figures_by_paper.get(short_code, [])
            if not figs:
                self.log.emit(f"  skip  [{short_code}]: no figures — skipping context")
                self.progress.emit(i, total)
                continue
            try:
                out = _generate_paper_context_md(
                    pdf_path, short_code, figs, self._output_dir, date_str
                )
                self.file_done.emit(str(out))
            except Exception as exc:
                self.log.emit(f"  WARN  [{short_code}] context failed: {exc}")
            self.progress.emit(i, total)
        self.finished.emit()


# ---------------------------------------------------------------------------
# ControlPanel  (Stage 1 + Stage 2 additions)
# ---------------------------------------------------------------------------

class ControlPanel(QWidget):
    """
    Top control bar: file queue management, output settings, DPI/min-size.
    """

    queue_changed = pyqtSignal(int)   # emits file count on every queue change

    def __init__(self, parent=None):
        super().__init__(parent)
        # Each entry: (pdf_path, QLineEdit) — QLineEdit holds the editable short code
        self._queue_rows: list[tuple[Path, object]] = []
        self._build_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def queued_entries(self) -> list[tuple[Path, str]]:
        """Return (pdf_path, short_code) pairs in queue order."""
        return [
            (path, edit.text().strip() or _make_short_code(path))
            for path, edit in self._queue_rows
        ]

    def queued_paths(self) -> list[Path]:
        return [path for path, _ in self._queue_rows]

    def output_dir(self) -> Path:
        text = self._outdir_edit.text().strip()
        return Path(text) if text else Path.home() / "figures"

    def dpi(self) -> int:
        return self._dpi_spin.value()

    def min_size(self) -> int:
        return self._minsize_spin.value()

    def page_range(self) -> "tuple[int, int] | None":
        """Return (start_page, end_page) in 1-indexed inclusive form.

        Convention:
        - 0 means "unset".
        - If both are 0: no filter (None).
        - If only start is set: start..infinity (worker clamps to doc length).
        - If only end is set: 1..end.
        - If start > end: auto-swap.
        """
        start = self._page_from_spin.value()
        end   = self._page_to_spin.value()
        if start == 0 and end == 0:
            return None
        if start == 0:
            start = 1
        if end == 0:
            end = 10 ** 9
        if start > end:
            start, end = end, start
        return start, end

    def page_range_text(self) -> str:
        """Human-readable description of the current page filter."""
        start = self._page_from_spin.value()
        end   = self._page_to_spin.value()
        if start == 0 and end == 0:
            return "all pages"
        if start == 0:
            return f"pages 1–{end}"
        if end == 0:
            return f"pages {start}–end"
        if start > end:
            start, end = end, start
        return f"pages {start}–{end}"

    def set_controls_enabled(self, enabled: bool) -> None:
        """Lock / unlock file-management controls during extraction."""
        for w in (
            self._add_pdf_btn,
            self._add_folder_btn,
            self._clear_btn,
            self._dpi_spin,
            self._minsize_spin,
            self._page_from_spin,
            self._page_to_spin,
            self._queue_scroll,
        ):
            w.setEnabled(enabled)

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 6, 10, 6)
        root.setSpacing(6)

        # Row 1: file buttons (left) + DPI/min-size settings (right)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self._add_pdf_btn = QPushButton("+ Add PDF")
        self._add_pdf_btn.setToolTip("Add one or more PDF files to the queue")
        self._add_pdf_btn.clicked.connect(self._on_add_pdf)

        self._add_folder_btn = QPushButton("+ Add Folder")
        self._add_folder_btn.setToolTip("Add all PDFs inside a folder to the queue")
        self._add_folder_btn.clicked.connect(self._on_add_folder)

        self._clear_btn = QPushButton("✕  Clear")
        self._clear_btn.setObjectName("clearBtn")
        self._clear_btn.setToolTip("Remove all files from the queue")
        self._clear_btn.clicked.connect(self._on_clear_all)

        toolbar.addWidget(self._add_pdf_btn)
        toolbar.addWidget(self._add_folder_btn)
        toolbar.addWidget(self._clear_btn)
        toolbar.addStretch()

        dpi_label = QLabel("DPI:")
        dpi_label.setObjectName("sectionLabel")
        self._dpi_spin = QSpinBox()
        self._dpi_spin.setRange(72, 400)
        self._dpi_spin.setValue(200)
        self._dpi_spin.setSingleStep(25)
        self._dpi_spin.setToolTip("Render resolution (default 200)")

        minsize_label = QLabel("Min size:")
        minsize_label.setObjectName("sectionLabel")
        self._minsize_spin = QSpinBox()
        self._minsize_spin.setRange(20, 500)
        self._minsize_spin.setValue(80)
        self._minsize_spin.setSuffix(" px")
        self._minsize_spin.setToolTip("Minimum figure dimension to keep (default 80 px)")

        toolbar.addWidget(dpi_label)
        toolbar.addWidget(self._dpi_spin)
        toolbar.addSpacing(8)
        toolbar.addWidget(minsize_label)
        toolbar.addWidget(self._minsize_spin)

        # Page filter (optional)
        toolbar.addSpacing(10)
        pages_label = QLabel("Pages:")
        pages_label.setObjectName("sectionLabel")
        self._page_from_spin = QSpinBox()
        self._page_from_spin.setRange(0, 9999)
        self._page_from_spin.setValue(0)
        self._page_from_spin.setToolTip(
            "Start page (1-indexed). Use 0 for all pages."
        )
        to_label = QLabel("to")
        to_label.setStyleSheet("color: #858585;")
        self._page_to_spin = QSpinBox()
        self._page_to_spin.setRange(0, 9999)
        self._page_to_spin.setValue(0)
        self._page_to_spin.setToolTip(
            "End page (inclusive, 1-indexed). Use 0 for all pages."
        )
        toolbar.addWidget(pages_label)
        toolbar.addWidget(self._page_from_spin)
        toolbar.addWidget(to_label)
        toolbar.addWidget(self._page_to_spin)
        root.addLayout(toolbar)

        # Row 2: output directory
        out_row = QHBoxLayout()
        out_row.setSpacing(8)

        out_label = QLabel("Output:")
        out_label.setObjectName("sectionLabel")
        out_label.setFixedWidth(60)

        self._outdir_edit = QLineEdit()
        self._outdir_edit.setPlaceholderText("Choose output folder…")
        self._outdir_edit.setText(str(Path.home() / "figures"))

        browse_out_btn = QPushButton("Browse")
        browse_out_btn.setFixedWidth(72)
        browse_out_btn.clicked.connect(self._on_browse_output)

        out_row.addWidget(out_label)
        out_row.addWidget(self._outdir_edit, stretch=1)
        out_row.addWidget(browse_out_btn)
        root.addLayout(out_row)

        # Row 3: scrollable queue with per-row short-code fields
        self._queue_container = QWidget()
        self._queue_container.setObjectName("queueContainer")
        self._queue_layout = QVBoxLayout(self._queue_container)
        self._queue_layout.setContentsMargins(4, 3, 4, 3)
        self._queue_layout.setSpacing(2)

        self._queue_empty_label = QLabel("No files queued — add PDFs above")
        self._queue_empty_label.setObjectName("queueLabel")
        self._queue_layout.addWidget(self._queue_empty_label)
        self._queue_layout.addStretch()

        self._queue_scroll = QScrollArea()
        self._queue_scroll.setObjectName("queueScroll")
        self._queue_scroll.setWidget(self._queue_container)
        self._queue_scroll.setWidgetResizable(True)
        self._queue_scroll.setMaximumHeight(110)
        self._queue_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        root.addWidget(self._queue_scroll)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_add_pdf(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select PDF files", str(Path.home()),
            "PDF files (*.pdf);;All files (*)",
        )
        existing = {path for path, _ in self._queue_rows}
        for p in paths:
            path = Path(p)
            if path not in existing:
                self._add_queue_row(path)
                existing.add(path)
        self._refresh_queue()

    def _on_add_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select folder containing PDFs", str(Path.home()),
        )
        if folder:
            existing = {path for path, _ in self._queue_rows}
            for path in sorted(Path(folder).glob("*.pdf")):
                if path not in existing:
                    self._add_queue_row(path)
                    existing.add(path)
        self._refresh_queue()

    def _on_clear_all(self):
        self._queue_rows.clear()
        # Remove all row widgets from layout (keep empty label and stretch)
        while self._queue_layout.count() > 2:
            item = self._queue_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._refresh_queue()

    def _on_browse_output(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select output directory",
            self._outdir_edit.text() or str(Path.home()),
        )
        if folder:
            self._outdir_edit.setText(folder)

    def _add_queue_row(self, path: Path):
        """Add one PDF entry row to the queue widget."""
        row_widget = QWidget()
        row_widget.setObjectName("queueContainer")
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        # Filename label (truncated)
        name = path.name
        display_name = name if len(name) <= 38 else name[:35] + "…"
        name_label = QLabel(display_name)
        name_label.setObjectName("queueRowName")
        name_label.setToolTip(str(path))

        # Short-code editor
        code_edit = QLineEdit()
        code_edit.setObjectName("queueRowCode")
        code_edit.setText(_make_short_code(path))
        code_edit.setToolTip("Short code used as filename prefix (e.g. CHB_DBM)")
        code_edit.setPlaceholderText("CODE")

        # Remove button
        remove_btn = QPushButton("✕")
        remove_btn.setObjectName("queueRowRemove")
        remove_btn.setToolTip("Remove this PDF from queue")
        remove_btn.clicked.connect(lambda _, p=path, w=row_widget: self._remove_row(p, w))

        row_layout.addWidget(name_label, stretch=1)
        row_layout.addWidget(code_edit)
        row_layout.addWidget(remove_btn)

        # Insert before the stretch (last item) and the empty label (second-to-last)
        insert_pos = max(0, self._queue_layout.count() - 1)
        self._queue_layout.insertWidget(insert_pos, row_widget)
        self._queue_rows.append((path, code_edit))

    def _remove_row(self, path: Path, row_widget):
        """Remove a single PDF row from the queue."""
        self._queue_rows = [(p, e) for p, e in self._queue_rows if p != path]
        row_widget.deleteLater()
        self._refresh_queue()

    def _refresh_queue(self):
        n = len(self._queue_rows)
        self._queue_empty_label.setVisible(n == 0)
        self.queue_changed.emit(n)


# ---------------------------------------------------------------------------
# ImageCropWidget  (Stage 6) — image display with mouse crop selection
# ---------------------------------------------------------------------------

class ImageCropWidget(QWidget):
    """
    Displays a QPixmap scaled to fit the widget (aspect-ratio preserved) and
    lets the user draw a crop rectangle with the mouse.

    Interaction
    -----------
    Left-drag  : draw / redraw the selection rectangle
    Right-click: clear the selection
    Release    : emits ``crop_selected(x0, y0, x1, y1)`` as fractions [0-1]
                 of the displayed image (NOT the widget).  Values <5 px wide/tall
                 are silently discarded.
    """

    crop_selected    = pyqtSignal(float, float, float, float)
    edge_drag_started = pyqtSignal(str)           # 'top'|'bottom'|'left'|'right'
    edge_drag_moved   = pyqtSignal(str, float)    # edge, cumulative fraction from drag start

    _HANDLE_SZ  = 7
    _HANDLE_W   = 14   # pixel hit-zone half-width around each edge
    _SEL_COLOR  = QColor(86, 156, 214)
    _SEL_FILL   = QColor(86, 156, 214, 40)
    _EDGE_COLOR = QColor(78, 201, 176)            # teal tab colour

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._img_rect = QRect()          # where the scaled image sits (widget coords)
        self._sel_start = None            # QPoint — drag origin (interior crop)
        self._sel_rect: QRect | None = None   # current selection (widget coords, normalised)
        self._dragging = False
        # Edge-drag state
        self._hover_edge: str | None = None
        self._dragging_edge: str | None = None
        self._drag_start_pos = None       # QPoint when edge drag began
        self._drag_current_pos = None     # QPoint current drag position
        self.setMinimumSize(100, 80)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.CrossCursor)

    # ---------------------------------------------------------------- public

    def set_pixmap(self, pixmap: QPixmap):
        self._pixmap = pixmap
        self.clear_selection()          # new image — discard stale selection
        self.update()

    def clear(self):
        self._pixmap = None
        self.clear_selection()
        self.update()

    def clear_selection(self):
        self._sel_start = None
        self._sel_rect  = None
        self._dragging  = False
        self._hover_edge = None
        self._dragging_edge = None
        self._drag_start_pos = None
        self._drag_current_pos = None
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.update()

    # -------------------------------------------------------------- painting

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor("#111111"))

        if not self._pixmap or self._pixmap.isNull():
            painter.setPen(QColor("#555555"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "Select a figure to preview")
            return

        # Scale pixmap to fit, keep aspect ratio, centre it
        scaled = self._pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        ox = (self.width()  - scaled.width())  // 2
        oy = (self.height() - scaled.height()) // 2
        self._img_rect = QRect(ox, oy, scaled.width(), scaled.height())
        painter.drawPixmap(self._img_rect.topLeft(), scaled)

        # Draw edge-drag handles (small teal tabs at midpoint of each edge)
        r = self._img_rect
        painter.setPen(Qt.PenStyle.NoPen)
        for edge, tab_rect in (
            ('top',    (r.center().x() - 18, r.top()    - 4,  36, 8)),
            ('bottom', (r.center().x() - 18, r.bottom() - 4,  36, 8)),
            ('left',   (r.left()   - 4,  r.center().y() - 18, 8, 36)),
            ('right',  (r.right()  - 4,  r.center().y() - 18, 8, 36)),
        ):
            alpha = 210 if edge == self._hover_edge or edge == self._dragging_edge else 110
            painter.setBrush(QColor(self._EDGE_COLOR.red(),
                                    self._EDGE_COLOR.green(),
                                    self._EDGE_COLOR.blue(), alpha))
            painter.drawRoundedRect(*tab_rect, 3, 3)

        # Drag line — dashed teal line showing new edge position while dragging
        if self._dragging_edge and self._drag_current_pos:
            pen = QPen(self._EDGE_COLOR, 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            cp = self._drag_current_pos
            if self._dragging_edge in ('top', 'bottom'):
                y = max(r.top(), min(cp.y(), r.bottom()))
                painter.drawLine(r.left(), y, r.right(), y)
            else:
                x = max(r.left(), min(cp.x(), r.right()))
                painter.drawLine(x, r.top(), x, r.bottom())

        # Draw selection overlay
        if self._sel_rect and not self._sel_rect.isEmpty():
            sel = self._sel_rect.intersected(self._img_rect)
            if not sel.isEmpty():
                # Semi-transparent fill
                painter.fillRect(sel, self._SEL_FILL)
                # Dashed border
                pen = QPen(self._SEL_COLOR, 2, Qt.PenStyle.DashLine)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(sel)
                # Corner handles
                hs = self._HANDLE_SZ
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(self._SEL_COLOR)
                for hx, hy in [
                    (sel.left(),  sel.top()),
                    (sel.right(), sel.top()),
                    (sel.left(),  sel.bottom()),
                    (sel.right(), sel.bottom()),
                ]:
                    painter.drawRect(hx - hs // 2, hy - hs // 2, hs, hs)

                # Dimensions label inside selection
                if sel.width() > 60 and sel.height() > 20:
                    iw = self._img_rect.width()
                    ih = self._img_rect.height()
                    if iw > 0 and ih > 0:
                        w_frac = sel.width()  / iw
                        h_frac = sel.height() / ih
                        dim_text = f"{w_frac*100:.0f}% × {h_frac*100:.0f}%"
                        painter.setPen(self._SEL_COLOR)
                        painter.drawText(sel, Qt.AlignmentFlag.AlignCenter, dim_text)

    # -------------------------------------------------------------- mouse

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._pixmap:
            pos = event.pos()
            # Edge drag takes priority over interior crop selection
            edge = self._edge_at(pos)
            if edge:
                self._dragging_edge  = edge
                self._drag_start_pos = pos
                self._drag_current_pos = pos
                self.edge_drag_started.emit(edge)
                self.update()
                return
            if self._img_rect.contains(pos):
                self._sel_start = pos
                self._sel_rect  = QRect(pos, pos)
                self._dragging  = True
                self.update()
        elif event.button() == Qt.MouseButton.RightButton:
            self.clear_selection()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        pos = event.pos()

        # ── Edge drag in progress ──────────────────────────────────────────
        if self._dragging_edge and self._drag_start_pos:
            self._drag_current_pos = pos
            r   = self._img_rect
            edge = self._dragging_edge
            if edge in ('top', 'bottom'):
                ref = r.height() if r.height() > 0 else 1
                dy  = pos.y() - self._drag_start_pos.y()
                frac = (-dy / ref) if edge == 'top' else (dy / ref)
            else:
                ref = r.width() if r.width() > 0 else 1
                dx  = pos.x() - self._drag_start_pos.x()
                frac = (-dx / ref) if edge == 'left' else (dx / ref)
            self.edge_drag_moved.emit(edge, frac)
            self.update()
            return

        # ── Interior crop drag ────────────────────────────────────────────
        if self._dragging and self._sel_start:
            p = pos
            p.setX(max(self._img_rect.left(), min(p.x(), self._img_rect.right())))
            p.setY(max(self._img_rect.top(),  min(p.y(), self._img_rect.bottom())))
            self._sel_rect = QRect(self._sel_start, p).normalized()
            self.update()
            super().mouseMoveEvent(event)
            return

        # ── Hover — update cursor and highlight ───────────────────────────
        old_hover = self._hover_edge
        self._hover_edge = self._edge_at(pos)
        if self._hover_edge in ('top', 'bottom'):
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        elif self._hover_edge in ('left', 'right'):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)
        if self._hover_edge != old_hover:
            self.update()

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._dragging_edge:
                self._dragging_edge  = None
                self._drag_start_pos = None
                self._drag_current_pos = None
                self.update()
                super().mouseReleaseEvent(event)
                return
            if self._dragging:
                self._dragging = False
                if self._sel_rect and self._sel_rect.width() > 4 and self._sel_rect.height() > 4:
                    self._emit_crop()
                else:
                    self.clear_selection()   # too small — discard
        super().mouseReleaseEvent(event)

    def _edge_at(self, pos) -> "str | None":
        """Return which image edge the cursor is near, or None."""
        if not self._pixmap or self._img_rect.isEmpty():
            return None
        r = self._img_rect
        H = self._HANDLE_W
        if abs(pos.y() - r.top())    <= H and r.left() <= pos.x() <= r.right():
            return 'top'
        if abs(pos.y() - r.bottom()) <= H and r.left() <= pos.x() <= r.right():
            return 'bottom'
        if abs(pos.x() - r.left())   <= H and r.top() <= pos.y() <= r.bottom():
            return 'left'
        if abs(pos.x() - r.right())  <= H and r.top() <= pos.y() <= r.bottom():
            return 'right'
        return None

    def _emit_crop(self):
        if not self._sel_rect or self._img_rect.width() == 0 or self._img_rect.height() == 0:
            return
        sel = self._sel_rect.intersected(self._img_rect)
        if sel.isEmpty():
            return
        iw = self._img_rect.width()
        ih = self._img_rect.height()
        x0 = (sel.left()   - self._img_rect.left()) / iw
        y0 = (sel.top()    - self._img_rect.top())  / ih
        x1 = (sel.right()  - self._img_rect.left()) / iw
        y1 = (sel.bottom() - self._img_rect.top())  / ih
        self.crop_selected.emit(
            max(0.0, x0), max(0.0, y0),
            min(1.0, x1), min(1.0, y1),
        )


# ---------------------------------------------------------------------------
# Placeholder panels  (replaced in Stages 3 & 4)
# ---------------------------------------------------------------------------

class _PlaceholderPanel(QWidget):
    def __init__(self, text: str, object_name: str, parent=None):
        super().__init__(parent)
        self.setObjectName(object_name)
        layout = QVBoxLayout(self)
        label  = QLabel(text)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: #3c3c3c; font-size: 15px;")
        layout.addWidget(label)


# ---------------------------------------------------------------------------
# PreviewPanel  (Stage 4) — right splitter pane
# ---------------------------------------------------------------------------

class PreviewPanel(QWidget):
    """Right splitter pane — full-resolution image + metadata + inline rename."""

    rename_requested    = pyqtSignal(str, str)   # (old_abs_path, new_fname)
    reextract_requested = pyqtSignal(dict, float, float, float, float, int)
    # (data, expand_top, expand_bottom, expand_left, expand_right, dpi)
    subfigure_requested = pyqtSignal(dict, float, float, float, float, int)
    # same args — but saves to a new file instead of overwriting

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("previewPanel")
        self._current_data: dict | None = None
        self._edge_drag_start_vals: dict = {}
        self._exp: dict[str, float] = {"top": 0.0, "bottom": 0.0, "left": 0.0, "right": 0.0}
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Inner vertical splitter: image (top) | info scroll (bottom) ──
        self._inner_splitter = QSplitter(Qt.Orientation.Vertical)
        self._inner_splitter.setObjectName("previewSplitter")
        self._inner_splitter.setHandleWidth(5)
        root.addWidget(self._inner_splitter)

        # ── Top pane: image ──────────────────────────────────────────────
        img_pane = QWidget()
        img_pane.setObjectName("previewPanel")
        img_layout = QVBoxLayout(img_pane)
        img_layout.setContentsMargins(6, 6, 6, 4)
        img_layout.setSpacing(4)

        img_header = QLabel("Figure Preview")
        img_header.setObjectName("sectionLabel")
        img_layout.addWidget(img_header)

        self._crop_widget = ImageCropWidget()
        self._crop_widget.crop_selected.connect(self._on_mouse_crop)
        self._crop_widget.edge_drag_started.connect(self._on_edge_drag_started)
        self._crop_widget.edge_drag_moved.connect(self._on_edge_drag_moved)
        img_layout.addWidget(self._crop_widget, stretch=1)

        self._crop_hint = QLabel(
            "Drag edge tabs to adjust crop  •  Drag inside to select region  •  "
            "Right-click to clear  •  Ctrl+Enter to re-extract"
        )
        self._crop_hint.setObjectName("cropHint")
        self._crop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        img_layout.addWidget(self._crop_hint)

        self._inner_splitter.addWidget(img_pane)

        # ── Bottom pane: scrollable metadata + crop controls ─────────────
        info_scroll = QScrollArea()
        info_scroll.setObjectName("infoScroll")
        info_scroll.setWidgetResizable(True)
        info_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        info_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        scroll_w = QWidget()
        scroll_vbox = QVBoxLayout(scroll_w)
        scroll_vbox.setContentsMargins(6, 6, 6, 6)
        scroll_vbox.setSpacing(6)

        # Metadata frame (compact)
        meta_frame = QFrame()
        meta_frame.setObjectName("metaPanel")
        meta_grid = QGridLayout(meta_frame)
        meta_grid.setContentsMargins(8, 8, 8, 8)
        meta_grid.setSpacing(4)
        meta_grid.setColumnStretch(1, 1)
        meta_grid.setColumnStretch(3, 1)

        # File row — full width
        meta_grid.addWidget(QLabel("File:"), 0, 0, Qt.AlignmentFlag.AlignRight)
        self._fname_edit = QLineEdit()
        self._fname_edit.editingFinished.connect(self._on_rename)
        meta_grid.addWidget(self._fname_edit, 0, 1, 1, 3)

        # Page | Size on one row
        meta_grid.addWidget(QLabel("Page:"), 1, 0, Qt.AlignmentFlag.AlignRight)
        self._page_lbl = QLabel("—")
        meta_grid.addWidget(self._page_lbl, 1, 1)
        meta_grid.addWidget(QLabel("Size:"), 1, 2, Qt.AlignmentFlag.AlignRight)
        self._dims_lbl = QLabel("—")
        meta_grid.addWidget(self._dims_lbl, 1, 3)

        # Paper | Quality on one row
        meta_grid.addWidget(QLabel("Paper:"), 2, 0, Qt.AlignmentFlag.AlignRight)
        self._paper_lbl = QLabel("—")
        meta_grid.addWidget(self._paper_lbl, 2, 1)
        meta_grid.addWidget(QLabel("Quality:"), 2, 2, Qt.AlignmentFlag.AlignRight)
        self._quality_lbl = QLabel("—")
        meta_grid.addWidget(self._quality_lbl, 2, 3)

        scroll_vbox.addWidget(meta_frame)

        # ── Crop Correction frame ────────────────────────────────────────
        crop_frame = QFrame()
        crop_frame.setObjectName("cropPanel")
        crop_vbox = QVBoxLayout(crop_frame)
        crop_vbox.setContentsMargins(8, 8, 8, 8)
        crop_vbox.setSpacing(6)

        crop_hdr = QLabel("Crop Correction")
        crop_hdr.setObjectName("sectionLabel")
        crop_vbox.addWidget(crop_hdr)

        # Deltas display (drag/selection is the primary input)
        self._delta_lbl = QLabel("Δ crop: T 0.0pt | B 0.0pt | L 0.0pt | R 0.0pt")
        self._delta_lbl.setStyleSheet("color: #858585; font-size: 11px;")
        crop_vbox.addWidget(self._delta_lbl)

        dpi_btn_row = QHBoxLayout()
        dpi_btn_row.setSpacing(8)
        dpi_btn_row.addWidget(QLabel("DPI:"))
        self._reex_dpi_sb = QSpinBox()
        self._reex_dpi_sb.setRange(72, 600)
        self._reex_dpi_sb.setSingleStep(50)
        self._reex_dpi_sb.setValue(200)
        dpi_btn_row.addWidget(self._reex_dpi_sb)
        dpi_btn_row.addStretch()
        self._reset_btn = QPushButton("Reset")
        self._reset_btn.clicked.connect(self._on_crop_reset)
        self._reex_btn = QPushButton("Re-extract")
        self._reex_btn.setObjectName("reextractBtn")
        self._reex_btn.setEnabled(False)
        self._reex_btn.clicked.connect(self._on_reextract_click)
        self._subfig_btn = QPushButton("+ Sub-fig")
        self._subfig_btn.setObjectName("subfigBtn")
        self._subfig_btn.setEnabled(False)
        self._subfig_btn.setToolTip(
            "Save the current crop as a new sub-figure file.\n"
            "The original figure is unchanged.\n"
            "Rename the new card to match sub-figure labels (a, b, c…)."
        )
        self._subfig_btn.clicked.connect(self._on_subfig_click)
        dpi_btn_row.addWidget(self._reset_btn)
        dpi_btn_row.addWidget(self._reex_btn)
        dpi_btn_row.addWidget(self._subfig_btn)
        crop_vbox.addLayout(dpi_btn_row)

        # Keyboard shortcut: Ctrl+Enter triggers re-extract
        # Note: Qt distinguishes Return vs Enter (numpad). Register both.
        self._reextract_sc_return = QShortcut(QKeySequence("Ctrl+Return"), self)
        self._reextract_sc_enter  = QShortcut(QKeySequence("Ctrl+Enter"), self)
        for sc in (self._reextract_sc_return, self._reextract_sc_enter):
            sc.setContext(Qt.ShortcutContext.WindowShortcut)
            sc.activated.connect(self._on_reextract_shortcut)

        scroll_vbox.addWidget(crop_frame)
        scroll_vbox.addStretch()

        info_scroll.setWidget(scroll_w)
        self._inner_splitter.addWidget(info_scroll)

        # Default split: 70 % image / 30 % info
        self._inner_splitter.setStretchFactor(0, 7)
        self._inner_splitter.setStretchFactor(1, 3)
        self._inner_splitter.setSizes([600, 260])

        # Refresh delta label when DPI changes
        self._reex_dpi_sb.valueChanged.connect(self._update_delta_label)

    # ---- Public API ----

    def show_figure(self, data: dict):
        self._current_data = data
        self._crop_widget.set_pixmap(QPixmap(data["path"]))
        self._fname_edit.setText(data["fname"])
        self._page_lbl.setText(str(data.get("page", "—")))
        self._dims_lbl.setText(data.get("dims", "—"))
        self._paper_lbl.setText(data.get("paper_name", "—"))
        cls  = data.get("classification", "UNKNOWN")
        conf = data.get("confidence", 0.0)
        color = {"GOOD": "#4ec9b0", "MARGINAL": "#d7ba7d", "REJECT": "#f48771"}.get(cls, "#858585")
        self._quality_lbl.setText(f"{cls}  {conf:.2f}" if conf else cls)
        self._quality_lbl.setStyleSheet(f"color: {color};")
        self._exp = {"top": 0.0, "bottom": 0.0, "left": 0.0, "right": 0.0}
        self._reex_dpi_sb.setValue(data.get("dpi", 200))
        self._update_delta_label()
        has_crop = bool(data.get("crop_rect"))
        self._reex_btn.setEnabled(has_crop)
        self._subfig_btn.setEnabled(has_crop)

    def clear(self):
        self._current_data = None
        self._crop_widget.clear()
        self._fname_edit.clear()
        for lbl in (self._page_lbl, self._dims_lbl, self._paper_lbl, self._quality_lbl):
            lbl.setText("—")
        self._quality_lbl.setStyleSheet("")
        self._exp = {"top": 0.0, "bottom": 0.0, "left": 0.0, "right": 0.0}
        self._reex_dpi_sb.setValue(200)
        self._update_delta_label()
        self._reex_btn.setEnabled(False)
        self._subfig_btn.setEnabled(False)

    def refresh_path(self, new_path: str, new_fname: str):
        """Update internal state after a rename."""
        if self._current_data:
            self._current_data["path"] = new_path
            self._current_data["fname"] = new_fname
        self._fname_edit.setText(new_fname)
        QPixmapCache.clear()
        self._crop_widget.set_pixmap(QPixmap(new_path))

    # ---- Private helpers ----

    def _on_rename(self):
        if not self._current_data:
            return
        new_fname = self._fname_edit.text().strip()
        if not new_fname:
            return
        if not new_fname.lower().endswith(".png"):
            new_fname += ".png"
            self._fname_edit.setText(new_fname)
        if new_fname == self._current_data["fname"]:
            return   # no change — avoid no-op rename
        self.rename_requested.emit(self._current_data["path"], new_fname)

    def update_after_reextract(self, new_dims: str, new_crop_rect: tuple):
        """Refresh panel after a successful re-extraction."""
        self._dims_lbl.setText(new_dims)
        if self._current_data:
            self._current_data["dims"]      = new_dims
            self._current_data["crop_rect"] = new_crop_rect
        # Deltas are relative to the new rect — reset to zero
        self._exp = {"top": 0.0, "bottom": 0.0, "left": 0.0, "right": 0.0}
        self._update_delta_label()
        # Force-reload the image (Qt caches pixmaps by path — must clear)
        QPixmapCache.clear()
        self._crop_widget.set_pixmap(QPixmap(self._current_data["path"]))
        # set_pixmap already calls clear_selection — no extra call needed

    def set_reextracting(self, active: bool):
        self._reex_btn.setEnabled(not active)
        self._reset_btn.setEnabled(not active)
        # Sub-fig button: restore enabled state based on whether data is loaded
        if not active and self._current_data:
            self._subfig_btn.setEnabled("crop_rect" in self._current_data)
        else:
            self._subfig_btn.setEnabled(False)

    def _on_edge_drag_started(self, edge: str):
        """Snapshot spinbox values at the start of an edge drag."""
        self._edge_drag_start_vals = {
            'top':    self._exp["top"],
            'bottom': self._exp["bottom"],
            'left':   self._exp["left"],
            'right':  self._exp["right"],
        }

    def _on_edge_drag_moved(self, edge: str, frac: float):
        """
        Update the relevant spinbox as the user drags an edge.

        `frac` is cumulative from the drag-start (positive = expanding outward).
        Delta in PDF points = frac × dimension_of_crop_rect_in_pts.
        """
        if not self._current_data or "crop_rect" not in self._current_data:
            return
        x0, y0, x1, y1 = self._current_data["crop_rect"]
        ref_pt   = (y1 - y0) if edge in ('top', 'bottom') else (x1 - x0)
        delta_pt = frac * ref_pt
        start_val = self._edge_drag_start_vals.get(edge, 0.0)
        self._exp[edge] = round(start_val + delta_pt, 1)
        self._update_delta_label()

    def _on_mouse_crop(self, x0_frac: float, y0_frac: float,
                       x1_frac: float, y1_frac: float):
        """
        Translate a normalised image selection into spinbox deltas (PDF points).

        The selection [x0_frac … x1_frac, y0_frac … y1_frac] describes what
        portion of the current crop_rect the user wants to keep.  Convert that
        to the signed expand_* values the re-extraction machinery expects:

            expand_top    = current_y0 - new_y0   (neg = trim top)
            expand_bottom = new_y1    - current_y1 (neg = trim bottom)
            expand_left   = current_x0 - new_x0   (neg = trim left)
            expand_right  = new_x1    - current_x1 (neg = trim right)
        """
        if not self._current_data or "crop_rect" not in self._current_data:
            return
        x0, y0, x1, y1 = self._current_data["crop_rect"]
        w_pt = x1 - x0
        h_pt = y1 - y0
        new_x0 = x0 + x0_frac * w_pt
        new_y0 = y0 + y0_frac * h_pt
        new_x1 = x0 + x1_frac * w_pt
        new_y1 = y0 + y1_frac * h_pt
        self._exp["top"] = round(y0 - new_y0, 1)
        self._exp["bottom"] = round(new_y1 - y1, 1)
        self._exp["left"] = round(x0 - new_x0, 1)
        self._exp["right"] = round(new_x1 - x1, 1)
        self._update_delta_label()

    def _on_crop_reset(self):
        self._exp = {"top": 0.0, "bottom": 0.0, "left": 0.0, "right": 0.0}
        if self._current_data:
            self._reex_dpi_sb.setValue(self._current_data.get("dpi", 200))
        self._update_delta_label()
        self._crop_widget.clear_selection()

    def _update_delta_label(self):
        dpi = self._reex_dpi_sb.value()
        t = self._exp["top"]
        b = self._exp["bottom"]
        l = self._exp["left"]
        r = self._exp["right"]
        # Show px equivalents (abs) to help judge magnitude quickly.
        tp = abs(t) * dpi / 72
        bp = abs(b) * dpi / 72
        lp = abs(l) * dpi / 72
        rp = abs(r) * dpi / 72
        self._delta_lbl.setText(
            f"Δ crop: T {t:.1f}pt({tp:.0f}px) | B {b:.1f}pt({bp:.0f}px) | "
            f"L {l:.1f}pt({lp:.0f}px) | R {r:.1f}pt({rp:.0f}px)"
        )

    def _on_reextract_click(self):
        if not self._current_data:
            return
        self.reextract_requested.emit(
            self._current_data,
            self._exp["top"],
            self._exp["bottom"],
            self._exp["left"],
            self._exp["right"],
            self._reex_dpi_sb.value(),
        )

    def _on_reextract_shortcut(self):
        # Keep shortcut safe: only act when a real, crop-able figure is selected.
        if self._reex_btn.isEnabled() and self._current_data and self._current_data.get("crop_rect"):
            self._reex_btn.click()

    def _on_subfig_click(self):
        if not self._current_data:
            return
        self.subfigure_requested.emit(
            self._current_data,
            self._exp["top"],
            self._exp["bottom"],
            self._exp["left"],
            self._exp["right"],
            self._reex_dpi_sb.value(),
        )


# ---------------------------------------------------------------------------
# FlowLayout  (Stage 3) — wrapping grid layout
# ---------------------------------------------------------------------------

class FlowLayout(QLayout):
    """Left-to-right wrapping layout; starts a new row when width is exceeded."""

    def __init__(self, parent=None, h_spacing: int = 8, v_spacing: int = 8):
        super().__init__(parent)
        self._items: list = []
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing

    # ---- QLayout ABC ----

    def addItem(self, item):
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), test=True)

    def setGeometry(self, rect: QRect):
        super().setGeometry(rect)
        self._do_layout(rect, test=False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect: QRect, test: bool) -> int:
        m = self.contentsMargins()
        effective = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x = effective.x()
        y = effective.y()
        row_height = 0

        for item in self._items:
            hint = item.sizeHint()
            w, h = hint.width(), hint.height()
            next_x = x + w + self._h_spacing
            if next_x - self._h_spacing > effective.right() and row_height > 0:
                x = effective.x()
                y += row_height + self._v_spacing
                next_x = x + w + self._h_spacing
                row_height = 0
            if not test:
                item.setGeometry(QRect(x, y, w, h))
            x = next_x
            row_height = max(row_height, h)

        return y + row_height - rect.y() + m.bottom()


# ---------------------------------------------------------------------------
# FigureCard  (Stage 3) — one thumbnail card
# ---------------------------------------------------------------------------

class FigureCard(QFrame):
    """
    A 170×200 card showing a figure thumbnail and filename label.

    Signals
    -------
    selected(self)  -- emitted when card body is left-clicked
    removed(self)   -- emitted when the [×] button is clicked
    """

    selected = pyqtSignal(object)
    removed  = pyqtSignal(object)

    _CARD_W    = 170
    _CARD_H    = 200
    _THUMB_SZ  = 150

    def __init__(self, data: dict, parent=None):
        super().__init__(parent)
        self.data = data
        self.setObjectName("figureCard")
        self.setFixedSize(self._CARD_W, self._CARD_H)
        self.setFrameShape(QFrame.Shape.Box)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Thumbnail
        self._thumb_label = QLabel()
        self._thumb_label.setFixedSize(self._THUMB_SZ, self._THUMB_SZ)
        self._thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb_label.setScaledContents(False)
        self._load_thumbnail(self.data["path"])
        layout.addWidget(self._thumb_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Filename label (elided)
        self._fname_label = QLabel()
        self._fname_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._fname_label.setWordWrap(False)
        self._set_elided_fname(self.data["fname"])
        layout.addWidget(self._fname_label)

        # Confidence score badge (Maxwell measurement layer)
        classification = self.data.get("classification", "UNKNOWN")
        confidence     = self.data.get("confidence", None)
        self._confidence_label = QLabel()
        self._confidence_label.setObjectName("confidenceLabel")
        self._confidence_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._confidence_label.setProperty("quality", classification)
        if confidence is None:
            self._confidence_label.setText("—")
        else:
            abbrev = {"GOOD": "GOOD", "MARGINAL": "MARG", "REJECT": "RJCT"}.get(
                classification, "?"
            )
            self._confidence_label.setText(f"{abbrev}  {confidence:.2f}")
        layout.addWidget(self._confidence_label)

        # Apply quality-based border on the card frame itself
        self.setProperty("quality", classification)

        # Remove button — absolute overlay, outside the layout
        self._remove_btn = QPushButton("×")
        self._remove_btn.setObjectName("removeCardBtn")
        self._remove_btn.setFixedSize(18, 18)
        self._remove_btn.setParent(self)
        self._remove_btn.move(self._CARD_W - 22, 4)
        self._remove_btn.clicked.connect(lambda: self.removed.emit(self))
        self._remove_btn.raise_()

        # Sub-figure badge — amber strip across bottom of thumbnail, hidden until used
        _badge_h = 20
        self._subfig_badge = QLabel()
        self._subfig_badge.setObjectName("subfigBadge")
        self._subfig_badge.setParent(self)
        self._subfig_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._subfig_badge.resize(self._CARD_W - 8, _badge_h)
        self._subfig_badge.move(4, 4 + self._THUMB_SZ - _badge_h)
        self._subfig_badge.setVisible(False)
        self._subfig_badge.raise_()

    # ---- Helpers ----

    def _load_thumbnail(self, path: str):
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            pixmap = pixmap.scaled(
                self._THUMB_SZ, self._THUMB_SZ,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._thumb_label.setPixmap(pixmap)
        else:
            self._thumb_label.setText("(no image)")

    def _set_elided_fname(self, fname: str):
        fm = QFontMetrics(self._fname_label.font())
        elided = fm.elidedText(fname, Qt.TextElideMode.ElideRight, self._CARD_W - 16)
        self._fname_label.setText(elided)

    # ---- Public API ----

    def set_selected(self, selected: bool):
        self.setProperty("selected", "true" if selected else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def update_label(self, new_fname: str):
        self.data["fname"] = new_fname
        self._set_elided_fname(new_fname)

    def update_thumbnail(self, new_path: str):
        self.data["path"] = new_path
        self._load_thumbnail(new_path)

    def mark_has_subfigs(self, count: int):
        """Show / update the amber badge that indicates sub-figures were saved."""
        if count > 0:
            noun = "sub-fig" if count == 1 else "sub-figs"
            self._subfig_badge.setText(f"↓  {count} {noun} saved")
            self._subfig_badge.setVisible(True)
            self._subfig_badge.raise_()
        else:
            self._subfig_badge.setVisible(False)

    # ---- Events ----

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self)
        super().mousePressEvent(event)


# ---------------------------------------------------------------------------
# ThumbnailGallery  (Stage 3) — scrollable grid of FigureCard widgets
# ---------------------------------------------------------------------------

class ThumbnailGallery(QWidget):
    """Left splitter pane — scrollable FlowLayout of FigureCard widgets."""

    card_selected = pyqtSignal(dict)   # emits FigureData when a card is clicked

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: list[FigureCard] = []
        self._selected: FigureCard | None = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(6)

        self._header = QLabel("Extracted Figures  (0)")
        self._header.setObjectName("sectionLabel")
        root.addWidget(self._header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self._inner = QWidget()
        self._flow_layout = FlowLayout(self._inner)
        self._inner.setLayout(self._flow_layout)
        scroll.setWidget(self._inner)

        root.addWidget(scroll, stretch=1)

    # ---- Public API ----

    def add_card(self, data: dict):
        card = FigureCard(data)
        card.selected.connect(self._on_card_selected)
        card.removed.connect(self._on_card_removed)
        self._cards.append(card)
        self._flow_layout.addWidget(card)
        self._update_header()

    def clear_all(self):
        for card in self._cards:
            self._flow_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()
        self._selected = None
        self._update_header()

    @property
    def selected_card(self) -> "FigureCard | None":
        return self._selected

    # ---- Internal slots ----

    def _on_card_selected(self, card: FigureCard):
        if self._selected is not None and self._selected is not card:
            self._selected.set_selected(False)
        self._selected = card
        card.set_selected(True)
        self.card_selected.emit(card.data)

    def _on_card_removed(self, card: FigureCard):
        if card in self._cards:
            self._cards.remove(card)
        if self._selected is card:
            self._selected = None
        self._flow_layout.removeWidget(card)
        card.deleteLater()
        self._update_header()

    def _update_header(self):
        self._header.setText(f"Extracted Figures  ({len(self._cards)})")


# ---------------------------------------------------------------------------
# MainWindow  (Stage 1 + Stage 2 additions)
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    """Root application window — 1200 × 800, dark theme."""

    def __init__(self):
        super().__init__()
        self._worker: ExtractionWorker | None = None
        self._figures_extracted = 0
        self._selected_card: FigureCard | None = None
        self._sf_worker: SingleFigureWorker | None = None
        self._subfig_worker: SubFigureWorker | None = None
        self._subfig_counts: dict[str, int] = {}     # parent_path → count extracted
        self._ctx_worker: ContextWorker | None = None
        self._last_jobs: list = []                    # [(pdf_path, paper_num)]
        self._last_output_dir: Path | None = None
        self._figures_by_paper: dict[int, list] = {}  # paper_num → [fig_dict]
        self._build_ui()

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        self.setWindowTitle("PDF Figure Extractor")
        self.resize(1440, 900)
        self.setMinimumSize(1000, 680)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # Control panel
        self.control_panel = ControlPanel()
        self.control_panel.queue_changed.connect(self._on_queue_changed)
        main_layout.addWidget(self.control_panel)

        # Separator
        sep = QFrame()
        sep.setObjectName("hLine")
        sep.setFrameShape(QFrame.Shape.HLine)
        main_layout.addWidget(sep)

        # Extract button + Stop button row
        action_row = QHBoxLayout()
        action_row.setSpacing(8)

        self.extract_btn = QPushButton("EXTRACT FIGURES")
        self.extract_btn.setObjectName("extractBtn")
        self.extract_btn.setEnabled(False)
        self.extract_btn.clicked.connect(self._on_extract)

        self.stop_btn = QPushButton("■  Stop")
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.setFixedWidth(100)
        self.stop_btn.setVisible(False)
        self.stop_btn.clicked.connect(self._on_stop)

        action_row.addWidget(self.extract_btn, stretch=1)
        action_row.addWidget(self.stop_btn)
        main_layout.addLayout(action_row)

        # Generate Context Files button (enabled after extraction)
        self.ctx_btn = QPushButton("Generate Context Files")
        self.ctx_btn.setObjectName("ctxBtn")
        self.ctx_btn.setEnabled(False)
        self.ctx_btn.setToolTip(
            "Write one P{N}_context.md per paper into the output folder.\n"
            "Feed that file + the PNG images to Claude to generate Feynman tutorials."
        )
        self.ctx_btn.clicked.connect(self._on_generate_context)
        main_layout.addWidget(self.ctx_btn)

        # Progress bar (hidden until extraction starts)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%v / %m figures")
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        # Splitter: thumbnail gallery (left) | preview panel (right)
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(4)

        self.thumbnail_gallery = ThumbnailGallery()
        self.thumbnail_gallery.card_selected.connect(self._on_card_selected)
        self._right_panel = PreviewPanel()
        self._right_panel.rename_requested.connect(self._on_rename_requested)
        self._right_panel.reextract_requested.connect(self._on_reextract_requested)
        self._right_panel.subfigure_requested.connect(self._on_subfigure_requested)

        self._splitter.addWidget(self.thumbnail_gallery)
        self._splitter.addWidget(self._right_panel)
        self._splitter.setSizes([360, 1080])
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)

        main_layout.addWidget(self._splitter, stretch=1)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready  —  add PDFs to begin")

    # ------------------------------------------------------------------
    # Queue change
    # ------------------------------------------------------------------

    def _on_queue_changed(self, count: int):
        """Enable Extract only when there are files and no active worker."""
        self.extract_btn.setEnabled(count > 0 and self._worker is None)

    def _on_card_selected(self, data: dict):
        self._selected_card = self.thumbnail_gallery.selected_card
        self._right_panel.show_figure(data)

    def _on_rename_requested(self, old_path: str, new_fname: str):
        from pathlib import Path
        old = Path(old_path)
        new = old.parent / new_fname
        if new.exists():
            QMessageBox.warning(self, "Rename", f'"{new_fname}" already exists in that folder.')
            self._right_panel.refresh_path(old_path, old.name)   # restore field
            return
        try:
            old.rename(new)
        except OSError as exc:
            QMessageBox.warning(self, "Rename failed", str(exc))
            self._right_panel.refresh_path(old_path, old.name)
            return
        new_path = str(new)
        if self._selected_card:
            self._selected_card.update_label(new_fname)
            self._selected_card.update_thumbnail(new_path)
        self._right_panel.refresh_path(new_path, new_fname)

    # ------------------------------------------------------------------
    # Single-figure re-extraction  (Stage 5)
    # ------------------------------------------------------------------

    def _on_reextract_requested(self, data, exp_top, exp_bot, exp_lft, exp_rgt, dpi):
        if self._sf_worker and self._sf_worker.isRunning():
            return
        self._right_panel.set_reextracting(True)
        self.status_bar.showMessage("Re-extracting figure…")
        self._sf_worker = SingleFigureWorker(
            data, exp_top, exp_bot, exp_lft, exp_rgt, dpi
        )
        self._sf_worker.done.connect(self._on_sf_done)
        self._sf_worker.failed.connect(self._on_sf_failed)
        self._sf_worker.start()

    def _on_sf_done(self, new_dims: str, new_rect):
        if self._selected_card and self._right_panel._current_data:
            QPixmapCache.clear()
            self._selected_card.update_thumbnail(
                self._right_panel._current_data["path"]
            )
        self._right_panel.update_after_reextract(new_dims, new_rect)
        self._right_panel.set_reextracting(False)
        self.status_bar.showMessage(f"Re-extracted  —  {new_dims} px")
        self._sf_worker = None

    def _on_sf_failed(self, message: str):
        self._right_panel.set_reextracting(False)
        QMessageBox.warning(self, "Re-extraction failed", message)
        self.status_bar.showMessage("Re-extraction failed")
        self._sf_worker = None

    # ------------------------------------------------------------------
    # Sub-figure extraction  (Stage 8)
    # ------------------------------------------------------------------

    def _on_subfigure_requested(self, data, exp_top, exp_bot, exp_lft, exp_rgt, dpi):
        if self._subfig_worker and self._subfig_worker.isRunning():
            return
        # Auto-name: P1_Fig3_page05.png → P1_Fig3_page05_s1.png, _s2, …
        parent_path = Path(data["path"])
        count = self._subfig_counts.get(data["path"], 0) + 1
        self._subfig_counts[data["path"]] = count
        new_name = f"{parent_path.stem}_s{count}{parent_path.suffix}"
        out_path  = str(_make_unique_path(parent_path.parent, new_name))

        self._right_panel.set_reextracting(True)
        self.status_bar.showMessage(f"Saving sub-figure {count}…")
        self._subfig_worker = SubFigureWorker(
            data, exp_top, exp_bot, exp_lft, exp_rgt, dpi, out_path
        )
        self._subfig_worker.done.connect(self._on_subfig_card_done)
        self._subfig_worker.failed.connect(self._on_subfig_card_failed)
        self._subfig_worker.start()

    def _on_subfig_card_done(self, new_data: dict):
        self._right_panel.set_reextracting(False)
        # Update parent card's visual badge before adding the new card
        if self._selected_card:
            parent_path = self._selected_card.data["path"]
            count = self._subfig_counts.get(parent_path, 0)
            self._selected_card.mark_has_subfigs(count)
        self.thumbnail_gallery.add_card(new_data)
        self._figures_by_paper.setdefault(new_data["paper_num"], []).append(new_data)
        self.status_bar.showMessage(
            f"Sub-figure saved  —  {new_data['fname']}  ({new_data['dims']} px)"
            "  —  rename the card to label it (a, b, c…)"
        )
        self._subfig_worker = None

    def _on_subfig_card_failed(self, message: str):
        self._right_panel.set_reextracting(False)
        QMessageBox.warning(self, "Sub-figure extraction failed", message)
        self.status_bar.showMessage("Sub-figure extraction failed")
        self._subfig_worker = None

    # ------------------------------------------------------------------
    # Extraction
    # ------------------------------------------------------------------

    def _on_extract(self):
        entries = self.control_panel.queued_entries()
        if not entries:
            return

        output_dir = self.control_panel.output_dir()
        dpi        = self.control_panel.dpi()
        min_size   = self.control_panel.min_size()
        page_range = self.control_panel.page_range()
        page_text  = self.control_panel.page_range_text()

        # Jobs use user-defined short codes — queue order is preserved
        jobs = [(p, code) for p, code in entries]

        # Save for context generation
        self._last_jobs       = jobs
        self._last_output_dir = output_dir
        self._figures_by_paper.clear()
        self.ctx_btn.setEnabled(False)

        self.thumbnail_gallery.clear_all()
        self._selected_card = None
        self._right_panel.clear()
        self._figures_extracted = 0
        self._set_extracting(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Scanning… %v / %m")
        self.status_bar.showMessage(
            (
                f"Extracting from {len(jobs)} PDF(s)  →  {output_dir}"
                if page_text == "all pages"
                else f"Extracting from {len(jobs)} PDF(s)  →  {output_dir}  ({page_text})"
            )
        )

        self._worker = ExtractionWorker(jobs, output_dir, dpi, min_size, page_range=page_range)
        self._worker.progress.connect(self._on_progress)
        self._worker.figure_ready.connect(self._on_figure_ready)
        self._worker.log.connect(self._on_worker_log)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.error.connect(self._on_worker_error)
        self._worker.start()

    def _on_stop(self):
        if self._worker and self._worker.isRunning():
            self._worker.requestInterruption()
            self.stop_btn.setEnabled(False)
            self.status_bar.showMessage("Stopping after current figure…")

    # ------------------------------------------------------------------
    # Worker signal handlers
    # ------------------------------------------------------------------

    def _on_progress(self, current: int, total: int):
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(current)
        self.progress_bar.setFormat(f"%v / %m figures")

    def _on_figure_ready(self, data: dict):
        self._figures_extracted += 1
        self._figures_by_paper.setdefault(data["paper_num"], []).append(data)
        self.status_bar.showMessage(
            f"Saved  {data['fname']}  "
            f"({data['dims']} px)  —  "
            f"{self._figures_extracted} figure(s) extracted so far"
        )
        self.thumbnail_gallery.add_card(data)

    def _on_worker_log(self, message: str):
        # Warnings and skips visible in status bar only if no figure is in flight
        if "WARN" in message or "skip" in message:
            self.status_bar.showMessage(message)

    def _on_worker_finished(self):
        self._set_extracting(False)
        n = self._figures_extracted
        out = self.control_panel.output_dir()
        self.status_bar.showMessage(
            f"Done  —  {n} figure(s) extracted  →  {out}"
        )
        self.progress_bar.setFormat(f"Done  —  {n} figure(s)")
        self._worker = None
        if n > 0:
            self.ctx_btn.setEnabled(True)

    def _on_worker_error(self, message: str):
        self._set_extracting(False)
        self._worker = None
        QMessageBox.critical(self, "Extraction Error", message)
        self.status_bar.showMessage("Error — see dialog")

    # ------------------------------------------------------------------
    # Context-file generation  (Stage 7)
    # ------------------------------------------------------------------

    def _on_generate_context(self):
        if self._ctx_worker and self._ctx_worker.isRunning():
            return
        if not self._last_jobs or not self._figures_by_paper:
            QMessageBox.information(
                self, "No data",
                "Extract figures first, then generate context files."
            )
            return
        self.ctx_btn.setEnabled(False)
        self.ctx_btn.setText("Generating…")
        self.status_bar.showMessage(
            f"Writing context files for {len(self._last_jobs)} paper(s)…"
        )
        # Context generation is only meaningful for caption-based figure extracts.
        figs_caption_only = {
            k: [d for d in v if d.get("source") == "caption"]
            for k, v in self._figures_by_paper.items()
        }
        self._ctx_worker = ContextWorker(
            self._last_jobs,
            figs_caption_only,
            self._last_output_dir,
        )
        self._ctx_worker.progress.connect(self._on_ctx_progress)
        self._ctx_worker.file_done.connect(self._on_ctx_file_done)
        self._ctx_worker.log.connect(self._on_worker_log)   # reuse log handler
        self._ctx_worker.finished.connect(self._on_ctx_finished)
        self._ctx_worker.start()

    def _on_ctx_progress(self, current: int, total: int):
        self.status_bar.showMessage(
            f"Context files: {current} / {total} paper(s) done…"
        )

    def _on_ctx_file_done(self, path_str: str):
        fname = Path(path_str).name
        self.status_bar.showMessage(f"Written: {fname}")

    def _on_ctx_finished(self):
        n     = len(self._last_jobs)
        out   = self._last_output_dir
        self.status_bar.showMessage(
            f"Done  —  {n} context file(s) written  →  {out}"
        )
        self.ctx_btn.setText("Generate Context Files")
        self.ctx_btn.setEnabled(True)
        self._ctx_worker = None
        QMessageBox.information(
            self,
            "Context files ready",
            f"{n} context file(s) written to:\n{out}\n\n"
            "Attach the P*_context.md files + PNG images to a Claude conversation\n"
            "and ask it to generate Feynman-style tutorials.",
        )

    # ------------------------------------------------------------------
    # UI state helpers
    # ------------------------------------------------------------------

    def _set_extracting(self, active: bool):
        """Toggle the UI between idle and extracting states."""
        self.extract_btn.setVisible(not active)
        self.stop_btn.setVisible(active)
        self.stop_btn.setEnabled(active)
        self.progress_bar.setVisible(active)
        self.control_panel.set_controls_enabled(not active)
        if active:
            self.ctx_btn.setEnabled(False)
        else:
            # Restore extract button state based on queue
            self.extract_btn.setEnabled(
                len(self.control_panel.queued_paths()) > 0
            )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    font = QFont("Consolas", 11)
    app.setFont(font)

    app.setStyleSheet(DARK_STYLE)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
