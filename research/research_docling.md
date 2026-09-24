# Docling research notes (as of 2026-09-23)

Scope: docling-project/docling, docling-core, docling-ibm-models, docling-serve, docling-eval.
Latest PyPI version confirmed: **docling 2.130.0**, released Sep 22, 2026 (https://pypi.org/project/docling/).
Companion packages also moving fast in Sep 2026: docling-serve 1.34.0 (Sep 17, 2026), docling-ibm-models 4.0.2 (Sep 3, 2026), docling-core (Sep 18, 2026). Source: https://pypi.org/project/docling-serve/, https://pypi.org/project/docling-ibm-models/, https://pypi.org/project/docling-core/

Note on release-note dates: the GitHub Releases page rendering via WebFetch mis-stamped years (showed "2024" for entries that are clearly 2026 given version numbers ~2.12x-2.130 and the PyPI-confirmed date for 2.130.0). Treat the *version ordering* as reliable, the literal year strings from that one fetch as unverified/likely mis-OCR'd by the summarizer. https://github.com/docling-project/docling/releases

---

## 1. Pipelines and modes

### 1.1 StandardPdfPipeline (a.k.a. "standard")
- Deterministic PDF parsing (via `docling-parse`) + optional neural OCR + neural layout + neural table structure. This is the default (`--pipeline standard` in the CLI). https://docling-project.github.io/docling/examples/agent_skill/docling-document-intelligence/pipelines/
- A "native PDF pipeline" was introduced around v2.126.0 (per version-ordered release notes) and the PDF backend was later refactored to drop the `pypdfium` dependency (v2.128.0), consolidating around `docling-parse`. https://github.com/docling-project/docling/releases
- **Layout model**: RT-DETR-based object detector. Model family is "Heron" (current default, `docling-layout-heron`, plus `docling-layout-heron-101`) and "Egret" (Medium/Large/XLarge variants). Legacy `docling-layout-v2` is deprecated/no longer supported. Inference engine: Transformers, with ONNXRuntime support "in progress" as of the model catalog snapshot. https://docling-project.github.io/docling/usage/model_catalog/ , model card: https://huggingface.co/docling-project/docling-layout-heron
- **Layout labels** (DocItemLabel) confirmed: Caption, Footnote, Formula, List-item, Page-footer, Page-header, Picture, Section-header, Table, Text, Title, plus an extended set: Document Index, Code, Checkbox-Selected, Checkbox-Unselected, **Form**, **Key-Value Region**. https://huggingface.co/docling-project/docling-models , https://docling-project.github.io/docling/concepts/docling_document/
  - This label set is directly reusable as a **cheap routing signal**: pages/regions dominated by Table → table-heavy lane; Formula → math lane; Form/Key-Value Region → forms/KV lane; Code → code lane; Picture-heavy → image/chart lane.
- **Table structure (TableFormer)**: two modes.
  ```python
  from docling.datamodel.pipeline_options import TableFormerMode
  pipeline_options.do_table_structure = True
  pipeline_options.table_structure_options.mode = TableFormerMode.ACCURATE  # default, or TableFormerMode.FAST
  pipeline_options.table_structure_options.do_cell_matching = False  # let TableFormer define text cells instead of PDF cells
  ```
  Modes since v1.16.0. FAST = quicker/less accurate, ACCURATE = default, better on difficult structures. https://docling-project.github.io/docling/usage/advanced_options/
  - Cell matching: when enabled (default), TableFormer predictions are matched back to PDF text cells (avoids expensive re-OCR of the table crop, keeps the model language-agnostic); can break output when PDF cells are merged across columns — disable `do_cell_matching` in that case. https://docling-project.github.io/docling/usage/advanced_options/
  - Known regression: GitHub issue #4255 — "TableFormer (accurate) generates degenerate OTSL at max_steps cap → cell matcher drops table data rows (regression in 2.118.0+)". https://github.com/docling-project/docling/issues/4255
  - Alternate table structure model: a VLM-based path using `granite-vision-4.1-4b` (Transformers) is listed in the model catalog. https://docling-project.github.io/docling/usage/model_catalog/

### 1.2 OCR engine options (used within StandardPdfPipeline)
Six engine choices per model catalog: **EasyOCR**, **Tesseract**, **RapidOCR**, **OcrMac** (macOS Vision framework), **SuryaOCR**, and "Auto" for automatic engine selection. Language coverage ranges ~20 to 100+ languages depending on engine. https://docling-project.github.io/docling/usage/model_catalog/
- EasyOCR language prefetch: `docling-tools models download easyocr --easyocr-lang iso:zh-Hans --easyocr-lang ja` (BCP-47 or EasyOCR codes). https://docling-project.github.io/docling/usage/advanced_options/
- OCR languages were canonicalized to the BCP-47 standard around v2.127.0 (version-ordered). https://github.com/docling-project/docling/releases
- Practical trade-offs (community, not Docling docs):
  - Tesseract: fast, best on clean high-res scans, ~10MB footprint; weak on handwriting/complex layouts/low quality. https://invoicedataextraction.com/blog/python-ocr-library-comparison-invoices
  - RapidOCR: ONNX port of PaddleOCR models, ~80MB, ~0.2s/inference — good lightweight default. Docling+RapidOCR walkthrough: https://dev.to/aairom/using-doclings-ocr-features-with-rapidocr-29hd
  - EasyOCR: reasonable quality but slow on CPU, historically the biggest compute cost in the pipeline, and tied to a memory leak (see §5).

### 1.3 How Docling decides whether/where to OCR
- `do_ocr` (bool): turn OCR on/off for the pipeline.
- Default behavior: Docling first checks whether the PDF page already has a usable digital text layer. If yes, it uses that text directly (no OCR). If the text layer is missing/insufficient, it applies OCR **selectively**, driven by bitmap coverage of the page.
- `bitmap_area_threshold` (float, default ~0.05 = 5%): minimum fraction of page area a bitmap/image region must cover before OCR is triggered on it — skips small logos/icons/watermarks, avoiding OCR noise on born-digital pages that merely contain a small raster image. https://medium.com/@lukas.flaig/a-practical-guide-to-doclings-pdf-pipeline-working-with-complex-documents-at-scale-cbd1853303fc
- `force_full_page_ocr` (bool): bypasses the selective/text-layer-aware logic entirely and OCRs the whole page regardless of an existing text layer. Recommended only when layout/text extraction is known-unreliable or every page is a pure scan. There was a bug where the (now deprecated) flag wasn't applied correctly on assignment, fixed in PR #4085. https://github.com/docling-project/docling/pull/4085 ; example: https://docling-project.github.io/docling/_generated/examples/full_page_ocr/
- Open feature request (unresolved as of research date): "Add OCR option to skip pages with a usable text layer" — issue #3464, and a related ask "Conditional OCR when text layer is missing" — issue #2036. These indicate the page-level text-layer/OCR decision is not fully exposed/controllable today, which matters for routing (we may need to inspect `docling-parse` output ourselves rather than rely on a documented public per-page "needs OCR" flag). https://github.com/docling-project/docling/issues/3464 , https://github.com/docling-project/docling/issues/2036
- **Regression risk for our routing use case**: issue #4357 — "Threaded docling-parse default (2.123.0, #3764) drops most of a scanned PDF's embedded OCR text layer." In a sweep of 29 Internet Archive scans with OCR text layers, the threaded backend lost most of the text on 5 of them, vs. 1 for the serial backend. This directly affects any routing heuristic based on "does this page already have a text layer" since the parser itself can silently under-report it in threaded mode. https://github.com/docling-project/docling/issues/4357
- Backend note: the faster `pypdfium` backend is more memory-efficient than the default `docling-parse` backend but gives worse quality, especially for table structure recovery (community discussion). This backend dependency is reportedly being phased out as of v2.128.0 (PDF backend refactor to eliminate pypdfium dependency), so expect this trade-off to disappear/change soon. https://github.com/docling-project/docling/releases

### 1.4 Confidence scores — VERIFIED, matches what you recalled
Introduced in v2.34.0. Exposed as `result.confidence` on the `ConversionResult`. https://docling-project.github.io/docling/concepts/confidence_scores/
- Components (0.0-1.0 each):
  - `parse_score`: 10th-percentile score of digital text cells (emphasizes problem areas of native text extraction)
  - `layout_score`: overall quality of document element (layout) recognition
  - `ocr_score`: quality of OCR-extracted content
  - `table_score`: table extraction quality — **documented but "not yet implemented"** as of the snapshot fetched; verify current status before relying on it.
- Grades: POOR / FAIR / GOOD / EXCELLENT (categorical, docs recommend using grades over raw scores since score computation "may evolve").
- Per-page AND document-level: `result.confidence.pages` (dict keyed by page number → `PageConfidenceScores`), plus document-level aggregates `mean_grade` (average of components) and `low_grade` (5th percentile, worst-performing areas).
  ```python
  result.confidence.mean_grade
  result.confidence.low_grade
  result.confidence.pages[<page_no>].layout_score
  result.confidence.pages[<page_no>].ocr_score
  result.confidence.pages[<page_no>].parse_score
  ```
- **This is directly usable as a routing signal**: per-page `parse_score`/`ocr_score`/`layout_score` can flag "degraded/low quality" pages for a dedicated lane, or flag pages that need re-routing to VLM/full-page-OCR.
- Caveat: this per-page detail was historically computed internally but **not always surfaced through `docling-serve`'s API response** — see open issue "Preserve docling's per-page confidence scores in the convert response (ConfidenceScores.pages)" (#705 in docling-serve) and PR #4233 in docling core ("feat: expose per-page confidence breakdown in ConfidenceScores"), plus discussion #2814 asking how to get the score via API at all. If we plan to consume confidence scores through docling-serve's HTTP API rather than the Python SDK directly, we must verify this PR has landed and is exposed in the API response schema we intend to call. https://github.com/docling-project/docling-serve/issues/705 , https://github.com/docling-project/docling/pull/4233 , https://github.com/docling-project/docling/discussions/2814

### 1.5 VlmPipeline
- Runs a single Vision-Language Model over the full page image instead of composing separate layout/OCR/table models — a holistic page-understanding approach. CLI: `--pipeline vlm`. https://docling-project.github.io/docling/examples/agent_skill/docling-document-intelligence/pipelines/
- Output: the VLM emits **DocTags** (a compact tag-based intermediate format) which Docling then converts into a `DoclingDocument`. https://huggingface.co/ibm-granite/granite-docling-258M
- Models supported (per model catalog + HF), spanning multiple inference engines:
  - **Granite-Docling-258M** (258M params) — DocTags output, IBM/LF AI's own model, built on Idefics3 architecture with a SigLIP2-base-patch16-512 vision encoder + a 165M-param Granite LLM. Supports Transformers and MLX. Feature set per HF README: enhanced equation recognition, flexible inference modes, improved stability, enhanced inline equations, document element QA, and *experimental* Japanese/Arabic/Chinese support. https://huggingface.co/ibm-granite/granite-docling-258M , IBM announcement: https://ibm.com/new/announcements/granite-docling-end-to-end-document-conversion
  - **SmolDocling-256M** — DocTags format, the model that preceded/paralleled Granite-Docling.
  - **Phi-4-Multimodal**, **Qwen2.5-VL-3B**, **Pixtral-12B** — general VLMs usable via the same VlmPipeline abstraction (Transformers/vLLM/API depending on model).
  - API-only / remote endpoints: **DeepSeek-OCR-3B**, and generic Ollama/LM Studio-compatible endpoints.
  - Newer additions per version-ordered release notes (~v2.128-2.130, i.e. Sept 2026): **NVIDIA Nemotron Parse 2.0** added as a VLM option (v2.128.0), **Mineru 2.5 Pro** support added to VLMs (v2.130.0), and "improved Chandra OCR parsing" (v2.129.0) — Chandra appears to be another VLM/OCR backend option being integrated. https://github.com/docling-project/docling/releases (dates on this source are suspect — see note at top of file — but version ordering places these as the most recent VLM-related additions)
  - Engines across the board: Transformers, MLX (Apple Silicon), vLLM, and API-compatible runtimes (Ollama, LM Studio, hosted APIs). https://docling-project.github.io/docling/usage/model_catalog/
- RTX/GPU acceleration guide exists specifically for the VLM pipeline: https://docling-project.github.io/docling/getting_started/rtx/ and a GPU VLM pipeline example: https://docling-project.github.io/docling/_generated/examples/gpu_vlm_pipeline/
- Known rough edge: issue #1365 — `DocumentConverter` ignoring `pipeline=PdfPipeline.VLM` and silently defaulting to StandardPdfPipeline, causing an `AttributeError` because `StandardPdfPipeline` tried to read `ocr_options` off a `VlmPipelineOptions` object. Worth defensive-checking in our router/integration code that the VLM path is actually being invoked, not silently falling back. https://github.com/docling-project/docling/issues/1365

### 1.6 Enrichment options (post-processing on top of either pipeline)
All disabled by default; each is a boolean flag on `PdfPipelineOptions`. https://docling-project.github.io/docling/usage/enrichments/
```python
pipeline_options.do_formula_enrichment = True      # TextItem[label=FORMULA] -> CodeFormula model -> LaTeX
pipeline_options.do_code_enrichment = True          # CodeItem -> CodeFormula model
pipeline_options.do_picture_classification = True   # PictureItem -> DocumentFigureClassifier-v2.5
pipeline_options.do_picture_description = True      # PictureItem -> VLM caption/description
```
- Formula/code model: **CodeFormulaV2** (starred/default), also usable via Granite-Docling-258M. Transformers-only inference. https://docling-project.github.io/docling/usage/model_catalog/
- Picture description VLM presets: `granite_picture_description` (Granite-Vision-3.3-2B), `smolvlm_picture_description` (SmolVLM-256M, default/starred), plus custom via `PictureDescriptionVlmOptions(repo_id=...)`, or remote via `PictureDescriptionApiOptions(url=..., params=..., enable_remote_services=True)`.
- Known bug: formula enrichment mangles spacing — "Bug Report: LaTeX Formula Spacing Issue with do_formula_enrichment=True" (issue #2374): output LaTeX has every character space-separated, breaking notation. Relevant if the math/equations lane depends on clean LaTeX output. https://github.com/docling-project/docling/issues/2374
- Known misclassification: layout model mistakes dotted poetic/leader lines for a Formula element, exporting an empty/OCR-derived FormulaItem (issue #3780) — a source of false positives for a "math lane" router keyed on the Formula label alone. https://github.com/docling-project/docling/issues/3780

### 1.7 Picture/figure classifier (DocumentFigureClassifier-v2.5)
- Architecture: EfficientNet-B0 fine-tuned on a subset of HF "finepdfs"; 4.08M parameters (F32) — i.e., **cheap enough to run in a triage stage** ahead of full conversion. https://huggingface.co/docling-project/DocumentFigureClassifier-v2.5
- 26 categories: logo, photograph, icon, engineering drawing, line chart, bar chart, other, table, flow chart, screenshot from computer, signature, screenshot from manual, geographical map, pie chart, page thumbnail, stamp, music, calendar, QR code, bar code, full page image, scatter plot, chemistry structure, topographical map, crossword puzzle, box plot.
- v2.5 vs v2.0: accuracy 90.7% (+3.65pp), balanced accuracy 68.8% (+8.61pp), macro F1 68.9%, Cohen's kappa 0.87. Per-label precision strong for table (98.6%) and pie chart (96.9%).
- **Directly useful for our lanes**: signature → forms/handwritten lane signal; QR/bar code, stamp → forms lane; chart types (line/bar/pie/scatter/box plot) → image/chart-heavy lane; chemistry structure → math/equations-adjacent lane; screenshots → code/UI lane candidate.

### 1.8 ASR (audio/video) pipeline
- New capability (per community blog posts, mid-2025-ish origin, still current in the docs as of this research): audio files run through a dedicated ASR pipeline using **OpenAI Whisper**. Backend auto-selects per hardware: `mlx-whisper` on Apple Silicon, native Whisper elsewhere; an experimental faster `WhisperS2T` backend is also selectable. Requires `ffmpeg` on PATH. https://docling-project.github.io/docling/usage/processing_audio_media/ , example: https://docling-project.github.io/docling/examples/minimal_asr_pipeline/
- Supported formats: MP3, WAV, M4A, AAC, OGG, FLAC; video files have audio track + frames extracted before transcription.
- Output is a `DoclingDocument` like everything else, exportable to Markdown/JSON/HTML.
- Known issue: ASR pipeline fails on zero-duration Whisper segments (#3006); MIME validation bug rejected audio/m4a, audio/mp4 in docling-core (#787). Not relevant to our document-routing lanes but worth knowing if audio ever enters scope. https://github.com/docling-project/docling/issues/3006 , https://github.com/docling-project/docling-core/issues/787

### 1.9 Threaded / batch pipeline
- A "threaded docling-parse" backend became the SDK/CLI/service default around v2.123.0 (version-ordered). https://github.com/docling-project/docling/releases
- Threaded pipelines + batching OCR/layout/table stages can yield up to ~40% speedup, per community discussion "Best performance settings" (#2516). https://github.com/docling-project/docling/discussions/2516
- But GPU benchmarking discussion (#3442, docling 2.93.0, NVIDIA L4) found the pipeline is **stage-bound, not GPU-saturated**: GPU utilization averages 24-29% with only brief 100% bursts; increasing batch size 4→256 gave zero throughput improvement; document concurrency (1/2/4) gave no measurable difference. VLM stage = 58% of wall time, OCR = 38%, table structure/page parsing/layout the remainder. Conclusion pointed at CPU-side orchestration / Python GIL as the real bottleneck, not compute. https://github.com/docling-project/docling/discussions/3442
- Caution for routing design: the threaded backend has a correctness regression (#4357, above) that can silently drop OCR text layers on scanned PDFs — a reason to pin/verify backend choice per lane rather than assume "threaded = same output, just faster."

### 1.10 Extra input formats
Confirmed supported (docs + community, Sept 2026 snapshot): PDF, DOCX, PPTX, XLSX, HTML, Markdown, AsciiDoc, CSV, images (PNG/TIFF/JPEG/...), METS/GBS (domain XML), EPUB, Apple Pages (`.pages`, "completed" per v2.126.0 release-ordering, full support finished ~v2.130.0 per "Improved LibreOffice stability"), WAV/MP3/WebVTT and other audio via ASR pipeline, email (EML, MSG), Box Notes, LaTeX, plain text. Recent additions per version-ordered notes: **MHTML input backend** and **RTF support via LibreOffice** (~v2.127.0), **minimal AFP document support** (~v2.128.0). https://docling-project.github.io/docling/usage/supported_formats/ , https://github.com/docling-project/docling/blob/main/docs/usage/supported_formats.md , https://docling.ai/formats/

---

## 2. Speed numbers

### 2.1 Docling Technical Report (arXiv 2408.09869v5) — Table 1, 225-page test set
| Hardware | Threads | Backend | Time | Pages/sec | Peak memory |
|---|---|---|---|---|---|
| Apple M3 Max | 4 | Native (docling-parse) | 177s | 1.27 | 6.20 GB |
| Apple M3 Max | 4 | PyPDFium | 103s | 2.18 | 2.56 GB |
| Apple M3 Max | 16 | Native | 167s | 1.34 | — |
| Apple M3 Max | 16 | PyPDFium | 92s | 2.45 | — |
| Intel Xeon E5-2690 | 4 | Native | 375s | 0.60 | 6.16 GB |
| Intel Xeon E5-2690 | 4 | PyPDFium | 239s | 0.94 | 2.42 GB |
| Intel Xeon E5-2690 | 16 | Native | 244s | 0.92 | — |
| Intel Xeon E5-2690 | 16 | PyPDFium | 143s | 1.57 | — |

Source: https://arxiv.org/html/2408.09869v5 (this is the StandardPdfPipeline with OCR/tables on CPU-class hardware; the PyPDFium backend is faster and lower-memory but lower quality on table structure per community notes above — and is being phased out per the v2.128.0 backend refactor, so the "PyPDFium" row's speed advantage may not carry forward).

### 2.2 GPU (NVIDIA L4) numbers, community benchmark, docling 2.93.0
From GitHub discussion #3442: https://github.com/docling-project/docling/discussions/3442
- OCR off, VLM off (pure layout+table): **3.3 pages/sec**
- OCR only: **1.5 pages/sec**
- VLM only: **0.83 pages/sec**
- OCR + VLM together: **0.64 pages/sec**
- Per-stage wall time on a 189-page corpus (OCR+VLM on): VLM enrichment 170s, OCR 113s, table structure 44s, page parsing 43s, layout detection 10s.

### 2.3 Other cited GPU/CPU/MPS numbers (from an earlier search synthesis, re-verify exact source before quoting externally)
A separate summary (not independently re-fetched to a primary source in this pass) cited: Nvidia L4 GPU ~57/114/2081 ms per page at p5/median/p95, averaging ~481ms/page on L4 GPU vs ~3.1s/page on x86 CPU vs ~1.26s/page on M3 Max with MPS. **Flag as not fully verified** — this may be from the Docling GPU benchmark discussion thread or a downstream blog restating it; I could not pin an exact primary URL for this specific figure in this pass, so treat it as directionally consistent with §2.1/§2.2 but don't cite it externally without re-confirming. Planned benchmark configs mentioned: AWS EC2 g6.2xlarge (Nvidia L4, 24GB) and MacBook Pro M3 Max with optional MPS.

**Takeaway for lane design**: full VLM pipeline is ~4-5x slower than OCR-off standard pipeline even on GPU, and OCR roughly doubles cost over a pure born-digital path. This is strong justification for a routing layer: born-digital lane skips OCR entirely (parse-only, fastest), scanned lane pays the OCR cost, and only pages that truly need holistic understanding (handwriting, dense math, complex forms) should pay the VLM cost.

---

## 3. Accuracy evidence

### 3.1 OmniDocBench
- OmniDocBench (CVPR 2025, opendatalab) is the most-cited comprehensive doc-parsing benchmark, with per-module metrics for text (edit distance), tables (TEDS), formulas (CDM), and reading order. https://github.com/opendatalab/OmniDocBench , paper: https://openaccess.thecvf.com/content/CVPR2025/papers/Ouyang_OmniDocBench_Benchmarking_Diverse_PDF_Document_Parsing_with_Comprehensive_Annotations_CVPR_2025_paper.pdf
- Leaderboard context as of the "OmniDocBench is Saturated" piece: GLM-OCR reached 94.6% on OmniDocBench v1.5, with GLM-OCR and PaddleOCR-VL-1.5 both over 94% — these are newer end-to-end VLM-OCR systems, not Docling itself. https://www.llamaindex.ai/blog/omnidocbench-is-saturated-what-s-next-for-ocr-benchmarks
- Component reference points (not Docling-specific, general OmniDocBench context): DocLayout-YOLO (used inside MinerU) ~48.7 mAP for layout; RapidTable ~82.5 TEDS for tables; PaddleOCR ~73.6% normalized edit distance for text; GPT-4o/Mathpix/UniMERNet ~86-87% CDM for formulas.
- **I could not find a direct, current Docling-vs-OmniDocBench-leaderboard row/number in this research pass** — the searches surfaced the benchmark and general SOTA context but not a pinned "Docling scored X on OmniDocBench v1.5" citation. **Mark as unverified**; recommend running `docling-eval` against OmniDocBench directly (see §3.3) rather than relying on a secondhand number.

### 3.2 DP-Bench
- `docling-eval` (official IBM/LF AI eval framework) supports DP-Bench evaluation for layout, table structure, and reading order. https://github.com/docling-project/docling-eval
- Their DP-Bench doc describes methodology (mAP[0.5:0.95] for layout, TEDS struct-only/struct-with-text for tables, ARD/weighted-ARD for reading order, BLEU/edit-distance/F1/METEOR for markdown text) but the specific numeric comparison table lives in separate linked JSON/report files that I did not manage to open in this pass. https://github.com/docling-project/docling-eval/blob/main/docs/DP-Bench_benchmarks.md — **numbers unverified, methodology verified**.
- One secondary source (Procycons blog, "PDF Data Extraction Benchmark 2025") claims Docling reaching **97.9% table extraction accuracy** in their comparison of Docling vs Unstructured vs LlamaParse — this is a third-party benchmark, not Docling's own eval, and I have not cross-checked their methodology. **Treat as a single data point, not verified against DP-Bench/OmniDocBench directly.** https://procycons.com/en/blogs/pdf-data-extraction-benchmark/
- Historical: the original ask to benchmark Docling against DP-Bench is tracked in old issue #202 (pre-rename DS4SD/docling repo). https://github.com/DS4SD/docling/issues/202

### 3.3 Recommendation
Given the gaps above, if precise accuracy numbers are needed for the lane-design doc, the most defensible path is running `docling-eval` (https://github.com/docling-project/docling-eval) ourselves against a sample from each target lane (scanned invoices, handwritten forms, dense tables, math-heavy papers, multilingual docs) rather than citing secondhand aggregate benchmark numbers, since I could not verify a clean, current, Docling-specific OmniDocBench/DP-Bench score table from public sources in this pass.

---

## 4. Community reports: where it works, where it breaks

### 4.1 Tables
- Known limitation (multiple sources): merged cells, multi-level headers, and rows with varying column counts. The pipeline tends to enforce a rectangular grid and can misidentify headers or flatten nuanced layouts. https://www.codecademy.com/article/docling-ai-a-complete-guide-to-parsing
- Discussion #2241: "Docling not able to convert complex table into correct layout structure." https://github.com/docling-project/docling/discussions/2241
- Issue #2790: "Complex tables with page breaks produce hallucinating results." https://github.com/docling-project/docling/issues/2790
- Issue #2081: "Extraction of data from table is not accurate" — missing values, lost special characters like `=` and `~` (notably bad for tables containing formulas/math symbols — overlap with the math lane). https://github.com/docling-project/docling/issues/2081
- Issue #4255 (regression, 2.118.0+): TableFormer ACCURATE mode generates degenerate OTSL at the max_steps cap, causing the cell matcher to drop table data rows on very large/dense tables. https://github.com/docling-project/docling/issues/4255
- docling-parse-level bug: "Table cell parsing issue: Docling misaligns/mis-parses cells in PDF tables" (#167 in docling-parse). https://github.com/docling-project/docling-parse/issues/167

### 4.2 Math / formulas
- LaTeX spacing bug with `do_formula_enrichment=True` (#2374, above).
- Layout misclassifies dotted/poetic leader lines as Formula (#3780, above) — a false-positive risk when routing purely on the Formula label.
- Granite-Docling-258M explicitly advertises "enhanced equation recognition" and "enhanced inline equations" as 2026-era improvements, suggesting the VLM pipeline is being actively pushed as the better math-handling path vs. the standard pipeline's CodeFormula enrichment. https://huggingface.co/ibm-granite/granite-docling-258M

### 4.3 Multi-column / reading order — a real, recurring weak spot
Multiple independent issues describe the same failure mode across versions/timeframes:
- #1203 "Convoluted Reading Flow for Multi-Column PDFs" — headings/paragraphs attributed to the wrong column's flow, images misattached, paragraph order scrambled within a column. https://github.com/docling-project/docling/issues/1203
- #2067 "Multi-column layout extraction fails" — 3-column financial documents produce scrambled cross-column text. https://github.com/docling-project/docling/issues/2067
- #3198 "Unexpected Read-Order Inversion & Column Merging" (as recent as ~2026) — body-model reading order still inverts / merges disconnected text across columns in heavily indented or multi-column layouts. https://github.com/docling-project/docling/issues/3198
- #2201 "How to correctly detect order in two-column pdfs?" — default params hop to the next column mid-way through the first, breaking Introduction-section ordering in academic papers. https://github.com/docling-project/docling/issues/2201
- Discussion #2791 — reading order follows raw PDF creation/content-stream order rather than human reading order in some cases. https://github.com/docling-project/docling/discussions/2791
- **Implication for lane design**: multi-column academic/legal layouts are a standing risk category across the whole project history, not a one-off bug — worth a distinct "multi-column" consideration even if not a full separate lane, e.g. defaulting such docs to VLM pipeline (which reads holistically off the image rather than reconstructing order from parsed text blocks) or adding a post-hoc reading-order sanity check keyed on confidence scores.

### 4.4 RTL / multilingual
- Long-standing open issue #253 (original DS4SD/docling repo): Arabic PDF text is reversed (word order and letter order within words) even with `pipeline_options.ocr_options.lang` set to Arabic. Raises the general question of whether RTL and mixed-language (RTL+LTR) documents are properly supported at all. **Appears unresolved / not clearly fixed as of this research pass** — I did not find a closing PR or changelog entry confirming a fix; treat RTL as a known-weak area requiring its own validation before assuming a "multilingual" lane handles Arabic/Hebrew correctly. https://github.com/DS4SD/docling/issues/253
- Granite-Docling-258M's Japanese/Arabic/Chinese support is explicitly labeled "experimental" in its own model card, i.e. even the newest VLM path doesn't claim full multilingual maturity. https://huggingface.co/ibm-granite/granite-docling-258M

### 4.5 Memory / stability (relevant to a "degraded/low quality" or high-volume batch lane)
- Issue #1343: memory leak caused by EasyOCR — CPU memory climbs unbounded in containerized deployments until OOM-killed. https://github.com/docling-project/docling/issues/1343
- Issue #2779: "Docling consumes all available memory and gets killed." https://github.com/docling-project/docling/issues/2779
- docling-serve #474 and #344: memory not released between conversions in long-running server processes; one report cites 79GB RSS after 11 hours of docling-serve uptime, called "unsuitable for long-running production environments" as-is. https://github.com/docling-project/docling-serve/issues/474 , https://github.com/docling-project/docling-serve/issues/344
- **Implication**: if we run docling-serve as a long-lived service behind our router, plan for periodic worker recycling/restarts regardless of lane, and prefer EasyOCR alternatives (RapidOCR/Tesseract) for high-throughput OCR lanes given the specific leak attribution.

### 4.6 Handwriting
I was not able to find a specific, well-documented GitHub issue thread quantifying Docling's handwriting failure modes in this pass (searches surfaced tables/math/multi-column issues much more than handwriting-specific ones). This is itself a signal: Docling's own docs and model cards emphasize *printed/structured* documents (forms, tables, scientific papers), and neither StandardPdfPipeline's OCR engines (Tesseract/EasyOCR/RapidOCR/OcrMac) nor the VLM models (Granite-Docling, SmolDocling) are marketed with handwriting-recognition claims. **Mark as unverified-by-issue-thread but treat as a high-risk lane** — recommend empirical testing on a handwriting sample set before committing StandardPdfPipeline OR VlmPipeline to that lane; a dedicated handwriting-OCR model (outside Docling) is likely needed regardless.

---

## 5. DoclingDocument output model, export, chunking

- `DoclingDocument` is Docling's unified intermediate representation (defined in `docling-core`), used identically whether the source was PDF, DOCX, HTML, images, or audio (ASR). https://docling-project.github.io/docling/concepts/docling_document/
- Structure: a `body` tree (main content) and a `furniture` tree (headers/footers/non-body items), with `groups` as containers (lists, chapters) that aren't direct content; items reference each other via JSON pointers; each item can carry provenance/bounding-box info per page when available.
- Content collections referenced in the doc: `texts` (paragraphs, section headings, equations as TextItem), `tables` (TableItem with structure annotations), `pictures` (PictureItem with structure annotations), `key_value_items` (key-value pairs — relevant to the forms/KV lane).
- I was not able to fully verify the exact export method names (`export_to_markdown`, `export_to_html`, `export_to_dict`, `save_as_json`, etc.) against primary docs text in this pass — the fetched page didn't render the API reference section content; these names are consistent with what's used throughout Docling's own examples and widely mirrored downstream (LangChain/LlamaIndex integrations), but **verify exact method signatures against `docling_core.types.doc` source before depending on them**: https://github.com/docling-project/docling-core/tree/main/docling_core/types/doc

### Chunking
- Docling ships native chunkers that operate directly on `DoclingDocument` (rather than only chunking after Markdown export), producing chunks + metadata. https://docling-project.github.io/docling/concepts/chunking/
- `HybridChunker`: hierarchical, document-structure-aware chunking layered with tokenizer-aware refinement (so chunks respect both document structure and a target token budget). `repeat_table_header` (default True) repeats a table's header row in every chunk that table spans, preserving column context for downstream retrieval/LLM consumption. Example: https://docling-project.github.io/docling/examples/hybrid_chunking/
- This structure-aware chunking is precisely what makes Docling's output useful for "exact" downstream retrieval: because each chunk is tied back to document structure (and, via provenance, to page/bbox), a RAG/extraction pipeline downstream of our router can cite back to an exact page/region rather than an opaque text blob.

---

## 6. Reusable per-page/per-region signals for a triage/routing stage

Putting together everything above, the concretely reusable Docling signals for building the routing layer are:

1. **Text-layer presence** (from the PDF backend / docling-parse) — best proxy for born-digital vs scanned, but note the threaded-backend regression (#4357) that can under-report it; validate against a serial-backend cross-check if this signal drives a hard lane split.
2. **`bitmap_area_threshold`-style bitmap coverage per page** — cheap scanned/photographed-page detector.
3. **Confidence report** (`result.confidence.pages[i].{parse_score, layout_score, ocr_score}`) — degraded/low-quality lane trigger; note `table_score` may still be unimplemented — verify current status.
4. **Layout labels** (DocItemLabel: Table, Formula, Code, Form, Key-Value Region, Picture, etc.) and their per-page area/coverage — direct proxies for table-heavy, math, code, forms/KV, and image-heavy lanes.
5. **DocumentFigureClassifier-v2.5** (4.08M params, EfficientNet-B0) — cheap to run standalone as a triage classifier on any picture region even before full-document conversion; 26-class output maps well onto "image/chart-heavy" sub-routing and can flag signature/stamp/QR presence as forms-lane hints.
6. **Layout model itself (Heron/Egret, RT-DETR)** could in principle be run standalone as a fast triage pass (just layout, no OCR/table/VLM) to get element-type histograms per page cheaply, before committing a page to the expensive lane-specific pipeline — this matches the §2 speed data showing "layout only" (OCR off, VLM off) is the cheapest mode by far (3.3 pages/sec on an L4 GPU vs 0.64-1.5 for OCR/VLM combinations).
7. **Language detection** isn't itself a documented Docling output signal I could verify (OCR `lang` is an input, not a detected output) — for the multilingual lane we likely need an external language-ID step feeding into `ocr_options.lang` / VLM prompt choice, rather than relying on Docling to self-detect and report language. **Unverified**: whether newer versions (2.130.0-era) expose a detected-language field; worth checking `docling-core`'s `DocumentOrigin`/metadata classes directly if this matters.

---

## Open items / explicitly unverified in this pass
- Exact current (2.130.0) status of `table_score` in confidence reports (documented as "not yet implemented" in the version I could fetch — may have shipped since).
- Whether `ConfidenceScores.pages` is actually exposed through the docling-serve HTTP API today (PR #4233 existed; merge/release status not confirmed).
- Precise DP-Bench and OmniDocBench numeric scores *for Docling specifically* (methodology confirmed, numbers not pinned to a primary Docling source).
- Exact `DoclingDocument` export method signatures (names inferred from ecosystem-wide usage, not re-verified against current API reference text).
- Whether RTL support (issue #253) has been fixed since it was filed.
- Literal release dates on the GitHub Releases page (version ordering trusted, date strings not fully trusted due to a fetch/rendering artifact).
- The M3 Max/L4/x86 "ms per page" percentile figures in §2.3 (directionally plausible, source not re-confirmed to a primary URL in this pass).
- Whether a detected-language field exists anywhere in DoclingDocument metadata.
