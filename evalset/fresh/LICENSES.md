# Fresh set sources and licences

396 labelled cases for calibrating the review threshold (issue #3), disjoint from `evalset/` by source page and by file hash.
The groups match `evalset/`: image inputs (`img_*`, 246), PDF inputs (`pdf_*`, 125), PDFs with a garbled text layer (`garb_*`, 17: 5 real broken layers and 12 evidence-level overrides with no new file), and Tesseract OCR-layer PDFs (`ocr_*`, 8).
Per-case attribution is in `cases.jsonl` (`source` field); this table groups by dataset.
Licences are listed for information; the set is built from the most useful public sources, whatever their terms.

| Source | Licence | Cases | Composition |
|---|---|---|---|
| olmOCR-Bench (`allenai/olmOCR-bench`) | ODC-By 1.0 | 92 | 51 born-digital PDFs (24 L1, 26 L2, 1 either), 5 PDFs with a real garbled text layer, 36 scans as PDFs or images (18 L3, 6 L3/L4, 4 L4, 8 handwritten L5), from arXiv, web PDFs and Library of Congress letters |
| DocLayNet v1.2 (`docling-project/DocLayNet-v1.2`) | CDLA-Permissive-1.0 | 55 | Single-page PDFs from reports, manuals, patents, laws and articles: 24 L1, 23 L2, 2 either, 6 clean scans |
| PureDocBench (`zhihengli-casia/puredocbench`) | CC BY 4.0 | 66 | Clean, digital-degraded and real-degraded tracks of 31 pages, as images: 21 L3, 20 L3/L4, 25 L4 |
| OmniDocBench (`opendatalab/OmniDocBench`) | Research use only, not commercial | 47 | Page images: books, exams, newspapers, slides and reports (9 L3), fuzzy or deformed scans and photos (22 L3/L4, 6 L4), handwritten notes (10 L5) |
| GNHK (HF mirror `Berzerker/gnhk_ocr_dataset`) | CC BY 4.0 | 30 | Phone photos of handwritten notes, recipes and lists, all L5 |
| RVL-CDIP (100 per class, `jordyvl/rvl_cdip_100_examples_per_class`) | Research use; Truth Tobacco Industry Documents archive | 30 | Low-resolution business scans: forms, reports, invoices, articles and handwritten lab notes (9 L3, 7 L3/L4, 6 L4, 8 L5) |
| CORD v2 (`naver-clova-ix/cord-v2`) | CC BY 4.0 | 21 | Phone photos of shop receipts (20 L4, 1 L3/L4) |
| ICDAR 2019 SROIE (`jsdnrs/ICDAR2019-SROIE`) | CC BY 4.0 per the mirror; competition data for research | 14 | Scanned shop receipts (4 L3, 8 L3/L4, 2 L4) |
| FUNSD (train split, via `nielsr/funsd`) | Non-commercial research licence, evaluation only | 11 | 1990s business forms (6 L3, 4 L3/L4, 1 L4) |
| Synthetic (own construction) | Own construction, over the sources above | 30 | 12 garbled text overrides and 2 rotated renders (L3), 4 fax and 4 phone-photo simulations made with `bench/vision_bakeoff/data/scripts/synth_degrade.py` (L4), 8 Tesseract OCR-layer PDFs of images in the set (their image's lanes) |

Lanes follow the fixed mapping in `bench/jev_lanes/probe.py`.
They come from construction or dataset metadata where that settles the lane, and from a visual check of contact sheets otherwise; the checked labels and every drop are listed at the end of `build.py`.
The L4 pages the router sent to L3 had a second, blind look, mixed with as many pages it routed to L4; the 17 pages the second labeller saw as clean or borderline accept either lane (`SECOND_LOOK` in `build.py`).
Pages with personal data about private individuals were left out: consumer letters and envelopes, named students and patients, receipts that print a cashier's full name, and GNHK notes that name people.

This set is for internal evaluation only.
It is not redistributed outside this repository, and none of it is used to train or fine-tune a model.
