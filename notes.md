## Status
- [x] Stage 1: MainWindow skeleton + ControlPanel
- [x] Stage 2: ExtractionWorker (QThread) + extraction logic
- [x] Stage 3: ThumbnailGallery + FigureCard
- [x] Stage 4: PreviewPanel + inline rename
- [ ] Stage 5: Manual Crop Correction + Single-Figure Re-extraction
- [ ] Stage 6: Testing and polish

---

## Session Log — 2026-02-28

### Bug Fixes (figure_extractor_app.py — extraction utilities)

**Bug 1 — Image rect inflated past caption (PRIMARY)**
- `_find_figure_rect`: each image rect is now clipped to `search_zone`
  (`r_clipped = r & search_zone`) before being unioned into `fig_rect`.
- Prevents caption text + body paragraphs bleeding into the crop.

**Bug 2 — Max search height too short for tall figures**
- Default `max_search_height` raised 500 → 800 px.

**Bug 3 — Vector drawing tolerance too tight**
- Drawing gap tolerance widened +2 → +8 pt.
- Drawings also clipped to `search_zone` (same pattern as Bug 1).

**Bug 4 — Search zone overlapped preceding figure on same page**
- `_find_figure_rect` now accepts `page_captions: dict` (all captions on the page).
- `preceding_cap_y1` computed as bottom edge of nearest caption above current one;
  used as hard upper bound for `search_top`.
- `ExtractionWorker.run()` builds `page_caption_map` during the scan pass and
  passes `this_page_captions` into every `_find_figure_rect` call.

**Bug 5 — Caption regex matched in-text references**
- `_find_captions_on_page`: added `if text.count('\n') > 4: continue` to skip
  paragraph blocks that happen to start with "Fig. N".

**Safety Net — Residual paragraph contamination**
- New helper `_find_text_paragraphs_in_rect(page, rect, zone_width)`: returns
  text blocks inside `fig_rect` whose width >= 60% of the column width.
- After building `fig_rect`, if any wide text blocks are found inside it,
  `fig_rect.y1` is clipped to stop just above the topmost one.

---

### Maxwell Quality Layer (new file: figure_quality.py)

Principle: every extracted figure is evaluated against measurable quantities;
the algorithm can see its own outputs, measure them, and suggest adjustments.

**`FigureQualityStandard` (dataclass)**
Tunable thresholds defining a good extraction:
- `min/max_aspect_ratio`, `min/max_fill_ratio`
- `min_edge_sharpness`, `max_white_border_fraction`
- `max_text_contamination`, `min_pixel_intensity_std`
- `min_confidence_score` (0.65 = GOOD), `marginal_confidence_score` (0.35)

**`FigureMetrics` (dataclass)**
One record per extracted PNG:
- Geometric: `aspect_ratio`, `fill_ratio`, `edge_sharpness`
- Content: `white_border_fraction`, `text_contamination_ratio`, `pixel_intensity_std`
- Derived: `confidence_score`, `classification` (GOOD/MARGINAL/REJECT/UNKNOWN),
  `reason`, `suggested_adjustments`

**`QualityEvaluator`**
- `measure(image_path, *, fig_num, page, paper_num) → FigureMetrics`
  Loads PNG (Pillow), computes all 6 metrics (numpy), scores, classifies.
- `evaluate(metrics) → (classification, reason)`
- `suggest_adjustment(metrics) → dict`
  Maps each failure mode to a concrete extraction parameter change:
  `expand_box`, `shrink_y1`, `increase_dpi`, `check_merged_figures`, `likely_blank`.
- `log_session(pdf_name, all_metrics, output_dir) → Path`
  Writes `<pdf-stem>_metrics.json`: standards used, per-figure measurements,
  summary (total / good / marginal / reject / mean & min confidence).

