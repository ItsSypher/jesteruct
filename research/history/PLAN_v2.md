# Jesteruct: Document Sorting, Lane Routing and RouteBench

Status: plan v2, 2026-09-23.
v1 is kept at `archive/PLAN_v1.md`.
Scope: the sorting and routing layer, the benchmark that grades it, and the two deployment profiles (Apple Silicon demo, cloud cluster).
The processing lanes themselves are specified only as far as the router and the benchmark need them.

Research notes behind every claim live in `research/`, one file per track with URLs.
Numbers marked **[measured]** were taken on the dev machine (Apple M4, 10 cores, 24 GB, macOS 26.3) on 2026-09-23.
Anything marked **[unverified]** came from one secondary source, launch-week material, or recalled background knowledge, and must be re-checked before we rely on it.

### What changed from v1

- Confidentiality is out of scope for now.
  The optimisation target is the best quality-to-speed ratio, so hosted arbiters are the default and local models are the offline fallback.
- The demo runs on Apple Silicon only; the same code must scale out on cloud clusters.
  Section 11 defines both profiles, stage by stage, with measured M4 numbers.
- OpenRouter is the gateway for hosted models during the demo and the benchmark (one key, about $21 of credit left, with a self-imposed $15 cap).
- The routing benchmark (RouteBench, section 10) is new and is now the backbone of the build.
  It uses public parsing benchmarks with exact ground truth to measure which lane actually succeeds on each page.
  That removes v1's biggest schedule risk, which was hand-transcribing reference pages.

---

## 1. Summary

We will build a page-level router.
It measures every page of every incoming file cheaply, and writes a route manifest saying which lane each page, or run of pages, should go to and why.

The router is a cascade.
Deterministic probes (PDF structure, image quality, a fast layout detector, text-layer forensics) run on every page.
They settle most pages through rules and small calibrated models.
The ambiguous remainder goes to arbiters: TypeSafe Jev for questions about text, and a small hosted vision model for questions that need eyes.
A human queue takes what neither arbiter is sure about.

The router outputs a route vector, not one label: text-layer trust, capture type, degradation, layout, content flags, script, orientation, continuation and density.
A versioned policy table maps that vector to a lane by minimising expected cost.
Lanes can therefore change when processing is built, without retraining the router.

RouteBench grades the router the way it will be used.
For each benchmark page we store how well every lane did on it (a quality-and-cost matrix), so any router version can be scored offline in seconds.
The scores cover under-routing (the silent-failure number), wasted compute, calibration, stability under degradation, segmentation, crash resistance and speed.

Four research findings shape everything.

1. Degradation predicts parser failure better than document type.
   FinixDoc (arXiv 2608.22842) found a 25-35 point accuracy cliff from clean digital to camera-captured pages across every model tested.
2. Cheap pre-inference features route well when difficulty shows in them.
   A calibrated random forest over 13 such features cut cost 31-77% with no accuracy loss (arXiv 2608.06607).
3. Jev is text only, uncalibrated out of the box, and will not abstain unless given an option to.
4. Small local vision models on the M4 take 1.9-10.5 s per call, and none identified both the scan and the photo in a three-page check **[measured]**.
   In a 20-model hosted bake-off on 60 labelled pages, Gemini 3.8 Flash scored 0.979 at about 4 s and $2.75 per 1,000 calls **[measured]**.
   With confidentiality set aside, hosted wins the quality-to-speed ratio.

---

## 2. Goals, constraints and non-goals

**Goals**

- Route every page into the lane that gives exact output at the lowest cost and latency.
- Never fail silently.
  When the router is unsure it escalates, and it records why.
- Run the full demo on one Apple M4 laptop, with hosted APIs allowed.
- Run the same code on a cloud cluster by changing a profile, not the code.
- Measure all of this with a benchmark that is reproducible, statistically sound and hard to game.

**Constraints**

- Development cost is not a deciding factor; quality, simplicity and long-term maintainability are.
- Python with `uv`.
- OpenRouter spend during the demo phase is capped at $15, tracked by the harness.

**Non-goals for this phase**

- Building the processing lanes beyond the stubs RouteBench needs.
- Data residency and confidentiality controls.
  The arbiter interface keeps local substitutes (Kev, MLX models) so these can be added later.
- Semantic extraction schemas (invoice fields and the like).
  The router passes document-type hints on; extraction comes later.

---

## 3. What the research says

This section condenses the eight research files.
Details and URLs are in `research/`.

### 3.1 TypeSafe Jev (`research/research_jev.md`)

