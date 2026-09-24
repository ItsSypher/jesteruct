# Datalab tooling research (Marker / Surya / Chandra) — Sept 2026

Scope: informing a document-routing layer with lanes: born-digital, scanned,
handwritten, table-heavy, math/equations, forms, code, image-heavy, degraded
quality, multilingual, mixed.

All source code excerpts below were pulled directly from
`git clone https://github.com/datalab-to/marker` at commit dated
2026-09-13 (tag `v2.0.0`, current `master`). Where a claim comes from a
web-search-summarized page rather than a primary source I've fetched myself,
I've flagged it "(secondary, unverified in full)".

---

## 1. Marker modes, flags, converters, output formats

Source: https://github.com/datalab-to/marker (README, fetched via
raw.githubusercontent.com/datalab-to/marker/master/README.md) plus direct repo
inspection of `marker/providers/pdf.py`, `marker/builders/layout.py`,
`marker/processors/llm/*`, `marker/converters/*`.

### CLI flags (confirmed in source, not just README prose)

- `--force_ocr` — `marker/providers/pdf.py` field `force_ocr: bool`, doc
  "Whether to force OCR on the whole document." Used by
  `marker/builders/layout.py` (`LayoutBuilder.__call__`): in balanced mode
  + force_ocr, the layout pass is skipped entirely and every page is rebuilt
  by full-page OCR ("don't pay for a layout pass that gets thrown away").
  In fast mode it still needs layout boxes to drive block-mode OCR.
  https://github.com/datalab-to/marker/blob/master/marker/builders/layout.py
  https://github.com/datalab-to/marker/blob/master/marker/providers/pdf.py