**Measurement helpers (pure functions, no scipy)**
- `_aspect_ratio` — width / height
- `_fill_ratio` — non-white-pixel fraction (threshold: all channels >= 240)
- `_edge_sharpness` — variance of discrete Laplacian (numpy slicing, no scipy)
- `_white_border_fraction` — mean white fraction across 4 border bands (10 px each)
- `_text_contamination` — horizontal projection heuristic; rows with 3–45% dark
  pixel density counted as text-like

**Threshold Calibration — 2026-02-28**
Tested against `Auxiliary_Resonant_Commutated_Pole_Inverter_ARCPI_Operation_Using_online_voltage_measurements.pdf` (15 figures).
- `max_text_contamination` raised **0.40 → 0.80**
- Root cause: the horizontal projection heuristic cannot distinguish circuit/
  waveform axis labels from body-paragraph text. Clean figures scored up to
  0.78 (axis ticks, signal trace labels). Threshold 0.40 caused false-positive
  MARGINAL flags on every waveform/circuit figure.
- At 0.80: 15/15 GOOD, 0 MARGINAL, 0 REJECT. Mean confidence 0.88.
- Body-paragraph bleed-in is better caught by the fill_ratio penalty (low
  fill = mostly blank crop) and the `_find_text_paragraphs_in_rect` safety
  net inside `_find_figure_rect`, not by post-extraction text_contamination.
- Verified: Fig.4 and Fig.5 (both page 3, stacked) extract as separate clean
  crops — Bug 4 fix confirmed working.

---

### Pixel Whitespace-Gap Algorithm (replaces metadata approach)

**Motivation:** Metadata approach (get_images + get_drawings) was unreliable —
image rects span full PDF object bounds, not visual bounds; vector drawings were
missed when tolerances were tight. Replaced entirely with pixel-based detection.

**Algorithm (`_find_figure_rect`):**
1. Render the column strip above the caption to greyscale pixels at 150 DPI.
2. Compute dark-pixel fraction per row (horizontal projection).
3. Scan upward from caption bottom → find last row with content (`fig_bottom`).
4. Continue upward until `_GAP_MIN_PT` (15pt) consecutive whitespace rows → `fig_top`.
5. Convert pixel row indices back to PDF point coordinates; pad 4pt each side.

**Constants:** `_ANALYSIS_DPI=150`, `_DARK_THRESH=230`, `_CONTENT_FRAC=0.003`,
`_GAP_MIN_PT=15`

**Bug 6 — Two-column layout: cross-column ceiling contamination**
- Problem: Fig.7 (left column, y1=361) was used as `preceding_cap_y1` for
  Fig.8 (right column, y0=385), giving only 23pt of search zone → Fig.8
  truncated to just the x-axis bottom row.
- Fix: added x-range overlap check to `preceding_cap_y1` computation:
  ```python
  and r.x1 > col_x0 and r.x0 < col_x1  # must overlap our column
  ```
- Result: **15/15 GOOD**, mean confidence 0.90, Fig.8 now 723×573px (full plot).

**Final verified result (pixel approach, ARCPI paper, 15 figures):**
```
Fig. 1 p01   723x 331px  [GOOD 0.90]
Fig. 2 p01   746x 434px  [GOOD 0.90]
...
Fig. 8 p04   723x 573px  [GOOD 0.90]  ← was truncated, now full
...
Fig.15 p06   728x 830px  [GOOD 0.90]
15/15 GOOD, 0 MARGINAL, 0 REJECT, mean confidence 0.90
```

---

### GUI Integration (figure_extractor_app.py)

**Imports**
- `from figure_quality import ...` wrapped in `try/except ImportError`
  → `_QUALITY_AVAILABLE` flag; app still runs if deps missing.

