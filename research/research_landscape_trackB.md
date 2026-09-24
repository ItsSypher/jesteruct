# Track B: Cheap Triage/Routing Signals for Document Sorting Layer

Research notes, compiled 2026-09-23. Goal: concrete, source-grounded signals and architectures for
routing arbitrary pages to Docling / Marker / VLM-OCR lanes. Every claim below is cited; anything I
could not independently verify against primary source is flagged "unverified" / "secondary source."

---

## 1. Born-digital vs scanned detection

### Core signal: embedded text layer presence + coverage

The baseline check everyone uses: try to extract text from the PDF's content stream (PyMuPDF
`page.get_text()`, pdfplumber `page.extract_text()`, pdftext, pdfminer). Empty or near-empty output
on a visually non-blank page is the primary "this page is scanned" signal. PyMuPDF's own
recommendation: check `get_text()` for emptiness *and* cross-check `get_images()` — if text is empty
but one or more image XObjects cover the page, the page is image-based
([nutrient.io blog](https://www.nutrient.io/blog/extract-text-from-pdf-pymupdf/),
[PyMuPDF discussion #4217](https://github.com/pymupdf/PyMuPDF/discussions/4217)). A stricter
threshold used in practice: fall back to OCR/VLM if extracted text length is under ~50 characters
for an otherwise content-bearing page
([theneuralbase.com](https://theneuralbase.com/pdf-processing/learn/beginner/detecting-scanned-vs-digital-pdf/)).
Caveats raised repeatedly: hybrid pages (hi-res photo of a form pasted over machine text), rotated
pages (90°/180°) that make some libraries return nothing, and text drawn in the same color as the
background (technically present, practically invisible)
([subhajitbhar.com](https://subhajitbhar.com/blog/pdf-extraction/extract-data-scanned-pdf-python/)).

A materially better and directly source-verified signal is **image/bitmap coverage ratio per page**,
which is exactly what Docling implements. From Docling's actual OCR base class
(`docling/models/base_ocr_model.py`, current `main` branch, fetched directly —
[github.com/docling-project/docling](https://github.com/docling-project/docling/blob/main/docling/models/base_ocr_model.py)):

- `_deduplicate_rects()` rasterizes candidate OCR-input rects (bitmap regions, or layout-model
  regions with no overlapping programmatic text) into a binary mask, applies a small binary dilation
  (`DEFAULT_DILATION_SIZE = 20` px) to close gaps, and computes **coverage = area(rects) /
  area(page)**.
- Docling's `OcrMode` has three interesting operating points: `FULL_PAGE` (rasterize the whole
  page — the cheap "must be scanned" fallback), `LAYOUT_REGIONS` (run OCR only on layout-model
  boxes), and the default `PDF_AWARE_LAYOUT_REGIONS`/`DEFAULT`, which is the actual page-classifier
  logic: `_find_pdf_aware_layout_ocr_rects()` walks every layout-detected cluster and (a) keeps it as
  an OCR candidate if it overlaps a bitmap/shape ("has_non_text"), or (b) keeps it if it has **no**
  overlapping programmatic PDF text cell at all; clusters that already have programmatic text are
  dropped from the OCR set. This is a per-region born-digital-vs-scanned decision, not just a
  per-page one.
- An older, simpler global constant reported by search tooling and older Docling source
  (`layout_utils.py`, pre-refactor) was `BITMAP_COVERAGE_TRESHOLD = 0.75`: if bitmap coverage of a
  bounding box exceeds `max(0.75, bitmap_area_threshold)`, force full-page OCR over that box; between
  the `bitmap_area_threshold` option and 0.75 it OCRs the discovered rects individually; below the
  option's threshold it skips OCR ([DeepWiki summary](https://deepwiki.com/docling-project/docling/4.1-ocr-models),
  cross-referenced against the live `base_ocr_model.py` file above — **the 0.75 constant itself I
  could not find verbatim in the current file, so treat the exact number as secondary-sourced**; the
  live mechanism (bitmap-rect coverage → OCR trigger) is primary-sourced).
- Docling also directly detects **invisible PDF text rendering modes** — the true "Tr 3" case — via
  `PdfCellRenderingMode`: `_INVISIBLE_RENDERING_MODES = {INVISIBLE, ONLY_CLIPPING}`, and
  `_segregate_by_visibility()` splits text cells into visible/invisible sets before merging OCR
  output with programmatic text, treating cells with no rendering-mode tag (plain `TextCell`, e.g.
  raw OCR output) as visible by convention. This is the correct, spec-based way to detect an
  existing (often bad-quality) invisible OCR text layer already baked into a PDF, as opposed to
  inferring it from font metrics.

### Invisible text layer / "Tr 3" detection outside Docling

PDF's text-rendering-mode operator `Tr` with argument `3` paints no ink and is exactly what most
OCR tools (Tesseract's `pdf` output, Adobe's "searchable image" mode, ABBYY, etc.) use to overlay
invisible recognized text under a scanned image
([dev.to write-up on an invisible-text-finder tool](https://dev.to/okinawasoftware/i-built-a-tool-that-finds-invisible-text-hidden-in-pdfs-white-text-tiny-fonts-and-the-5982)).
PyMuPDF does not expose the `Tr` value directly through `get_text()`, but two documented low-level
workarounds exist:
1. `page.get_texttrace()` / `page.get_bboxlog()` — an item tagged `("ignore-text", (x0,y0,x1,y1))`
   in the paint log means text in that rectangle was suppressed by `3 Tr`
   ([PyMuPDF discussion #1814](https://github.com/pymupdf/PyMuPDF/discussions/1814)).
2. Render a `Pixmap` of just the text's bbox and test if it is unicolor (i.e., the "text" never
   actually differs from the background) — a heuristic proxy for invisibility when rendering-mode
   introspection isn't available.

Practically: **an existing invisible OCR layer is itself a routing signal** — it tells you the page
is scanned *and* that somebody already ran (possibly bad) OCR on it, so a pipeline can either trust
it, quality-check it, or discard it and re-run its own OCR/VLM lane. A firecrawl issue thread
(`firecrawl/pdf-inspector#500`, unverified beyond the issue title/snippet) reports exactly this
failure mode: a converter returning empty markdown because it only read the *invisible* Tr-3 layer
and treated the page as "already has text" without checking visibility.

### Garbled text / mojibake / broken ToUnicode detection

When a PDF's embedded font is a subset with a missing or corrupt `ToUnicode` CMap, extraction
libraries emit raw glyph indices or wrong Unicode code points instead of the visually-correct
characters — text that looks right when rendered but is garbage when copy-pasted or extracted
programmatically
([pypdf mojibake explainer](https://theneuralbase.com/document-ai/errors/pypdf-extract-text-encoding-garbled/),
[Mojibake overview](https://en.wikipedia.org/wiki/Mojibake)). Detection heuristics reported in the
wild:
- Character-class ratio: fraction of extracted characters that are alphanumeric/expected punctuation
  vs. control/private-use/replacement characters (`U+FFFD`) — low "printable ASCII / expected
  punctuation" ratio or any `U+FFFD` presence flags the page as garbled
  ([theneuralbase.com](https://theneuralbase.com/document-ai/errors/pypdf-extract-text-encoding-garbled/)).
- `pdfminer.six` mitigates some of this by decoding glyphs via the font's `/Encoding`/glyph-name
  table instead of trusting a broken `ToUnicode`, which is why the same PDF can extract cleanly in
  pdfminer but garbled in a naive CID-only extractor.
- A concrete, apparently-real routing pattern from a small open-source project (`ui-insight/vandalizer`,
  issue #858 / PR #887, **secondary source, could not verify by reading the diff itself**): a
  "classifier" component explicitly rejects a garbled PDF text layer instead of silently storing it,
  and forces a retry with OCR — i.e., garbled-text detection is wired directly into the routing
  decision, not just logged as a warning.

**Marker's actual, source-verified implementation is the strongest example in this category** (see
below) — it uses a small *learned* model over the extracted page text to output a `good`/`bad` label
(the "OCR error detection" model), rather than a hand-tuned character-class heuristic.

### MinerU

MinerU (opendatalab) explicitly documents that it "automatically detects scanned and garbled PDFs"
before deciding whether to run OCR, using conventional PDF parsing (PyMuPDF-based) for clean pages
and OCR/layout models otherwise
([opendatalab/MinerU](https://github.com/opendatalab/MinerU),
[PyPI mineru 2.0.0](https://pypi.org/project/mineru/2.0.0/)). I was not able to fetch MinerU's
current classify source file directly (old `magic_pdf/filter/pdf_classify_by_type.py` /
`pdf_meta_scan.py` paths 404 on the renamed/restructured repo, and the descriptive blog was
unreachable). Via search-engine-extracted summaries of a third-party technical write-up
(**secondary source, unverified against the file itself** —
[bbs.songma.com/89036.html](https://bbs.songma.com/89036.html), not independently fetchable at time
of writing), MinerU's classifier reportedly combines several named sub-checks whose log messages
include `by_image_area`, `by_text`, `by_avg_words`, `by_img_num`, `by_text_layout`,
`by_img_narrow_strips`, and `by_invalid_chars`:
- `classify_by_avg_words`: average characters per page; classify as text-type (no OCR) if the
  average exceeds ~100 chars/page.
- `classify_by_text_len`: samples pages; if any sampled page exceeds ~100 characters, treat as
  text-type.
- `classify_by_img_num`: a special case for "scanned PDF disguised as image-heavy" — after
  de-duplicating repeated images, checks whether the page actually has very few *distinct* images
  despite a high raw image count (some PDF generators tile the same scan into many small image
  objects), to avoid misclassifying a genuinely text-native PDF as scanned just because it embeds
  many small decorative images.
- Treat the exact thresholds (100 chars) and function names as **secondary-sourced**; the general
  shape (multi-signal vote combining text density, image count/area, garbled-char ratio, and layout
  regularity) is consistent with how the tool is described elsewhere in primary docs.

### Unstructured.io — primary-sourced, read directly from GitHub

Fetched directly from `unstructured/partition/strategies.py` and `unstructured/partition/pdf.py`
(main branch,
[github.com/Unstructured-IO/unstructured](https://github.com/Unstructured-IO/unstructured/blob/main/unstructured/partition/strategies.py)):

```python
def _determine_pdf_auto_strategy(
    pdf_text_extractable: bool = False,
    infer_table_structure: bool = False,
    extract_element: bool = False,
):
    if infer_table_structure or extract_element:
        return PartitionStrategy.HI_RES
    if pdf_text_extractable:
        return PartitionStrategy.FAST
    else:
        return PartitionStrategy.OCR_ONLY
```

`pdf_text_extractable` is computed upstream in `pdf.py` as: run pdfminer-based
`extractable_elements()` over every page, then
`pdf_text_extractable = any(isinstance(el, Text) and el.text.strip() for page_elements in
extracted_elements for el in page_elements)` — i.e. **any non-blank text element anywhere in the
document** flips the whole document to the fast (no-OCR) path; this is a document-level, not
page-level, decision in the open-source `auto` strategy. `determine_pdf_or_image_strategy()` also
implements dependency-aware fallback (if `unstructured_inference` isn't installed, hi_res degrades
to ocr_only or fast; if `pytesseract` isn't installed, ocr_only degrades to fast or hi_res) —
software-availability, not content, driving part of the routing.

A second, independently interesting real heuristic in the same file:
**`is_pdf_too_complex()`** — not about scanned-vs-digital, but about protecting text extraction from
pathological vector-graphics PDFs (CAD/engineering drawings) that would be extremely slow or produce
garbage with PDFMiner:
- Flags a page as "too complex" (falls back to hi_res without attempting text extraction) if its
  content-stream graphics-operator count exceeds `max_graphics_ops=10_000` **and** the
  graphics-to-text operator ratio exceeds `min_graphics_to_text_ratio=20.0`.
- Also fails closed (flags complex) as defense-in-depth against crafted/decompression-bomb content
  streams: per-page decoded-byte cap `DEFAULT_MAX_RAW_STREAM_BYTES = 50 MB`, per-page
  `/Contents` array-entry cap `10,000` (matching pypdf's own cap, explicitly referencing
  **CVE-2026-33123**), document-wide caps of `1 GB` decoded bytes and `1,000,000` array entries.
  This is a genuinely useful pattern for a sorting layer: treat "content stream fails safety/size
  caps" as its own routing verdict (reject/quarantine), separate from and prior to the
  scanned-vs-digital decision.

### Marker — primary-sourced, read directly from GitHub (`datalab-to/marker`, current `master`)

This is the most detailed, most directly reusable OCR-decision logic found in this research. Fetched
`marker/builders/line.py` and `marker/builders/ocr.py` directly
([github.com/datalab-to/marker](https://github.com/datalab-to/marker/blob/master/marker/builders/line.py)).

Marker's `LineBuilder.get_all_lines()` decides **per page** whether embedded ("pdftext") text is
usable or the page needs full OCR, using a *learned* small classifier plus two structural checks —
all three must pass for the page to keep its embedded text:

1. **Learned OCR-error model**: `surya.ocr_error.OCRErrorPredictor` takes the raw extracted page text
   and returns a `good`/`bad` label plus a page-level `P(bad)` score. This is a small model
   (architecture not confirmed beyond being part of the `surya` toolkit — treat "DistilBERT-based"
   framing as unconfirmed) trained specifically to recognize garbled/mojibake/broken-extraction text,
   which sidesteps hand-tuned character-ratio heuristics entirely.
2. **`check_layout_coverage()`**: intersects the layout model's detected block boxes (excluding
   Figure/Picture/Diagram/Table/*Group types) against the PDF's own extracted text-line boxes;
   computes `coverage_ratio = covered_blocks / total_blocks` and requires
   `coverage_ratio >= layout_coverage_threshold (0.25)`. I.e., if the layout model sees content
   regions but the embedded text doesn't actually land inside most of them, the page is presumed
   scanned/image-only even if some stray text exists. A one-block special case handles pages where
   the layout model outputs one big (possibly spurious) text block.
3. **`check_line_overlaps()`**: detects a duplicated/broken text layer (e.g. a bad pre-existing
   invisible OCR layer stacked under a scanned image) by intersecting the page's own provider text
   lines against each other; a line overlapping more than 2 others is "suspect" (a small number of
   overlaps is normal — inline math, stacked fraction/radical glyphs, dense figure labels); if the
   fraction of suspect lines exceeds `overlap_line_fraction_threshold (0.5)`, the page fails.

If all three pass, `document_page.text_extraction_method = "pdftext"`; otherwise `"surya"` (i.e.,
routed to VLM OCR). Beyond the page-level gate, `flag_bad_blocks()` implements a **second, block-level
pass** on pages that did pass as pdftext: individual layout blocks with genuinely empty text (above a
minimum area fraction of 0.01 of the page, and not already covered by a text-bearing sibling block,
and confirmed non-blank by `is_blank_image()` on the cropped region) get flagged for OCR; individual
blocks with *garbled* text (only re-checked if the page's own `P(bad)` was already ≥ 0.05, and only
trusted if the block has ≥ 50 characters — "short labels can't be judged reliably") are re-verified
through the same OCR-error model at block granularity. Finally, a **promotion rule** decides whether
to escalate flagged blocks into a full-page OCR request: in "balanced" mode, *any* flagged block
promotes the whole page to full-page OCR (higher quality, re-read in context); in "fast" mode, only
promote if `bad_blocks / total_blocks > block_ocr_promote_fraction (0.5)`, otherwise repair just the
flagged blocks in place (cheaper). `OcrBuilder` then does a single full-page VLM decode per flagged
page (documented as ~7x faster than N per-block decodes on llama.cpp, due to per-request overhead and
KV-cache contention), with per-page fallback to block-level OCR if the full-page VLM output fails or
loops (`_detect_repeat_loop`, guarding against the same repetition-loop failure mode LlamaIndex
reports in production — see Section 6).

This is directly reusable as a design pattern for a bespoke router: (a) a small learned
garbled/bad-extraction classifier over already-extracted text is cheaper and more robust than regex
heuristics; (b) cross-referencing layout-model boxes against extracted-text boxes catches
"text exists somewhere on the page but isn't where the content is" cases that a pure
text-length check misses; (c) self-overlap of extracted text lines is a cheap, specific signal for
"there's a bad duplicate/legacy OCR layer under this."

### Font / producer-metadata signals (general, not tied to one tool)

- `pdffonts` (poppler-utils) / PyMuPDF `page.get_fonts()` reveal whether fonts are embedded, whether
  they're Type3/bitmap fonts (common in old scan-to-PDF pipelines that fake a "text" layer from
  bitmap glyphs), and whether a `ToUnicode` CMap exists at all — no `ToUnicode` and a CID-keyed font
  is a strong prior for "extraction will be unreliable even though a text layer exists."
- PDF `/Producer` and `/Creator` metadata often reveal the tool that made the file (e.g.
  "Adobe Acrobat", "hp scanner", "ScanSnap", "Skia/PDF" for Chrome print-to-PDF, "LaTeX with
  hyperref"), which is a weak but free prior on document class (scanner software → likely scanned;
  LaTeX → likely a paper with math) usable as a tie-breaker feature in an ensemble router.

---

## 2. Image quality metrics for scanned/photographed pages

### Blur — Laplacian variance

The standard, cheap sharpness proxy: convolve grayscale image with the Laplacian operator and take
`variance()`; low variance ⇒ blurry (few sharp edges)
([PyImageSearch](https://pyimagesearch.com/2015/09/07/blur-detection-with-opencv/),
[GeeksforGeeks](https://www.geeksforgeeks.org/computer-vision/how-to-check-for-blurry-images-in-your-dataset-using-the-laplacian-method/)).
`cv2.Laplacian(gray, cv2.CV_64F).var()`. Reported thresholds vary widely by use case — commonly
cited figures are ~100–150 for document/OCR contexts vs. ~1000 for general photography, but the
consistent advice is to **calibrate on your own corpus** (score a few dozen known-sharp and
known-blurry samples, threshold at the separation point) rather than trust a universal constant
([theailearner.com](https://theailearner.com/2021/10/30/blur-detection-using-the-variance-of-the-laplacian-method/)).
Known failure mode directly relevant to documents: a crisp photo of a mostly-blank or sparse-text
page has few edges and can score as "blurry" under this metric even though it's perfectly in focus —
worth normalizing by text/ink density before thresholding, not using in isolation.

### No-reference IQA: BRISQUE / NIQE

- **BRISQUE**: models natural-scene statistics of locally-normalized luminance coefficients, fits an
  asymmetric generalized Gaussian distribution to them, and maps the fitted parameters to a quality
  score via an SVR trained on human ratings; lower = better
  ([LearnOpenCV](https://learnopencv.com/image-quality-assessment-brisque/),
  [rehanguha/brisque](https://github.com/rehanguha/brisque),
  [krshrimali/No-Reference-Image-Quality-Assessment-using-BRISQUE-Model](https://github.com/krshrimali/No-Reference-Image-Quality-Assessment-using-BRISQUE-Model)).
- **NIQE**: trained only on a corpus of pristine ("natural") images (no human quality labels needed,
  "opinion-unaware"), so easier to (re)train/adapt than BRISQUE, at some cost in
  correlation-with-human-judgment precision.
- Python: `pyiqa` (PyTorch-based IQA toolbox implementing both, plus many other FR/NR metrics),
  simple pip packages like `brisque` and the `EadCat/NIQA` collection implementing BRISQUE/NIQE/
  PIQE/RankIQA/MetaIQA together
  ([EadCat/NIQA](https://github.com/EadCat/NIQA)).
- Important caveat for this use case: BRISQUE/NIQE are trained/calibrated on **natural photographic
  scenes**, not documents; their absolute scores don't transfer cleanly to "will OCR work on this
  page," so treat them as one more feature into a learned router rather than a document-specific
  quality metric on their own.

### Document-specific IQA (DIQA) — trained to predict OCR outcome, not generic perceptual quality

This is the more relevant literature: DIQA models predict OCR accuracy directly from the image,
without running an OCR engine. Key facts from the survey and specific papers:
- "Document Image Quality Assessment: A Survey" frames DIQA methods along two axes: **perception-based**
  (full-reference vs. no-reference, closer to BRISQUE-style) and **understanding/modeling-based**
  (model the actual degradation process, sometimes using an OCR engine's output as a training signal)
  ([ACM Computing Surveys](https://dl.acm.org/doi/10.1145/3606692)).
- **CG-DIQA** ("No-reference Document Image Quality Assessment Based on Character Gradient"): detects
  character-like patches via MSER, computes gradient magnitude within each patch, and uses the
  standard deviation of pooled patch gradients as a sharpness/OCR-suitability score, trained against
  actual OCR accuracy as ground truth
  ([ResearchGate](https://www.researchgate.net/publication/326343099_CG-DIQA_No-reference_Document_Image_Quality_Assessment_Based_on_Character_Gradient)).
- General feature-based approach: extract ~12 features capturing sharpness/focus/edge-clarity/
  geometric distortion, then train a regression surrogate (SVR / ANN / Gaussian Process) mapping
  features → predicted OCR-quality score, useful specifically because it doesn't require running the
  expensive OCR/VLM to get the quality estimate at routing time
  ([emergentmind.com summary](https://www.emergentmind.com/topics/document-image-quality-assessment-diqa),
  [IEEE no-reference high-order-statistics DIQA](https://ieeexplore.ieee.org/document/7532968/)).

This DIQA-as-surrogate-regressor pattern (predict downstream-engine success from cheap upstream
features) is structurally the same idea as the "Pre-Inference Routing" paper in Section 6 — worth
treating as one unified technique: **train a small regressor/classifier on (cheap features) →
(downstream-tool success), and use its output as the routing signal**, rather than hand-picking
thresholds per feature.

### Skew detection

Classic techniques, all pre-deep-learning and cheap: **projection-profile analysis** (rotate
candidate angles, find the angle that maximizes the variance/peakiness of the horizontal projection
histogram — text lines produce sharp peaks when correctly aligned), **Hough transform** (detect
line segments from binarized edges, then take the dominant line-angle as page skew), nearest-neighbor
component clustering, and transition-count/morphology-based methods
([ResearchGate summary of standard techniques](https://www.researchgate.net/publication/226492892_A_Document_Skew_Detection_Method_Using_the_Hough_Transform)).
A **Fast Hough Transform** variant avoids an initial binarization step and computes both
"mostly-horizontal" and "mostly-vertical" line directions with reduced cost, improving applicability
to noisier real-world scans ([arxiv 1912.02504](https://arxiv.org/pdf/1912.02504)). A more recent
adaptive approach (SKLD + Piecewise Projection Profile + Morphological Clustering) targets robustness
across document classes rather than a single fixed global angle
([ResearchGate](https://www.researchgate.net/publication/364426821_A_Novel_Adaptive_Deskewing_Algorithm_for_Document_Images)).
For a sorting layer, the useful output isn't the corrected image — it's the **estimated skew angle
magnitude** itself as a routing feature (large skew ⇒ downgrade confidence in a pipeline parser,
route toward a lane that deskews before OCR, or straight to VLM which is more rotation-tolerant).

### DPI estimation

For scanned/photographed images, DPI is simply `pixel_dimension / physical_size_in_inches`; for a
PDF's embedded raster image, physical size is recoverable from the PDF page's point dimensions
(`72 pt = 1 inch`), giving `DPI ≈ image_pixels_wide / (page_width_pt / 72)` without needing external
metadata (this is the standard way tools like Ghostscript/OCRmyPDF infer effective scan resolution;
general DPI arithmetic reference: [scantips.com](https://www.scantips.com/calc.html)). OCRmyPDF's
own advanced-options documentation encodes a real-world routing consequence of this: **low/unknown
DPI vector-only pages, when force-OCR'd without an explicit `--oversample`, get rasterized at a
default `VECTOR_PAGE_DPI` and OCRmyPDF logs a warning that this may lose resolution**; supplying
`--oversample <DPI>` resamples up before OCR to recover quality
([ocrmypdf docs / advanced features](https://ocrmypdf.readthedocs.io/en/latest/advanced.html); source
logic referenced via [Fossies mirror of `_pipeline.py`](https://fossies.org/linux/OCRmyPDF/src/ocrmypdf/_pipeline.py),
not independently re-read line-by-line here — **treat exact constant names as secondary-sourced**).
A DPI estimate under a corpus-calibrated floor (300 DPI is the conventional "good" scan target per
general scanning guidance) is a reasonable standalone routing feature: very low effective DPI should
downweight a cheap OCR lane in favor of VLM or should trigger `--oversample`-style upsampling first.

### JPEG artifact / noise / contrast — general note

No single widely-cited document-specific tool for JPEG-block-artifact detection turned up distinct
from the generic no-reference IQA literature above; blockiness/ringing detectors exist in the general
IQA literature (e.g., as one of several distortion-specific NIQA variants) but treat this as an area
where BRISQUE/NIQE-style general features, plus simple global-contrast statistics (histogram spread,
Michelson contrast), are the practical starting point rather than a specialized library.

---

## 3. Content-type detectors and layout models

### Layout detection models — speed/accuracy, with sources

| Model | Basis | Reported accuracy | Reported speed | Source |
|---|---|---|---|---|
| **DocLayout-YOLO** | YOLO, doc-specific pretraining + "global-to-local adaptive perception" | mAP 70.3% / 79.7% / 78.8% across benchmark splits | 85.5 FPS (GPU, batch not specified) | [arxiv 2410.12628](https://arxiv.org/abs/2410.12628), [code](https://github.com/opendatalab/DocLayout-YOLO) |
| **PP-DocLayout-L** | RT-DETR-L | 90.4% mAP@0.5 | 13.4 ms/page T4 GPU (~74.6 FPS); ~759.8 ms CPU (~1.3 FPS) | [arxiv 2503.17213](https://arxiv.org/pdf/2503.17213) |
| **PP-DocLayout-M** | RT-DETR, balanced | 75.2% mAP@0.5 | 12.7 ms T4 GPU; ~59.8 ms CPU (~16.7 FPS) | same |
| **PP-DocLayout-S** | RT-DETR, small | (efficiency tier; exact mAP not captured here) | 8.1 ms T4 GPU; **14.49 ms CPU (~69 FPS)**, 1.21M params, measured on Xeon Gold 6271C @ 2.6GHz/8 threads FP16 | same |
| **Docling "Heron" (heron-101)** | RT-DETRv2, ResNet-101 backbone, IBM Research | 78% mAP on DocLayNet (23.9% relative improvement over Docling's prior layout model) | 28 ms/image on a single A100 GPU | [arxiv 2509.11720](https://arxiv.org/html/2509.11720v1), [HF model card](https://huggingface.co/docling-project/docling-layout-heron) |
| **Docling "egret-m"** | (same model family, fastest variant) | slightly lower mAP than heron-101 | 0.024 sec/image (fastest of the 5 new Docling layout models) | same |
| **Surya (layout+OCR unified, v2)** | single 650M-param model, served via vLLM (GPU) or llama.cpp (CPU/Apple Silicon) | 83.3% on olmOCR-bench (best-in-class <3B params); 87.2% avg across a 91-language internal benchmark | 5 pages/s on RTX 5090 | [datalab-to/surya](https://github.com/datalab-to/surya) |
| **YOLOv5 (on DocLayNet)** | YOLOv5 | 0.768 mAP — reported as still the best of the compared models in one study | not captured | [arxiv survey, "Document AI: comparative study"](https://arxiv.org/pdf/2308.15517) |
| **GLAM** | Graph-based layout model | not captured here | **10 ms/page on a single GPU** (vs. 56 ms YOLOv5x6, 687 ms LayoutLMv3 in the same comparison) | search-engine-summarized only, **treat as secondary-sourced**, no direct paper URL captured |

Takeaway for a routing layer: CPU-only layout detection is viable at interactive-ish speed with the
small RT-DETR variants (PP-DocLayout-S: ~14.5 ms/page CPU) or DocLayout-YOLO's lightweight configs,
which matters if the sorting stage must run before any GPU is provisioned.

### Math/formula region detection

MinerU's PDF-Extract-Kit pipeline uses a **YOLOv8-based formula detector (MFD)** specifically
fine-tuned for math regions, reported at **87.7% AP50** on academic papers vs. 60.1% for the prior
Pix2Text-MFD baseline, feeding into **UniMERNet** for LaTeX recognition (0.968 CDM score, comparable
to commercial Mathpix at 0.951)
([arxiv 2409.18839](https://arxiv.org/abs/2409.18839),
[opendatalab/UniMERNet](https://github.com/opendatalab/unimernet)). This is a good concrete example
of "detect region type cheaply with a small YOLO model, then route only that region to a specialized
(expensive) recognizer" — the same pattern this project needs at page level.

### Code-block detection

Not as separately well-covered in the literature as tables/formulas. Docling ships a dedicated
**CodeFormula** enrichment model (`docling-project/CodeFormula` / `docling-project/CodeFormulaV2` on
Hugging Face) that classifies and extracts both code blocks and math formulas as part of its
enrichment pipeline, downloaded via `docling-tools models download` alongside the layout and
tableformer models
([docling advanced options docs](https://docling-project.github.io/docling/usage/advanced_options/),
[HF ds4sd/CodeFormula](https://huggingface.co/ds4sd/CodeFormula),
[dev.to Docling enrichment write-up](https://dev.to/aairom/docling-enrichment-features-94j)). Beyond
this, code-block detection in general document-layout benchmarks (DocLayNet's 11 classes, PP-DocLayout's
23 classes) is typically folded into a generic "Text"/"Code"/"Formula" label taxonomy rather than
having its own dedicated open detector — DocLayNet's category list and construction are described in
[arxiv 2206.01062](https://arxiv.org/abs/2206.01062) / [ACM KDD paper](https://dl.acm.org/doi/10.1145/3534678.3539043).

### Table detection

Not deeply re-researched beyond what's implicit in the layout models above (all of DocLayout-YOLO,
PP-DocLayout, and Docling's Heron/TableFormer stack detect "Table" as a first-class layout region);
Docling additionally runs a dedicated **TableFormer** structure-recognition model after table-region
detection (mentioned in the `docling-tools models download` output: "Downloading tableformer
model..." — [docling advanced options](https://docling-project.github.io/docling/usage/advanced_options/)).
Table Transformer (TATR) and CascadeTabNet, which I intended to compare directly, did not surface
usable comparative numbers in this pass of research — flag as a gap if precise TATR CPU-speed figures
are needed later.

### Handwriting vs. printed text

- CNN-based page/word classifiers are the standard approach: simple 3-4 layer CNNs (3×3 kernels,
  ReLU + final sigmoid) trained to output a binary handwritten/printed label, sometimes at word level
  and sometimes at page level; one reported page-level result is **98.01% mean cross-validated
  accuracy** (specific dataset/paper not captured beyond the aggregator summary — **secondary
  source**, [ResearchGate](https://www.researchgate.net/publication/369471914_Handwritten_Text_Classification_Based_on_Convolutional_Neural_Network)).
- Practical framing from an applied ML paper: in production document-ingestion systems, it's common
  to run **independent printed-text and handwriting recognizers** and use a lightweight upstream
  classifier only to decide which to invoke, rather than one model handling both
  ([arxiv 2003.00838, "A Machine Learning Framework for Data Ingestion in Document Images"](https://arxiv.org/pdf/2003.00838)).
- A production-hosted pretrained option exists (Nyckel's "handwriting vs printed text identifier" —
  a commercial small-classifier API, not open-source/self-hostable per the page content seen;
  [nyckel.com](https://www.nyckel.com/pretrained-classifiers/handwriting-vs-printed-text-identifier/)).

---

## 4. Document image classifiers (page-type / genre)

### RVL-CDIP benchmark — accuracy by model family

RVL-CDIP: 16-category document-type benchmark (resume, invoice, letter, form, scientific paper,
etc.). Reported accuracies:
- Text-only baseline (BERT-base on OCR'd text): **89%**.
- Pure vision transformer, **DiT** (Document Image Transformer): **92%**, using image only, no OCR
  dependency — relevant because it doesn't need a text extraction step at all.
- Multimodal (text + layout + vision) models — **LayoutLMv3: 95.44%**, **Donut (OCR-free, image→text
  generative): 95.30%** — both from the same benchmark round
  ([huggingface.co/blog/document-ai](https://huggingface.co/blog/document-ai)).
- With RVL-CDIP label-noise corrected, LayoutLMv3's *cleaned*-test accuracy rises to **97.32%**,
  underscoring that a meaningful chunk of the "error" on this benchmark is annotation noise, not model
  weakness ([arxiv 2606.31446, "Revising RVL-CDIP: Quantifying Errors and Test-Train Overlap"](https://arxiv.org/html/2606.31446)).
- Donut is notable for this project specifically because it is **OCR-free**: it consumes the raw page
  image and generates structured output directly, which makes it usable as a first-pass page-type
  classifier with no text-extraction dependency at all (useful for routing decisions that must happen
  *before* you know whether the page even has usable embedded/extractable text).

### Zero-shot CLIP / SigLIP for page-type classification

Results are inconsistent and domain-dependent, so treat zero-shot CLIP/SigLIP as a weak/cheap signal,
not a reliable classifier on its own:
- One domain-specific study found CLIP's zero-shot mean accuracy at only **35.69%** on a
  specialized page-type task, attributing failure to prompt ambiguity and page types with no good
  natural-language description ([arxiv 2602.13345, BLUEPRINT](https://arxiv.org/pdf/2602.13345)).
- A narrower, easier binary task (engineering drawing vs. textual document) got CLIP zero-shot up to
  **93.3% accuracy with balanced performance** — showing the technique works when the class
  boundary is visually crisp and prompts are simple, but degrades on fine-grained genre distinctions
  (form vs. invoice vs. scientific paper) ([same source](https://arxiv.org/pdf/2602.13345)).
- SigLIP (sigmoid-loss CLIP variant from Google DeepMind, March 2023) is distributed as an
  image+text encoder pair supporting zero-shot classification with arbitrary label vocabularies and
  serves well as a frozen backbone for downstream fine-tuning
  ([SigLIP 2 paper](https://arxiv.org/pdf/2502.14786), [Roboflow model page](https://roboflow.com/model/siglip)).
- A directly relevant, better-fitting result: **CLIP embeddings + fine-tuned classifier head** for
  page-type classification on real archival material is the subject of a dedicated thesis/paper —
  "Page image classification for content-specific data processing"
  ([arxiv 2507.21114](https://arxiv.org/abs/2507.21114)) — which builds a category taxonomy
  explicitly designed to route pages to different downstream pipelines: separating handwritten vs.
  typed vs. printed text, graphical content (drawings/maps/photos), and layout types (plain
  text/tables/forms), precisely the sorting-layer use case here. A related follow-up,
  "Page image classifier fine-tuned on century-spanning archives of scanned documents for further
  content-specific processing" ([arxiv 2606.07558](https://arxiv.org/pdf/2606.07558)), extends this
  to century-spanning historical archives — worth a closer read if pursuing a from-scratch trained
  page-type classifier, though I did not extract its numeric accuracy figures in this pass.

### Practical hybrid pattern reported in industry write-ups

A "CLIP embeddings + k-NN index as primary classifier, escalate to a VLM only below a confidence
threshold" design was surfaced by search tooling, described as triggering VLM fallback on only ~4%
of pages and reducing direct classification cost roughly 10x vs. VLM-only while recovering most of
the accuracy gap. **I could not re-locate or independently verify the original source URL for this
specific claim in a follow-up search** — mark it clearly as unverified/uncited, but note it as a
directionally sensible and commonly-implemented pattern (cheap embedding + nearest-neighbor gate,
VLM only on low-confidence tail) that shows up in adjacent, verifiable sources too (see Section 6's
tiered-fallback pattern, which is independently and directly sourced).

---

## 5. Language / script detection without full OCR

### fastText language ID (`lid.176`)

Facebook's fastText ships pretrained language-ID models covering **176 languages**, trained on
Wikipedia + Tatoeba + SETimes text, distributed in two sizes: `lid.176.bin` (126 MB, faster and
slightly more accurate) and `lid.176.ftz` (917 KB, compressed, for constrained environments)
([fasttext.cc/docs/en/language-identification.html](https://fasttext.cc/docs/en/language-identification.html),
[fastText GitHub docs](https://github.com/facebookresearch/fastText/blob/main/docs/language-identification.md)).
Usage is `model.predict(text)` → `(label, confidence)`, expects UTF-8 input, and works on any text
you already have (e.g. OCR/extraction output, or embedded PDF text) — it is not itself an image-based
tool, so for a page whose script you don't yet have text for, it's only usable *after* some text has
been extracted or lightly OCR'd, not as a pre-OCR gate on its own.

For explicit **script** (as opposed to language) identification, the newer NLLB-derived LID model
uses combined codes like `eng_Latn`, `ukr_Cyrl` (ISO 639-3 + ISO 15924 script code), giving script
directly where the original `lid.176` model does not separate script from language
([NVIDIA NeMo Curator docs on language ID](https://docs.nvidia.com/nemo/curator/latest/curate-text/process-data/language-management/language.html)).

### Script detection without any text extraction

The genuinely pre-OCR approach (relevant when you don't yet trust or have any extracted text) is
**Unicode block / codepoint-range classification** on whatever raw bytes you can get (e.g., a thin,
fast OCR pass, or embedded PDF `ToUnicode` hints even if the visual rendering is unreliable): CJK
ideographs, Hangul, Arabic/Hebrew (RTL) blocks, Devanagari, Cyrillic, etc. each occupy distinct
Unicode ranges, so a coarse script tag can be assigned from any codepoints you can recover cheaply,
before running a full language-ID model on cleaner text. This is standard practice but I did not find
a single canonical open-source "reference" implementation worth citing distinctly from the general
Unicode-block-lookup approach; treat it as an established technique rather than a specific tool.

---

## 6. Routing architectures

### The core industry pattern: tiered/cascaded fallback with calibrated confidence

The clearest, most directly citable synthesis of production practice is a 2026 engineering guide
("The Definitive Guide to OCR in 2026: From Pipelines to VLMs" —
[slavadubrov.github.io/blog/2026/03/04/ocr-guide](https://slavadubrov.github.io/blog/2026/03/04/ocr-guide/),
fetched directly). Its **tiered fallback pattern**:

> 0. Check for embedded text (Tier 0) — inspect the text layer with PyMuPDF/pdfplumber before
>    rasterizing, but validate the layer is complete and correctly ordered.
> 1. Attempt with a fast/traditional engine for document classes it's known to handle.
> 2. Evaluate calibrated confidence — combine model confidence with document class, field
>    criticality, and validation rules (not raw OCR confidence alone).
> 3. Escalate uncertain pages to a specialized or general VLM.
> 4. Escalate high-risk failures (cost-of-error exceeds automation benefit) to a human reviewer as a
>    separate tier.

Key implementation details, quoted/paraphrased directly from the source:
- **Area-weighted confidence aggregation** is explicitly recommended over a naive mean, so a single
  wrong high-area field (e.g. a wrong total) isn't diluted by many small, easy, high-confidence
  tokens:
  ```python
  def area_weighted_confidence(page):
      total_area, weighted_sum = 0, 0
      for (x_min, y_min, x_max, y_max), score in zip(page["rec_boxes"], page["rec_scores"]):
          area = (int(x_max) - int(x_min)) * (int(y_max) - int(y_min))
          weighted_sum += score * area
          total_area += area
      return weighted_sum / total_area if total_area > 0 else 0
  ```
  But the same source explicitly warns this is "a baseline for page-level aggregation, not a
  universal router" — calibrate against labeled pages, and give critical fields (IDs, totals) their
  own independent validation rather than relying on an averaged score.
- **A tiered architecture separates CPU preprocessing from GPU/API inference**, reserving the
  expensive path only for documents that actually need it (diagram in source: PDFs test embedded
  text first; images and failed-text-check pages continue through preprocessing into progressively
  stronger OCR paths, then post-processing/human review).
- **No universal cost break-even exists** between self-hosted and API-based OCR/VLM lanes — the
  guide gives a concrete cost model: `monthly_pages × cost_per_successful_page + review_cost +
  fixed_operating_cost`, with "successful page" held to the *same* quality bar across both paths
  (retries, human review, and fixed ops cost must all be included, not just per-call API price).
- **Validation against hallucination**: because VLM extraction errors can be internally consistent
  yet factually wrong (a receipt total that's arithmetically self-consistent but reads the wrong
  digit off the image), the guide recommends: arithmetic reconciliation of totals within rounding
  tolerance, regex sanity checks (impossible dates/phone formats), cross-model verification of
  critical fields, and independent second-pass OCR cross-checks — agreement across two
  *differently-failing* methods raises confidence; agreement alone is not proof of correctness.

### Pre-inference routing — direct experimental evidence for cost-aware routing on document features

**"Pre-Inference Routing for Cost-Efficient Document Field Extraction"**
([arxiv 2608.06607](https://arxiv.org/pdf/2608.06607), fetched and read directly) is the single most
load-bearing source for this section: it directly tests whether document difficulty (and hence,
which extractor a page should be routed to) can be predicted **before** running any extraction call,
purely from cheap document-intrinsic features. Findings:
- Routing cuts cost **31–33% on receipts** and **77% on degraded ad-buy forms** vs. always using the
  stronger/more expensive extractor, while holding accuracy roughly constant — but **only when two
  conditions both hold**: (a) a non-trivial fraction of documents are genuinely hard for the cheap
  model, and (b) that difficulty is visible in cheap, pre-inference features. Absent either
  condition (e.g. clean digital invoices with no feature-detectable difficulty — DocILE dataset),
  routing provides **no benefit** ("no signal").
- Router is a **calibrated random forest (isotonic calibration)** over **13 hand-engineered,
  leakage-free features**, computed only from the image, OCR text, or OCR box geometry — never from
  ground-truth. Full feature table (their Table cited directly):

  | Family | Feature | Description |
  |---|---|---|
  | OCR quality | `ocr_conf` | mean per-token OCR confidence |
  | OCR quality | `ocr_std` | std. of per-token OCR confidence |
  | OCR quality | `ocr_stage` | preprocessing stage needed to read the image |
  | OCR quality | `short_token_ratio` | fraction of tokens < 2 characters |
  | OCR quality | `inv_chars_per_word` | inverse mean chars/token (fragmentation) |
  | Image quality | `blur_score` | variance of the image Laplacian (sharpness) |
  | Image quality | `image_contrast` | global pixel-intensity contrast |
  | Image quality | `word_height_cv` | coefficient of variation of word-box heights |
  | Layout | `crowded_line_frame` | fraction of lines with > 3 words |
  | Layout | `line_density` | text lines per unit page height |
  | Layout | `aspect_ratio` | page height / width |
  | Content/structure | `item_density` | line-items per text line (table density proxy) |
  | Content/structure | `tokens` | total OCR token count |

- Ablation: the full 13-feature model beats a single-feature (`ocr_conf`-only) rule by **+0.156**
  (pooled CORD+SROIE; 0.707 vs. 0.551), and beats every single-family subset (OCR-only, image-only,
  layout-only, content-only), confirming that no one feature family dominates — a router needs
  cross-family signal.
- Feature importance ranking: `inv_chars_per_word` (token fragmentation) ranked highest (+0.082),
  then `item_density` (+0.037, table/structure density), then `ocr_std` (+0.018); simple image
  quality features like `blur_score` contributed comparatively little on their own in this study.
- Generalizes across two different cheap/expensive model pairs at **5× and 3× cost differentials**,
  and the paper explicitly frames this as a way for a small labeled pilot to predict, **before full
  deployment**, whether pre-inference routing will pay off for a given document genre — directly
  answering "should we even build a router for this document type."

This is the strongest evidence-backed template for this project's own router: build a small feature
set spanning OCR-quality/image-quality/layout/content families (many of which overlap directly with
the image-quality metrics in Section 2 and layout features in Section 3), train a calibrated
classifier against actual downstream success/failure, and validate on a labeled pilot before
committing to full-scale routing — rather than hand-setting thresholds per feature.

### Cost-quality gap and production VLM economics

**"Closing Cost-Quality Gap in Document VLMs: Difficulty-Aware Data Curation and Quality-Adjusted
Deployment Economics"** ([arxiv 2609.01575](https://arxiv.org/html/2609.01575v1)) describes a
deployed document-understanding system built around a **Mixture-of-Experts VLM (35B total params,
3B active)**, fine-tuned on production data using **difficulty-aware data curation** — i.e., the same
difficulty-estimation idea from the routing paper above, but applied to *training data selection*
rather than runtime routing. Not fetched in full depth in this pass; flagged for deeper follow-up if
VLM fine-tuning/curation strategy becomes in-scope.

**"Cluster, Route, Escalate: Cascaded Framework for Cost-Aware LLM Serving"**
([arxiv 2606.27457](https://arxiv.org/html/2606.27457)) — general (not document-specific) two-stage
cascade: stage 1 routes queries to the most cost-effective model by clustering; stage 2 escalates
low-confidence outputs to a stronger model. Relevant as a general architecture reference for the
escalation-on-low-confidence pattern, but not document-specific — treat as background, not a primary
source for this project's page-level routing.

General LLM-routing cost figures cited in adjacent (non-document-specific, **secondary/aggregator
sourced**) material: RouteLLM reportedly achieves ~85% cost reduction while retaining ~95% of GPT-4-tier
performance; FrugalGPT reportedly achieves up to 98% cost reduction via cascade routing; a third
source frames routing as generally cutting inference cost 40–70%
([NeuralTrust blog](https://neuraltrust.ai/blog/llm-model-routing),
[TrueFoundry blog](https://www.truefoundry.com/blog/llm-routing-cost-quality-aware-model-selection),
[ResumeLens blog](https://www.resumelens.org/blog/ai/llm-routing-cascades)) — these are general LLM
API-routing figures, not document-page-routing figures specifically; useful only as directional
context for how much cost cascading typically saves in adjacent domains.

### Production failure modes that a router/fallback layer must defend against

LlamaIndex's engineering post-mortem on LlamaParse (their VLM-powered document parsing product) is a
concrete, directly-fetched account of two failure modes that broke production OCR/parsing pipelines
and the fixes they shipped
([llamaindex.ai/blog/engineering-insights-failure-modes-that-break-vlm-powered-ocr-in-production](https://www.llamaindex.ai/blog/engineering-insights-failure-modes-that-break-vlm-powered-ocr-in-production),
fetched directly, Apr 8 2026):
- **"Infinite loop" / repetition-loop errors**: a VLM gets stuck emitting whitespace/repeated tokens,
  causing latency spikes and token-usage blowups that cascade into stalling the whole agent fleet
  waiting on those jobs, exhausting concurrent-connection capacity network-wide. Mitigation: model
  cutover fallback (switch models on detected repetition) and (implicitly, per the Marker source
  above) a `_detect_repeat_loop()`-style output check that drops/retries repetitive output rather than
  accepting it.
- **"Hard stop" / recitation & content-filter errors**: provider-side copyright/recitation filters can
  abruptly kill generation on boilerplate/standardized text that merely *resembles* copyrighted
  material (public laws, technical standards), and providers often still bill for the killed
  request. Mitigations shipped: **finish-reason routing** (parse `finish_reason`/`RECITATION`/
  `content_filter` from every API response and treat it as a distinct, cleanly-propagated error rather
  than letting it crash the pipeline or trigger a blind retry loop), with **nested-retry-explosion
  guards**, and **dynamic temperature adjustment on retry** (inject entropy so the retried generation
  paraphrases rather than reproduces verbatim, which tends to evade the recitation filter while
  preserving factual content).

These are exactly the class of failure a "VLM OCR lane" in this project's router needs explicit
handling for — not just a confidence threshold, but response-level defenses (repeat-loop detection,
finish-reason inspection, retry budgeting) wrapped around any expensive VLM call.

### Commercial routing/tiering products (context, not architecture detail)

- **LlamaParse** offers multiple "Parsing Tiers" trading cost/accuracy/latency, plus "auto-routing"
  for cost efficiency at scale ([llamaindex.ai compare page](https://www.llamaindex.ai/compare/llamaparse-vs-reducto)).
- **Reducto** frames itself as a multi-pass "Agentic OCR" architecture: CV + multiple VLMs, plus a
  distinct review pass explicitly modeled on a human editor re-checking the parse before output —
  i.e., a built-in verification stage after extraction, not just before it
  ([reducto.ai compare page](https://reducto.ai/compare/reducto-vs-llamaparse)). Both are commercial,
  closed-implementation products — cite as directional evidence that a review/verification pass is
  considered production-necessary, not as a source of reusable technique detail.

### Synthesis: recommended shape for this project's router (not from any single source; my synthesis of the above)

1. **Segment first, route per-page, not per-document** — several sources above (Docling's per-cluster
   OCR decision, Marker's per-page-then-per-block cascade, the pre-inference routing paper's
   page-level feature set) converge on treating routing as a per-page (sometimes per-region)
   decision, since mixed documents (e.g. a born-digital cover page + scanned appendix) are common and
   Unstructured's document-level `any()` gate is called out in its own source as a coarser
   compromise.
2. **Compute a small, cross-family feature vector per page before any expensive call**: embedded-text
   presence/coverage/invisibility (Section 1), blur/skew/DPI/contrast (Section 2), layout-model
   region counts and text-coverage-of-regions (Section 3, reusing Marker's `check_layout_coverage`
   idea), and OCR-quality features if a cheap first-pass OCR is already available (Section 6's
   13-feature table is a ready-made starting schema).
3. **Use a calibrated classifier/regressor, not hand-set thresholds**, trained against actual
   downstream lane success (isotonic-calibrated random forest is what the most directly-relevant
   paper used, and it's cheap to train/retrain as labeled failures accumulate).
4. **Validate on a small labeled pilot before full rollout**, per the routing paper's explicit
   recommendation — and be willing to *not* route (always use one lane) for document genres where
   the pilot shows no feature-detectable difficulty gap, since routing overhead isn't free and
   provides zero benefit in that regime.
5. **Wrap the expensive (VLM) lane in explicit failure-mode defenses**: repeat-loop detection,
   finish-reason/content-filter handling, bounded retries with backoff/temperature jitter, arithmetic
   /regex sanity-checks on extracted fields, and treat "security/DoS-shaped" inputs (Unstructured's
   `is_pdf_too_complex` complexity/size caps) as a routing verdict of their own, evaluated before
   the scanned-vs-digital decision.
6. **Keep a human-review tier** for the tail where the cost of an automation error exceeds the
   automation benefit — every credible production source above (OCR guide, Reducto, LlamaParse) keeps
   this as an explicit final tier rather than trying to close the gap purely with a stronger model.