- `--strip_existing_ocr` — `marker/providers/pdf.py` field
  `strip_existing_ocr: bool` = False, "Whether to strip existing OCR text
  from the PDF." Useful for scans that already carry a bad/garbled invisible
  text layer from a prior OCR pass (e.g. a scanner's built-in OCR) — this
  discards it so Marker re-OCRs cleanly rather than trusting bad embedded
  text. https://github.com/datalab-to/marker/blob/master/marker/providers/pdf.py

- `--redo_inline_math` — exists on TWO processors:
  `marker/processors/llm/llm_mathblock.py` (`LLMMathBlockProcessor`) and
  `marker/processors/llm/llm_equation.py` (`LLMEquationProcessor`). Doc:
  "If True, the inline math will be re-done, otherwise left as is. Requires
  use_llm. Balanced mode already OCRs inline math natively (see
  EquationProcessor.ocr_inline_math); this is mainly useful with fast mode
  or a different LLM." So: balanced mode already handles inline math without
  this flag; the flag matters for fast mode or when using a non-default LLM.
  https://github.com/datalab-to/marker/blob/master/marker/processors/llm/llm_mathblock.py

- `--use_llm` — enables an LLM postprocessing pass. Default service is
  Google Gemini (`marker.services.gemini.GoogleGeminiService`); other
  supported services confirmed in README: Google Vertex, Ollama (local),
  Claude (Anthropic API), OpenAI-compatible endpoints, Azure OpenAI,
  OpenRouter. It activates a family of `marker/processors/llm/*`
  block-specific processors — confirmed directory listing:
  `llm_complex.py, llm_equation.py, llm_form.py, llm_handwriting.py,
  llm_image_description.py, llm_mathblock.py, llm_meta.py,
  llm_page_correction.py, llm_sectionheader.py, llm_table.py,
  llm_table_merge.py`.
  https://github.com/datalab-to/marker/tree/master/marker/processors/llm

  - **Forms**: `LLMFormProcessor` (`block_types = (BlockTypes.Form,)`) sends
    the form's HTML + block image to the LLM with a prompt that asks it to
    reproduce label/value pairs as an HTML table with labels on the left,
    values on the right, and to answer "No corrections needed" if nothing's
    wrong (a hallucination-guard pattern).
    https://github.com/datalab-to/marker/blob/master/marker/processors/llm/llm_form.py
  - **Handwriting**: `LLMHandwritingProcessor`
    (`block_types = (BlockTypes.Handwriting, BlockTypes.Text)`) — this is the
    dedicated handwriting path; it only fires on `BlockTypes.Handwriting`
    blocks (a layout-model label) or on `Text` blocks with zero lines/text
    (i.e. a text region pdftext found nothing readable in). Prompt asks for
    faithful markdown reproduction, including turning form-like label/value
    pairs into markdown tables. **Handwriting quality is therefore gated on
    both (a) the layout model correctly labeling the region as Handwriting,
    and (b) `--use_llm` being on** — without `--use_llm`, handwriting blocks
    just get generic OCR from Surya, which is not tuned for cursive/messy
    writing.
    https://github.com/datalab-to/marker/blob/master/marker/processors/llm/llm_handwriting.py
  - **Table merging across pages / adjacent tables**:
    `LLMTableMergeProcessor` — geometric heuristics decide candidate pairs
    (`table_height_threshold=0.6`, `vertical_table_height_threshold=0.25`,
    `vertical_table_distance_threshold=20px`,
    `horizontal_table_width_threshold=0.25`,
    `horizontal_table_distance_threshold=10px`,
    `column_gap_threshold=50px`), then an LLM call confirms/merges. Flag
    `no_merge_tables_across_pages` disables it.
    https://github.com/datalab-to/marker/blob/master/marker/processors/llm/llm_table_merge.py

- `--disable_ocr` — pure text-layer extraction, no VLM/inference server at
  all; forces the lightweight CPU layout detector
  (`LayoutBuilder.disable_ocr`). Confirmed: "Pure text-layer path (no VLM).
  Forces the lightweight rf-detr layout detector so the whole pipeline runs
  on CPU without an inference server."
  https://github.com/datalab-to/marker/blob/master/marker/builders/layout.py

- `--page_range` — confirmed in `marker/config/parser.py`
  (`case "page_range": config["page_range"] = parse_range_str(v)`), format
  "0,5-10,20". https://github.com/datalab-to/marker/blob/master/marker/config/parser.py

- `--converter_cls` — selects converter class; confirmed in
  `marker/config/parser.py get_converter_cls()`.

- `--mode [balanced|fast]` — balanced defaults on GPU, fast on CPU/MPS
  (README + confirmed via `LayoutBuilder.mode` docstring: "'balanced' (GPU)
  uses the VLM layout model; 'fast' (CPU) uses the lightweight
  rf-detr/onnx layout detector").

- Other README-documented flags I did not independently verify in source
  (secondary, but README is a primary doc so reasonably trustworthy):
  `--disable_image_extraction`, `--keep_pageheader_in_output`,
  `--keep_pagefooter_in_output`, `--block_correction_prompt`,
  `--processors`, `--config_json`, `--debug`.

### Converters

- `PdfConverter` (default) — full pipeline. `marker/converters/pdf.py`.
- `TableConverter` — table-only extraction; same config surface as
  PdfConverter. Confirmed: `marker/converters/table.py` sets
  `layout_builder.force_ocr = False` explicitly (tables never force full
  OCR even if global force_ocr is set — presumably to keep the text-layer
  table reconstruction path available). Reconstructs digital tables from
  the PDF text layer; scanned tables go through the VLM.
  https://github.com/datalab-to/marker/blob/master/marker/converters/table.py
- `OCRConverter` — OCR-only path; `--keep_chars` preserves per-character
  boxes for digital PDFs.
- **`ExtractionConverter` (structured JSON-schema extraction) — IMPORTANT:
  this class existed in Marker 1.x** (confirmed present at
  https://github.com/datalab-to/marker/blob/v1.10.2/marker/converters/extraction.py,
  using Pydantic-schema-driven extraction via `DocumentExtractor`/
  `PageExtractor`/`ExtractionRenderer`) **but is ABSENT from the Marker 2.0
  rewrite** — I grepped the full v2.0.0/master tree for "Extraction" and got
  zero matches (`marker/converters/` in master only contains
  `__init__.py, ocr.py, pdf.py, table.py` — no `extraction.py`). Several
  blog posts / SEO articles describe `ExtractionConverter` and JSON-schema
  extraction as if current — that's stale, describing Marker 1.x. As of
  Sept 2026, schema-based structured extraction is offered instead through
  Datalab's **hosted API** (see §7), not the open-source `marker` package.
  Verify against the exact pip version you install before relying on this.

### Output formats

`markdown`, `json`, `html`, `chunks` (flattened list of top-level blocks
per page with full HTML, aimed at RAG — no tree traversal needed).
Confirmed via README.

### Batch / multi-GPU throughput (per README + Marker 2 blog)

- Single GPU: one vLLM server auto-managed, CPU worker pool budgeted to
  GPU capacity.
- Multi-GPU single machine: `VLLM_GPUS=0,1,2,3` spans one inference server
  across GPUs.
- Multi-machine: shard file lists with `--num_chunks <N> --chunk_idx <i>`,
  each node runs its own server.
- CPU-only: `marker /folder --disable_ocr`.
- Sustained throughput, single B200 GPU (from datalab.to/blog/marker-2):
  fast+no-OCR 23.7 pages/s, fast 7.4 pages/s, balanced 2.9 pages/s.
  https://www.datalab.to/blog/marker-2

---

## 2. How Marker decides whether to OCR a page — exact heuristics (source-verified)

This is the most directly useful section for the router. Full source:
https://github.com/datalab-to/marker/blob/master/marker/builders/line.py
(`LineBuilder`) and
https://github.com/datalab-to/marker/blob/master/marker/builders/ocr.py
(`OcrBuilder`).

**Page-level decision** (`LineBuilder.get_all_lines`): a page's embedded
(pdftext) text is accepted (`text_extraction_method = "pdftext"`) only if
ALL of the following hold; otherwise the whole page is flagged
`text_extraction_method = "surya"` and gets full-page VLM OCR:

1. `bool(provider_lines)` — pdftext actually returned lines (non-empty text
   layer).
2. `not ocr_errors_detected` — a dedicated model,
   `surya.ocr_error.OCRErrorPredictor`, classifies the page's extracted
   text as "good" or "bad" and also returns a page-level `P(bad)` score.
   This is a general text-quality classifier (garbled/mojibake/encoding
   issues), not a rule list.
3. `check_layout_coverage(...)` — cross-references pdftext line boxes
   against layout-detected block boxes. Excludes Figure/Picture/Diagram/
   Table/FigureGroup/TableGroup/PictureGroup from the denominator. A block
   counts "covered" if ≥`layout_coverage_min_lines` (default 1) pdftext
   lines intersect it. Passes if `covered_blocks / total_blocks >=
   layout_coverage_threshold` (default **0.25**). Special case: if there's
   exactly one large text block that looks blank, it's treated as OK (avoids
   false-flagging genuinely blank pages).
4. `check_line_overlaps(...)` — detects a duplicated/broken text layer
   (e.g. a bad prior OCR pass baked into the PDF): if a pdftext line
   overlaps >2 other lines it's "suspect" (a little overlap is normal for
   inline math/figure labels); if the fraction of suspect lines exceeds
   `overlap_line_fraction_threshold` (default **0.5**), the page fails.
   Also rejects pages where any line's bbox falls outside the page bounds
   (+5px margin).