**DARK_STYLE additions**
- `QFrame#figureCard[quality="MARGINAL"]` — amber border (#d7ba7d)
- `QFrame#figureCard[quality="REJECT"]` — red border (#f48771)
- `QFrame#figureCard[selected="true"]` placed AFTER quality rules so
  blue selection border always wins.
- `QLabel#confidenceLabel` — 10 px, color-coded per quality classification.

**ExtractionWorker**
- `self._evaluator = QualityEvaluator() if _QUALITY_AVAILABLE else None`
- Per-PDF `pdf_metrics: list = []` reset at start of each job.
- After `pix.save()`: `self._evaluator.measure(out_path, ...)` called;
  `confidence` and `classification` added to `figure_ready` signal dict.
- Log line extended: `[GOOD 0.87]` suffix on every saved-figure message.
- After `doc.close()`: `log_session()` writes `<stem>_metrics.json`.

**FigureCard**
- Confidence badge label (`QLabel#confidenceLabel`) added below filename:
  `GOOD 0.87` / `MARG 0.52` / `RJCT 0.21` / `—` (if no measurement).
- Card frame gets `quality` property → CSS border activates automatically.
- Gracefully handles missing `confidence`/`classification` keys in `data`.

---

## Decisions Made
- Single file app (figure_extractor_app.py, ~1200 lines)
- PyQt6 chosen over Electron and CustomTkinter
- Unique filename collision: add _1, _2 suffix
- Paper numbering: sorted alphabetically P1, P2...
- Quality module in separate file (figure_quality.py) — keeps extraction
  utilities and measurement layer independently testable
- numpy + Pillow for pixel analysis; no scipy dependency
- Quality measurement is non-blocking: failures are logged as WARN,
  never abort the extraction of the figure itself

---

---

## Stage 5 Plan — Manual Crop Correction + Single-Figure Re-extraction

### Goal
After automatic extraction, individual figures may have wrong crops (top cut off,
caption bleeds in, sides too tight, image blurry). Stage 5 lets the user select a
figure card, adjust the crop window using numeric controls, and re-extract just
that one figure without reprocessing the whole PDF.

---

### Background: how the crop window works

`_find_figure_rect(page, caption_rect, ...)` returns a `fitz.Rect(x0, y0, x1, y1)`
in **PDF points** (1 pt = 1/72 inch, origin top-left of page).
- x0 = left edge, x1 = right edge (increase x1 or decrease x0 to widen)
- y0 = top edge, y1 = bottom edge (decrease y0 to show more above; increase y1 to show more below)

This rect is passed directly to `page.get_pixmap(clip=fig_rect, matrix=mat)`.
The `mat` scales by `dpi / 72` so the output pixel size = pt_size × dpi / 72.

---

### Adjustment variables (all in PDF points, signed)

| Variable | Meaning | Applied as |
|---|---|---|
| `expand_top` | Positive → pull top edge UP (show more above). Negative → trim top. | `new_y0 = crop_y0 - expand_top` |
| `expand_bottom` | Positive → pull bottom edge DOWN (show more below). Negative → trim bottom (e.g. cut out caption bleed). | `new_y1 = crop_y1 + expand_bottom` |
| `expand_left` | Positive → pull left edge LEFT (wider left margin). Negative → trim left. | `new_x0 = crop_x0 - expand_left` |
| `expand_right` | Positive → pull right edge RIGHT (wider right margin). Negative → trim right. | `new_x1 = crop_x1 + expand_right` |
| `dpi_override` | Re-render at this DPI instead of the original. Use to get a sharper/larger image. Default = original dpi. | replaces `mat` in `get_pixmap` |

Convention: all variables default to 0 (no change). Positive = expand outward.
Negative = trim inward. Applied after clamping to page bounds.

Suggested UI range: −200 pt to +200 pt in steps of 2 pt (covers ~2.75 inches each direction).
Equivalent pixel reference displayed alongside: `pixels ≈ pts × dpi / 72`.

---

### Data dict additions required (ExtractionWorker.figure_ready signal)

The following keys must be added to the dict emitted by `figure_ready` so that
re-extraction has everything it needs without re-scanning the PDF:

```python
"pdf_path"  : str(pdf_path),          # absolute path to source PDF
"page_num"  : page_num,               # 0-indexed page (int), for fitz doc[page_num]
"crop_rect" : (fig_rect.x0, fig_rect.y0, fig_rect.x1, fig_rect.y1),  # PDF points
"dpi"       : self._dpi,              # DPI used for the original render
```

`page` (1-indexed, str display) already exists. `page_num` (0-indexed) is the new key.

---

### Re-extraction algorithm (`_reextract_figure`)

Standalone function (not a method), callable from main thread or worker:

```python
def _reextract_figure(
    data: dict,
    expand_top: float, expand_bottom: float,
    expand_left: float, expand_right: float,
    dpi_override: int | None = None,
) -> tuple[str, str]:
    """
    Re-render one figure with adjusted crop. Overwrites the existing PNG.
    Returns (new_dims_str, classification).
    Raises OSError / fitz.FileNotFoundError on failure.
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
    new_rect = new_rect.intersect(page.rect)   # clamp to page
    dpi = dpi_override or data["dpi"]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, clip=new_rect, alpha=False)
    doc.close()
    pix.save(data["path"])                     # overwrite same file
    return f"{pix.width} x {pix.height}", new_rect
```

After calling this, update `data["crop_rect"]` to the new rect's coordinates so
subsequent re-extractions are relative to the adjusted crop, not the original.

---

### Threading model

Re-extraction of a single figure renders one page → typically < 0.3 s.
Run in a lightweight `QThread` (`SingleFigureWorker`) to avoid blocking the UI,
emitting `done(dims, new_rect_tuple)` or `failed(message)` signals.

---

### UI additions (PreviewPanel)

Add a collapsible "Crop Correction" section below the metadata frame:

```
┌─ Crop Correction ─────────────────────────────────┐
│  Expand top    [ ±  0 pt]   ≈   0 px @ 200 dpi   │
│  Expand bottom [ ±  0 pt]   ≈   0 px @ 200 dpi   │
│  Expand left   [ ±  0 pt]   ≈   0 px @ 200 dpi   │
│  Expand right  [ ±  0 pt]   ≈   0 px @ 200 dpi   │
│  DPI           [  200    ]                         │
│              [Reset]  [Re-extract]                 │
└───────────────────────────────────────────────────┘
```

Controls:
- 4 `QDoubleSpinBox` widgets, range −200 to +200, step 2, suffix " pt"
- 1 `QSpinBox` for DPI, range 72–600, step 50, default = data["dpi"]
- Pixel equivalent label next to each spinbox (auto-updates on value change)
- **Re-extract** button → runs `SingleFigureWorker`; button disabled during run
- **Reset** button → zeros all spinboxes and restores DPI to original
- Section hidden (or greyed out) when no card is selected

---

### Files that change

| File | Change |
|---|---|
| `figure_extractor_app.py` | Add `pdf_path`, `page_num`, `crop_rect`, `dpi` to `figure_ready` dict; add `_reextract_figure()` function; add `SingleFigureWorker(QThread)`; extend `PreviewPanel` with Crop Correction section and `update_after_reextract()` method; wire `MainWindow._on_reextract_requested()` |
| `notes.md` | This document |

`figure_quality.py` does not change — `QualityEvaluator.measure()` is called again
on the new PNG path after re-extraction, exactly as during initial extraction.

---

### Common use-case examples

| What user sees | Control to adjust | Value |
|---|---|---|
| Top of waveform cut off | expand_top | +20 to +40 pt |
| Caption text visible inside crop | expand_bottom | −10 to −20 pt |
| Figure bleeds into next figure below | expand_bottom | −15 pt |
| Narrow side margins clipping axis labels | expand_left / expand_right | +6 to +12 pt |
| Image pixelated / too small | dpi_override | 300 or 400 |