- **What it is.** A "System One" decision model, in early access since 15 Sep 2026.
  It returns typed answers with probabilities instead of text ([API docs](https://docs.typesafe.ai/api)).
- **Primitives.** `choice` (up to 255 options, reliable to about 240), `score` (2-10 ordered levels) and `noul` (a yes/no probability).
  Many questions over one `state` are answered independently in one request.
- **Input.** Text or JSON only; no images.
  The context is 64k in the docs and 32k at OpenRouter and Cloudflare, so treat 32k as the limit.
- **Cost.** $0.042 per million input tokens, output free.
  That is about $42 per million pages at 1k tokens each.
- **Latency.** The US figure is 70-500 ms.
  From the Netherlands it measured 250-580 ms warm and up to about 1.3 s cold; request size barely matters (712 ms at 3 questions vs 714 ms at 100) ([research_apple_cloud §5](research/research_apple_cloud.md)).
- **Limits.** The rate limit is 1,200 requests per minute.
  At a 15% arbitration rate that supports about 133 pages/s of total router throughput.
- **Strengths.** Page-type classification from extracted text: 20/20 OCR'd pages with the previous page as context, and every answer at 0.8 or above correct ([Classmethod](https://dev.classmethod.jp/en/articles/typesafe-jev-doc-type-classification/)).
  Document typing: 40/40 in DocJev.
- **Weaknesses.**
  - Numbers, counting, dates, large noisy state, adversarial text.
  - Criteria wording swings accuracy by 15-30 points.
  - Non-English input costs 3-11 points.
- **Calibration.** Not calibrated out of the box: ECE is 0.107 on unseen data, and some errors come out at 1.0.
  The `confidence` field is a function of `probabilities` and adds nothing.
  Without an abstain option, accuracy on unanswerable items drops to zero.
- **Determinism.** 50 identical requests gave 15 distinct answer sets.
  Pin `jev-1.13.0` and log the returned model.
- **Terms.** The agreement forbids training a model to imitate the service, so router training labels must not come from Jev.
- **Open alternative.** Kev (Apache-2.0; 0.8B, 4B, 9B) serves the same API shape.
- **On OpenRouter.** Served through a separate decisions endpoint (`/api/alpha/decisions`), not chat completions.
  It is absent from the model catalogue, as expected.
  We confirm access with our key in Phase 0.

### 3.2 Docling (`research/research_docling.md`)

- **Version and pipelines.** 2.130.0 (22 Sep 2026).
  The standard pipeline runs text extraction, optional OCR, the Heron or Egret layout model and TableFormer; the VLM pipeline runs Granite-Docling-258M, SmolDocling, or larger models including Chandra.
- **Layout labels.** Table, Formula, Code, Picture, Form, Key-Value Region and Checkbox, all usable routing signals.
- **Speed on the M4.** egret-m through ONNX Runtime with the Core ML backend runs about 40 ms/page, about 25 pages/s **[measured]**.
  The same model on PyTorch's GPU backend (MPS) is about 5 pages/s, so we avoid MPS for this stage.
- **Self-assessment.** A per-page `ConfidenceReport` (parse, layout and OCR scores) is a post-parse feedback signal.
- **Figure classifier.** DocumentFigureClassifier-v2.5 has 4M parameters and 26 classes; it tells charts, photos, signatures, stamps and barcodes apart.
- **Weak spots.**
  - Multi-column reading order is a multi-year open problem.
  - Complex tables break, and `ACCURATE` mode drops rows on dense tables (#4255).
  - RTL text comes out reversed (#253).
  - No handwriting support.
  - The threaded backend drops existing OCR text layers on about 17% of a sample (#4357), so the router does its own text-layer forensics.

### 3.3 Marker, Surya and Chandra (`research/research_marker.md`)

- **Marker 2.0 text-layer trust check.** Read from source, all four must hold:
  1. text lines exist;
  2. `OCRErrorPredictor` does not flag the text;
  3. at least 25% layout-to-text coverage;
  4. fewer than 50% of lines overlapping more than two neighbours.

  We reuse this logic in S3.
- **Olmocr-bench scores (vendor-reported).**

  | System | Overall | Old or degraded scans | Throughput |
  |---|---|---|---|
  | Marker balanced | 76.0% | 43.2% | 2.9 pages/s |
  | Marker fast | 66.6% | 43.2% | 7.4 pages/s |
  | Docling | 50.3% | | 2.1 pages/s |
  | Chandra 2 | about 85.8% | | |

  Balanced mode gains nothing over fast mode on degraded scans, which argues for a separate degraded lane backed by a strong VLM.
- **Licences.** Code is Apache 2.0.
  Weights are free under $5M revenue for Marker and Surya, and under $2M for Chandra, which also carries a non-compete clause.

### 3.4 Parser landscape (`research/research_landscape.md`)

- **OmniDocBench v1.6 leaders.** PaddleOCR-VL-1.6 (0.9B) at 96.3 overall, MinerU2.5-Pro at 95.75 and WeVisDoc-4B at 95.38; WeVisDoc adds 4 points on degraded input through a refinement stage.
  DeepSeek-OCR-2 gets 90.25 at 2,932 tokens/s.
  Accuracy and speed trade off per tool, which argues for tiers.
- **Cost driver.** VLM parsing cost is driven by output length (HPD-Parsing, arXiv 2607.18839), so the router estimates content density.
- **Failure modes to monitor downstream.**
  - VLM repetition loops.
  - Silent named-entity substitution (arXiv 2607.24077).
  - Fragile tables everywhere, and cross-page tables broken almost everywhere.
- **Reusable heuristics.** Unstructured's per-document `auto` strategy is the baseline to beat.
  Its `is_pdf_too_complex()` safety gate is worth copying.

### 3.5 Small vision models (`research/research_vlm.md`, `research/research_apple_cloud.md`)

- **Local on the M4.** Run with mlx-vlm 0.7.2 and strict JSON-schema output.
  Each call sent a ~1024 px page and got back a ~45-token answer.
  The test pages were a clean render, a synthetic scan and a synthetic camera photo **[measured]**.

  | Model (4-bit unless noted) | p50 per call | Prefill / decode tok/s | Peak RAM | Valid JSON | Capture right |
  |---|---|---|---|---|---|
  | Gemma-4-e4b | 1.9 s | 244 / 33 | 2.2-5.8 GB | 6/6 | 1/3 |
  | MiniCPM-V-4.6 | 2.0 s | 310 / 76 | 2.7-3.0 GB | 6/6 | 1/3 |
  | Qwen3-VL-2B (timed while the GPU was shared; rough) | 3.0 s | 391 / 86 | 2.1-2.7 GB | 6/6 | 1/3 |
  | Qwen3.5-4B | 4.0 s | 239 / 37 | 3.8-4.1 GB | 6/6 | 2/3 (only one to get the scan) |
  | Qwen3-VL-4B | 4.9 s | 241 / 37 | 3.7-4.0 GB | 6/6 | 1/3 |
  | Qwen3-VL-4B, 8-bit | 6.5 s | 229 / 22 | 5.5-6.0 GB | 6/6 | 1/3 |
  | SmolVLM2-2.2B | 6.2 s | | 5.3 GB | 6/6 | 1/3 |
  | Qwen3-VL-8B | 10.5 s | 129 / 22 | 6.0-6.7 GB | 6/6 | 1/3 |

  - Most models call everything `digital_render`.
  - 8-bit changed no answers against 4-bit and was about 35% slower.
  - Every schema list field needs `maxItems`: without it, Qwen3-VL repeated items until the token limit.
  - Image prefill dominates (about 800 image tokens), so a 768 px image helps most: MiniCPM-V-4.6 drops to 1.5 s and Qwen3.5-4B to 3.7 s.
  - Concurrent requests add only 12-20% throughput, so one M4 handles roughly 1,000-1,900 locally arbitrated pages an hour.
  - InternVL3.5 and Moondream have no ready MLX builds and were not tested. vllm-mlx supports Qwen3-VL and Gemma 4 with schema output and is worth tracking, since it matches the cluster's vLLM API.
  - Local models are the offline fallback only.
- **Hosted bake-off, 2026-09-24** (`bench/vision_bakeoff/REPORT.md`) **[measured]**.
  - **Setup.** 20 of the newest vision models on OpenRouter, run on 60 labelled pages: PureDocBench triplets, olmOCR-Bench, FUNSD, GNHK, Arabic, and synthetic fax, screenshot and camera pages.
  - **Equal footing.** Same image, prompt and strict schema, with no output cap or reasoning overrides.
  - **Score.** The composite is the mean accuracy over capture, handwriting, content flags and script, with a 95% page-bootstrap interval.
  - **Spend.** $2.65 in total.

  | Model | Composite (95% CI) | p50 / p95 s | $ per 1k calls |
  |---|---|---|---|
  | GPT-6-sol | 0.985 (0.969-0.996) | 4.8 / 7.6 | 5.08 |
  | Gemini 3.8 Flash | 0.979 (0.962-0.993) | 4.2 / 8.7 | 2.75 |
  | Claude Sonnet 5 | 0.966 (0.943-0.987) | 3.0 / 4.3 | 5.23 |
  | Seed-2.1-turbo | 0.963 | 32.6 / 117 | 6.97 |
  | Muse-spark-1.3 (contributor) | 0.960 | 12.1 / 23.4 | 0.40 |
  | Grok 4.7 | 0.953 | 8.4 / 26.5 | 5.43 |
  | GPT-6-luna-pro | 0.950 | 5.9 / 14.1 | 0.52 |
  | GPT-6-luna | 0.941 | 4.0 / 7.5 | 0.26 |
  | DeepSeek V4.1-flash | 0.927 | 4.6 / 18.5 | 1.53 |
  | Claude Haiku (latest) | 0.912 | 2.8 / 3.6 | 2.31 |
  | Gemini 3.5 Flash-Lite | 0.909 | 1.6 / 2.2 | 0.79 |

  - **Top group.** The top three overlap within their intervals; cost and latency separate them. Scoring against the labels as first built keeps the same top group.
  - **Qwen3.8-omni-flash** wraps its answers in a list and fails strict parsing (0.29 strict, 0.93 lenient).
  - **Unavailable.** Mistral Small and Command-A-plus were rate-limited upstream and are not ranked.
  - **Legibility** is left out of the composite. Its labels meant image degradation, but the prompt asked about OCR difficulty. Section 8.2 fixes the definition.
  - **Consistency over two runs.** Gemini 3.8 Flash gave identical answers on 93% of pages. For the strongest models, pages where the runs disagreed were no less accurate, so self-agreement is not a usable confidence signal for them (section 8.2).
- **Hosted with strict JSON schema on image input.** Confirmed for Gemini Flash-Lite, Mistral Small and GPT-5-nano.
  DeepSeek V4.1-Flash is slow in thinking mode (7.6-10.5 s to first token per Artificial Analysis); non-thinking mode is **[unverified]**.
- **Ceiling.** Zero-shot small-VLM document typing plateaus around 60-70% on 16 classes, against about 95% for a trained model.
  VLMs belong on the ambiguous tail and on narrow visual questions.
- **Verification rule.** A verifier must be a different model family from the extractor.
- **Live OpenRouter catalogue** (pulled 2026-09-23; price in / out per million tokens; all support structured outputs).
  This is the arbiter bake-off pool:

  | Model | In / out |
  |---|---|
  | `google/gemini-3.5-flash-lite` | $0.30 / $2.50 |
  | `google/gemini-3.1-flash-lite` | $0.25 / $1.50 |
  | `openai/gpt-6-luna` | $0.10 / $0.50 |
  | `openai/gpt-5-nano` | $0.05 / $0.40 |
  | `deepseek/deepseek-v4.1-flash` | $0.10 / $0.50 |
  | `qwen/qwen3.8-flash` | $0.15 / $0.47 |
  | `xiaomi/mimo-v2.6-flash` | $0.14 / $0.28 |
  | `inclusionai/ling-3.0-flash-vl` | $0.06 / $0.18 |
  | `google/gemma-4-26b-a4b-it` | $0.09 / $0.30 |
  | `mistralai/mistral-small-2603` | $0.15 / $0.60 |
  | `qwen/qwen3-vl-8b-instruct` (a local-equivalent check) | $0.117 / $0.455 |
  | `anthropic/claude-haiku-4.5` (quality reference) | $1 / $5 |
  | `google/gemini-3.8-flash` (upper reference) | $0.75 / $3.75 |

### 3.6 Apple Silicon specifics (`research/research_apple_cloud.md`)

- **Apple Vision APIs.** These are optional feature columns: null in the cloud, and never a router dependency.
  - **`DetectDocumentSegmentationRequest`.** Flagged every synthetic camera photo at 0.99 confidence in about 10 ms, and is callable from Python through PyObjC **[measured]**.
    This is the strongest cheap camera-photo signal we have.
  - **`DetectLensSmudgeRequest`** (new in macOS 26).
    Scored synthetic scans 0.72-1.00 and clean pages near 0 **[measured, three pages]**.
    It is a candidate blur and quality feature, to be validated on RouteBench.
  - **`CalculateImageAestheticsScoresRequest`.** Came out near 0 on every page, so it is useless for routing.
  - **`RecognizeDocumentsRequest`.** Returns paragraphs, titles, lists, tables and barcodes.
    PyObjC can run the request but cannot read its structured output, so this one alone needs a small Swift helper.
- **OCR and orientation timings.**
  - Apple Vision OCR on a 150 dpi page: 328 ms in fast mode, 649 ms in accurate mode **[measured]**.
  - Tesseract orientation and script detection: 470-900 ms/page at 120-150 dpi, and only 23/36 orientations right at 120 dpi (36/36 at 200 dpi, but about 2 s per page) **[measured]**.
    It is dropped from the per-page path.
  - Rotation comes from PP-LCNet_x1_0_doc_ori instead (about 3 ms claimed, **[unverified]** on M4).
- **PDF libraries.** pypdfium2 renders at an average of 38 ms/page vs 48 ms for PyMuPDF **[measured, research agent]**.
  Pages that are one full-page JPEG can skip rendering: pikepdf passes the embedded image straight through in 16 ms.
  There is no speed reason to take on PyMuPDF's AGPL licence.
- **Measured cheap-stage costs on the M4**, single process, on a 9-page born-digital paper:

  | Stage | Median per page |
  |---|---|
  | pypdfium2 text extraction | 2.9 ms |
  | pikepdf image and filter walk | 0.4 ms |
  | 120 dpi grayscale render | 12 ms |
  | Laplacian, contrast and noise metrics | 8 ms |

  With 8-10 worker processes the M4 sustains roughly 80-120 pages/s of S1+S2 CPU probing, excluding the layout model **[measured, research agent]**.

### 3.7 Public benchmarks we can build on (`research/research_benchmarks.md`)

The datasets that matter most for RouteBench:

- **PureDocBench** (CC BY 4.0). 1,475 pages rendered from HTML, each in three versions (clean, digitally degraded, real degraded capture), with exact text, formula, table and reading-order ground truth.
  The triplets make it the natural source for monotonicity tests.
- **olmOCR-Bench** (ODC-By). 1,403 PDFs and 7,010 pass/fail unit tests, split into:

  | Category | PDFs |
  |---|---|
  | arXiv math | 522 |
  | old scans math | 36 |
  | tables | 188 |
  | old scans | 98 |
  | headers and footers | 266 |
  | multi-column | 231 |
  | long tiny text | 62 |

  The unit tests give a cheap per-page success signal for any lane.
- **OmniDocBench** (research-use notice on the dataset card).
  About 1,650 pages with page attributes (source type, layout, language, fuzzy scan, watermark, coloured background **[verify exact attribute names]**).
- **ExtractBench** (Apache-2.0).
  Tags scanned (P2), handwriting (P3) and rotated or image-only (P1) pages, plus 38 clean-vs-degraded pairs.
- **More data sources:**

  | Dataset | Contributes | Licence |
  |---|---|---|
  | getomni-ai benchmark | Per-document quality tags (HIGH_QUALITY, CLEAN, PHOTO, LOW_QUALITY) | MIT |
  | Dr.DocBench | Pages where top parsers disagree, in 14 languages; the hard challenge split | Data reported as CC0 |
  | GNHK | Phone-photographed handwriting | CC BY 4.0 |
  | KITAB-Bench | Arabic pages | MIT |
  | DocLayNet | Born-digital pages with exact layout boxes, including a laws-and-regulations category | CDLA-Permissive |
  | Stress corpora | Crash and quarantine tests: Unstructured example-docs, Docling test data, the PDF Association Stressful Corpus, the openpreserve Cabinet of Horrors, a GovDocs1 sample | |
  | CourtListener RECAP | Real scanned court filings, unlabelled; our legal-domain slice | |

---

## 4. Design principles

1. **Route pages, then group them.** Real files mix born-digital pages with scanned signature pages, faxed annexes and photos.
   Per-page routing followed by smoothing into segments is the core behaviour.
2. **Measure before you ask.** Anything a probe can answer, a probe answers.
   Arbiters see our measurements as evidence.
3. **Degradation first, content second, semantics third.** Degradation picks the base lane, content switches processors on inside it, and document semantics go downstream.
4. **Output requirements, not tool names.** A policy table turns requirements into lanes.
5. **Calibrated probabilities, asymmetric costs.** The lane minimises expected cost.
   Under-routing is priced far above over-routing, because its failures are silent.
6. **Explained and replayable.** Every decision records its features, the deciding component, probabilities and versions.
   Routes can be recomputed from stored features and cached arbiter replies.
7. **Portable by construction.** Every model stage sits behind an interface with an Apple backend and a cloud backend.
   CV models share ONNX as their format; VLMs share an OpenAI-compatible `json_schema` chat contract.
   Moving between the M4 and the cluster changes a profile file, not code.
8. **The benchmark comes first.** No router change merges without a RouteBench run that shows it does not regress the headline metrics.
9. **Close the loop.** Post-parse quality signals come back to drive escalation now and training data later.

---

## 5. Lane architecture (proposal, to be ratified)

### 5.1 Route vector

| Axis | Values | Main sources |
|---|---|---|
| `container` | native_office, pdf, image, email, archive, audio_video, unsupported | magic bytes, MIME |
| `text_layer` | none, trusted, untrusted_ocr_layer, garbled, partial | PDF forensics, Marker-style checks |
| `capture` | vector, flatbed_scan, fax_bilevel, camera_photo, screenshot | image filters, EXIF, page quadrilateral, borders |
| `degradation` | 0 clean, 1 mild, 2 heavy, 3 severe | blur, contrast, noise, DPI, skew, JPEG quality |
| `layout` | single_column, multi_column, complex | line-start clustering, layout detector |
| `content_flags` | tables, table_dense, math_display, math_inline, code, form_fields, checkboxes, handwriting_major, handwriting_minor, signatures_stamps, charts, photos, barcodes | layout labels, PDF objects, fonts, figure classifier |
| `script` | latin, cyrillic, greek, arabic_rtl, hebrew_rtl, cjk, devanagari, other, mixed, plus ISO language | Unicode histogram, GlotLID, VLM on image pages |
| `orientation` | 0/90/180/270, plus skew degrees | orientation classifier, skew estimate |
| `density` | estimated output tokens | characters or text-region area |
| `continuation` | probability that this page continues the previous page's table, list or paragraph | geometry, Jev |

### 5.2 Base lanes

| Lane | Enters when | Candidate processors (decided later) |
|---|---|---|
| **L0 native** | Office, HTML, Markdown, email body, CSV | Docling native backends |
| **L1 digital-simple** | trusted text layer, single column, no heavy content flags | Docling standard without OCR, or Marker `--disable_ocr` |
| **L2 digital-complex** | trusted text layer, plus multi-column, dense tables, math or code | Marker balanced, Docling with enrichments, MinerU or PaddleOCR-VL |
| **L3 scan-clean** | no trusted text, degradation 0-1, printed text | PaddleOCR-VL, MinerU2.5, Granite-Docling, Marker with `--force_ocr` |
| **L4 scan-degraded** | degradation 2-3, camera, fax, or a poor old OCR layer on a poor image | Preprocessing, then Chandra 2 or a large general VLM |
| **L5 handwriting** | handwriting_major, or handwriting_minor in fields that matter | Chandra 2 or a frontier VLM, with review |
| **LQ quarantine** | encrypted, corrupt, too complex, empty, unsupported, over limits | none; flagged with a reason code |
| **LH human** | arbiters not confident, or policy requires review | review queue |

Capability order for the escalation ladder and for monotonicity tests: L1 < L2 < L3 < L4 < L5 < LH.
L0 and LQ sit outside the ladder.

### 5.3 Modifiers

Tables, math, code, forms, charts, signatures, RTL/CJK scripts and multi-column layout are modifiers, not lanes, because each one cuts across the base lanes.

| Modifier | Effect inside the lane |
|---|---|
| `tables`, `table_dense` | Table model on; for dense tables, avoid engines with a row cap; keep continuation pages in one segment |
| `math_display`, `math_inline` | Formula enrichment or a math-strong engine |
| `code` | Code enrichment; preserve whitespace |
| `form_fields`, `checkboxes` | Read AcroForm values directly when present; otherwise use form-aware extraction |
| `handwriting_minor` | Crop the handwritten regions and send them to a handwriting-capable model |
| `charts`, `photos` | Picture classification and description |
| `signatures_stamps` | Record their presence and position; no transcription |
| `rtl`, `cjk` | Choose engines by script support; avoid Docling for RTL |
| `multi_column` | Avoid Docling's standard reading order |

### 5.4 Tiers

The tiers are `economy`, `standard` and `exact`.
The tier sets the cost matrix, the review bands and whether verification runs.
The default is `exact`.

---

## 6. Router architecture

```
files ─► S0 Intake ─► per-page records
                         │
        ┌────────────────┼──────────────────┐
        ▼                ▼                  ▼
  S1 Structural     S2 Visual          S3 Text
  (PDF objects,     (render, IQA,      (trust check, garble,
   fonts, AcroForm)  layout, orient.)   LID, glyph stats)
        └────────────────┼──────────────────┘
                         ▼
                S4 Feature vector (versioned, stored)
                         ▼
                S5 Rules → per-axis calibrated models → expected-cost lane
                         │
            confident ◄──┴──► ambiguous
                │                 ▼
                │         S6 Arbiters: Jev (text) · hosted VLM (visual)
                │                 │ unsure ─► LH
                ▼                 ▼
                S7 Segmentation (smoothing, continuation, regions)
                         ▼
                S8 Route manifest ─► processing lanes (later)
                         ▲
                S9 Feedback: post-parse signals, escalations, labels
```

### 6.1 S0 Intake

- Detect the real type from magic bytes, not the extension.
- Hash each file (sha256) and each rendered page (perceptual hash), so duplicates reuse cached routes.
- Unpack recursively: zip archives, EML and MSG emails (attachments become child documents that keep a link to their parent), multi-page TIFF, PDF portfolios, and embedded files.
- Safety gates, each ending in LQ with a reason code:
  - encrypted;
  - fails to open in two independent parsers (pypdfium2 and pikepdf);
  - too complex (Unstructured's rule: more than 10,000 graphics operations and a graphics-to-text ratio above 20);
  - over page or pixel limits;
  - zero content.
- Native office files go to L0, after checking for embedded page images that are really scans.
  Those embedded images re-enter S2 as image pages.

### 6.2 S1 Structural probe (PDF)

This stage uses pypdfium2 and pikepdf only.
It costs 3-4 ms per page **[measured]**.

| Signal | Tells us |
|---|---|
| Characters per page, text-area coverage | whether a text layer exists |
| Image coverage from placed image boxes | the page is an image, with or without text on top |
| Image filters (`DCTDecode`, `CCITTFaxDecode`, `JBIG2Decode`) and bit depth | photo, fax or bilevel scan, scanner output |
| Effective image DPI | scan resolution |
| Invisible text (render mode 3) share | an old OCR layer under a scan |
| Producer and Creator metadata | scanner and OCR software vs Word or LaTeX |
| Fonts: Type3, missing ToUnicode, math fonts, monospace fonts | garbled text, math, code |
| AcroForm fields and widgets | real form fields whose values can be read exactly |
| Vector ruling lines | tables and form boxes |
| Line-start x clustering | column count |
| Tagged PDF structure tree | free reading order |
| `/Rotate` and box mismatches | orientation hints |

### 6.3 S2 Visual probe

- **Render path.** Render once at about 120 dpi in grayscale (12 ms median **[measured]**).
  A page that is a single full-page JPEG skips rendering: pikepdf passes the embedded image straight through (16 ms).
  Images arrive as they are.
- **Image quality.** Laplacian variance, RMS contrast, a noise estimate, a JPEG quality estimate, and background uniformity (about 8 ms **[measured]**).
  Skew and ruling-line detection run on a 60 dpi copy, or only when S1 found no vector lines, because at 120 dpi they cost about 49 ms.
- **Capture type.**
  - Border and background analysis, EXIF camera tags, and bilevel-fax signatures.
  - On the M4, optionally Apple's `DetectDocumentSegmentationRequest` page quadrilateral through PyObjC (about 10 ms; 0.99 confidence on every synthetic photo **[measured]**).
- **Layout detector.** egret-m through ONNX Runtime, using the Core ML backend on the M4 (about 40 ms, about 25 pages/s **[measured]**) and CUDA or TensorRT in the cloud.
  The detector sits behind a `LayoutDetector` interface.
  The Phase 2 bake-off compares it with PP-DocLayout-S, Heron and Surya layout; DocLayout-YOLO needs an AGPL check first.
- **Orientation.** PP-LCNet_x1_0_doc_ori on image pages without a text layer.
  Text-layer pages take rotation from the PDF itself.
- **Figure classifier.** DocumentFigureClassifier-v2.5 on Picture regions.
- **Handwriting.** Start from layout labels.
  If precision is not good enough, train a small crop classifier on labelled crops.

### 6.4 S3 Text probe

- Marker's four-part trust check (section 3.3).
- **Garble detectors:**
  - the share of `(cid:NNN)`, private-use and U+FFFD characters;
  - mojibake patterns;
  - dictionary hit rate per language;
  - the short-token ratio and characters per word (from arXiv 2608.06607).
- **Language ID.** GlotLID (or fastText `lid.176`) per page and per block, keeping its confidence.
- **Script from the text itself.** A Unicode script histogram.
- **Text-to-layout agreement.** Text regions with no embedded text under them set `text_layer = partial`, which becomes region-level OCR.
- **Math and code glyph statistics.**
- **Density estimate**, a stand-in for output tokens.
- **Image-only pages flagged as unclear.** Optionally, a quick OCR pass supplies a text sample for Jev and an OCR confidence feature: Apple Vision fast mode on the M4 (328 ms **[measured]**), a GPU OCR detector in the cloud.
  It runs only on pages that go to arbitration, never on every page.

### 6.5 S4 Feature vector

One flat record per page (`features.v1`), stored in Parquet and queried with DuckDB.
Every later decision reads only from this record.
Section 7 lists the features.

### 6.6 S5 Rules and learned router

1. **Hard rules**, auditable and each one recorded:
   - native office with no image-only pages → L0;
   - safety gate failure → LQ;
   - image coverage above 0.9 with no text layer → never L1 or L2;
   - AcroForm fields present → `form_fields`.
2. **One calibrated model per axis.** LightGBM with isotonic calibration on a held-out fold.
   Separate models for text_layer, degradation (ordinal), capture, layout, handwriting and each content flag.
3. **Expected-cost lane.** Per tier, `C[true][assigned]`.
   Combined axis probabilities give `p` over lanes, and the lane is `argmin_j Σ_i p_i·C[i][j]`.
4. **Ambiguity test.** A page goes to S6 when any of these hold:
   - the gap between the best and second-best expected cost is small;
   - any axis probability falls inside its review band;
   - rules and models disagree.

   Bands are set so that at most 15% of pages are arbitrated.

### 6.7 S6 Arbiters

Arbiters answer only the ambiguous axes.
Their calibrated answers go back into the same expected-cost step.

| Ambiguous axis | First arbiter | Then |
|---|---|---|
| text_layer, continuation, separator pages, document type | Jev | VLM if still unsure, then LH |
| handwriting, capture, degradation, charts vs photos, form appearance, script on image pages | Hosted VLM | Jev on OCR text if relevant, then LH |
| arbiters disagree with each other or with strong probe evidence | | LH |

### 6.8 S7 Segmentation

- **Contiguous runs.** Segments are contiguous page runs with the same lane and compatible modifiers.
- **Smoothing.** A Viterbi pass adds a switching penalty.
  It may raise a page to a more capable lane but never lower one.
- **Continuation.** A page with high continuation probability stays in the same segment as the page before it.
- **Regions.** Handwritten fields and image-only regions travel as crop instructions inside a segment; they do not split the page.

### 6.9 S8 Manifest and S9 feedback

The manifest (section 12.4) is the only interface to processing.

Feedback signals the processing layer must send back:

- Docling confidence grades.
- `OCRErrorPredictor` run on the output.
- The ratio of output length to the S3 density estimate, which catches truncation and loops.
- VLM `finish_reason` and repetition detection.
- Cross-engine disagreement.
- Human corrections.

A failed page escalates one rung up the ladder.
Every escalation becomes a labelled example with the tag "needed a higher lane".

---

## 7. Feature catalogue v1

About 60 features, all cheap and none needing ground truth.

| Group | Features |
|---|---|
| Container | mime, page_count, file_size, is_encrypted, has_embedded_files, parse_errors |
| PDF text | chars, text_area_ratio, render_mode3_ratio, fonts_count, type3_ratio, no_tounicode_ratio, cid_ratio, pua_ratio, fffd_ratio |
| PDF images | image_area_ratio, max_image_dpi, filter_ccitt, filter_jbig2, filter_dct, bits_per_component |
| PDF structure | producer_class, is_tagged, acroform_fields, widget_count, vector_hline_count, vector_vline_count, rotate |
| Fonts | math_font_ratio, mono_font_ratio |
| Image quality | laplacian_var, rms_contrast, noise_sigma, jpeg_q_est, skew_deg, bg_uniformity, border_nonpage_ratio, exif_camera |
| Apple-only (null elsewhere) | apple_quad_found, apple_quad_area, apple_quad_perspective, apple_doc_table_count |
| Layout histogram | area share and count per label (text, title, table, formula, code, picture, form, key-value, checkbox, handwriting, caption, list, header/footer) |
| Geometry | column_count_est, line_density, word_height_cv, crowded_line_frame, text_region_ratio |
| Text forensics | ocr_error_bad, layout_text_coverage, line_overlap_ratio, dict_hit_rate, short_token_ratio, inv_chars_per_word, lid_lang, lid_conf, script_hist |
| Figures | per-class counts (chart, photo, signature, stamp, barcode) |
| Orientation | orient_pred, orient_conf |
| Density | est_output_tokens |
| Context | prev_page_lane, prev_page_table_at_bottom, same_size_as_prev |

Apple-only columns are null on the cluster.
The models must be trained with those columns masked at random, so they do not come to depend on them.

---

## 8. Arbiters

### 8.1 Jev (text arbiter)

We reach Jev through OpenRouter's decisions endpoint during the demo, and through TypeSafe directly on the cluster.
One client interface covers both, and Kev implements the same interface.

```json
{
  "model": "jev-1.13.0",
  "state": {
    "page_evidence": "Text layer: present on most of the page. Earlier OCR layer: yes, invisible text over a full-page image. Scan quality: mild blur, high contrast. Columns: two. Layout detector: one large table in the lower half, no formulas. Language guess: Finnish, low confidence.",
    "page_text_sample": "<first ~1,500 characters of the text layer or quick OCR>",
    "previous_page_text_sample": "<last ~600 characters of the previous page>"
  },
  "questions": {
    "text_layer": {"type": "choice",
      "instructions": "Judge only `page_text_sample`. Is it usable text from this page?",
      "criteria": {
        "trusted": "Readable words and sentences in a real language, consistent with a normal document.",
        "untrusted": "Mostly readable but with frequent misspellings, broken words or merged columns typical of a poor earlier OCR.",
        "garbled": "Mostly symbols, broken encoding or random characters.",
        "insufficient": "Too little text to judge."
      }},
    "is_continuation": {"type": "noul",
      "instructions": "`page_text_sample` continues the same table, list or sentence that ends `previous_page_text_sample`."},
    "is_separator": {"type": "noul",
      "instructions": "This page is a fax cover sheet, blank separator or scanning slip with no document content."}
  }
}
```

Rules:

1. Verbalise numbers through a fixed, versioned mapping ("mild blur", not `212.4`).
2. Put one page in each state, with the previous page as context.
3. Always include an abstain option.
4. Write criteria as observable evidence, and freeze criteria text once tested.
   Wording is code: it changes only after a RouteBench run.
5. Page text goes only into state fields; filenames stay out.
6. Threshold on calibrated `probabilities`, never on `confidence`.
7. Run a daily drift probe of about 200 pages.
   On drift, fall back to the VLM or LH and raise an alert.
8. Parallelise across pages with a token bucket under 1,200 RPM.
9. Never train on Jev outputs.

### 8.2 Hosted vision arbiter

**Default: Gemini 3.8 Flash.**
It came within the interval of the best score (0.979 vs 0.985) at about half GPT-6-sol's price, and was the most consistent model across two runs.
At a 15% arbitration rate it costs about $0.41 per 1,000 routed pages, so cost is no reason to pick a weaker model.

**Second family: GPT-6-sol.**
It is the top scorer, and it acts as the cross-family check and as the RouteBench silver labeller, keeping pre-labels in a different family from the live arbiter.

**Alternatives by constraint:**

- **Latency-bound:** Claude Sonnet 5, with the tightest tail (p95 4.3 s) and no reasoning tokens.
- **Budget-bound:** GPT-6-luna (0.941 at $0.26 per 1,000 calls).
- **Speed-first pre-pass:** Gemini 3.5 Flash-Lite (1.6 s). It labels Chinese pages with Latin formulas "mixed".

Re-run the bake-off whenever a new model version ships.

**Fallback:** a local model through `mlx_vlm.server` on the M4 (Qwen3.5-4B at 768 px is the most accurate so far at about 3.7 s and 4 GB; Gemma-4-e4b and MiniCPM-V-4.6 are faster at about 1.5-2 s but less accurate), or vLLM on the cluster, reached through the same OpenAI-compatible client.
It is used only offline, and only after it passes Track H.

**Where it is used:**

- S6 arbitration on the visual axes.
- S7 region checks (for example, a filled-in handwritten field).
- RouteBench silver pre-labels, always from a different model family than the live arbiter.
- Later, verification against extraction output, again from a different family than the extractor.

**Request pattern:**

- Page questions use a 768-1024 px thumbnail; region questions use a full-resolution crop.
- Document-level questions use a contact sheet of page thumbnails in one image.
- The answer is closed-set JSON, one field per axis, each with an explicit `unsure`:

```json
{
  "handwriting": "none | annotations_only | fields_filled_by_hand | mostly_handwritten | unsure",
  "capture": "digital_render | flatbed_scan | fax | camera_photo | screenshot | unsure",
  "degradation": "none | mild | heavy | severe | unsure",
  "main_content": ["prose", "table", "form", "chart", "photo", "math", "code", "letterhead", "signature_page"],
  "script": "latin | cyrillic | arabic | hebrew | cjk | other | mixed | unsure"
}
```

**Confidence:** hosted APIs rarely expose log-probabilities, and the bake-off showed that sampling the same model twice does not flag its errors.
The strongest models repeat their mistakes: for Gemini 3.8 Flash and GPT-6-luna, pages where two runs disagreed were no less accurate.
So confidence comes from cross-family disagreement instead.
A page is asked of the default arbiter first.
If that answer conflicts with probe evidence, or lands in a review band, the second family (GPT-6-sol) is asked.
Agreement between the two families is the raw confidence, calibrated on RouteBench.
The schema asks for image `degradation` (noise, blur, fading, compression), not "legibility".
The bake-off showed that "how hard is this to read" mixes image quality with handwriting difficulty, which the router measures on separate axes.
When the VLM conflicts with strong probe evidence (EXIF, page quadrilateral, image filters), the page goes to LH; the VLM does not win by default.

**Cost:** measured at $2.75 per 1,000 calls for Gemini 3.8 Flash and $5.08 for GPT-6-sol, with no output cap. The second family is only asked on the conflicting slice.

---

## 9. Decision policy

- **The policy file.** `policies/lanes.yaml` holds, per tier:
  - lanes with their capability requirements;
  - the cost matrix;
  - review bands;
  - the escalation ladder;
  - modifier-to-processor mappings.
- **Versioning.** The policy has a version, and the manifest records it.
- **Cost matrix.**
  - Under-routing costs 20-50 times an over-route.
    Under `exact` it also forces review.
  - Over-routing costs the measured compute difference, taken from the RouteBench cost columns.
  - LH costs a fixed reviewer-minute price.
- **Worked example.** Take p(degraded) = 0.15 at a 30:1 ratio.
  L3 has an expected cost of 4.5 units against about 1 unit for L4, so under `exact` the page goes to L4.
  Under `economy`, at 5:1, it goes to L3.
- **Calibration.** Isotonic per axis and per arbiter, fitted on the RouteBench calibration split.

---

## 10. RouteBench: the routing benchmark

RouteBench answers one question.
**If we trust this router, how often will a page end up somewhere it cannot be processed correctly, and what do we pay in compute, latency and review to avoid that?**
Everything else in it serves that question or makes the answer trustworthy.

### 10.1 Design rules for a benchmark we can trust

1. **Grade outcomes, not opinions.** The main label for a page is which lanes actually produce correct output on it, measured against exact ground truth.
   Human attribute labels are secondary and used for per-axis diagnosis.
2. **Ground truth by construction wherever possible.** Rendered-from-source pages (PureDocBench), unit-tested PDFs (olmOCR-Bench), synthetic degradations with recorded parameters, and synthetic bundles whose true boundaries we know.
3. **Split by source document, never by page.** PureDocBench triplets, pages of one PDF, and near-duplicates (by perceptual hash) always share a split.
4. **A sealed test split.** It runs only for release candidates and is never used for tuning thresholds, calibration or prompts.
   Its manifest hash is recorded, and every sealed run is logged.
5. **Statistics, not point estimates.**
   - Every headline number carries a 95% interval from a cluster bootstrap by source document.
   - Router comparisons are paired: a paired bootstrap on regret, McNemar on under-route.
   - Slices with fewer than 30 pages are reported but flagged as not interpretable.
6. **Baselines that bracket the result.** Random, always-cheapest, always-strongest, Unstructured-style per-document `auto`, rules-only, and the oracle.
   Numbers are reported relative to these so they mean something.
7. **Validate the benchmark itself.** It must rank the baselines in the expected order.
   Its routing score must also predict end-to-end parse quality on a held-out set (section 10.8).
   A benchmark that fails either check is fixed before it is used.
8. **Deterministic replay.** Features, lane outcomes and arbiter replies are stored content-addressed.
   Scoring a router version needs no model calls and runs in seconds.
   A separate live mode measures real latency, API drift and cost.
9. **Licence and PII registry.** Every item records its source, licence and allowed use.
   Non-commercial sets are marked evaluation-only and are never redistributed.
   Sets with known PII (RVL-CDIP, Enron) are excluded.
10. **Documented.** The benchmark has a datasheet (in the style of "Datasheets for Datasets") and a changelog.
    Versions are immutable; a new version never silently changes old scores.

### 10.2 Tracks

| Track | Measures | Ground truth |
|---|---|---|
| **A. Lane outcome** (headline) | under-route, over-route, regret, quality at cost | per-page lane quality/cost matrix from stub lanes scored against dataset ground truth |
| **B. Axis accuracy** | per-axis F1, ordinal error, confusion | construction, dataset metadata, human or silver labels |
| **C. Calibration and selection** | ECE, Brier, reliability, risk-coverage for review bands | axis labels + outcome labels |
| **D. Metamorphic stability** | monotonicity under degradation, invariance under neutral edits, determinism | pairs by construction |
| **E. Segmentation** | page-boundary and lane-run accuracy in mixed bundles | synthetic bundles with known boundaries, plus hand-labelled real bundles |
| **F. Intake and stress** | crash, timeout, quarantine precision and recall, container unpacking | known-bad corpora, crafted containers |
| **G. Efficiency** | pages/s per stage, p50/p95 latency, $ per 1k pages, arbitration and review rates, per profile | timing harness |
| **H. Arbiter bake-off** | per-model accuracy on the ambiguous slice, latency, cost, JSON validity, agreement | tracks A-C restricted to ambiguous pages |

### 10.3 Data composition (v0 pilot and v1 target)

Pages are drawn by stratified sampling over capture × degradation × content × script × container.
Every cell gets a minimum count.

| Source | Role | v0 pages | v1 pages | Label types |
|---|---|---:|---:|---|
| PureDocBench (all 3 versions, full triplets) | degradation and capture axes; monotonicity; lane outcomes with exact ground truth | 150 triplets (450) | 500 triplets (1,500) | construction, exact GT |
| olmOCR-Bench | born-digital vs old scans, math, tables, multi-column, tiny text; lane outcomes through unit tests | 250 | 900 | category metadata, unit tests |
| OmniDocBench slice | document-type and layout variety; fuzzy scans; handwritten notes | 100 | 400 | page attributes, exact GT (evaluation-only notice) |
| ExtractBench short split | forms, checkboxes, handwriting, scanned, rotated | 60 | 300 | tags P1-P3, pages checked by hand |
| getomni-ai benchmark | photo and low-quality capture | 40 | 200 | quality tags |
| Dr.DocBench | hard pages where parsers disagree; multilingual; challenge split | 40 | 300 | its GT, used as a separate challenge score |
| GNHK | phone-photographed handwriting | 30 | 150 | construction (handwriting_major, camera) |
| KITAB-Bench | Arabic, RTL | 30 | 150 | script |
| DocLayNet | exact layout-derived content flags on born-digital pages, including laws and regulations | 60 | 300 | layout boxes turned into flags |
| CourtListener RECAP | real scanned legal filings | 40 | 300 | human or silver labels |
| Synthetic text-layer set | invisible OCR layers of good and bad quality, stripped ToUnicode, misaligned layers, partial image regions | 80 | 400 | construction |
| Synthetic degradation ladders (Augraphy + our transforms) | monotonic degradation levels with recorded parameters | 60 pages × 4 levels | 250 × 4 | construction |
| Synthetic bundles | segmentation: 3-40 page documents mixing sources | 40 bundles | 300 bundles | construction |
| Containers set | DOCX with scanned images, EML/MSG with attachments, zip, HEIC, multi-page TIFF, password-protected files | 60 files | 400 files | construction |
| Stress corpora | Unstructured example-docs, Docling test data, Stressful PDF Corpus sample, Cabinet of Horrors, GovDocs1 sample | 300 files | 3,000 files | expected intake outcome |

**Sizes.**
v0 is about 1,500 labelled pages plus bundles and stress files.
v1 is about 6,000 pages.

**Sample size reasoning.**
Estimating a 1% under-route rate to ±0.5% at 95% confidence needs about 1,520 pages (Wilson/normal approximation, n = 1.96² × 0.0099 / 0.005²).
v1's sealed test split has at least 1,600 outcome-labelled pages for that reason.
v0 gives about ±0.8%, which is enough to steer the build but not to sign off a release.

### 10.4 Labels

Labels come in four grades.
Each label records its grade, and metrics can be restricted to any grade.

1. **Construction.** Known by how the page was made.
   Examples: a PureDocBench track, Augraphy parameters, synthetic text layers, bundle boundaries.
2. **Metadata.** Mapped from dataset annotations through a written, versioned mapping (`routebench/mappings/*.yaml`).
   Examples: olmOCR category `old_scans` → capture flatbed_scan and degradation at least 1; DocLayNet Table boxes → `tables`; ExtractBench P3 → handwriting, then checked per page.
3. **Gold (human).** Two annotators work independently in Label Studio from a written guide with visual examples.
   - Agreement is reported per axis as Krippendorff's α, with 0.8 as the target.
   - An axis below 0.67 has its definition revised before its labels are used.
   - Disagreements are adjudicated by a third person.
   - Pre-labels are hidden on a 20% blind subset, so we can measure whether pre-labels anchor the annotators.
4. **Silver (model).** Two different strong model families label independently through batch APIs, for example Gemini 3.8 Flash and Claude Haiku 4.5.
   Pages where they agree become silver; disagreements go to a person first.
   Silver labels are never used in the sealed test split's headline numbers.

**Label noise audit.**
After the first trained router exists, run confident-learning style checks: the pages where the router disagrees with the label with high confidence are re-reviewed.
Corrections go into a new benchmark version, never silently into the old one.

### 10.5 The lane outcome matrix (Track A)

For every page in the outcome set, and every lane L1-L5, we store:

- `quality[page][lane]`, a score in [0, 1] from the dataset's own evaluation:
  - PureDocBench and OmniDocBench: normalised text edit similarity, table TEDS, formula CDM, reading-order edit.
  - olmOCR-Bench: unit-test pass rate.
- `pass[page][lane]`, whether the quality clears the tier bar.
  The bars are stored with the tier, so they can change without re-running lanes.
  Proposed `exact` bars:
  - text similarity ≥ 0.98;
  - TEDS ≥ 0.90 where tables are present;
  - CDM ≥ 0.90 where formulas are present;
  - olmOCR tests ≥ 0.95.
- `cost[page][lane]` in seconds and dollars per profile.
  Latency and API cost are measured, not estimated.
- `runs`, the number of repeats.
  VLM lanes run twice; if the two disagree on `pass`, the page is marked `unstable` for that lane and scored with the worse result.

**The acceptable set.** It holds every lane that passes, plus any lane within ε of the best quality when none pass.
The oracle lane is the cheapest lane in the acceptable set.
A page where no lane passes is labelled `hard`, and the correct route for it is LH, or the best lane under `economy`.

**Stub lanes.**
These are minimal default configurations that stand in for the real lanes, which come later.
Their outcome columns are replaced when real lanes arrive; the pages, ground truth and scoring stay fixed.

| Lane | v0 stub on the M4 | v1 on the cluster |
|---|---|---|
| L1 | pypdfium2 text + Docling standard, no OCR | same |
| L2 | Marker balanced, `--disable_ocr` off | Marker balanced |
| L3 | Granite-Docling-258M through MLX; or Gemini 3.5 Flash-Lite page OCR through OpenRouter | PaddleOCR-VL-1.6 or MinerU2.5 on GPU |
| L4 | Gemini 3.8 Flash page OCR through OpenRouter | Chandra 2 on GPU |
| L5 | same as L4, with a handwriting-specific prompt | Chandra 2 |

### 10.6 Metrics

**Track A (headline).**

- **Under-route rate (UR).** The share of pages whose assigned lane is below every lane in the acceptable set, or whose assigned lane fails when a passing lane existed.
  Reported overall, per slice and per tier.
  This is the release-gating number.
- **Over-route rate and wasted cost.** Compute spent above the oracle lane's cost.
- **Routing regret per 1,000 pages.** For each page, cost(assigned) + λ·fail(assigned), minus the same for the oracle, summed. λ comes from the tier's cost matrix.
- **Quality-at-cost curve.** Sweep the tier thresholds and plot end quality against compute spent, with the always-cheapest and always-strongest points.
  Report two summary numbers:
  - **APGR**, the share of the quality gap between always-cheapest and always-strongest that the router recovers, at matched cost;
  - the **cost to reach 95% of always-strongest quality**.

  Both follow the LLM-routing benchmarks RouteLLM (arXiv 2406.18665) and RouterBench (arXiv 2403.12031) **[recalled; verify the definitions before publishing numbers]**.
- **LH rate.** The share of pages sent to review, and the share of those that were actually `hard`.

**Track B.** Macro-F1 and confusion per axis.
For the ordinal degradation axis, quadratic-weighted kappa and mean absolute level error.

**Track C.**

- Adaptive-bin ECE and Brier score per axis and per arbiter, with reliability diagrams.
- Risk-coverage curves and their area (AURC) for the review bands: as bands tighten, how fast does under-routing fall and review volume rise?

**Track D.**

- **Monotonicity violation rate (MVR).** Over PureDocBench triplets and degradation ladders, the share of pairs where the more degraded version gets a lower-capability lane than the cleaner one.
  The target is 0 on hard-constraint pairs; every violation is listed.
- **Invariance violation rate (IVR).** The same page after neutral edits should get the same lane.
  The edits:
  - re-saving the file with qpdf;
  - stripping metadata;
  - renaming the file;
  - lossless re-encoding of images;
  - a rotation that the orientation stage should undo.
- **Determinism.** The same input twice gives an identical manifest in replay mode.
  In live mode the rate of lane changes is reported, which exposes Jev and VLM variance.

**Track E.** Page-boundary F1, segmentation error on lane runs (Pk and WindowDiff), and cross-page table continuity recall.

**Track F.**

- Crash rate and timeout rate, both with a target of 0.
- LQ precision and recall against expected outcomes.
- Container recall: the share of child documents found.
- Peak memory per file.

**Track G.** Per profile and per stage: pages/s, p50/p95 latency, memory, and $ per 1,000 pages split by arbiter.

**Track H.** Per candidate model on the ambiguous slice:

- per-axis accuracy against gold;
- JSON validity rate and `unsure` rate;
- p50/p95 latency from our network;
- $ per 1,000 calls;
- agreement between two samples;
- the Track A metrics when that model is the arbiter.

### 10.7 Splits

| Split | Share | Use |
|---|---|---|
| `train` | 50% | learned router |
| `calib` | 15% | isotonic calibration and review bands |
| `dev` | 15% | iteration, prompt and criteria changes, CI |
| `test` (sealed) | 20% | release candidates only |
| `challenge` | separate | Dr.DocBench plus the hardest RECAP pages; reported separately, never averaged in |
| `fresh` | rolling | 200 new real-world pages labelled each quarter, to catch overfitting to the benchmark |

`routebench-mini` is a fixed stratified 150-page subset of `dev`.
It runs on every commit in replay mode in under a minute.

### 10.8 Validity checks

1. **Baseline ordering.** The benchmark must rank oracle ahead of learned router, rules-only, Unstructured-auto, always-strongest (on regret), always-cheapest and random, in that order.
   If a sensible ordering flips, the benchmark has a bug.
2. **Predictive validity.** On 300 held-out pages with full ground truth, run each router version's chosen lanes end to end.
   The rank correlation between RouteBench regret and measured end-to-end quality at cost must be strong (Spearman ρ ≥ 0.8 across at least five router variants).
   This checks that the benchmark measures what we care about.
3. **Label-grade sensitivity.** Headline metrics computed on gold-only and construction-only labels must agree with the full set within their intervals.
   If they do not, silver labels are biasing the result.
4. **Leakage test.** Retrain with duplicate-aware splitting turned off.
   If scores jump, the split was leaking and must stay duplicate-aware.

### 10.9 Harness

```
routebench/
  datasets/      loaders per source, licence registry, download + checksum
  mappings/      metadata → axis label mappings (versioned yaml)
  synth/         text-layer forger, degradation ladders, bundle maker, container maker
  labels/        Label Studio config, guide, agreement stats, adjudication
  lanes/         stub lane runners and scorers (edit distance, TEDS, CDM, olmOCR tests)
  store/         content-addressed cache: features, lane outcomes, arbiter replies
  metrics/       tracks A-H, bootstrap, paired tests
  report/        markdown + HTML report, misroute gallery with thumbnails and reasons
  cli.py         rb build | rb lanes | rb score <router> | rb compare a b | rb live | rb report
```

- **Replay by default.** `rb score` reads stored features and outcomes and makes no network calls.
- **Live mode.** `rb live` re-runs probes and arbiters with rate limiting, budget accounting and response caching keyed by (page hash, stage, model, prompt version).
- **Reproducibility.** Every run writes a run record: git SHA, benchmark version, feature, router and policy versions, arbiter models, profile, seed and timings.
- **CI gates on `dev`**, each at the 95% level on paired tests:
  - UR does not regress by more than 0.3 points;
  - MVR on hard pairs stays 0;
  - Track F crash rate stays 0;
  - ECE does not regress by more than 0.01.
- **The misroute gallery.** Every under-routed page with its thumbnail, features, decision path and lane outcomes.
  Most improvements will come from reading this page.

### 10.10 Budget and cost control

OpenRouter credit is about $21; we cap spend at $15.

| Item | Estimate |
|---|---|
| Arbiter bake-off (done 2026-09-24: 20 models × 60 pages, plus a second run for 5 finalists) | $2.65 actual |
| Jev on ~1,500 pages × 2 runs | under $0.20 |
| v0 lane outcomes, hosted stubs: ~900 image pages × L3 (Flash-Lite, ~$0.004/page) + L4/L5 (3.8 Flash, ~$0.007/page) | about $10 |
| Silver labels, batch APIs (50% off), ~500 pages × 2 families | about $1-2 |

That comes to about $14-16, so v0 runs in two passes: a 300-page pilot first, then a check against the cap before the rest.
The harness reads the key's usage endpoint before and after each batch and stops at the cap.
v1 lane outcomes need GPU time for Chandra 2 and PaddleOCR-VL (about 1.4-2 pages/s per H100 for Chandra), and a separate budget.

---

## 11. Deployment profiles

The profile files are `profiles/m4-demo.yaml` and `profiles/cluster.yaml`.
The code path is the same; only backends and concurrency differ.

| Stage | M4 demo | Cloud cluster |
|---|---|---|
| S0 intake | process pool, 8 workers | Ray Data CPU tasks |
| S1 structural | pypdfium2 + pikepdf, 3-4 ms/page **[measured]** | same, on arm64 or x86 nodes |
| S2 render + IQA | pypdfium2 render at 12 ms plus IQA at 8 ms **[measured]**; JPEG passthrough for scans | same |
| S2 layout | egret-m, ONNX Runtime with the Core ML backend, ~40 ms/page **[measured]** | egret-m ONNX with the CUDA/TensorRT backend, batched on a GPU pool |
| S2 orientation | PP-LCNet doc_ori ONNX, image pages only | same |
| S2 Apple extras | PyObjC: page quadrilateral (~10 ms), lens-smudge score; Swift helper only for `RecognizeDocumentsRequest` (all optional columns) | null |
| S3 text forensics | CPU; `OCRErrorPredictor` on CPU or through the Core ML backend | CPU or GPU batch |
| S3 quick OCR (ambiguous image pages only) | Apple Vision fast mode, ~330 ms **[measured]** | GPU text detector and recogniser (e.g. PaddleOCR) |
| S5 router | LightGBM in process, under 1 ms | same, inside the Ray task |
| S6 Jev | OpenRouter decisions endpoint | TypeSafe direct; enterprise limits if needed |
| S6 VLM | hosted bake-off winner through OpenRouter; local fallback `mlx_vlm.server` | provider API with batch discounts, or vLLM on our GPUs with the same OpenAI-compatible contract |
| Storage | local Parquet + DuckDB | object storage + Parquet; DuckDB or Trino for queries |
| Orchestration | `jst route` CLI with a local queue | Ray Data pipeline on Kubernetes; KEDA scales on queue depth; CPU and GPU pools scale separately **[recalled; validate in Phase 5]** |

**M4 throughput estimate.**
CPU probing runs at about 80-120 pages/s across workers **[measured, research agent]**.
The layout model single-stream runs at about 25 pages/s, and probably 30-40 with batching and two sessions **[to be measured]**.
So the M4 routes somewhere around 20-35 pages/s before arbitration.
At 15% arbitration with about 0.5-1 s per arbiter call and 16-32 concurrent requests, arbitration keeps up.
The Jev rate limit (1,200 RPM) is not binding at this scale.

**Cluster sizing rule of thumb.**
One GPU running the layout detector serves several hundred pages per second, if batched and not stage-bound.
Docling's own L4 benchmark found its pipeline stage-bound at 24-29% GPU use, so we measure our pipeline rather than assume.
CPU probes scale linearly with cores.
Above about 130 pages/s the Jev rate limit binds at 15% arbitration: request higher limits, lower the arbitration rate, or add Kev replicas.

**The demo itself.**
`jst route <folder>` writes manifests.
`jst view` opens a local HTML page with each page's thumbnail, lane, modifiers, probabilities and the decision path.
`rb report` shows the RouteBench results for the router version being demoed.

---

## 12. Implementation

### 12.1 Stack

- Python 3.12 with `uv`, and Pydantic v2 for contracts.
- **PDF and images.** pypdfium2, pikepdf and pdfminer.six (font detail); opencv-python-headless, numpy, Pillow; Augraphy for degradation ladders.
- **Models.** onnxruntime with the Core ML backend on the M4 and onnxruntime-gpu on the cluster; `docling-ibm-models` and surya where no ONNX export exists yet.
- **Learning.** LightGBM and scikit-learn (isotonic calibration).
- **Storage.** Parquet and DuckDB.
- **Arbiters.** An OpenAI-compatible client (httpx) for VLMs and a Jev client over OpenRouter or `typesafe-sdk`, both behind `arbiters.base`.
- **Labelling and scoring.** Label Studio; the official scorers from PureDocBench, OmniDocBench and olmOCR-Bench, vendored and pinned.
- **Cluster.** Ray, Ray Data, KubeRay and KEDA.

### 12.2 Repository layout

```
jesteruct/
  pyproject.toml
  policies/lanes.yaml
  profiles/m4-demo.yaml  profiles/cluster.yaml
  src/jesteruct/
    intake/  probes/  features/  router/  arbiters/  segment/  manifest/  feedback/
    backends/        onnx.py (CoreML/CUDA EPs)  vlm_client.py  jev_client.py  apple_helper.py
    cli.py           jst route | jst view | jst explain <doc> <page>
  swift/AppleVisionHelper/   long-lived JSON-over-stdio helper (macOS only)
  routebench/        (section 10.9)
  tests/
  data/              gitignored: datasets, caches, outcomes
  research/  archive/
```

### 12.3 Phases

Weeks assume one engineer full time and are rough.
Each phase ends with something that runs end to end.

| Phase | Build | Exit criterion |
|---|---|---|
| **0. Foundations** (week 1) | repo, `uv` project, profiles; licence registry; downloads with checksums for PureDocBench, olmOCR-Bench, OmniDocBench slice, ExtractBench short, GNHK, KITAB, DocLayNet sample, stress corpora; axis definitions and labelling guide; confirm Jev access through OpenRouter with one test call | datasets on disk with checksums; guide agreed; a Jev call succeeds |
| **1. RouteBench v0 skeleton + rules router** (weeks 1-3) | loaders, metadata mappings, synthetic text-layer set, degradation ladders, bundles, containers; content-addressed store; S0, S1, S3 and rules-only S5; manifest v1; baselines (random, always-cheapest, always-strongest, Unstructured-auto, rules-only); Tracks B, D, F scoring | `rb score rules-only` produces a report with intervals; baseline ordering check passes on Tracks B, D, F |
| **2. Visual probe + lane outcomes pilot** (weeks 3-5) | S2 on the M4 (render, IQA, egret-m via the Core ML backend, orientation, figure classifier, optional Swift helper); layout bake-off; stub lanes; outcome matrix for the 300-page pilot, then all of v0 within budget | Track A works; oracle and always-strongest baselines computed; M4 stage timings in Track G |
| **3. Learned router + arbiters** (weeks 5-8) | per-axis LightGBM, calibration, expected-cost policy, review bands; Jev arbiter with frozen criteria; VLM bake-off over the section 3.5 pool; gold labels on ~600 pages, silver on the rest | on `dev`: UR ≤ 1.5% (v0 precision), arbitration ≤ 15%, MVR = 0 on hard pairs; bake-off winner chosen with numbers |
| **4. Segmentation, feedback, demo** (weeks 8-10) | Viterbi smoothing, continuation, region instructions, escalation ladder, feedback contract; `jst view` demo UI; Track E; predictive-validity study on 300 pages | Track E reported; predictive validity ρ ≥ 0.8; demo runs on a mixed folder on the M4 |
| **5. Cluster profile** (weeks 10-12) | container images; Ray Data pipeline; CUDA EP layout serving; vLLM fallback arbiter; KEDA autoscaling; load test | same RouteBench scores on both profiles (within intervals); throughput target met at the chosen cluster size |
| **6. RouteBench v1 + release** (weeks 12-14) | v1 data (~6,000 pages), real or GPU lanes for L3-L5 outcomes, sealed test run, datasheet, runbook | sealed test: UR < 1% on `exact` with interval upper bound under 1.5%; Track F crash rate 0 |

### 12.4 Route manifest contract (`manifest.v1`)

```json
{
  "manifest_version": "1.0",
  "doc_id": "sha256:…",
  "source": {"path": "…", "mime": "application/pdf", "parent_doc_id": null},
  "versions": {"features": "1.0", "router": "0.3.1", "policy": "2026-10-01",
               "arbiters": {"jev": "jev-1.13.0", "vlm": "google/gemini-3.8-flash"},
               "profile": "m4-demo"},
  "tier": "exact",
  "pages": [{
    "index": 0,
    "phash": "…",
    "route_vector": {
      "text_layer": {"value": "untrusted_ocr_layer", "p": 0.91},
      "capture": {"value": "flatbed_scan", "p": 0.97},
      "degradation": {"value": 1, "p": 0.72},
      "layout": {"value": "multi_column", "p": 0.88},
      "content_flags": {"tables": 0.95, "math_display": 0.02, "handwriting_minor": 0.64},
      "script": {"value": "latin", "lang": "fi", "p": 0.93},
      "orientation": {"rotation": 0, "skew_deg": 0.8},
      "continuation": 0.12,
      "density_tokens": 1450
    },
    "lane": "L3",
    "modifiers": ["tables", "multi_column", "handwriting_minor"],
    "regions": [{"bbox": [0.62, 0.81, 0.95, 0.90], "kind": "handwriting", "target": "handwriting"}],
    "decided_by": "model+vlm",
    "expected_cost": {"L3": 1.8, "L4": 2.4, "L5": 6.0},
    "reasons": ["rule:image_coverage>0.9", "axis:degradation p(>=2)=0.21",
                "vlm:handwriting=fields_filled_by_hand (2/2 agree)"],
    "timings_ms": {"s1": 3, "s2": 58, "s3": 11, "s6": 640}
  }],
  "segments": [{"pages": [0, 5], "lane": "L3", "modifiers": ["tables"]}],
  "quarantine": null
}
```

---

## 13. Risks

| Risk | Mitigation |
|---|---|
| Stub lanes make oracle labels that differ from the real lanes | outcome columns are pluggable and re-run when real lanes land; pages and ground truth stay fixed; report which lane versions produced the matrix |
| Public benchmarks do not look like our real documents | RECAP legal slice, the rolling `fresh` split, per-slice reporting, drift monitoring on feature distributions |
| Benchmark overfitting through repeated `dev` use | sealed test, `fresh` split, CI on `routebench-mini` only, logged sealed runs |
| Jev is weeks old; its behaviour and terms may change | pinned version, drift probe, arbiter interface with a Kev fallback, no training on its outputs |
| Hosted VLM latency or price changes | bake-off repeated monthly in live mode; the policy can switch models by config |
| Local MLX models misjudge capture type | fallback only; must pass Track H before use |
| Apple-only features leak into router dependence | the columns are masked at random during training; cluster-profile RouteBench scores must match the M4's |
| OpenRouter budget overrun | budget guard in the harness, pilot first, response cache |
| Licence limits (Datalab weights, AGPL detectors, evaluation-only datasets) | licence registry per item and per model; interfaces allow swaps |
| Labelling is slow | construction and metadata labels cover most axes; gold labels only where needed; active selection of what to label |

---

## 14. Open decisions

Settled since v1: confidentiality is out of scope for now; hosted APIs are allowed; the demo runs on Apple Silicon; the cloud cluster comes later; OpenRouter is available with a $15 cap.

Still open:

1. **Lane set.** Sign-off on L0-L5, LQ and LH, with modifiers instead of more lanes.
2. **Default tier and cost ratio.** How bad is a silent extraction error compared with a reviewer-minute?
   A starting point of 30:1 is assumed.
3. **Who labels gold pages?** Two people are needed for about 600 pages in Phase 3.
   If there is only one, gold becomes single-annotator plus silver agreement, and the benchmark reports that.
4. **v1 GPU budget.** Lane outcomes with Chandra 2 and PaddleOCR-VL need GPU hours; a rough figure is a few hundred H100-minutes for 6,000 pages.
5. **Commercial use.** If the organisation passes Datalab's revenue thresholds, Chandra, Marker and Surya weights (including `OCRErrorPredictor`) need a licence or replacements.
   Evaluation-only datasets stay in RouteBench either way, but are never redistributed.

---

## 15. Sources

Full lists with URLs are in `research/`.

- **Jev.**
  - [API docs](https://docs.typesafe.ai/api), [models](https://docs.typesafe.ai/models), [jaggedness](https://docs.typesafe.ai/model-jaggedness/jev-1.13), [MCA](https://typesafe.ai/legal/mca)
  - [Classmethod](https://dev.classmethod.jp/en/articles/typesafe-jev-doc-type-classification/), [DocJev](https://github.com/jerryjliu/docjev), [doc-router](https://github.com/misbahsy/doc-router)
  - [OOD calibration](https://github.com/scienthoon/jev-ood-calibration), [Kev](https://github.com/jaredpalmer/kev), [OpenRouter on Jev](https://openrouter.ai/blog/insights/what-is-jev/), [learnjev FAQ](https://learnjev.com/faq)
- **Docling.** [model catalog](https://docling-project.github.io/docling/usage/model_catalog/), [confidence scores](https://docling-project.github.io/docling/concepts/confidence_scores/), [issue #4357](https://github.com/docling-project/docling/issues/4357), [Docling layout paper, arXiv 2509.11720](https://arxiv.org/abs/2509.11720).
- **Datalab.** [Marker](https://github.com/datalab-to/marker), [Chandra](https://github.com/datalab-to/chandra), [Marker 2 benchmarks](https://www.datalab.to/blog/marker-2).
- **Apple.** [RecognizeDocumentsRequest](https://developer.apple.com/documentation/vision/recognizedocumentsrequest).
- **Papers.**
  - [arXiv 2608.06607 pre-inference routing](https://arxiv.org/pdf/2608.06607)
  - [FinixDoc 2608.22842](https://arxiv.org/pdf/2608.22842)
  - [HPD-Parsing 2607.18839](https://arxiv.org/pdf/2607.18839)
  - [WeVisDoc 2609.20423](https://arxiv.org/pdf/2609.20423)
  - [PureDocBench 2605.07492](https://arxiv.org/abs/2605.07492)
  - [ExtractBench 2607.29677](https://arxiv.org/abs/2607.29677)
- **Benchmarks.** [PureDocBench](https://github.com/zhihengli-casia/PureDocBench), [olmOCR-Bench](https://huggingface.co/datasets/allenai/olmOCR-bench), [OmniDocBench](https://github.com/opendatalab/OmniDocBench), [ExtractBench](https://github.com/run-llama/ExtractBench), [Dr.DocBench](https://github.com/2077AI/DrDocBench), [GNHK](https://github.com/GoodNotes/GNHK-dataset), [KITAB-Bench](https://github.com/mbzuai-oryx/KITAB-Bench), [DocLayNet](https://github.com/DS4SD/DocLayNet), [PDF Association Stressful Corpus](https://pdfa.org/stressful-pdf-corpus/), [CourtListener bulk data](https://www.courtlistener.com/help/api/bulk-data/bulk-legal-data).
- **Vision models.** OpenRouter model catalogue (pulled 2026-09-23 via `/api/v1/models`), [DeepSeek vision guide](https://api-docs.deepseek.com/guides/vision/), [RVL-CDIP zero-shot test](https://murraycole.com/posts/ai-document-classification).