**Block-level repair** (`LineBuilder.flag_bad_blocks`, runs only on pages
that passed the page-level check): flags individual blocks bad, then:
- An **empty** block is only sent for OCR if its area exceeds
  `min_ocr_block_area_fraction` (0.01 of page area) AND its image crop is
  not blank (`is_blank_image`) AND it isn't ≥`empty_block_contained_threshold`
  (0.75) contained inside a sibling block that already has text (avoids
  duplicate OCR of overlapping layout boxes, e.g. line-numbered transcripts).
- A **non-empty** block is only re-checked for garbling if it has
  ≥`min_garbled_text_chars` (50) characters, AND only if the page's overall
  `P(bad)` from the OCR-error model is ≥`block_garbled_check_min_page_score`
  (0.05) — i.e. the expensive per-block recheck is skipped entirely on
  confidently-clean pages.
- **Promotion to full-page OCR**: in `balanced` mode, ANY flagged block
  promotes the whole page to full-page OCR (`promote_fraction = 0.0` —
  re-reading in context is considered higher quality). In `fast` mode, the
  page is only promoted if more than `block_ocr_promote_fraction` (0.5, i.e.
  >50%) of its text blocks are bad; otherwise the flagged blocks are
  repaired individually (cheaper, no full-page decode).

**Reading order**: pdftext pages are ordered by the PDF's own character
stream position (`span.minimum_position`), not the layout model's spatial
guess, because — per the code comment — this "beat surya's learned order
head on multi-column pages (olmocr-bench order tests: 75% vs 56%)". OCR'd
pages get reading order from the full-page OCR output directly.
https://github.com/datalab-to/marker/blob/master/marker/builders/line.py

