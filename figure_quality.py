"""
figure_quality.py
Maxwell-inspired measurable quality layer for PDF figure extraction.

Principle (Maxwell, 1871):
    "The most important aspect of any phenomena from a mathematical point
    of view is that of a measurable quantity — describing the methods of
    measurement and defining the standards on which they depend."

Applied here: every extracted figure is evaluated against measurable quality
criteria.  The QualityEvaluator can 'see' its own outputs, measure them,
and suggest extraction parameter adjustments to improve quality — not just
run blindly.

Dependencies: numpy, Pillow (pip install numpy pillow)
If these are unavailable the module still imports; measure() returns an
UNKNOWN classification so the rest of the app is unaffected.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

try:
    import numpy as np
    from PIL import Image
    _DEPS_OK = True
    _DEPS_ERR = ""
except ImportError as _e:
    _DEPS_OK = False
    _DEPS_ERR = str(_e)


# ---------------------------------------------------------------------------
# Standards — "the standards on which measurements depend" (Maxwell)
# ---------------------------------------------------------------------------

@dataclass
class FigureQualityStandard:
    """
    Threshold values that define a good figure extraction.
    These are the 'standards' Maxwell refers to — tunable per document type.
    """
    # Geometric bounds
    min_aspect_ratio: float = 0.3    # too narrow → bad crop
    max_aspect_ratio: float = 4.0    # too wide  → bad crop or merged figures
    min_fill_ratio: float = 0.05     # too empty → blank region captured
    max_fill_ratio: float = 0.95     # too dense → text bleed / solid block

    # Content quality
    min_edge_sharpness: float = 50.0        # variance of Laplacian; low → blank / blurry
    max_white_border_fraction: float = 0.30 # large white margins → over-padded
    max_text_contamination: float = 0.80    # fraction of rows with text-like ink density
                                            # Calibrated against ARCPI paper: clean circuit/
                                            # waveform figures score up to 0.78 due to axis
                                            # labels and signal traces matching the heuristic.
                                            # Body-paragraph bleed-in is better caught by the
                                            # fill_ratio + safety-net clip in _find_figure_rect.
    min_pixel_intensity_std: float = 10.0   # near-zero → uniform / blank region

    # Classification thresholds
    min_confidence_score: float = 0.65      # >= GOOD
    marginal_confidence_score: float = 0.35 # >= MARGINAL, < GOOD; below = REJECT


# ---------------------------------------------------------------------------
# Metrics — the measurable quantities for one extracted figure
# ---------------------------------------------------------------------------

@dataclass
class FigureMetrics:
    """All measurable quantities for one extracted figure PNG."""

    # Identity
    path: str = ""
    fig_num: int = 0
    page: int = 0
    paper_num: int = 0

    # GEOMETRIC MEASUREMENTS
    aspect_ratio: float = 0.0           # width / height
    fill_ratio: float = 0.0             # non-white pixels / total pixels
    edge_sharpness: float = 0.0         # variance of discrete Laplacian

    # CONTENT MEASUREMENTS
    white_border_fraction: float = 0.0  # mean white fraction across 4 border bands
    text_contamination_ratio: float = 0.0  # fraction of rows with text-like ink density
    pixel_intensity_std: float = 0.0    # std dev of greyscale intensity

    # DERIVED
    confidence_score: float = 0.0       # 0.0 – 1.0  (1.0 = perfect extraction)
    classification: str = "UNKNOWN"     # GOOD | MARGINAL | REJECT | UNKNOWN
    reason: str = ""                    # human-readable failure explanation

    # SELF-IMPROVEMENT FEEDBACK
    suggested_adjustments: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# QualityEvaluator
# ---------------------------------------------------------------------------

class QualityEvaluator:
    """
    Measures, classifies, and suggests adjustments for extracted figures.

    Usage
    -----
    ev = QualityEvaluator()
    m  = ev.measure("P1_Fig5_page03.png", fig_num=5, page=3, paper_num=1)
    print(m.classification, f"{m.confidence_score:.2f}", m.reason)
    ev.log_session("paper.pdf", [m, ...], output_dir)
    """

    def __init__(self, standard: FigureQualityStandard | None = None):
        self._std = standard or FigureQualityStandard()

    @property
    def standard(self) -> FigureQualityStandard:
        return self._std

    # ------------------------------------------------------------------
    # STAGE 1: Measurement
    # ------------------------------------------------------------------

    def measure(
        self,
        image_path: str | Path,
        *,
        fig_num: int = 0,
        page: int = 0,
        paper_num: int = 0,
    ) -> FigureMetrics:
        """
        Load the PNG and compute all measurable quantities.
        Returns a fully populated FigureMetrics with classification and
        suggested adjustments — the complete feedback record.
        """
        m = FigureMetrics(
            path=str(image_path),
            fig_num=fig_num,
            page=page,
            paper_num=paper_num,
        )

        if not _DEPS_OK:
            m.classification = "UNKNOWN"
            m.reason = f"quality deps unavailable ({_DEPS_ERR})"
            return m

        try:
            img = Image.open(str(image_path)).convert("RGB")
        except Exception as exc:
            m.classification = "REJECT"
            m.reason = f"image_load_failed: {exc}"
            return m

        arr  = np.asarray(img, dtype=np.uint8)
        gray = arr.mean(axis=2).astype(np.float32)

        m.aspect_ratio             = _aspect_ratio(img)
        m.fill_ratio               = _fill_ratio(arr)
        m.edge_sharpness           = _edge_sharpness(gray)
        m.white_border_fraction    = _white_border_fraction(arr)
        m.text_contamination_ratio = _text_contamination(gray)
        m.pixel_intensity_std      = float(gray.std())

        m.confidence_score         = self._compute_confidence(m)
        m.classification, m.reason = self._classify(m)
        m.suggested_adjustments    = self.suggest_adjustment(m)
        return m

    # ------------------------------------------------------------------
    # STAGE 2: Classification
    # ------------------------------------------------------------------

    def evaluate(self, metrics: FigureMetrics) -> tuple[str, str]:
        """Return (classification, reason) from already-measured metrics."""
        return self._classify(metrics)

    # ------------------------------------------------------------------
    # STAGE 3: Feedback — diagnose failure and suggest parameter changes
    # ------------------------------------------------------------------

    def suggest_adjustment(self, m: FigureMetrics) -> dict:
        """
        Diagnose which quality criterion failed and recommend how to
        adjust the extraction parameters on a re-attempt.
        """
        s = self._std
        adj: dict = {}

        if m.fill_ratio < s.min_fill_ratio:
            # Too empty → bounding box missed content
            adj["expand_box"] = True
            adj["pad_extra_px"] = 20

        if m.text_contamination_ratio > s.max_text_contamination:
            # Caption / paragraph text bled into crop
            adj["shrink_y1"] = True
            adj["shrink_amount_px"] = 15

        if m.edge_sharpness < s.min_edge_sharpness:
            # Blurry or near-blank region → increase render resolution
            adj["increase_dpi"] = True
            adj["dpi_delta"] = 50

        if not (s.min_aspect_ratio <= m.aspect_ratio <= s.max_aspect_ratio):
            # Wrong proportions → two figures merged or bad column detection
            adj["check_merged_figures"] = True

        if m.pixel_intensity_std < s.min_pixel_intensity_std:
            # Uniform intensity → almost certainly a blank region
            adj["likely_blank"] = True

        return adj

    # ------------------------------------------------------------------
    # STAGE 4: Logging — write standards + measurements to metrics.json
    # ------------------------------------------------------------------

    def log_session(
        self,
        pdf_name: str,
        all_metrics: list[FigureMetrics],
        output_dir: Path,
    ) -> Path:
        """
        Write per-session metrics.json alongside the extracted figures.
        This is Maxwell's 'record' — measurements + standards in one place
        so the algorithm's performance can be audited and improved.
        """
        confidences = [m.confidence_score for m in all_metrics]
        mean_conf   = sum(confidences) / len(confidences) if confidences else 0.0
        min_conf    = min(confidences, default=0.0)

        stem     = Path(pdf_name).stem
        log_path = output_dir / f"{stem}_metrics.json"

        payload = {
            "pdf": pdf_name,
            "standard": asdict(self._std),
            "summary": {
                "total"           : len(all_metrics),
                "good"            : sum(1 for m in all_metrics if m.classification == "GOOD"),
                "marginal"        : sum(1 for m in all_metrics if m.classification == "MARGINAL"),
                "reject"          : sum(1 for m in all_metrics if m.classification == "REJECT"),
                "mean_confidence" : round(mean_conf, 4),
                "min_confidence"  : round(min_conf,  4),
            },
            "figures": [asdict(m) for m in all_metrics],
        }

        log_path.write_text(json.dumps(payload, indent=2))
        return log_path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_confidence(self, m: FigureMetrics) -> float:
        """
        Map all measured quantities to a single [0, 1] confidence score.

        Each criterion deducts from a perfect score of 1.0.
        Penalties are sized proportionally to how damaging the failure is
        for the final extracted image quality.
        """
        s     = self._std
        score = 1.0

        # --- Geometric ---
        if not (s.min_aspect_ratio <= m.aspect_ratio <= s.max_aspect_ratio):
            score -= 0.25   # structurally wrong crop shape

        if m.fill_ratio < s.min_fill_ratio:
            score -= 0.25   # nearly empty — bounding box missed the figure
        elif m.fill_ratio > s.max_fill_ratio:
            score -= 0.15   # overly dense — likely text bleed

        if m.edge_sharpness < s.min_edge_sharpness:
            score -= 0.20   # blurry / blank region

        # --- Content ---
        # Text contamination: penalise proportionally to how far beyond the
        # threshold we are, up to a maximum of -0.40 for a fully text-filled image.
        excess = max(0.0, m.text_contamination_ratio - s.max_text_contamination)
        if excess > 0.0:
            normalised = excess / max(1.0 - s.max_text_contamination, 1e-9)
            score -= normalised * 0.40

        if m.pixel_intensity_std < s.min_pixel_intensity_std:
            score -= 0.20   # near-uniform → blank

        if m.white_border_fraction > s.max_white_border_fraction:
            score -= 0.10   # over-padded / empty margin

        return max(0.0, min(1.0, score))

    def _classify(self, m: FigureMetrics) -> tuple[str, str]:
        s     = self._std
        score = m.confidence_score

        if score >= s.min_confidence_score:
            return "GOOD", ""

        reasons = self._failure_reasons(m)
        label   = "; ".join(reasons) if reasons else "low_confidence"

        if score >= s.marginal_confidence_score:
            return "MARGINAL", label
        return "REJECT", label

    def _failure_reasons(self, m: FigureMetrics) -> list[str]:
        s       = self._std
        reasons: list[str] = []

        ar = m.aspect_ratio
        if not (s.min_aspect_ratio <= ar <= s.max_aspect_ratio):
            reasons.append(f"aspect_ratio={ar:.2f}")
        if m.fill_ratio < s.min_fill_ratio:
            reasons.append(f"fill_ratio_low={m.fill_ratio:.3f}")
        elif m.fill_ratio > s.max_fill_ratio:
            reasons.append(f"fill_ratio_high={m.fill_ratio:.3f}")
        if m.edge_sharpness < s.min_edge_sharpness:
            reasons.append(f"sharpness={m.edge_sharpness:.1f}")
        if m.text_contamination_ratio > s.max_text_contamination:
            reasons.append(f"text_contam={m.text_contamination_ratio:.2f}")
        if m.pixel_intensity_std < s.min_pixel_intensity_std:
            reasons.append(f"intensity_std={m.pixel_intensity_std:.1f}")
        return reasons


# ---------------------------------------------------------------------------
# Measurement helpers — pure functions, no class state
# ---------------------------------------------------------------------------

def _aspect_ratio(img: "Image.Image") -> float:
    """width / height of the extracted image."""
    w, h = img.size
    return w / h if h > 0 else 0.0


def _fill_ratio(arr: "np.ndarray") -> float:
    """
    Fraction of pixels that are NOT near-white.
    Near-white = all three RGB channels ≥ 240.
    Low fill → mostly blank background captured; high fill → text/ink everywhere.
    """
    near_white = np.all(arr >= 240, axis=2)
    total = arr.shape[0] * arr.shape[1]
    return float(np.count_nonzero(~near_white)) / total if total > 0 else 0.0


def _edge_sharpness(gray: "np.ndarray") -> float:
    """
    Variance of a discrete Laplacian kernel applied to the greyscale image.
    High variance = sharp edges / rich structure (a real figure).
    Low variance = blurry or near-blank region.
    No scipy dependency — computed with pure numpy slicing.
    """
    if gray.shape[0] < 3 or gray.shape[1] < 3:
        return 0.0
    lap = (
        gray[:-2, 1:-1] + gray[2:, 1:-1]
        + gray[1:-1, :-2] + gray[1:-1, 2:]
        - 4.0 * gray[1:-1, 1:-1]
    )
    return float(lap.var())


def _white_border_fraction(arr: "np.ndarray", band: int = 10) -> float:
    """
    Mean fraction of near-white pixels across the 4 border bands
    (top, bottom, left, right), each `band` pixels wide.

    High value → large white margins (over-padded) or empty region captured.
    Low value  → content extends to the very edge (figure may be clipped).
    """
    h, w = arr.shape[:2]
    band = min(band, max(1, h // 6), max(1, w // 6))

    def _wf(region: "np.ndarray") -> float:
        return float(np.mean(np.all(region >= 240, axis=2)))

    top    = _wf(arr[:band,  :])
    bottom = _wf(arr[-band:, :])
    left   = _wf(arr[:,  :band])
    right  = _wf(arr[:, -band:])
    return (top + bottom + left + right) / 4.0


def _text_contamination(gray: "np.ndarray") -> float:
    """
    Estimate the fraction of image rows that have text-like ink density.

    Method (horizontal projection heuristic):
      - Binarise to dark pixels (greyscale < 180).
      - Compute dark-pixel fraction per row.
      - Rows where 3 % < dark_fraction < 45 % are characteristic of text
        lines: not blank and not solid figure fill.
      - The fraction of such rows over the whole image is the contamination
        ratio.

    Threshold range [0.03, 0.45] is deliberately wide to catch body-paragraph
    text (5–25 % at 200 DPI) while tolerating thin circuit lines (which also
    fall in this range but are far fewer in total).
    """
    if gray.size == 0:
        return 0.0
    h, w      = gray.shape
    dark_frac = (gray < 180).sum(axis=1) / w   # dark fraction per row
    text_rows = int(np.count_nonzero((dark_frac > 0.03) & (dark_frac < 0.45)))
    return text_rows / h
