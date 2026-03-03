# CLAUDE.md

- Project: PDF Figure Extractor Desktop App
- Framework: PyQt6
- Entry point: figure_extractor_app.py
- Architecture: MainWindow > ControlPanel, QSplitter > ThumbnailGallery + PreviewPanel (with CropCorrectionPanel), FigureCard, ExtractionWorker(QThread), SingleFigureWorker(QThread)
- Output format: P{N}_Fig{N}_page{NN}.png
- DPI default: 200, Min size default: 80px
- Conventions: dark theme, monospace font, all logic in single file figure_extractor_app.py
- Crop correction unit: PDF points (1 pt = 1/72 inch). Variables: expand_top, expand_bottom, expand_left, expand_right (all in pt, signed). Positive = expand outward.
- figure_ready dict must carry: path, fname, page (1-indexed), page_num (0-indexed), dims, paper_num, paper_name, fig_num, confidence, classification, pdf_path, crop_rect (tuple of 4 floats in pt), dpi