**Related "bad text" thresholds live in `marker/providers/pdf.py`** (used
elsewhere in text extraction, e.g. per-line/page invalid-character ratios):
`ocr_space_threshold=0.7` ("minimum ratio of spaces to non-spaces to detect
bad text"), `ocr_newline_threshold=0.6`, `ocr_alphanum_threshold=0.3`,
`ocr_invalid_chars=(chr(0xFFFD), "�")`, `image_threshold=0.65` ("minimum
coverage ratio of the image to the page to consider skipping the page" —
i.e. a page that's basically one giant image).
https://github.com/datalab-to/marker/blob/master/marker/providers/pdf.py

**Router implication**: Marker's own page-quality signal
(`page.ocr_errors_detected` / the OCR-error model's `P(bad)`, plus layout
coverage ratio and line-overlap fraction) is essentially a reusable
"scanned/degraded vs born-digital" classifier that could be run standalone
(via `surya.ocr_error.OCRErrorPredictor`) as a cheap page-triage step ahead
of full conversion, rather than only reading it out after a full Marker run.

---

## 3. Surya

Source: https://github.com/datalab-to/surya (README fetched via raw
githubusercontent) + https://www.datalab.to/blog/marker-2 (Surya 2 details).

- **Architecture (Surya 2)**: layout, OCR, and table recognition share one
  vision-language model (~650M params, "Qwen3.5-style"), trained to emit
  either layout JSON or full-page HTML depending on prompt. Text-line
  detection is a separate small model (modified EfficientViT/segformer)
  trained from scratch on line annotations. (secondary — summarized from
  README, not independently code-verified.)
- **OCR languages**: 90+ (README title says "90+ languages"; one
  secondary summary quoted 91 with per-language pass rates on some
  internal benchmark — treat exact language count/scores as
  unverified-in-detail, but "90+ languages, sizable multilingual support"
  is a safe, repeatedly-confirmed claim).
- **Layout detection labels** (secondary summary, not directly grepped
  from surya's source in this pass): Caption, Footnote, Equation,
  ListGroup, PageHeader, PageFooter, Picture, SectionHeader, Table, Text,
  Figure, Code, Form, TableOfContents, ChemicalBlock, Diagram,
  Bibliography, BlankPage. This lines up well with Marker's own
  `BlockTypes` enum, which I did verify directly in
  https://github.com/datalab-to/marker/blob/master/marker/schema/__init__.py:
  `Line, Span, Char, FigureGroup, TableGroup, ListGroup, PictureGroup, Page,
  Caption, Code, Figure, Footnote, Form, Equation, Handwriting,
  TextInlineMath, ListItem, PageFooter, PageHeader, Picture, SectionHeader,
  Table, Text, TableOfContents, Document, ComplexRegion, TableCell,
  Reference, Bibliography, ChemicalBlock, Diagram`. Note **`Handwriting` and
  `TextInlineMath` are distinct block types** — directly relevant to
  routing (a page can be classified by which block types its layout pass
  emits: presence of `Handwriting` → handwritten lane; `Code` → code lane;
  `Table`/`TableGroup` → table lane; `Equation`/`TextInlineMath` → math
  lane; `Form` → forms lane).
- **Reading order**: layout output includes position indices for reading
  order reconstruction on multi-column pages (see also §2 — Marker's own
  benchmark says the raw pdftext char order actually beats Surya's learned
  reading-order head on multi-column layouts).
- **Table recognition**: row/column detection with cell positions derived
  from intersections; can also emit full HTML (better for spanning
  cells/headers).
- **Math/LaTeX**: Surya 2 does NOT have a separate LaTeX-OCR pass anymore —
  math is recognized inline as part of full-page OCR, returned in
  `<math>...</math>` tags, KaTeX-compatible LaTeX, alongside surrounding
  prose in the same HTML output. (This is a change from older Surya
  versions that had a standalone LaTeX OCR model — treat any "Surya has a
  separate LaTeX OCR mode" claim as outdated for Surya 2 / Sept 2026.)
- **Speed**: RTX 5090 ~5.35 pages/sec; Apple Silicon ~0.108 pages/sec
  (secondary, from a summarized blog/README source — order-of-magnitude
  credible given Marker's own B200 numbers, but I did not independently
  verify these exact figures against a primary benchmark table).
- **Benchmark**: 83.3% olmOCR-bench, described as "top under 3B params"
  (secondary).
- **License**: code Apache 2.0; weights under modified "AI Pubs Open
  Rail-M" — free for research/personal/startups under $5M funding or
  revenue (this $5M figure is corroborated independently for Marker's own
  weights license — see §6).
- **CLI / API**: `surya_ocr`, `surya_layout`, `surya_table` CLIs;
  Python API `RecognitionPredictor`, `LayoutPredictor`, `TableRecPredictor`;
  `surya_gui` Streamlit app.
- **Page classification**: no dedicated "classify this page's document
  type" feature found in Surya's own docs — its output (layout labels +
  OCR-error score, see §2) is the closest thing, and that's what a router
  would consume rather than a purpose-built classifier.

---

## 4. Chandra

Sources: https://github.com/datalab-to/chandra (fetched directly),
https://huggingface.co/datalab-to/chandra-ocr-2 (model card, fetched
directly), https://www.datalab.to/blog/chandra-2 (fetched directly),
https://www.datalab.to/blog/introducing-chandra (Chandra 1 announcement,
not separately fetched in full this pass).

