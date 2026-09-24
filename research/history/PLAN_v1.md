# Jesteruct: Document Sorting and Lane Routing Plan

Status: draft v1, 2026-09-23.
Scope: the sorting and routing layer.
The processing lanes themselves (Docling, Marker, VLM OCR and so on) are defined here only as far as the router needs them; building them comes later.

Research notes behind every claim here live in `research/` (one file per track, each with URLs).
Anything marked **[unverified]** came from a single secondary source or launch-week material and should be re-checked before we depend on it.

---

## 1. Summary

We will build a page-level router that looks at every page of every incoming file, measures it cheaply, and writes a route manifest saying which lane each page (or run of pages) should go to and why.

The router is a cascade.
Deterministic probes (PDF structure, image quality, a fast layout detector, text-layer forensics) run on every page and settle most of them with rules or a small calibrated model.
Only the ambiguous remainder goes to arbiters: TypeSafe Jev for text-evidence decisions, and a small vision LLM for the questions that need eyes, such as "is this handwriting?" or "is this a camera photo of a page?".
A human review queue catches what neither arbiter is confident about.

Three findings drive the design more than anything else.

1. Degradation level predicts parser failure better than document type does.
   FinixDoc (arXiv 2608.22842) measured a 25-35 point accuracy cliff between clean digital pages and camera-captured pages across every model it tested, and large general VLMs beat small document specialists only on the degraded side.
2. Cheap pre-inference features are enough to route well, when difficulty is visible in them.
   A calibrated random forest over 13 such features cut extraction cost 31-77% with no accuracy loss (arXiv 2608.06607), and gave no benefit on clean digital invoices where there was no difficulty to detect.
3. Jev is text only.
   It cannot look at a page, its probabilities are not calibrated out of the box, and it will not abstain unless we give it an explicit way to.
   It is a good arbiter over evidence we compute, not a replacement for computing it.

The router does not output a single label.
It outputs a route vector (source, text-layer trust, degradation, layout complexity, content flags, script) and a lane chosen from that vector by a versioned policy table.
That split means the lane set can change later, when processing is built, without retraining or rewriting the probes.

---

## 2. What the research says

### 2.1 TypeSafe Jev

