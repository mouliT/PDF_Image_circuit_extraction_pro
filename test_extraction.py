"""Quick headless extraction test — run from the project directory."""
import sys, fitz
from pathlib import Path

sys.path.insert(0, ".")
from figure_extractor_app import (
    _find_captions_on_page,
    _find_figure_rect,
    _make_unique_path,
    _fig_id_for_filename,
    _fig_sort_key,
)
from figure_quality import QualityEvaluator

PDF = Path(r"C:/Users/tmouli/Documents/AI_trainig_data/Vignesh/ARCP_literature/"
           r"Auxiliary_Resonant_Commutated_Pole_Inverter_ARCPI_Operation_Using_online_voltage_measurements.pdf")
OUT = Path(r"C:/Users/tmouli/figures")
OUT.mkdir(exist_ok=True)
DPI = 200
mat = fitz.Matrix(DPI / 72, DPI / 72)
ev  = QualityEvaluator()

doc = fitz.open(str(PDF))

all_captions: dict = {}
page_caption_map: dict = {}
for pn in range(len(doc)):
    found = _find_captions_on_page(doc[pn])
    page_caption_map[pn] = found
    for fig_id, cr in found.items():
        if fig_id not in all_captions:
            all_captions[fig_id] = (pn, cr)

print(f"Captions found: {sorted(all_captions.keys(), key=_fig_sort_key)}")
print()

results = []
for fig_id in sorted(all_captions, key=_fig_sort_key):
    pn, cap_rect = all_captions[fig_id]
    page          = doc[pn]
    this_page_caps = page_caption_map.get(pn, {})
    fig_rect      = _find_figure_rect(
        page,
        cap_rect,
        this_page_caps,
        output_dpi=DPI,
        min_size_px=80,
    )

    if fig_rect is None:
        print(f"Fig.{fig_id} p{pn+1:02d}  SKIP — no content above caption")
        continue

    pix  = page.get_pixmap(matrix=mat, clip=fig_rect, alpha=False)
    w, h = pix.width, pix.height
    out  = _make_unique_path(OUT, f"P1_Fig{_fig_id_for_filename(fig_id)}_page{pn+1:02d}.png")
    pix.save(str(out))

    m = ev.measure(out, fig_num=fig_id, page=pn+1, paper_num=1)
    results.append(m)

    flag = "  *** REVIEW" if m.classification != "GOOD" else ""
    print(f"Fig.{fig_id} p{pn+1:02d}  {w:4d}x{h:4d}px"
          f"  [{m.classification:8s} {m.confidence_score:.2f}]"
          f"  fill={m.fill_ratio:.3f}  text={m.text_contamination_ratio:.2f}"
          f"  {m.reason}{flag}")

doc.close()
log = ev.log_session(PDF.name, results, OUT)
print()
print(f"Done. {len(results)} figures  ->  {OUT}")
print(f"Metrics -> {log.name}")