- **What it is**: a full-page OCR **VLM** (not a pipeline like Marker) that
  converts images/PDFs directly to structured HTML/Markdown/JSON while
  preserving layout — one model call per page rather than Marker's
  detect-then-selectively-OCR pipeline.
- **Capabilities** (from GitHub README): "handles complex tables, forms,
  handwriting with full layout" — explicitly markets itself on exactly the
  hard cases: cursive/handwritten notes, form field reconstruction
  including checkboxes, complex tables, math notation (including
  handwritten equations and math in non-Latin scripts), diagrams/images
  with captions, multi-column layout preservation.
- **Versions**:
  - Chandra 1 (per blog, ~Oct 2025): 9B params, olmOCR-bench 83.1±0.9.
  - **Chandra 2** (per blog, ~March 2026, and HF model card): model card
    states **5B params (BF16)**; the blog/GitHub summaries said "4B" — this
    is a real discrepancy between the model card I fetched directly
    (huggingface.co/datalab-to/chandra-ocr-2, says 5B) and the blog/GitHub
    secondary summaries (say 4B, "down from 9B, 2x throughput"). **Flag as
    unverified/conflicting — confirm exact parameter count before citing a
    specific number.**
  - olmOCR-bench overall: **85.8 ± 0.8** (model card) / "85.9%" (blog,
    rounding) — state of the art claim for open-weight OCR models as of the
    blog's publish date. Category breakdown (model card / blog):
    ArXiv 86.9–90.2, old-scans-math 89.1–89.3, tables 89.9–92.1,
    multi-column 83.5. (Small numeric spread between the two sources —
    likely different eval runs/rounding; both are Datalab's own numbers.)
  - Multilingual: 43-language average 77.8% (Chandra 2) vs Gemini 2.5
    Flash 67.6%, GPT-5 Mini 60.5%; full 90-language average 72.7%. Biggest
    jumps vs Chandra 1 in South Asian/Indic scripts (Bengali +27.2,
    Kannada +42.6, Malayalam +46.2, Tamil +26.9, Telugu +39.1) and RTL
    (Arabic +34.4, Hebrew +31.5).
  - **Hosted API version scores higher than the open weights**: 86.7±0.8
    olmOCR / 80.4% multilingual — Datalab's managed endpoint apparently
    runs additional pre/post-processing or a slightly different checkpoint
    than the released open weights.
- **License**: code Apache 2.0. Model weights: modified OpenRAIL-M,
  "free for research, personal use, and startups under **$2M**
  funding/revenue. Cannot be used competitively with our API." — this is
  directly quoted from the HuggingFace model card and is a **different,
  lower threshold than Marker/Surya's $5M** stated in those repos' own
  READMEs. Both are Datalab products but apparently carry different
  commercial thresholds per-model; do not assume one number applies
  across the whole Datalab stack. See §6.
- **Inference**: HuggingFace backend (needs PyTorch/Transformers, Flash
  Attention recommended) or vLLM server backend (`chandra_vllm` Docker
  launch); CLI `chandra --method hf|vllm`, plus a Streamlit app
  (`chandra_app`). Throughput: 1.44 pages/sec on one H100 80GB at 96
  concurrent sequences (benchmark conditions); ~2 pages/sec cited as a
  more realistic real-world estimate (note: this "~2/s real world" vs
  "1.44/s benchmark" ordering is a little odd — the real-world estimate
  is higher than the concurrent-benchmark number, worth double-checking
  against the primary blog post rather than taking at face value).
  `MAX_OUTPUT_TOKENS` default 12,384/page; `BATCH_SIZE` 28 (vLLM) / 1 (HF);
  `--page-range`, `--max-workers` CLI flags.
- **Datalab hosted API**: SOC 2 Type 2 compliant, custom BAAs for
  enterprise, "$5 in free credits" for new signups, batch capacity cited
  as "200M+ pages weekly" (secondary, from GitHub README summary — not
  independently verified against a primary capacity-claim page).

**Router relevance**: Chandra is the tool to route to for the
**handwritten, forms, and math lanes specifically because it's benchmarked
end-to-end on exactly those categories**, whereas Marker's handling of
those same lanes depends on `--use_llm` invoking a *general-purpose* LLM
(Gemini/Claude/GPT) through a block-specific prompt rather than a model
purpose-trained on handwriting/forms. For pure table-heavy and born-digital
lanes, Marker balanced mode is cheaper per page and close in accuracy
(73.4% vs Chandra's ~89.9–92.1% on the tables category specifically,
though — Chandra clearly wins tables on olmOCR-bench).

---

## 5. Benchmarks: Marker vs Docling vs MinerU vs Chandra

Primary source: https://www.datalab.to/blog/marker-2 (Datalab's own
benchmark post, fetched directly). Secondary corroboration:
https://www.marktechpost.com/2026/07/24/datalab-marker-v2-vs-mineru-docling-and-liteparse-benchmark-breakdown/,
https://lumienai.com/news/marker-2-vs-mineru-docling-liteparse-olmocr-bench-benchmark,
https://saipien.org/marker-2-datalab-document-conversion-benchmarks-accuracy-cost-deployment-checklist/.
(These are all describing the same underlying olmOCR-bench numbers Datalab
published; treat the MarkTechPost/lumienai/saipien pieces as re-reporting,
not independent benchmarking.)