Jev is TypeSafe AI's "System One" decision model, in limited early access since 15 September 2026.
It returns typed answers with probabilities instead of text ([docs](https://docs.typesafe.ai/api), [Simon Willison](https://simonwillison.net/2026/Sep/21/jev/)).

- **Primitives.** `choice` (up to 255 options, reliable to roughly 240 per TypeSafe), `score` (2-10 ordered levels) and `noul` (a yes/no probability; the name is short for Bernoulli).
  Many questions can be asked over one `state` in one request, and they are answered independently: one audit found 16 questions vs 1 moved answers by 0.008 on average ([jev-calibration-audit](https://github.com/jujumilk3/jev-calibration-audit)).
- **Input.** Text or JSON only.
  "No image, audio, or video input" ([models](https://docs.typesafe.ai/models)).
  The context limit is 64k per request in the docs and 32k on OpenRouter and Cloudflare; treat 32k as the safe limit.
- **Cost and speed.** $0.042 per million input tokens, output free.
  Independent medians run from 139 to 650 ms, with tails past 1.4 s ([DocJev](https://github.com/jerryjliu/docjev)).
  At roughly 1k tokens per page that is about $42 per million pages.
  The binding constraint is the 1,200 requests/minute rate limit, which is about 72k pages per hour at one page per request.
- **Where it does well.** Classifying page type from extracted text.
  Classmethod got 19/20 OCR'd trade-document pages right on the page alone and 20/20 when the previous page was included; every answer at 0.8 or above was correct ([Classmethod](https://dev.classmethod.jp/en/articles/typesafe-jev-doc-type-classification/)).
  DocJev got 40/40 on document typing and 7/8 packets split exactly right.
- **Where it is weak.** TypeSafe's own list covers numbers, counting, dates, multi-step questions, large irrelevant state and adversarial text ([jaggedness](https://docs.typesafe.ai/model-jaggedness/jev-1.13)).
  Independent audits add these:
  - Rewording the criteria moves accuracy 15-30 points.
  - Packing many items into one state hurts.
  - Adding an irrelevant option shifts the other options' probabilities.
  - Non-English input costs 3-11 points.
- **Calibration.** ECE was about 0.03 on public benchmarks it has probably seen, and 0.107 on 900 unseen tickets ([jev-ood-calibration](https://github.com/scienthoon/jev-ood-calibration)).
  Choice and score run overconfident while noul runs underconfident.
  The `confidence` field is a function of `probabilities` and adds nothing.
  Remove the "unknown" option and accuracy on unanswerable items goes from 0.95 to 0.00 at 0.79 stated confidence.
- **Determinism.** 50 identical requests produced 15 distinct answer sets, and borderline probabilities wandered between 0.43 and 0.53.
  There is no seed.
  Pin `jev-1.13.0` and log the returned `model`.
- **Terms.** The customer agreement forbids using outputs to "train a model to imitate" the service ([MCA](https://typesafe.ai/legal/mca)).
  That probably rules out training our own router on Jev labels; legal should read it.
  Zero data retention is enterprise-only, and hosting is in the US with EU transfers under standard contractual clauses.
- **Open alternative.** Kev (Apache-2.0; 0.8B, 4B and 9B) serves the same API shape ([kev](https://github.com/jaredpalmer/kev)).
  We should code against that shared shape so a local model can stand in for confidential material.
  I found no independent quality comparison for Kev itself **[unverified]**.

### 2.2 Docling

Latest is 2.130.0, released 22 September 2026 ([PyPI](https://pypi.org/project/docling/)).

- **Two pipeline families.** The first is `StandardPdfPipeline`: docling-parse text, then optional OCR, the Heron or Egret layout model, and TableFormer in `ACCURATE` or `FAST` mode.
  The second is `VlmPipeline`: one VLM over the page image emitting DocTags, with Granite-Docling-258M, SmolDocling and several larger models including Chandra and Nemotron Parse.
- **Layout labels useful for routing.** Table, Formula, Code, Picture, Form, Key-Value Region and Checkbox-Selected/Unselected ([model catalog](https://docling-project.github.io/docling/usage/model_catalog/)).
  A layout-only pass is its fastest mode: about 3.3 pages/s on an L4 GPU, vs 0.64-1.5 for OCR or VLM combinations (community benchmark, discussion #3442).
- **OCR decision.** OCR runs per layout cluster, on regions that overlap bitmaps or have no programmatic text, with explicit handling of invisible text in render mode 3 (`base_ocr_model.py`).
  `bitmap_area_threshold` defaults to about 0.05.
- **Self-assessment.** `result.confidence` gives per-page `parse_score`, `layout_score` and `ocr_score`, plus POOR/FAIR/GOOD/EXCELLENT grades ([confidence scores](https://docling-project.github.io/docling/concepts/confidence_scores/)).
  `table_score` was documented but not implemented in the snapshot we read.
  This is the post-parse signal the feedback loop (section 5.9) will use for Docling lanes.
- **Cheap classifier.** DocumentFigureClassifier-v2.5: EfficientNet-B0, 4.08M parameters, 26 classes (chart types, table, signature, stamp, QR code, screenshot, chemistry and more), 90.7% accuracy ([HF](https://huggingface.co/docling-project/DocumentFigureClassifier-v2.5)).
- **Weak spots that should shape routing.**
  - Multi-column reading order has been broken across several releases and is still open (#1203, #2067, #3198, #2201).
  - Complex tables with merged cells or multi-level headers break (#2241, #2790).
    TableFormer `ACCURATE` drops rows on dense tables from 2.118.0 (#4255).
  - RTL text comes out reversed (#253), and Granite-Docling's JA/AR/ZH support is labelled experimental.
  - Handwriting is not a target of any Docling model.
  - Formula LaTeX has spacing bugs (#2374).
- **A trap for the router.** From 2.123.0 the threaded docling-parse backend silently drops most of an existing OCR text layer on about 17% of a 29-document sample (#4357).
  Our router must do its own text-layer forensics rather than trust what a parser reports.

### 2.3 Marker, Surya and Chandra (Datalab)

Marker 2.0 is a July 2026 rewrite ([repo](https://github.com/datalab-to/marker)).

- **Modes and flags.**
  - `--mode balanced|fast`, `--force_ocr`, `--strip_existing_ocr` and `--disable_ocr` (pure text layer, CPU only).
  - `--use_llm` adds per-block LLM processors for forms, handwriting, cross-page table merging and math.
  - Structured JSON-schema extraction (`ExtractionConverter`) existed in 1.x but is gone from the 2.0 open-source code.
    It now lives in the hosted API.
- **Text-layer trust heuristic, read from source** (`marker/builders/line.py`, `ocr.py`).
  A page's embedded text is trusted only if all four of these hold:
  1. pdftext returned lines.
  2. `surya.ocr_error.OCRErrorPredictor` does not call the text bad.
  3. At least 25% of layout blocks (excluding figures, pictures and tables) overlap an embedded text line.
  4. Fewer than 50% of lines overlap more than two neighbours, a pattern that signals a duplicated or broken layer.

  This is the best single born-digital-vs-bad-layer check we found, and we will reuse its logic.
- **Surya 2.** One VLM of about 650M parameters for OCR, layout, tables and reading order, plus a small line detector.
  It covers 90+ languages and scores 83.3% on olmOCR-bench.
  Its layout labels include `Handwriting`, which Marker's handwriting processor keys on.
- **Chandra 2.** A full-page OCR VLM aimed at handwriting, forms, complex tables and math.
  It scores about 85.8% on olmOCR-bench and 77.8% averaged over 43 languages ([repo](https://github.com/datalab-to/chandra)).
  Sources disagree on 4B or 5B parameters, and it runs at 1.4-2 pages/s on an H100.
- **Datalab's own olmOCR-bench numbers** ([blog](https://www.datalab.to/blog/marker-2)).
  Treat them as vendor-reported.

  | System | Overall | Throughput |
  |---|---|---|
  | Marker balanced | 76.0% (83.5% born-digital) | 2.9 pages/s |
  | Marker fast | 66.6% | 7.4 pages/s |
  | MinerU pipeline | 72.7% | 0.54 pages/s |
  | Docling | 50.3% | 2.1 pages/s |

  On old and degraded scans Marker scores 43.2% in both modes, so balanced mode buys nothing there.
  That is a direct argument for a separate degraded lane with a real VLM behind it.
- **Licences.** Code is Apache 2.0.
  The Marker and Surya weights are free under $5M revenue or funding.
  Chandra's weights are free only under $2M and add a clause against competing with Datalab's API. This matters for a commercial deployment and needs a decision (section 15).

### 2.4 The wider parser landscape

- **OmniDocBench v1.6**, a harder set that is not comparable to v1.5:

  | Model | Overall | Notes |
  |---|---|---|
  | PaddleOCR-VL-1.6 (0.9B) | 96.3 | Formula CDM 97.5, table TEDS 94.8; claims state of the art on degraded Real5-OmniDocBench |
  | MinerU2.5-Pro (1.2B) | 95.75 | |
  | WeVisDoc-4B | 95.38 | A refinement stage adds +4.03 on degraded input ([arXiv 2609.20423](https://arxiv.org/pdf/2609.20423)) |
  | DeepSeek-OCR-2 | 90.25 | 2,932 tokens/s |
  | Youtu-Parsing | n/a | Best table TEDS, but only 315 tokens/s |

  Accuracy and speed clearly trade off per tool, so the policy table needs a cost/quality tier as well as a lane.
- **Cost driver.** HPD-Parsing (arXiv 2607.18839) found decoder latency dominates VLM parsing cost and scales with output length.
  Content density is a better cost predictor than input resolution, so the router should estimate it.
- **Known VLM failure modes.** dots.ocr and olmOCR loop on repeated characters such as dot leaders and underscores; olmOCR 2 mitigates this with temperature scaling.
  Historical-document work (arXiv 2607.24077) shows VLM OCR can beat classical OCR on CER while quietly substituting named entities, an error class standard metrics miss.
  For legal material that is the worst possible failure, so the processing layer must verify.
- **Unstructured's `auto` strategy**, read from source: images go to hi_res; PDFs with embedded tables or images go to hi_res; PDFs with any extractable text go to fast; everything else goes to ocr_only.
  Its check is per document, not per page, which is exactly what we want to improve on.
  Its `is_pdf_too_complex()` safety gate (more than 10,000 graphics operations and a graphics-to-text ratio above 20) is worth copying.

### 2.5 Small vision LLMs

- **DeepSeek.** The "new flash model" is DeepSeek-V4.1-Flash, generally available since 10 September 2026 with native vision (`deepseek-flash`; images downsampled to about 1300 px, about 1024 tokens each) ([vision guide](https://api-docs.deepseek.com/guides/vision/)).
  It is very cheap, roughly $0.15-0.30 per million input tokens with peak and off-peak tiers **[unverified: secondary sources]**.
  The hosted API runs in mainland China, which likely rules it out for client documents.
  The open weights could be self-hosted.
- **Hosted picks.** Gemini 3.1 and 3.5 Flash-Lite run about $0.25-0.30 in and $1.50-2.50 out per million tokens, with strict `responseSchema` JSON on image input.
  Gemini 3.8 Flash is $0.75/$3.75 on introductory pricing.
  Claude Haiku 4.5 is $1/$5 with predictable image tokenisation.
  GPT-5-nano is $0.05/$0.40, but strict schema support on image input is untested.
  Mistral Small is a cheap EU-hosted option.
- **Local picks.**
  - Qwen3-VL-4B (Apache-2.0) and InternVL3.5-4B (Apache-2.0), both with vLLM and MLX support.
  - MiniCPM-V-4.6 (1.3B) as the ultra-cheap choice.
  - Moondream 3.1, for grounded detect and point outputs that can be checked.
  - Phi-4-reasoning-vision-15B, which can switch reasoning on for hard pages.
- **Ceiling.** Zero-shot document typing with a small VLM plateaus around 60-70% across the 16 RVL-CDIP classes, against about 95% for a trained model ([murraycole.com](https://murraycole.com/posts/ai-document-classification)).
  Few-shot or light fine-tuning closes most of the gap.
  So a VLM belongs on the ambiguous tail and on questions with a yes/no visual answer, not as the first pass.
- **Handwriting.** Still unsolved as transcription in 2026 (WildHandBench, KIE-HVQA).
  Detecting that a page is handwritten is easy; reading it correctly is not.
- **Verification.** VLMs confirm plausible-but-wrong text.
  A verifier must never be the same model or prompt that extracted the text.

---

## 3. Design principles

1. **Route pages, then group them.** Real files mix born-digital pages with scanned signature pages, faxed annexes and photographed exhibits.
   Route each page, then merge contiguous pages into segments.
   Per-document routing, as in Unstructured's `auto`, is the failure we are avoiding.
2. **Measure before you ask.** Every question a probe can answer is answered by the probe.
   Arbiters see our measurements as evidence; they are not asked to rediscover them.
3. **Degradation first, content second, semantics third.** Degradation decides the base lane, content decides which processors are switched on inside it, and document semantics (contract, invoice, letter) go downstream to extraction schemas.
4. **Output requirements, not tools.** The router says "this page needs OCR on a degraded camera image with a table and Finnish text".
   A policy table maps that to a lane and a tool.
   Lanes can then change without touching the router.
5. **Calibrated probabilities, asymmetric costs.** Every model decision carries a calibrated probability.
   The lane is chosen by minimising expected cost, and sending a hard page to a cheap lane costs far more than the reverse, because the first failure is silent.
6. **Every decision is explained and replayable.** The manifest records the features, the rule or model that decided, its probability, and all versions.
   A route can be recomputed exactly from the stored features.
7. **Local by default.** Probes, rules and the learned router run on our hardware.
   External arbiters are optional, per-tenant, and swappable for local equivalents (Kev for Jev, Qwen3-VL for Gemini).
8. **Close the loop.** Post-parse quality signals come back to the router.
   They drive automatic escalation now and training data later.

---

## 4. Lane architecture (proposal, to be ratified)

### 4.1 The route vector

Each page gets a vector across these axes.
Everything the policy table needs is here.

| Axis | Values | Primary sources |
|---|---|---|
| `container` | native_office, pdf, image, email, archive, audio_video, unsupported | magic bytes, extension, MIME |
| `text_layer` | none, trusted, untrusted_ocr_layer, garbled, partial | PDF forensics, Marker-style checks |
| `capture` | vector, flatbed_scan, fax_bilevel, camera_photo, screenshot | image filters, EXIF, border and perspective analysis |
| `degradation` | 0 clean, 1 mild, 2 heavy, 3 severe (4-level score) | blur, contrast, noise, DPI, skew, JPEG quality |
| `layout` | single_column, multi_column, complex (magazine, slides, posters) | line-start clustering, layout detector |
| `content_flags` | tables, table_dense, math_display, math_inline, code, form_fields, checkboxes, handwriting_major, handwriting_minor, signatures_stamps, charts, photos, barcodes | layout labels, PDF objects, fonts, classifiers |
| `script` | latin, cyrillic, greek, arabic_rtl, hebrew_rtl, cjk, devanagari, other, mixed; plus ISO language | Unicode histogram, lid model, Tesseract OSD |
| `orientation` | 0, 90, 180, 270, plus skew degrees | Tesseract OSD or an orientation classifier |
| `density` | estimated output tokens | text chars or detected text area |
| `continuation` | probability this page continues the previous one's content (table, list, paragraph) | geometry, Jev noul |

### 4.2 Base lanes

A page lands in exactly one base lane.

| Lane | Enters when | Likely processors (decided later) |
|---|---|---|
| **L0 native** | Office, HTML, Markdown, email body, CSV: structure is already in the file | Docling native backends, no rendering |
| **L1 digital-simple** | text_layer = trusted, single column, no heavy content flags | Docling standard without OCR, or Marker `--disable_ocr` |
| **L2 digital-complex** | text_layer = trusted, plus multi-column, dense tables, math or code | Marker balanced, or Docling with TableFormer accurate and enrichments; MinerU or PaddleOCR-VL for math and tables |
| **L3 scan-clean** | no trusted text, degradation 0-1, printed text | PaddleOCR-VL, MinerU2.5, Docling VLM or Marker balanced with `--force_ocr` |
| **L4 scan-degraded** | degradation 2-3, camera capture, fax, or an untrusted old OCR layer on a poor image | Preprocessing (deskew, dewarp, binarise), then Chandra 2 or a large general VLM |
| **L5 handwriting** | handwriting_major, or handwriting_minor inside fields that matter | Chandra 2 or a frontier VLM, with mandatory human review |
| **LQ quarantine** | encrypted, corrupt, too complex, zero content, unsupported, over size limits | none; flagged for a person |
| **LH human** | arbiters not confident enough, or policy says so | review UI |

Forms, math, tables, code, charts and RTL are deliberately not base lanes.
They are **modifiers**, because they cut across base lanes: a table can sit on a clean born-digital page or on a faxed scan, and it needs different treatment in each.
Making them lanes would multiply the lane count and fragment the training data.

### 4.3 Modifiers

The policy turns each modifier into processor options within the base lane.

| Modifier | Effect inside the lane (examples) |
|---|---|
| `tables` / `table_dense` | Table-structure model on; for dense tables, prefer an engine without the #4255 row cap; keep continuation pages in one segment |
| `math_display` / `math_inline` | Formula enrichment or a math-strong engine (PaddleOCR-VL, MinerU, Marker math processors) |
| `code` | Code enrichment; preserve whitespace |
| `form_fields` / `checkboxes` | Form-aware extraction; read AcroForm values directly when they are present |
| `handwriting_minor` | Crop the handwritten regions and send them to a handwriting-capable model; the printed remainder stays in its lane |
| `charts` / `photos` | Picture classification and description; chart-to-data only if requested |
| `signatures_stamps` | Detect and record their presence (legal relevance); no transcription |
| `rtl` / `cjk` | Avoid engines with known RTL reversal (Docling #253); pick engines by script support |
| `multi_column` | Avoid Docling's standard reading order; prefer Marker or a VLM that reads the page whole |

### 4.4 Tiers

Each tenant or job carries a tier: `economy`, `standard` or `exact`.
The tier changes the cost matrix, which in turn moves the lane thresholds and decides whether verification runs.
`exact` is the default for anything that feeds legal work.

---

## 5. Router architecture

```
             files
               │
   ┌───────────▼────────────┐
   │ S0 Intake              │  sniff type, hash, unpack archives/emails,
   │                        │  decrypt check, safety gates, dedup
   └───────────┬────────────┘
               │ one record per page
   ┌───────────▼────────────┐   ┌──────────────────────────┐
   │ S1 Structural probe    │   │ S2 Visual probe          │
   │ PDF objects, fonts,    │   │ render ~120 dpi, IQA,    │
   │ text layer, AcroForm   │   │ layout detector, OSD,    │
   │ (pure CPU, ms)         │   │ figure classifier        │
   └───────────┬────────────┘   └────────────┬─────────────┘
               │ S3 Text probe (text-layer forensics, lid, glyph stats)
               └──────────────┬──────────────┘
                   ┌──────────▼──────────┐
                   │ S4 Feature vector   │  versioned, stored
                   └──────────┬──────────┘
                   ┌──────────▼──────────┐
                   │ S5 Rules + learned  │  hard constraints, then calibrated
                   │ router              │  per-axis models; expected-cost lane
                   └──────────┬──────────┘
            confident │                 │ ambiguous (per-axis thresholds)
                      │      ┌──────────▼──────────┐
                      │      │ S6 Arbiters         │  Jev (text evidence)
                      │      │                     │  small VLM (visual q's)
                      │      └──────────┬──────────┘
                      │     confident │ │ still unsure
                      │               │ └──────► LH human queue
                   ┌──▼───────────────▼──┐
                   │ S7 Segmentation     │  smooth per-page lanes into runs,
                   │                     │  keep continuations together
                   └──────────┬──────────┘
                   ┌──────────▼──────────┐
                   │ S8 Route manifest   │  → processing lanes (later)
                   └──────────┬──────────┘
                              ▲
                   S9 Feedback: post-parse quality signals, escalations,
                   human labels → re-route now, retrain later
```

### 5.1 S0 Intake

- Detect the real type from magic bytes (`python-magic` or `puremagic`), not the extension.
- Hash each file (sha256) and each rendered page (perceptual hash) so repeated cover sheets and duplicates reuse cached routes.
- Unpack containers recursively: zip, email (EML and MSG attachments become child documents that keep their parent link), multi-page TIFF, and PDF portfolios and embedded files.
- Safety gates, each ending in LQ with a reason code:
  - encrypted or password-protected;
  - malformed (it fails to open in two independent parsers, say pypdfium2 and pikepdf);
  - too complex (Unstructured's rule: more than 10,000 graphics operations and a graphics-to-text ratio above 20);
  - page count or pixel dimensions over limits;
  - zero content.
- Native office formats go straight to L0, but only after checking for embedded images that are really scans (a DOCX made of page photos is common).
  Those embedded images go back through S2 as image pages.

### 5.2 S1 Structural probe (PDF)

Pure object inspection with no rendering, a few milliseconds per page.

| Signal | How | Tells us |
|---|---|---|
| Characters per page and text area coverage | pypdfium2 text page; char boxes vs page area | Is there a text layer at all |
| Image coverage | image XObjects' placed bboxes / page area | Page is an image with or without text on top |
| Image filters | `DCTDecode` (JPEG), `CCITTFaxDecode`, `JBIG2Decode`, bit depth | Fax or bilevel scan (CCITT, 1-bit), scanner output (JBIG2), photo (JPEG) |
| Effective DPI | image pixel size / placed size in inches | Scan resolution; under ~200 dpi hurts OCR |
| Text render mode 3 (invisible) share | content-stream text state | An earlier OCR layer sitting under a scan |
| Producer and Creator metadata | document info and XMP | Scanner software, ABBYY, Adobe Paper Capture and others mean an OCR'd scan; Word or LaTeX mean born-digital |
| Fonts | names, embedded or not, Type3, ToUnicode present | Missing ToUnicode means garbled text; CMMI/CMSY/STIX/Cambria Math mean math; Courier/Consolas/Menlo/"Mono" mean code |
| AcroForm and widget annotations | pikepdf | Real form fields; values can be read exactly without OCR |
| Vector ruling lines | path operators, horizontal/vertical line counts | Tables and form boxes |
| Line-start x clustering | char/line boxes | Column count |
| Tagged PDF and structure tree | `/MarkInfo`, `/StructTreeRoot` | Reading order may be available for free |
| Rotation and crop boxes | `/Rotate`, box mismatch | Orientation hints |

### 5.3 S2 Visual probe

Render each page once at about 120 dpi, grayscale.
That is enough for layout and quality; OCR lanes re-render at their own resolution.

- **Image quality.** Laplacian variance (blur), RMS contrast, a noise estimate, a JPEG quality estimate, background uniformity and skew angle (projection profile or Hough).
  Thresholds are fitted on our corpus, not copied from blogs.
  Later, a document-specific quality model trained against OCR accuracy (the CG-DIQA line of work) can replace the generic metrics.
- **Capture type.** Camera photos show non-page background at the edges, perspective, uneven lighting and EXIF camera tags.
  Fax pages are bilevel with a characteristic resolution.
  Screenshots have exact pixel grids and UI chrome.
- **Layout detector** over the whole page, giving a region histogram (area share and count per label).
  Candidates, all to be benchmarked on our pages:

  | Detector | Speed | Notes |
  |---|---|---|
  | PP-DocLayout-S | ~14.5 ms/page on CPU | |
  | Docling Heron | 28 ms/image on GPU | Its labels include Form, Key-Value Region and Checkbox |
  | Surya layout | | Has a `Handwriting` label |
  | DocLayout-YOLO | fastest | AGPL through ultralytics; check the licence before use |
- **Orientation and script.** Tesseract `--psm 0` (orientation and script detection) is cheap and gives rotation plus a script guess on image pages.
- **Figure classifier.** DocumentFigureClassifier-v2.5 on Picture regions tells a chart from a photo, a signature, a stamp or a barcode.
- **Handwriting detector.** Start with the layout model's handwriting class.
  If that is not precise enough on our data, train a small classifier on region crops (an EfficientNet or DiT-small fine-tune) using golden-set labels.

### 5.4 S3 Text probe (pages with a text layer)

This is where most wrong "born-digital" calls are caught.

- **Marker's four-part trust check** (section 2.3): lines present, `OCRErrorPredictor` verdict, at least 25% layout-to-text coverage, and fewer than 50% of lines with multiple overlaps.
- **Garble detectors:**
  - share of `(cid:NNN)` sequences, private-use and U+FFFD characters;
  - mojibake patterns;
  - dictionary hit rate per detected language;
  - share of tokens shorter than two characters, and characters per word (from arXiv 2608.06607).
- **Language ID** with GlotLID or fastText `lid.176`, per page and per block, keeping the confidence.
  Low confidence on long text is itself a garble signal.
- **Unicode script histogram**, giving the script axis for born-digital pages directly.
- **Text-to-layout agreement.** Layout regions labelled Text that have no embedded text under them mean part of the page is image-only (a scanned signature page, a pasted image of a table).
  That sets `text_layer = partial`, which becomes a region-level OCR instruction rather than full-page OCR.
- **Math and code glyph statistics.** Density of math operators and Greek, and indentation and symbol patterns typical of code.
- **Density estimate** from characters, or from text-region area on image pages, as a stand-in for output tokens.

### 5.5 S4 Feature vector

One flat, versioned record per page (`features.v1`), stored in Parquet and queryable with DuckDB.
Every downstream decision reads only from it, so routes are reproducible and models can be retrained offline.
Section 6 lists the initial set.

### 5.6 S5 Rules and learned router

**Hard rules first.**
They are short, auditable, and cover cases where a model has nothing to add:

- container = native_office and no image-only pages → L0.
- Safety gate failure → LQ.
- No text layer and image coverage above 0.9 → not L1 or L2, whatever else is true.
- AcroForm fields present → `form_fields` on.
- Every rule firing is recorded in the manifest.

**Then one calibrated model per axis.**
Following arXiv 2608.06607: gradient-boosted trees (LightGBM) or a random forest, with isotonic calibration on a held-out fold.
There are separate models for `text_layer`, `degradation` (ordinal), `capture`, `layout`, each content flag, and `handwriting`.
Per-axis models are easier to label, debug and calibrate than one model over the full lane set, and they survive changes to the lane set.

**Then the lane, by expected cost.**
The policy table defines a cost matrix `C[true_lane][assigned_lane]` for each tier.
The combined per-axis probabilities give a distribution over true lanes `p`, and the router picks `argmin_j Σ_i p_i · C[i][j]`.
This single rule handles the asymmetry.
A page with a 15% chance of being degraded still goes to L4 under the `exact` tier when the cost of a silent failure in L3 is high enough, and goes to L3 under `economy`.

**Ambiguity test.**
A page goes to arbitration when any of these hold:

- the expected-cost gap between the best and second-best lane is below a threshold;
- any single axis probability falls in its review band;
- rules and models disagree.

Bands are fitted per axis so that arbitration volume stays within budget (proposed start: at most 15% of pages).

### 5.7 S6 Arbiters

Arbiters answer only the axes that were ambiguous, and their answers feed back into the same expected-cost step.
They do not pick the lane directly.

Question routing:

| Ambiguous axis | Arbiter |
|---|---|
| text_layer (is this text real and readable?), continuation, document type, "is this a cover sheet or separator page?" | Jev |
| handwriting, capture, degradation, charts vs photos, form appearance on scans, script on image pages | Small vision model |
| both uncertain after one arbiter, or arbiters disagree | Other arbiter, then LH |

Section 7 covers Jev and section 8 the vision model.

### 5.8 S7 Segmentation

Most processors accept page ranges (Marker `--page_range`, Docling page ranges), so segments are contiguous runs of pages with the same lane and compatible modifiers.

- **Smoothing.** A one-page lane change inside a long run is suspicious.
  Apply a small penalty for switching lanes (a Viterbi pass over per-page lane costs) and switch only when a page's cost clearly favours it.
- **Never merge downwards.** Smoothing may raise a page to a more capable lane, never lower it.
- **Continuation.** Pages whose continuation probability is high stay in the same segment as the page before, so cross-page tables and lists reach the same processor together.
- **Handwriting and partial regions.** Region-level instructions ride along inside the segment (crop boxes plus a target processor); they do not split the page.

### 5.9 S8 Route manifest and S9 feedback

The manifest (section 11) is the only interface to the processing layer.

Feedback signals the processing layer must send back, even in its first crude form:

- Docling `ConfidenceReport` grades per page.
- Marker `OCRErrorPredictor` run on the output text.
- Output-to-expected length ratio: output tokens vs the S3 density estimate, which catches truncation and repetition loops.
- Repetition-loop detection and `finish_reason` from VLM lanes.
- Cross-engine disagreement where verification ran.
- Human corrections.

A page that fails in its lane is automatically re-routed one step up the escalation ladder the policy defines (for example L1 → L2 → L3 with force OCR → L4 → LH).
Every such event also becomes a labelled training example: this page, with these features, needed a lane above the one we chose.

---

## 6. Feature catalogue v1

About 60 features to start.
All are cheap, none needs ground truth, and each lists what it mainly informs.

| Group | Features | Informs |
|---|---|---|
| Container | mime, page_count, file_size, is_encrypted, has_embedded_files, parse_errors | intake, LQ |
| PDF text | chars, text_area_ratio, render_mode3_ratio, fonts_count, type3_ratio, no_tounicode_ratio, cid_ratio, pua_ratio, fffd_ratio | text_layer |
| PDF images | image_area_ratio, max_image_dpi, filter_ccitt, filter_jbig2, filter_dct, bits_per_component | capture, text_layer |
| PDF structure | producer_class, is_tagged, acroform_fields, widget_count, vector_hline_count, vector_vline_count, rotate | form, tables, orientation |
| Fonts | math_font_ratio, mono_font_ratio | math, code |
| Image quality | laplacian_var, rms_contrast, noise_sigma, jpeg_q_est, skew_deg, bg_uniformity, border_nonpage_ratio, exif_camera | degradation, capture |
| Layout histogram | area and count per label (text, title, table, formula, code, picture, form, kv, checkbox, handwriting, caption, list, header/footer) | content flags, layout |
| Geometry | column_count_est, line_density, word_height_cv, crowded_line_frame, text_region_ratio | layout, degradation |
| Text forensics | marker_ocr_error_bad, layout_text_coverage, line_overlap_ratio, dict_hit_rate, short_token_ratio, inv_chars_per_word, lid_lang, lid_conf, script_hist | text_layer, script |
| Figures | per-class counts from the figure classifier (chart, photo, signature, stamp, barcode) | charts, signatures |
| OSD | osd_rotation, osd_rotation_conf, osd_script, osd_script_conf | orientation, script |
| Density | est_output_tokens | cost, tier |
| Context | prev_page_lane, prev_page_table_at_bottom, same_size_as_prev | continuation, smoothing |

---

## 7. Using Jev

**Role:** the text-evidence arbiter for the ambiguous remainder, plus two jobs it is suited to that no probe does well: continuation and document-type decisions across page boundaries.

**Not its role:** anything that needs pixels, and any decision rules can make.

Request pattern, one page per request with the previous page as context:

```json
{
  "model": "jev-1.13.0",
  "state": {
    "page_evidence": "Text layer: present on most of the page. Earlier OCR layer: yes, invisible text over a full-page image. Scan quality: mild blur, high contrast. Columns: two. Layout detector found: one large table in the lower half, no formulas. Language guess: Finnish, low confidence.",
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
      "instructions": "This page is a fax cover sheet, blank separator, or scanning slip with no document content."}
  }
}
```

Rules that follow from the research:

1. **Verbalise numbers.** Jev is weak with numbers, so the state says "mild blur, high contrast", not `laplacian_var: 212.4`.
   A fixed mapping from each feature to words is part of `features.v1`, so the wording is stable and versioned.
2. **One page per state**, previous page as context.
   Many items in one state degraded accuracy in two independent tests.
3. **Always include an abstain option** (`insufficient`, `uncertain`).
   Without one, Jev is confidently wrong on items it cannot answer.
4. **Write criteria as observable evidence**, and freeze the wording once it is tested.
   A 15-30 point swing from rewording means criteria text is code: it lives in version control and changes only after a golden-set run.
5. **Keep filenames and user-controlled text out of the instructions.** Page text goes only in a state field, so injected text is treated as evidence rather than instructions.
   Injection can still move a verdict, so Jev must never decide anything security-relevant.
6. **Threshold on `probabilities`, never on `confidence`.** Fit isotonic calibration per question on golden-set pages and refit when the model version changes.
7. **Drift probe.** A fixed set of about 200 pages runs daily.
   If agreement or calibration moves past a bound, arbitration falls back to the local model and we are alerted.
8. **Batch across pages, not within a state.** Parallelise requests up to the rate limit (1,200/min) with a client-side token bucket and backoff.
9. **Do not train on Jev outputs.** The terms likely forbid it.
   Training labels come from people and from downstream outcomes (section 10), which is better data anyway.
10. **Keep a local substitute.** The client talks to an interface that Kev (local) also implements.
    Tenants whose data cannot leave our infrastructure use Kev, or skip text arbitration and go straight to the vision model or a human.

---

## 8. Using a small vision LLM

**Role:** the visual arbiter for ambiguous pages, and later a visual checker in verification.
It answers narrow questions about a downscaled page image and returns strict JSON.

**Where it fits:**

1. **S6 arbitration** on the visual axes: handwriting, capture type, degradation, chart vs photo, form appearance on scans, and script on image pages.
2. **Golden-set pre-labelling** (section 10).
   The model proposes labels and a person confirms or corrects them, which cuts labelling time.
   Labels are only final after human review.
3. **Region checks** in S7, for example "does this cropped region contain handwriting in a filled field?" This decides whether `handwriting_minor` needs a dedicated handwriting pass.
4. **Processing-time verification** (later): comparing the rendered page with extracted output on selected regions.
   It always uses a different model family from the extractor.

**Model choice:**

- **Default for confidential data:** Qwen3-VL-4B, local (vLLM on GPU or MLX on Apple Silicon).
  InternVL3.5-4B is the second candidate.
  MiniCPM-V-4.6 is the ultra-cheap fallback if throughput matters more than accuracy.
- **Hosted, where policy allows:** Gemini Flash-Lite, for strict `responseSchema` JSON on image input and the lowest cost per page among the Western providers.
  Vertex AI with an EU region should be checked for residency.
- **Avoid:** DeepSeek's hosted API for client data (jurisdiction), and frontier models for triage.
  The research found the ceiling here is set by question design, not model size.
- **Choose by bake-off.** Pick the final model by running it on the golden set's ambiguous slice, not from benchmark tables.

**Request pattern:**

- **Image size.** Send a thumbnail at 768-1024 px on the long side for page-level questions.
  Send a full-resolution crop only for region questions.
- **Contact sheets.** For document-level questions (does this bundle mix sources?), send a grid of page thumbnails in one image, so one call covers many pages.
- **Answer format.** Ask observable, closed questions, one field each, with an explicit `unsure` value:

```json
{
  "handwriting": "none | annotations_only | fields_filled_by_hand | mostly_handwritten | unsure",
  "capture": "digital_render | flatbed_scan | fax | camera_photo | screenshot | unsure",
  "legibility": "clean | mild_issues | hard_to_read | illegible | unsure",
  "main_content": ["prose", "table", "form", "chart", "photo", "math", "code", "letterhead", "signature_page"],
  "script": "latin | cyrillic | arabic | hebrew | cjk | other | mixed | unsure"
}
```

- **Consistency as confidence.** Hosted VLMs rarely give usable log-probabilities, so ambiguous pages get two samples, one at a different crop or scale.
  We accept only answers that agree, and record the agreement rate as that axis's arbitration confidence.
  The calibration step then maps agreement to a probability, the same way it does for Jev.
- **Cross-check against probes.** If the VLM says `camera_photo` but EXIF, borders and perspective all say flatbed, the conflict goes to LH. The VLM does not win by default.

**Cost, rough.**
A 1,000-pixel thumbnail is on the order of 1,000 input tokens.
With a short JSON reply, that is well under a tenth of a cent per call on Flash-Lite pricing, and only for the ambiguous slice.
Local Qwen3-VL-4B costs only GPU time.
Real numbers come from the Phase 4 bake-off.

---

## 9. Decision policy

- **The policy file.** `policies/lanes.yaml` holds, per tier:
  - the lane list, with each lane's capability requirements (which route-vector values it can handle);
  - the cost matrix;
  - review bands per axis;
  - the escalation ladder;
  - the modifier-to-processor option mapping.
- **Versioning.** The policy has a version, and the manifest records it.
- **Cost matrix defaults**, to be tuned with you:
  - Under-routing into a lane that cannot handle the page (degraded scan into L1, handwriting into L3) costs 20 to 50 times an over-route.
    Under `exact` it also forces review.
  - Over-routing costs the compute difference between lanes, measured in Phase 3.
  - Sending a page to LH costs a fixed reviewer-minute cost.
- **Worked example.** Take a page with p(degraded) = 0.15 and a cost ratio of 30:1.
  The expected cost of L3 is 0.15 × 30 = 4.5 units, against about 1 unit for over-routing to L4.
  So under `exact` the page goes to L4, which is intended.
  Under `economy`, with a ratio of 5:1, it goes to L3.
- **Calibration.** Isotonic, per axis and per arbiter, fitted on a held-out split of the golden set.
  We track reliability diagrams and ECE in every eval run.

---

## 10. Ground truth and evaluation

This is the part most likely to decide whether the router is good, so it starts in week one.

### 10.1 Golden set

- **Size and spread.** 2,000-3,000 pages at first, stratified by container × capture × degradation × content flags × script.
  The corpus must include the awkward cases:
  - OCR'd scans with invisible text layers;
  - PDFs with missing ToUnicode;
  - faxes and phone photos;
  - mixed bundles;
  - handwriting in form fields;
  - multi-column and RTL pages.
- **Source.** Our real documents come first.
  Public sets such as OmniDocBench pages, RVL-CDIP and DocLayNet only fill gaps.
- **Labels.** Each route-vector axis per page, plus segment boundaries per document.
- **Tooling.** Label Studio, with VLM pre-labels.
  Two labellers per page on a 10% overlap sample, reporting agreement per axis.
  An axis people cannot agree on cannot be learned either, so its definition gets fixed.

### 10.2 Oracle-lane labels

Human axis labels say what a page is.
Oracle labels say what it needs, which is what routing is actually for.

- **Stub lanes.** In Phase 3 we stand up minimal versions of each lane with default settings.
  This is not the real processing layer, just enough to run.
- **Runs.** A subset of about 500 pages goes through every lane.
- **Scoring.** Each output is scored against reference transcriptions with text edit distance, table TEDS, formula CDM and field exactness.
- **The label.** A page's oracle lane is the cheapest lane whose output clears the tier's quality bar.
- **Use.** Oracle labels train the lane-level check, and are the main test of whether the cost matrix is set right.

This follows arXiv 2608.06607 and produces labels without Jev outputs, avoiding the terms problem.

### 10.3 Metrics

Every eval run reports these, per slice (capture, degradation, script, container):

- Per-axis macro-F1 and confusion matrices.
- **Under-route rate**: pages assigned below their oracle lane.
  This is the headline number.
- Over-route rate and its compute cost.
- Arbitration rate and human-review rate.
- ECE and reliability curves per axis and arbiter.
- Segment-boundary F1.
- p50/p95 latency and cost per 1,000 pages for each stage.

### 10.4 Proposed acceptance targets

These are set before we have data and will be revised after Phase 3.

- Under-route rate under 1% on the `exact` tier.
- Arbitration on at most 15% of pages.
- Human review on at most 2% of pages outside handwriting.
- S0-S5 at 10 pages/s or more per CPU worker, excluding the layout model.
- Router ECE under 0.05 per axis after calibration.

---

## 11. Route manifest contract

Pydantic models, exported as JSON Schema and versioned (`manifest.v1`).
This is a sketch; the field list will settle in Phase 1.

```json
{
  "manifest_version": "1.0",
  "doc_id": "sha256:…",
  "source": {"path": "…", "mime": "application/pdf", "parent_doc_id": null},
  "versions": {"features": "1.0", "router": "0.3.1", "policy": "2026-10-01", "arbiters": {"jev": "jev-1.13.0", "vlm": "qwen3-vl-4b@…"}},
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
    "regions": [{"bbox": [0.62, 0.81, 0.95, 0.9], "kind": "handwriting", "target": "handwriting"}],
    "decided_by": "model+vlm",
    "expected_cost": {"L3": 1.8, "L4": 2.4, "L5": 6.0},
    "reasons": ["rule:image_coverage>0.9", "axis:degradation p(>=2)=0.21", "vlm:handwriting=fields_filled_by_hand (2/2 agree)"]
  }],
  "segments": [{"pages": [0, 5], "lane": "L3", "modifiers": ["tables"]}],
  "quarantine": null
}
```

---

## 12. Implementation plan

### 12.1 Stack

- Python 3.12, managed with `uv`.
- **PDF.**
  - `pypdfium2` (Apache/BSD) for text and rendering.
  - `pikepdf` (MPL-2.0) for objects, filters, AcroForm and metadata.
  - `pdfminer.six` for char-level font detail where pdfium is not enough.
  - PyMuPDF is AGPL; use it only if we accept that or buy a licence.
- **Images.** `opencv-python-headless`, `numpy`, `Pillow`; `pytesseract` for OSD only.
- **Models.** ONNX Runtime for the layout detector and figure classifier where exports exist; otherwise `docling-ibm-models` and `surya` directly, behind one `LayoutDetector` interface so we can switch.
- **Text.** GlotLID or fastText lid; the Marker `OCRErrorPredictor` from surya (check the weight licence, section 15).
- **Learning.** LightGBM plus scikit-learn isotonic calibration.
- **Storage.** Parquet feature store with DuckDB queries.
- **Contracts.** Pydantic v2 schemas.
- **Arbiters.** `typesafe-sdk` for Jev behind an interface Kev also implements.
  Vision models through one client with vLLM, MLX and Gemini backends.
- **Labelling.** Label Studio.
- **Execution.** A process pool per stage to begin with.
  S0-S5 are embarrassingly parallel per page, so moving to Ray or a queue later changes little.

### 12.2 Repository layout

```
jesteruct/
  pyproject.toml
  policies/lanes.yaml
  src/jesteruct/
    intake/        sniff.py unpack.py safety.py dedup.py
    probes/        structural.py visual.py layout.py text.py osd.py
    features/      schema.py verbalise.py store.py
    router/        rules.py axes.py calibrate.py policy.py cost.py
    arbiters/      base.py jev.py kev.py vlm.py
    segment/       smooth.py
    manifest/      schema.py
    feedback/      signals.py escalate.py
    eval/          golden.py oracle.py metrics.py report.py
    cli.py         jst route <path> ; jst eval ; jst explain <doc> <page>
  tests/
  data/            (gitignored: golden set, features, oracle runs)
  research/
```

### 12.3 Phases

Each phase ends with something that runs end to end and a measurable exit criterion.

| Phase | Build | Exit criterion |
|---|---|---|
| **0. Decisions and corpus** (week 1) | Answers to section 15; collect a raw sample of 5-10k real pages; set up Label Studio; freeze the axis definitions | Labelling guide agreed; first 300 pages double-labelled with per-axis agreement reported |
| **1. Skeleton and structural router** (weeks 1-3) | S0 intake with safety gates, S1 structural probe, S3 text forensics, S4 store, rules only, manifest v1, CLI | `jst route` works on any file in the sample; rules-only baseline measured on the golden set |
| **2. Visual probe** (weeks 3-5) | Rendering, image quality, capture, OSD, layout detector bake-off (PP-DocLayout-S vs Heron vs Surya), figure classifier, handwriting via the layout label | Per-axis F1 for degradation, capture and content flags; S2 throughput measured per page on CPU and GPU |
| **3. Oracle harness** (weeks 4-7) | Stub lanes L1-L5 with default configs; the reference-scoring pipeline; oracle labels for about 500 pages | Oracle labels exist; the first cost matrix is filled from measured compute and failure costs |
| **4. Learned router and arbiters** (weeks 6-9) | Per-axis LightGBM plus calibration; expected-cost lane choice; Jev and Kev arbiter; VLM arbiter bake-off (Qwen3-VL-4B, InternVL3.5-4B, Gemini Flash-Lite); review bands | Under-route under 1% and arbitration at most 15% on the golden set, or a written account of the gap |
| **5. Segmentation and feedback** (weeks 8-10) | Viterbi smoothing, continuation, region instructions, the feedback contract, the escalation ladder, human-review queue | Segment F1 reported; one full loop shown in which an injected failure escalates and becomes a labelled example |
| **6. Hardening** (weeks 10-12) | Drift probes, monitoring dashboards, load test at target volume, a pinned-versions release | p95 latency and cost per 1,000 pages at target volume; runbook written |

The weeks assume one engineer full time and are rough.
Phase 3 carries the most schedule risk, because reference transcriptions take time to make.

---

## 13. Throughput and cost budget (estimates to be replaced by Phase 2 measurements)

| Stage | Where it runs | Expected per-page cost |
|---|---|---|
| S0-S1 structural | CPU | milliseconds |
| S2 render at 120 dpi + quality metrics | CPU | tens of milliseconds |
| S2 layout detector | CPU (PP-DocLayout-S ~15 ms) or GPU | 15-50 ms |
| S3 text forensics incl. `OCRErrorPredictor` | CPU or GPU | tens of milliseconds, to be measured |
| S5 rules + trees | CPU | under 1 ms |
| S6 Jev (ambiguous slice) | API | ~0.1-0.7 s latency; ~$0.00004 |
| S6 VLM (ambiguous slice) | local GPU or API | ~0.3-2 s; hosted well under $0.001 |

If about 15% of pages reach arbitration, the router's cost is dominated by the layout detector and a few API calls per hundred pages.
That is small next to the processing lanes, where a VLM page costs 0.5-2 s of GPU time.
It also means a 1% cut in over-routing pays for the router several times over.

---

## 14. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Jev is weeks old; audits are small and some contradict each other | Treat it as an optional arbiter behind an interface; run our own calibration; daily drift probe; Kev as local fallback |
| Jev and hosted-VLM data terms clash with confidentiality duties | Per-tenant arbiter policy; local-only mode (Kev plus Qwen3-VL) available from Phase 4 |
| Parsers misreport text layers (Docling #4357) | The router does its own forensics and never trusts a parser's claim |
| Golden-set labelling is slow | VLM pre-labels, active learning (label the pages the router is least sure about), start in week 1 |
| Lane set changes when processing is built | Route vector plus policy table; per-axis models do not depend on lane names |
| Model weight licences (Datalab thresholds, AGPL detectors) | Licence check per component in Phase 0; interfaces allow swapping |
| Router overfits to our current mix of documents | Stratified golden set; per-slice metrics; drift monitoring on the feature distribution |
| Silent VLM errors downstream (entity substitution, loops) | Feedback signals, and verification using a different model family under the `exact` tier |

---

## 15. Decisions needed from you

1. **Data residency.** Can page text go to Jev (US-hosted, zero retention only on enterprise terms)?
   Can page images go to Google (Gemini on Vertex, EU region) or any other hosted provider?
   Or must everything stay on our infrastructure?
   This decides whether the arbiters are Jev plus Gemini or Kev plus Qwen3-VL.
2. **Hardware.** Apple Silicon machines only, or a GPU server?
   This changes the layout detector and VLM choices and all the throughput numbers.
3. **Volume and latency.** Roughly how many pages per day, and is routing batch or interactive?
4. **Languages.** Which languages and scripts appear in practice (Finnish, Swedish, English, Russian, others)?
   This sets golden-set strata and the OCR engine short list.
5. **Commercial licences.** Does the organisation exceed Datalab's $2M and $5M thresholds?
   If so, Chandra, Marker and Surya weights (including the `OCRErrorPredictor` we want to reuse) need a commercial licence or replacements.
6. **Lane set.** Sign-off on L0-L5, LQ and LH, with modifiers rather than extra lanes (section 4).
7. **Default tier and cost ratios.** Is `exact` the default, and roughly how bad is a silent extraction error compared with a reviewer-minute?

---

## 16. Sources

Full URL lists are in `research/`.
The main ones:

- **Jev.**
  - [TypeSafe API docs](https://docs.typesafe.ai/api), [models](https://docs.typesafe.ai/models), [confidence](https://docs.typesafe.ai/confidence), [jaggedness](https://docs.typesafe.ai/model-jaggedness/jev-1.13), [MCA](https://typesafe.ai/legal/mca), [launch blog](https://typesafe.ai/blog/introducing-system-one-models-and-jev)
  - [Simon Willison](https://simonwillison.net/2026/Sep/21/jev/), [Wikipedia](https://en.wikipedia.org/wiki/Jev_(AI_model))
  - [Classmethod page classification](https://dev.classmethod.jp/en/articles/typesafe-jev-doc-type-classification/), [DocJev](https://github.com/jerryjliu/docjev), [doc-router](https://github.com/misbahsy/doc-router), [jev-doc-classification](https://github.com/lucassarcanjo/jev-doc-classification)
  - [calibration audit](https://github.com/jujumilk3/jev-calibration-audit), [OOD calibration](https://github.com/scienthoon/jev-ood-calibration), [awesome-jev-robustness](https://github.com/Yifan-Lan/awesome-jev-robustness)
  - [Kev](https://github.com/jaredpalmer/kev), [OpenRouter](https://openrouter.ai/typesafe), [Cloudflare](https://developers.cloudflare.com/ai/models/typesafe/jev/)
- **Docling.**
  - [Docs: model catalog](https://docling-project.github.io/docling/usage/model_catalog/), [advanced options](https://docling-project.github.io/docling/usage/advanced_options/), [enrichments](https://docling-project.github.io/docling/usage/enrichments/), [confidence scores](https://docling-project.github.io/docling/concepts/confidence_scores/)
  - [DocumentFigureClassifier-v2.5](https://huggingface.co/docling-project/DocumentFigureClassifier-v2.5), [Granite-Docling](https://huggingface.co/ibm-granite/granite-docling-258M)
  - [issue #4357](https://github.com/docling-project/docling/issues/4357), [issue #4255](https://github.com/docling-project/docling/issues/4255)
- **Datalab.** [Marker](https://github.com/datalab-to/marker), [Surya](https://github.com/datalab-to/surya), [Chandra](https://github.com/datalab-to/chandra), [Marker 2 benchmarks](https://www.datalab.to/blog/marker-2).
- **Papers.**
  - [Pre-Inference Routing, arXiv 2608.06607](https://arxiv.org/pdf/2608.06607)
  - [FinixDoc, arXiv 2608.22842](https://arxiv.org/pdf/2608.22842)
  - [HPD-Parsing, arXiv 2607.18839](https://arxiv.org/pdf/2607.18839)
  - [WeVisDoc, arXiv 2609.20423](https://arxiv.org/pdf/2609.20423)
  - [Real5-OmniDocBench, arXiv 2603.04205](https://arxiv.org/pdf/2603.04205)
  - [olmOCR 2, arXiv 2510.19817](https://arxiv.org/abs/2510.19817)
- **Vision models.** [DeepSeek vision guide](https://api-docs.deepseek.com/guides/vision/), [DeepSeek changelog](https://api-docs.deepseek.com/updates/), [OpenAI pricing](https://developers.openai.com/api/docs/pricing), [RVL-CDIP zero-shot test](https://murraycole.com/posts/ai-document-classification).
