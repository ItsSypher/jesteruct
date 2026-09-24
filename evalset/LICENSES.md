# Eval set sources and licences

98 labelled cases used to measure lane routing accuracy, across four groups: image inputs (`img_*`), PDF inputs (`pdf_*`), Tesseract OCR-layer PDFs (`ocr_*`), and PDFs with a garbled text layer (`garb_*`, evidence-level synthetic, no new file).
Per-case attribution is in `cases.jsonl` (`source` field); this table groups by dataset.

| Source | Licence | Cases | Composition |
|---|---|---|---|
| olmOCR-Bench (`allenai/olmOCR-bench`) | ODC-By 1.0 | 47 | 17 image inputs, 23 PDF inputs (11 labelled pages plus 12 extra one-page PDFs), 2 OCR-wrapped, 5 garbled-text-layer variants |
| PureDocBench (`zhihengli-casia/puredocbench`) | CC BY 4.0 | 23 | 21 image inputs (clean, digital-degraded and real-degraded tracks of 7 triplets), 2 OCR-wrapped |
| FUNSD (test split, via `nielsr/funsd`) | Non-commercial research licence, evaluation only | 7 | 5 image inputs, 2 OCR-wrapped; 1990s US business records, public via the Truth Tobacco Industry Documents archive |
| GNHK handwriting photos (via HF mirror `Berzerker/gnhk_ocr_dataset`) | CC BY 4.0 | 6 | 5 image inputs, 1 OCR-wrapped; mirrors the GoodNotes GNHK dataset |
| HumynLabs Arabic PDFs (`HumynLabs/Arabic_Documents_Dataset_PDF`) | CC BY 4.0 | 3 | 3 image inputs, from a freely distributed Arabic teaching text |
| Synthetic (own construction; two code pages carry CPython stdlib source under the PSF License) | Own construction / PSF License | 12 | 9 image inputs (fax, screenshot, camera-photo and rotated simulations, plus two rendered code pages), 2 PDF code-page inputs, 1 OCR-wrapped |

This set is for internal evaluation only.
It is not redistributed outside this repository, and none of it is used to train or fine-tune a model.