olmOCR-bench (1,403 PDFs; arXiv, historical scans, complex tables,
multi-column, headers/footers, tiny text, math):

| System | Overall | Born-digital only | Throughput |
|---|---|---|---|
| Marker balanced (GPU, B200) | 76.0% | 83.5% | 2.9 pg/s |
| Marker fast | 66.6% | 71.6% | 7.4 pg/s |
| Marker fast, no OCR (`--disable_ocr`) | 43.6% | 55.8% | 23.7 pg/s |
| MinerU pipeline (GPU) | 72.7% | 83.3% | 0.54 pg/s |
| Docling (GPU) | 50.3% | 64.0% | 2.1 pg/s |
| Chandra 2 (full-page VLM) | 85.8–85.9% | — | ~1.44–2 pg/s (H100) |

Marker per-category (balanced/fast): arXiv math 83.9%/23.4%, tables
73.4%/69.0%, multi-column 76.6%/76.0%, headers/footers 95.9%/93.2%, long
tiny text 71.3%/68.3%, old scans 43.2%/43.2% (flat across modes — old/
degraded scans are Marker's weakest category regardless of mode, since both
modes ultimately fall back to the same Surya OCR for genuinely bad scans).

**Framing from Datalab itself** (important nuance, not just marketing): the
team is explicit that Marker (a pipeline: layout→text-layer/OCR→
processors) and Chandra (a single full-page VLM call) are "distinct tools"
solving the same problem differently — Marker wins on throughput and
born-digital/table-CPU-reconstruction paths, Chandra wins on raw accuracy
for hard categories (handwriting, forms, degraded scans, math, low-resource
languages) at much lower throughput and needing a real GPU per request.
Docling has the weakest raw scores here but is the only one of the three
under a vendor-neutral license/governance (MIT, Linux Foundation AI & Data)
— relevant if licensing risk matters more than raw score for your org.
https://www.marktechpost.com/2026/07/24/datalab-marker-v2-vs-mineru-docling-and-liteparse-benchmark-breakdown/

**Router implication**: this benchmark table is close to a ready-made
lookup for lane→tool mapping: born-digital → Marker fast/balanced (cheap,
83.5% born-digital-only score, no VLM needed for `--disable_ocr` path if
you can tolerate 55.8%); degraded/old-scan → neither Marker mode does well
(43.2% flat) — this is the strongest signal in the whole research pass
that a **dedicated degraded-quality lane should route to Chandra or a
larger general VLM, not Marker**, since Marker's own numbers show it
doesn't meaningfully improve on old scans between fast and balanced modes.

---

## 6. Community reports: strengths, failures, licensing

**Failure/limitation reports (GitHub issues, primary source, all on
datalab-to/marker):**
- Issue #982 ("Performance", Feb 2026): user reports `--disable_ocr` does
  not meaningfully speed up conversion vs expectations, ~6 pages/min
  observed vs promised throughput — worth stress-testing before assuming
  README throughput numbers transfer to arbitrary hardware/document mixes.
  https://github.com/datalab-to/marker/issues/982
- Issue #737 ("Complex PDF OCR Problems"): headers/footers ignored, some
  text mis-treated as an image, "random mathematical artifacts" appearing
  in output — reported specifically against the Datalab.to Marker **API**
  (hosted), not just the OSS library.
  https://github.com/datalab-to/marker/issues/737
- Issue #613 / #658: users asking how to force OCR on regions the layout
  model detected as images (i.e. false negatives in the
  text-vs-image/figure classification step), and cases where "OCR cannot
  recognize the image" at all — both point at the layout-detection step as
  a real failure mode distinct from the text-quality heuristics in §2:
  if a region is mislabeled as Picture/Figure it gets *excluded* from OCR
  entirely (see `skip_ocr_blocks` in `ocr.py`, §2), so bad layout labeling
  can silently drop content.
  https://github.com/datalab-to/marker/issues/613
  https://github.com/datalab-to/marker/issues/658
- General handwriting-OCR context (secondary, not Marker-specific):
  handwriting recognition remains an open research problem industry-wide;
  image quality (lighting, angle, resolution) is called out as the primary
  accuracy bottleneck across tools, not model choice alone.
  https://inkscan.app/en/blog/why-handwriting-ocr-still-fails

**Hallucination risk in `--use_llm` mode**: I could not find a specific,
citable community report (HN/Reddit) quantifying hallucination rates for
Marker's `--use_llm` path — this should be marked **unverified**. What I
can confirm from source is that Datalab's own LLM prompts (§1, e.g.
`llm_form.py`) include an explicit "if nothing needs fixing, output 'No
corrections needed'" instruction, which is a hallucination-mitigation
pattern built into the prompts themselves — suggesting Datalab is aware of
and actively guarding against over-eager LLM "corrections."

**Licensing (verified directly from primary sources, with an important
discrepancy):**
- Marker: code **Apache 2.0** — confirmed both from the README's own
  license section text ("Our code is licensed under Apache 2.0 — free to
  use, including commercially") and from a direct fetch of
  https://github.com/datalab-to/marker/blob/master/LICENSE, which is the
  standard Apache 2.0 text with no revenue carve-outs. **Weights**: modified
  AI Pubs / OpenRAIL-M license, "free for research, personal use, and
  startups under **$5M** funding/revenue," commercial license required
  above that via Datalab's pricing page.
  https://github.com/datalab-to/marker (README)
  https://github.com/datalab-to/marker/blob/master/LICENSE
- Surya: same pattern — code Apache 2.0, weights modified AI Pubs
  Open-Rail-M, **$5M** threshold (per Surya's own README).
- Chandra: code Apache 2.0, weights modified OpenRAIL-M, but
  **$2M** funding/revenue threshold (per Chandra's HF model card,
  huggingface.co/datalab-to/chandra-ocr-2) — plus an additional clause
  ("cannot be used competitively with our API") not present in the
  Marker/Surya wording I found.
- One older secondary web summary claimed Marker's *code* was still under
  GPL-3.0 with a $2M threshold — this is **stale/wrong for the current
  repo state**: I independently confirmed via direct LICENSE fetch that
  Marker's code is Apache 2.0 as of the v2.0 rewrite (July 2026). Marker
  1.x was reportedly GPL-3.0 for code before that rewrite — if you're
  pinned to a pre-2.0 Marker version, re-check its LICENSE file
  specifically, don't assume current terms apply.
- **Bottom line for routing/build decisions**: code is unrestricted
  (Apache 2.0) across Marker, Surya, and Chandra. The revenue/funding
  threshold is a **weights-license** matter and differs per model —
  Marker/Surya weights at $5M, Chandra weights at $2M — so if your
  document-routing layer's provider revenue or funding crosses $2M you may
  already need a commercial license for Chandra specifically even while
  still inside Marker/Surya's free tier. This is exactly the kind of
  detail worth re-verifying against Datalab's pricing page
  (https://www.datalab.to/pricing, not fetched in this pass) before
  finalizing a build.

---

## 7. Page-level classification/triage features in Datalab tooling

- **No dedicated "classify this document/page into lane X" product
  feature** was found in Marker, Surya, or Chandra's own docs. There is no
  API or CLI flag whose stated purpose is "tell me if this page is
  scanned/handwritten/table-heavy/etc." as an end in itself.
- **What functionally exists and can be reused as router signal**:
  - Marker's page-level `text_extraction_method` ("pdftext" vs "surya")
    plus the underlying `OCRErrorPredictor` `P(bad)` score, layout coverage
    ratio, and line-overlap fraction (§2) — this is a genuine born-digital
    vs needs-OCR/degraded classifier, already isolated as
    `surya.ocr_error.OCRErrorPredictor`, usable standalone.
  - Layout-detected `BlockTypes` per page (`Table`/`TableGroup` →
    table-heavy, `Equation`/`TextInlineMath` → math, `Handwriting` →
    handwritten, `Code` → code, `Form` → forms, `Picture`/`Figure`/
    `Diagram` proportion → image-heavy) — a lane classifier could be built
    by running just Marker's layout pass (fast mode, CPU-only, no VLM) and
    counting block-type proportions per page, without running full
    conversion.
  - The Datalab hosted **API** references a `/api/v1/segment` endpoint
    ("documents can be segmented into structured sections using a JSON
    schema") found via search of
    https://documentation.datalab.to/docs/welcome/api — I could not fetch
    the API reference page directly (404 on the specific URL I tried), so
    **treat the segment endpoint's exact behavior as unverified** — it may
    be schema-based content segmentation (like the old ExtractionConverter)
    rather than a document-type classifier. Recommend a maintainer fetch
    https://documentation.datalab.to/docs/ live (it 404'd for me at the
    `/docs/api-reference` and `/docs/welcome/api` paths I guessed) to
    confirm current endpoint names/behavior before depending on it.
  - Multilingual detection: no explicit "detect language" pre-step was
    found documented; Surya/Chandra just run inference and presumably
    handle whatever language appears, relying on their broad training
    coverage (90+ languages) rather than a language-ID pre-classifier.

**Practical recommendation for the router**: since no first-party
page-classifier exists, the cheapest reusable signal is running Marker's
**fast-mode, `--disable_ocr`, CPU-only layout pass** on every incoming page
(no GPU, no VLM call) to get (a) the OCR-error-model good/bad verdict and
(b) block-type proportions, then routing based on that — before deciding
whether to send the page to full Marker balanced mode, Chandra, or a
different specialist tool for its lane.

---

## Open items I could not verify (flagged explicitly)

1. Chandra 2 parameter count: model card says 5B, blog/GitHub summaries say
   4B. Unresolved discrepancy — confirm before citing a number.
2. Datalab's exact current API endpoint names/parameters
   (`/api/v1/marker`, `/api/v1/extract`, `/api/v1/segment`) — the API
   reference URLs I tried 404'd; only found via search-engine summaries,
   not a direct fetch.
3. Community hallucination-rate reports for `--use_llm` mode — no citable
   HN/Reddit source found; only inferred from prompt design that Datalab
   is aware of the risk.
4. Exact current $/pricing page terms for Datalab commercial weight
   licenses (I did not fetch datalab.to/pricing directly) — the $5M
   (Marker/Surya) vs $2M (Chandra) figures come from each repo's own
   README/model-card text as of this research date, not the pricing page
   itself; these terms could change.
5. Surya's exact per-language OCR pass-rate table and the RTX 5090/Apple
   Silicon speed figures — sourced from a secondary summarized fetch of
   Surya's README, not independently cross-checked against a raw benchmark
   file in the repo.
6. Datalab API's claimed "200M+ pages weekly" batch capacity — from a
   GitHub README secondary summary, not a primary capacity/SLA page.
