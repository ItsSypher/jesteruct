# Research: Apple Silicon demo and cloud scale-out for the Jesteruct router

Date: 2026-09-24.
Scope: the routing layer only (S0-S6 in PLAN.md sections 5, 6, 8, 12 and 13).
New constraints: confidentiality does not matter for now, hosted APIs are allowed, and the goal is the best performance-to-speed ratio.
Demo hardware: Apple M4 base (4 performance + 6 efficiency cores, 10-core GPU, 24 GB unified memory), macOS 26.3.1.
The same code must later run on CUDA clusters.

Tags used below:

- **[measured]** means I ran it on this M4 during this session; the method is in section 9.
- **[source]** means a cited page states it.
- **[unverified]** means I could not confirm it against a primary source.
- **[estimate]** means my own arithmetic, not a measurement.

---

## 0. Headline findings

1. The cheapest good layout signal on the M4 is **PP-DocLayout-S on ONNX Runtime CPU: 14.9 ms/page** with all threads, 32 ms on one thread **[measured]**.
   The CoreML execution provider makes it slower (62-65 ms) because the graph is split into CPU and ANE/GPU partitions **[measured]**.
2. Docling's **Egret-m exported to ONNX runs at 40-42 ms/page on ONNX Runtime's CoreML EP** (MLProgram, GPU or ALL compute units), against 52 ms on PyTorch MPS fp16 and 103 ms on ORT CPU **[measured]**.
   Heron is 112 ms on the CoreML EP (official ONNX) and 105 ms on MPS fp16 **[measured]**.
   The MPS figures are 1.5-2.5x slower than the published M3 Max numbers (33 and 44 ms), which fits the M3 Max's larger GPU **[source + measured]**.
   The same `egret_m.onnx` file runs on the CUDA and TensorRT EPs in the cloud, so one artefact covers both environments.
3. **PP-DocLayoutV3 exists** (Apache-2.0, RT-DETR based, polygon boxes plus reading order, ECCV 2026) but costs 196 ms/page on MPS fp16 on the M4 **[measured]**, so it is a processing-lane model, not a router probe.
4. Apple's **`RecognizeDocumentsRequest` is macOS 26 only and Swift only** (checked in the SDK's Swift interface).
   It returns paragraphs, tables with cells, lists, barcodes and detected data, at 0.5-0.8 s per page, or 2.5 pages/s with four concurrent requests **[measured]**.
   It is too slow for every page but useful as a second opinion on image pages.
5. `DetectDocumentSegmentationRequest` costs 3-5 ms per page and returned a 0.99-confidence quadrilateral for a synthetic camera photo and nothing for flat renders **[measured]**.
   It is a cheap, direct `capture` feature.
   `CalculateImageAestheticsScoresRequest` returned `overallScore 0.000, isUtility true` for every document image **[measured]**, so it carries no quality information for our pages.
6. **Local VLMs on the M4 are prefill-bound.**
   Qwen3-VL-4B-4bit takes 3.7 s per page at 768 px, and batching through the `mlx_vlm.server` continuous-batching backend does not raise throughput (0.30-0.35 pages/s) **[measured]**.
   Hosted small VLMs answer the same JSON question in 0.8-2.5 s from Finland, so on this machine hosted is both faster and cheaper per unit of wall time.
7. **Hosted arbiter pick: Gemini 3.5 Flash-Lite with minimal reasoning** (1.23 s median total, about $0.0006 per call, strict JSON 9/9) or Gemini 2.5 Flash-Lite (1.49 s, $0.00016) **[measured]**.
   The Qwen3-VL family is the fastest hosted option (0.80-0.86 s) but got the capture type wrong on scans and photos in this small test.
8. **Jev from Finland: 0.37 s median** per request through OpenRouter's decisions endpoint (532 input tokens, $0.000022) **[measured]**.
   The direct API sits behind a Cloudflare edge in Stockholm; the network round trip to the US origin is about 0.24-0.30 s **[measured]**.
   The docs state 250,000 tokens per second and 1,200 RPM, with higher limits on custom or enterprise plans through sales **[source]**.
9. **pypdfium2 is as fast as PyMuPDF for 120 dpi renders and 3-10x faster for text extraction** on the M4 **[measured]**, so there is no speed reason to take on PyMuPDF's AGPL licence.

---

## 1. Apple-native signals (Vision framework, macOS 26)

### 1.1 What each API returns

| API | Availability | Returns | Router use |
|---|---|---|---|
| `RecognizeDocumentsRequest` | macOS 26.0 / iOS 26.0, Swift only | `DocumentObservation` with `title`, `text`, `paragraphs`, `tables` (rows and columns of cells, each cell a container with row and column ranges), `lists` (items with marker type and marker string), `barcodes`, and per-text `detectedData` (dates, addresses, phone numbers, amounts and others from the DataDetection framework) | Structure probe on image pages: table and list presence, paragraph count, barcode detection |
| `RecognizeTextRequest` (Swift) / `VNRecognizeTextRequest` (ObjC) | macOS 15+ for the Swift type | Lines with candidates and a `confidence` | Quick OCR sample for S3 on image pages, feeding Jev and garble checks |
| `DetectDocumentSegmentationRequest` / `VNDetectDocumentSegmentationRequest` | Swift type macOS 15+ | Four normalised corners, a bounding box, a confidence and a low-resolution mask | Camera photo vs flat scan |
| `CalculateImageAestheticsScoresRequest` | macOS 15+ | `overallScore` (-1 to 1) and `isUtility` | Not useful for documents (see 1.2) |
| `DetectTextRectanglesRequest` / `VNDetectTextRectanglesRequest` | Swift type exists alongside the ObjC one | Text boxes without recognition | Cheap text-density and text-coverage feature on image pages |
| `DetectLensSmudgeRequest` | macOS 26.0, Swift only (SDK check) | `SmudgeObservation.confidence` | Candidate blur / soft-capture feature (see 1.2); a sibling agent spotted it |

Sources and checks:

- WWDC25 session 272, "Read documents using the Vision framework", introduces `RecognizeDocumentsRequest` with tables, lists, paragraphs, barcodes and data detection ([WWDC25 272](https://developer.apple.com/videos/play/wwdc2025/272/), [API page](https://developer.apple.com/documentation/vision/recognizedocumentsrequest)).
  Apple's documentation page would not render through the fetch tool, so I checked the macOS SDK's `Vision.swiftinterface` on this machine instead: it declares `@available(macOS 26.0, iOS 26.0, tvOS 26.0, visionOS 26.0, *) public struct RecognizeDocumentsRequest`, and `DocumentObservation` exposes the fields listed above **[measured, SDK check]**.
- The request options are `recognitionLanguages`, `automaticallyDetectLanguage`, `useLanguageCorrection`, `customWords`, `minimumTextHeightFraction` and `maximumCandidateCount` (SDK interface) **[measured]**.
  Word-level output is not provided for Chinese, Japanese, Korean or Thai ([WWDC25 272](https://developer.apple.com/videos/play/wwdc2025/272/)).
  A figure of 26 recognised languages comes from a search summary only **[unverified]**.
- The segmentation request's corners, confidence and mask are documented at [VNDetectDocumentSegmentationRequest](https://developer.apple.com/documentation/vision/vndetectdocumentsegmentationrequest) and in a worked example ([createwithswift](https://www.createwithswift.com/detecting-documents-in-an-image-with-the-vision-framework/)).
- The aesthetics request scores blur, exposure, colour balance and composition and flags "utility" images such as screenshots, receipts and documents ([Apple](https://developer.apple.com/documentation/vision/calculateimageaestheticsscoresrequest), [createwithswift](https://www.createwithswift.com/scoring-the-aesthetics-of-an-image-with-the-vision-framework/)).
- `VNDetectTextRectanglesRequest` is marked as superseded by the text-recognition request in Apple's docs ([Apple](https://developer.apple.com/documentation/vision/vndetecttextrectanglesrequest)); the Swift `DetectTextRectanglesRequest` still compiles and runs on macOS 26 **[measured]**.
- Handwriting: Apple does not position either text request as a handwriting recogniser ([danielsaidi.com](https://danielsaidi.com/blog/2026/01/10/detecting-text-in-images-with-the-vision-framework)); no handwriting flag or class exists in the SDK interface (grep for "handwrit" returns nothing) **[measured]**.
  Vision gives the router no handwriting signal.

### 1.2 Measured on the M4 (clean run, no other GPU work)

Images: a 120 dpi render of a two-column paper page (1020x1320), a synthetic camera photo of a tax form (perspective warp, background, lighting gradient, blur; 1400x1600) and two others.
Median of 3-5 warm runs; the first call is 10-400 ms slower (model load).

| Request | Paper page, 120 dpi | Camera photo | Output |
|---|---|---|---|
| `RecognizeTextRequest` accurate | 920 ms | 484 ms | 166 and 92 lines; confidence takes only the values 0.3, 0.5 and 1.0 |
| `RecognizeTextRequest` fast | 60 ms | 15 ms | **0 lines** on every test image (see note) |
| `RecognizeDocumentsRequest` | 768 ms | 526 ms | 91 paragraphs and 1 table on the paper page; 87 paragraphs and 1 list on the form photo |
| `DetectDocumentSegmentationRequest` | 3 ms | 5 ms | None on the flat render; confidence 0.99 with the corners of the warped page on the photo |
| `CalculateImageAestheticsScoresRequest` | 4 ms | 8 ms | `overallScore 0.000, isUtility true` on all four images |
| `DetectTextRectanglesRequest` | 13 ms | 9 ms | 43 and 6 rectangles |
| `DetectLensSmudgeRequest` | 2 ms | 4 ms | 0.000 on both; 0.985 on the synthetic scan (Gaussian blur sigma 1.6, noise, JPEG q60); 0.000 on the clean form render |

Throughput with Swift concurrency on one image:

- accurate OCR: 1.05 pages/s at concurrency 1, 1.44 at 4, 1.42 at 8;
- `RecognizeDocumentsRequest`: 1.29 pages/s at concurrency 1, 2.47 at 4.

Notes:

- An earlier run of the same binary overlapped with another agent's MLX jobs on the GPU and was 2-4x slower (for example 2.5 s for accurate OCR); the table above is the clean rerun.
  Vision work shares the GPU and Neural Engine with the layout model and any local VLM, so production timings on the M4 depend on what else is running.
- `.fast` returning nothing through the new Swift API is odd.
  The old `VNRecognizeTextRequest` at `.fast`, called through `ocrmac`, returned 156 lines for the same page in about 390 ms, and `.accurate` returned 175 lines in about 935 ms **[measured]**.
  Treat the Swift `.fast` behaviour as a possible bug or a `minimumTextHeightFraction` default until checked.
- The bimodal confidence matches developer reports that `VNRecognizedText.confidence` is effectively 0.5 or 1.0 ([Apple forums 695693](https://developer.apple.com/forums/thread/695693)).
  It is too coarse for a threshold; use line counts, the S3 garble detectors and Jev instead.
- Published M-series numbers: the ocrmac README gives 207 ms (accurate), 131 ms (fast) and 174 ms (LiveText) per image on an M3 Max, without the image size ([ocrmac README](https://github.com/straussmaximilian/ocrmac/blob/main/README.md)) **[source, found by a sibling agent]**.
  Nothing else was found for M-series chips.
- The smudge detector fired only on the one strongly blurred image, so it may work as a cheap blur flag, but one image is an anecdote; test it against Laplacian variance on the golden set.

### 1.3 Python access

- `ocrmac` 1.0.1 wraps `VNRecognizeTextRequest` and a LiveText backend through PyObjC ([ocrmac](https://github.com/straussmaximilian/ocrmac)); it works on macOS 26 with `pyobjc-framework-Vision` 12.2.2 **[measured]**.
  It does not wrap the newer Swift-only requests.
- The Swift-native request types (`RecognizeTextRequest`, `RecognizeDocumentsRequest`) have no Objective-C bridge, so PyObjC cannot reach them ([apple-vision-mcp README](https://github.com/eneko-codes/apple-vision-mcp)).
- The pattern that works is a compiled Swift helper; `mac-ocr` ships one for `RecognizeDocumentsRequest` and gates that command on macOS 26 ([mac-ocr](https://github.com/privatenumber/mac-ocr)).
  I built a 90-line Swift benchmark with `swiftc -O` in seconds on this machine with only the Command Line Tools **[measured]**.
- Recommendation: one long-lived `jst-vision` Swift process per worker that reads JSON lines (image path, requested probes) on stdin and writes JSON results on stdout.
  That avoids process start-up and the 10-400 ms first-call cost on every page.
  It sits behind a `VisionProbe` interface with a no-op implementation on Linux, so the router treats these as optional features (missing values are allowed in `features.v1`).

### 1.4 What to use in S2

- **Use now:** document segmentation (capture axis), text rectangles (text coverage on image pages), lens smudge as an experimental blur feature; together they cost under 20 ms per image page.
- **Use on image pages only, or on the ambiguous slice:** `RecognizeDocumentsRequest` for table, list and barcode presence and a quick OCR sample.
  At 2.5 pages/s it costs more than the whole rest of S2.
- **Do not use:** the aesthetics score (constant on documents), Vision OCR confidence as a threshold.
- **Cloud:** none of this exists on Linux, so every Vision-derived feature needs a portable counterpart (PP-DocLayout for tables, OpenCV for page quadrilaterals, Tesseract or a small OCR for text samples), and the router must be trained with the Vision features dropped or imputed.
  My view: keep Vision features out of the trained model until the cloud path has an equivalent, and use them in the demo only for display and for rules.

---

## 2. Layout detector runtime on Apple Silicon

### 2.1 Published numbers

Docling layout models, from the Heron/Egret technical report ([arXiv 2509.11720](https://arxiv.org/html/2509.11720v1)), seconds per image, all RT-DETRv2 based, 640x640 input:

| Model | A100, batch 200 | EPYC 7763 CPU, 4 threads, batch 32 | M3 Max MPS, batch 50 | DocLayNet mAP (canonical, COCO tools) |
|---|---|---|---|---|
| egret-m | 0.024 | 0.334 | 0.033 | 0.765 |
| egret-l | 0.026 | 0.472 | 0.040 | n/a in my extract |
| egret-x | 0.031 | 0.808 | 0.094 | n/a in my extract |
| heron (Docling default) | 0.031 | 0.643 | 0.044 | 0.776 |
| heron-101 | 0.028 | 0.988 | 0.062 | 0.780 |

The same paper's `docling-eval` numbers with post-processing are much lower (0.59-0.61 on DocLayNet), so compare models only within one evaluation mode.
Docling's model catalog lists Heron as the default, all layout models as Transformers-loadable on CPU, CUDA, MPS and XPU, and ONNX Runtime support for Heron as in progress ([model catalog](https://docling-project.github.io/docling/usage/model_catalog/)).
Licence: Apache-2.0 ([docling-layout-heron](https://huggingface.co/docling-project/docling-layout-heron)).

PaddleX layout table (Tesla T4 GPU, Xeon Gold 6271C CPU with 8 threads, FP32; second number is the high-performance mode) ([PaddleX layout detection](https://paddlepaddle.github.io/PaddleX/latest/en/module_usage/tutorials/ocr_modules/layout_detection.html)):

| Model | mAP(0.5), Paddle's own test set | GPU ms | CPU ms | Size | Classes |
|---|---|---|---|---|---|
| PP-DocLayout-S | 70.9 | 11.5 / 3.9 | 18.5 / 6.3 | 4.8 MB | 23 |
| PP-DocLayout-M | 75.2 | 13.0 / 4.7 | 43.4 / 24.4 | 22.6 MB | 23 |
| PP-DocLayout-L | 90.4 | 33.6 / 33.6 | 503 / 251 | 124 MB | 23 |
| PP-DocLayout_plus-L | 83.2 | 53.0 / 17.2 | 635 / 378 | 126 MB | 20 |

- **PP-DocLayoutV2**: RT-DETR detector from PP-DocLayout_plus-L plus a six-layer pointer network for reading order, 25 classes, 81.4 mAP(0.5) on a 1,000-image in-house set, 204 MB ([PaddleOCR docs](https://www.paddleocr.ai/main/en/version3.x/module_usage/layout_analysis.html), [PaddleOCR-VL paper](https://arxiv.org/pdf/2510.14528)).
  The same docs compare backends for it on Xeon plus A100: ONNX Runtime 25.8 ms, Paddle static 42.9 ms, Transformers 69.3 ms, Paddle dynamic 99.8 ms end to end.
- **PP-DocLayoutV3**: exists and is Apache-2.0; it predicts multi-point (polygon) boxes and reading order in one pass and targets skewed, curved and screen-photographed pages; it is the layout module of PaddleOCR-VL 1.5/1.6 and GLM-OCR; paper "RT-DocLayout", accepted to ECCV 2026 ([model card](https://huggingface.co/PaddlePaddle/PP-DocLayoutV3_safetensors), [arXiv 2606.23344](https://arxiv.org/abs/2606.23344)).
  Community ONNX, OpenVINO, TensorRT, CoreML and MLX conversions exist on Hugging Face (for example [alex-dinh/PP-DocLayoutV3-ONNX](https://huggingface.co/alex-dinh/PP-DocLayoutV3-ONNX), `aoiandroid/PP-DocLayoutV3-safetensors-CoreML`, `agentable/pp-doclayoutv3-mlx`) **[measured: HF API listing; quality of these conversions unverified]**.
  I found no published accuracy table for V3 against V2 or Heron **[unverified]**.
- **Surya**: now a unified 650M-parameter VLM covering OCR, layout and tables, served via vLLM on NVIDIA or llama.cpp on CPU and Apple Silicon ([surya](https://github.com/datalab-to/surya)).
  Weights use a modified OpenRAIL-M licence, free below $5M revenue or funding ([LICENSE](https://github.com/VikParuchuri/surya/blob/master/LICENSE)).
  It is far too heavy for a per-page router probe; its `Handwriting` label is the only reason to keep it in mind.
- **DocLayout-YOLO**: YOLOv10 based; DocLayNet 79.7 mAP with DocSynth300K pre-training ([DocLayout-YOLO](https://github.com/opendatalab/DocLayout-YOLO)).
  It depends on Ultralytics, which is AGPL-3.0 with a paid enterprise licence ([Ultralytics licence](https://www.ultralytics.com/license), [HN discussion](https://news.ycombinator.com/item?id=43595236)).
  A community ONNX export exists and is labelled Apache-2.0 on its card ([anyformat/doclayout-yolo-docstructbench](https://huggingface.co/anyformat/doclayout-yolo-docstructbench)); whether an ONNX export of AGPL-trained code escapes the AGPL is a legal question, not a technical one **[unverified]**.
- **CoreML execution provider pitfalls**: unsupported operators fall back to CPU per partition, which can cost more than it saves ([ORT CoreML EP docs](https://onnxruntime.ai/docs/execution-providers/CoreML-ExecutionProvider.html), [onnxruntime#28022](https://github.com/microsoft/onnxruntime/issues/28022)); the older NeuralNetwork format aborted Docling layout inference in one report and MLProgram is recommended ([docling.rs#324](https://github.com/docling-project/docling.rs/issues/324)).

### 2.2 Measured on the M4

Pages: 28-32 pages at 120 dpi from the PDF 1.7 specification, the Heron/Egret paper and the Docling paper.
Clean runs, no other GPU work.
Timings include preprocessing and post-processing, measured per page after warm-up.
Libraries: torch and transformers latest from PyPI on 2026-09-24, onnxruntime 1.30.0.

| Model | Runtime | ms/page | Notes |
|---|---|---|---|
| PP-DocLayout-S (480 px) | ORT CPU, all threads | **14.9** (2.2 ms preprocessing) | 23 classes; label histograms looked right on a spot check (text, tables, charts, figure titles, footers) |
| PP-DocLayout-S | ORT CPU, 1 thread | 32.3 | 2 threads: 19.1 |
| PP-DocLayout-S | ORT CoreML EP, MLProgram, ALL / CPUAndGPU | 65.1 / 61.7 | Slower than CPU; graph partitioning overhead |
| Egret-m (640 px) | ORT CoreML EP, MLProgram, CPUAndGPU / ALL | **40 / 42** (model forward only; post-processing adds about 1 ms) | ONNX export by a sibling agent (`/tmp/jstbench/egret_m.onnx`, opset 17), which checked it against PyTorch: 313 of 313 detections above 0.5 matched label with IoU above 0.9; max output difference against ORT CPU 0.008 in my run; session creation 7-10 s (compilation), so keep sessions alive |
| Egret-m | ORT CoreML EP, CPUAndNeuralEngine / ORT CPU | 82 / 103 | |
| Egret-m (640 px) | PyTorch MPS fp16, batch 8 | 51.7 | fp32: 68.7 |
| Egret-m | PyTorch CPU, batch 8 | 153 | |
| Heron (640 px) | PyTorch MPS fp16, batch 8 | 105.4 | fp32: 130.2; batch 1 fp32: 137.9 |
| Heron | PyTorch CPU, batch 8 | 236.5 | |
| Heron | ORT CoreML EP (official [heron-onnx](https://huggingface.co/docling-project/docling-layout-heron-onnx)), CPUAndGPU / ALL | 112 / 113 | uint8 input; CPUAndNeuralEngine 198; ORT CPU 191; the sibling agent counted 801 of 949 nodes on CoreML in 46 partitions |
| PP-DocLayoutV3 (800 px) | PyTorch MPS fp16 / fp32, batch 8 | 195.6 / 266.0 | 57 ms of that is post-processing (polygons, reading order) |
| PP-DocLayoutV3 | PyTorch CPU | 412.8 | |
| PP-DocLayout_plus-L (800 px) | ORT CPU | 237 | |
| PP-DocLayout_plus-L | ORT CoreML EP | fails to compile | "MaxPool: ceil_mode must be False when pad_type is ..." |
| DocLayout-YOLO (1024 px) | ORT CoreML EP / CPU | 120 / 805 | Licence caveat above |

Reading of the numbers:

- The M4's 10-core GPU gives roughly a third to a half of the M3 Max throughput on the Docling models (Egret-m 52 vs 33 ms, Heron 105 vs 44 ms), consistent with the difference in GPU size.
- The best execution provider differs by model: CPU wins for the tiny PP-DocLayout-S, CoreML wins for Egret-m and DocLayout-YOLO, and CoreML cannot compile PP-DocLayout_plus-L at all.
  Provider lists must be per-model configuration.
- On the M4, the GPU is a single shared queue; the CPU has ten cores (4 performance, 6 efficiency).
  PP-DocLayout-S at 32 ms per core scales across worker processes, while a GPU-resident model caps the whole machine at about 25 pages/s for Egret-m on CoreML or about 9 pages/s for Heron **[estimate from measured per-page times]**.
  The GPU is also shared with the Vision framework and any local VLM.
- A sibling agent measured Egret-m on MPS at 185-199 ms and Heron at 316-596 ms earlier in the session, while my benchmarks were running at the same time; those numbers were inflated by contention and are superseded by the clean runs above.
- The accuracy figures are not comparable across families (PP-DocLayout-S is scored on Paddle's own set with 23 classes; Egret and Heron on DocLayNet).
  Accuracy per millisecond has to be measured on our golden set, using the downstream metric we care about: does the region histogram predict the right lane?
  For that purpose a coarse detector may be enough, because the router needs "is there a table, a formula, a figure, how much text area", not precise boxes.

### 2.3 Docling end-to-end speed on Apple Silicon, verified

- The first Docling technical report measured 225 pages (three arXiv papers and two IBM Redbooks) with **OCR disabled**: M3 Max with 4 threads ran at **1.27 pages/s** with the native docling-parse backend (6.2 GB peak) and 2.18 pages/s with the pypdfium backend (2.56 GB); with 16 threads, 1.34 and 2.45 pages/s ([arXiv 2408.09869v1](https://arxiv.org/html/2408.09869v1)).
  So the "M3 Max about 1.3 pages/s" figure in the plan is correct, but it is the native backend without OCR.
- A later version of the report measured the full default pipeline with OCR on a larger set: median 0.32 s per page on an M3 Max, 0.79 s on x86 CPU, 114 ms on an L4 GPU; disabling OCR saves about 60% of runtime on CPU and M3 Max; on the L4 the layout model took 44 ms per page and OCR 1.6 s per page ([arXiv 2408.09869v4](https://arxiv.org/html/2408.09869v4)).

---

## 3. Local vision LLMs on the M4 via MLX

### 3.1 Support in mlx-vlm

- `mlx-vlm` 0.7.2 with `mlx` 0.32.2 was current on PyPI on 2026-09-24 **[measured]** ([mlx-vlm](https://github.com/Blaizzy/mlx-vlm)).
- Qwen3-VL 2B, 4B and 8B load and run from `mlx-community` 4-bit conversions **[measured]** ([Qwen3-VL-4B-Instruct-4bit](https://huggingface.co/mlx-community/Qwen3-VL-4B-Instruct-4bit)).
- MiniCPM-V-4.6 runs from [mlx-community/MiniCPM-V-4.6-4bit](https://huggingface.co/mlx-community/MiniCPM-V-4.6-4bit) **[measured]**; Hugging Face metadata puts the base model near 1.3B parameters ([openbmb/MiniCPM-V-4_6](https://huggingface.co/openbmb/MiniCPM-V-4_6)).
- InternVL3.5: MLX conversions found only for 1B and the MoE variants, not a 4B dense model ([InternVL3_5-1B-4bit](https://huggingface.co/mlx-community/InternVL3_5-1B-4bit)) **[unverified that no 4B conversion exists]**.
- Moondream 3 is listed in the mlx-vlm README's model table; SmolVLM2 conversions exist but look old **[source, not run]**.
- `mlx-lm`'s server is text only ([mlx-lm](https://github.com/ml-explore/mlx-lm)); `vllm-mlx` projects exist but are community efforts, not the vLLM project ([waybarrios/vllm-mlx](https://github.com/waybarrios/vllm-mlx)).
  `mlx_vlm.server` already exposes an OpenAI-compatible API with a continuous-batching backend **[measured]**.
- Structured output: `mlx_vlm.server` accepts OpenAI `response_format` `json_schema` on `/v1/chat/completions` and `/v1/responses` ([README](https://github.com/Blaizzy/mlx-vlm)), implemented with `llguidance` in 0.7.2 **[measured: import in the package source]**.
  `outlines` lists no MLX backend ([outlines](https://github.com/dottxt-ai/outlines)).

### 3.2 Measured on the M4 (clean runs)

Prompt: the plan's five-field classification, one page image at 768 px on the long side, temperature 0, `mlx_vlm.generate` from Python.
Three images (clean digital render, synthetic flatbed scan, synthetic camera photo), second of two passes.

| Model | Total per call | Prefill | Decode | Peak memory | Output quality on the three images |
|---|---|---|---|---|---|
| Qwen3-VL-2B-Instruct 4-bit | 2.1-2.7 s | 450-460 tok/s over 590-638 tokens | 84 tok/s | 2.5-2.6 GB | Ignores the enum and copies page text into `main_content`; capture "screenshot" or "camera_photo" for everything |
| Qwen3-VL-4B-Instruct 4-bit | 3.7-3.8 s | 234-239 tok/s | 36-40 tok/s | 3.8-3.9 GB | Clean JSON; `digital_render` for all three images (misses scan and photo) |
| Qwen3-VL-8B-Instruct 4-bit | 6.5-7.1 s | 125-132 tok/s | 22 tok/s | 6.7 GB | Clean JSON; `flatbed_scan` for all three |
| MiniCPM-V-4.6 4-bit | 1.8-2.1 s | 337-397 tok/s over 464 tokens | 76-81 tok/s | 2.7 GB | Does not follow the JSON instruction without a grammar; claimed "mostly_handwritten" on a typed form |

With the server and a strict `json_schema`:

- Qwen3-VL-4B: 3.7 s per call, valid JSON 3/3, **once the array had `maxItems`**.
  Without `maxItems` the grammar allowed `["form", "form", ...]` until `max_tokens` ran out (8 s, invalid JSON) **[measured]**.
  `uniqueItems` is rejected with HTTP 400 "Unimplemented keys" **[measured]**.
  So every array in our schemas needs `maxItems`, and the enum should be de-duplicated in code.
- Concurrency does not help: Qwen3-VL-4B gave 0.30, 0.35 and 0.33 pages/s at concurrency 1, 4 and 8; Qwen3-VL-2B gave 0.42, 0.43 and 0.46 **[measured]**.
  The vision encoder and prefill dominate (about 2.5 s of the 3.7 s for the 4B model), and they do not batch across requests on this backend.
- Memory is no constraint: even the 8B model peaks at 6.7 GB of 24 GB.
- An earlier set of runs overlapped with another agent's MLX jobs and was about 10-30% slower; the numbers above are the clean rerun.
  That agent separately reported 19 tok/s decode for the 4B model under contention.

Quality caveat: three synthetic images show instruction-following and speed, nothing about accuracy.
No published 4-bit vs 16-bit comparison on document tasks was found for these models **[unverified]**.

### 3.3 Conclusion for local VLMs

On a base M4, a local 4B VLM costs 3.7 s of the whole GPU per ambiguous page and cannot be parallelised, against 1.1-1.5 s wall time and well under $0.001 hosted.
At a 15% arbitration rate that caps the demo at about 2 pages/s overall if every ambiguous page waits for the local model **[estimate]**.
Keep MLX as an offline fallback and as the like-for-like stand-in for the cloud's vLLM Qwen3-VL, not as the default arbiter.
If it is used, prefer Qwen3-VL-4B-4bit with a strict schema, and cut the image to 512-640 px for page-level questions, since prefill scales with image tokens.

---

## 4. Hosted small vision LLMs

### 4.1 Current models and list prices

Live prices from the OpenRouter models API on 2026-09-24, USD per million tokens, input / output; `:batch` variants are half price **[measured: API listing]**:

| Model | Price in / out | Batch variant | Notes |
|---|---|---|---|
| google/gemini-2.5-flash-lite | 0.10 / 0.40 | yes | Oldest and cheapest Flash-Lite |
| google/gemini-3.1-flash-lite | 0.25 / 1.50 | yes | Vertex list price is the same; non-global (for example EU) endpoints cost 10% more ([Vertex pricing](https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing)) |
| google/gemini-3.5-flash-lite | 0.30 / 2.50 | yes | Reasoning cannot be disabled; "minimal" works |
| google/gemini-3.8-flash | 0.75 / 3.75 | yes | Newest Flash |
| openai/gpt-5-nano | 0.05 / 0.40 | yes | OpenAI now recommends newer models for new low-latency work ([GPT-5 mini page](https://developers.openai.com/api/docs/models/gpt-5-mini)) |
| openai/gpt-5-mini | 0.25 / 2.00 | yes | |
| openai/gpt-6-luna | 0.10 / 0.50 | yes | Cheapest current OpenAI line ([OpenAI pricing](https://developers.openai.com/api/docs/pricing)) |
| anthropic/claude-haiku-4.5 | 1.00 / 5.00 | yes | ([Anthropic](https://www.anthropic.com/claude/haiku)) |
| mistralai/mistral-small-2603 (Mistral Small 4) | 0.15 / 0.60 | yes | 119B total, 6B active, natively multimodal ([Mistral](https://mistral.ai/news/mistral-small-4/)) |
| qwen/qwen3-vl-8b-instruct | 0.117 / 0.455 | no | |
| qwen/qwen3-vl-30b-a3b-instruct | 0.13 / 0.52 | no | |
| meta-llama/llama-4-scout | 0.10 / 0.30 | no | |
| google/gemma-4-26b-a4b-it | 0.09 / 0.30 | no | |
| deepseek/deepseek-v4.1-flash | 0.10 / 0.50 | yes | Image input listed; DeepSeek's own API is operated by a Chinese entity ([privacy policy](https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy.html)) |

Structured output with image input is documented for Gemini ([structured output](https://ai.google.dev/gemini-api/docs/structured-output)) and OpenAI ([GPT-5 mini](https://developers.openai.com/api/docs/models/gpt-5-mini)).
Fireworks and Together host Qwen3-VL-32B and larger ([Fireworks](https://fireworks.ai/models/fireworks/qwen3-vl-32b-instruct), [Together](https://www.together.ai/models/qwen3-vl-32b-instruct)); Groq hosts Llama 4 Scout per a secondary source ([morphllm](https://www.morphllm.com/comparisons/fireworks-vs-groq)) **[unverified for image input]**.
General latency boards exist ([Artificial Analysis](https://artificialanalysis.ai/models), [BenchLM](https://benchlm.ai/llm-speed)) but measure long text tasks, not one image with a short JSON reply, so I measured directly.

### 4.2 Measured from Finland through OpenRouter

Setup: streaming chat completions with strict `json_schema` (the plan's five fields), one JPEG of about 790x1024, three images (digital render, synthetic flatbed scan, synthetic camera photo) times three repetitions, sequential calls, reasoning off or minimal.
Expected capture labels: `digital_render`, `flatbed_scan`, `camera_photo`.
OpenRouter adds its own routing hop; direct provider APIs will be somewhat faster **[unverified by how much]**.

| Model (provider) | TTFT median | Total median | Total max | Cost per call | Valid JSON | Capture right (of 3 types) |
|---|---|---|---|---|---|---|
| qwen3-vl-8b (Alibaba) | 0.49 s | **0.80 s** | 0.85 s | $0.00016 | 9/9 | 1 (called the scan digital, the photo flatbed) |
| qwen3-vl-30b-a3b (Alibaba) | 0.59 s | 0.86 s | 1.02 s | $0.00017 | 9/9 | 1 (all digital) |
| gemini-3.1-flash-lite (Google) | 0.97 s | 1.13 s | 1.42 s | $0.00044 | 9/9 | 1 (all digital) |
| gemini-3.5-flash-lite, minimal (Google) | 1.14 s | **1.23 s** | 1.60 s | $0.00059 | 9/9 | 2 (scan called camera photo, legibility "hard_to_read") |
| gemini-2.5-flash-lite (Google) | 1.41 s | 1.49 s | 1.62 s | $0.00016 | 9/9 | 2 (scan called camera photo) |
| gpt-5-nano, minimal (OpenAI) | 1.24 s | 1.69 s | 2.00 s | $0.00010 | 9/9 | 1 (all camera photo) |
| gemma-4-26b-a4b (CoreWeave) | 0.59 s | 2.04 s | 4.09 s | $0.00003 | 9/9 | 0 (mostly "unsure") |
| gpt-5-mini, minimal (OpenAI) | 1.49 s | 2.12 s | 2.55 s | $0.00020 | 9/9 | 2 (digital called flatbed) |
| llama-4-scout (DeepInfra) | 1.08 s | 2.35 s | 2.67 s | $0.00021 | 9/9 | 0 (all fax) |
| claude-haiku-4.5 (Bedrock) | 1.84 s | 2.51 s | 2.96 s | $0.0019 | 9/9 | 2 (digital called flatbed; also claimed hand-filled fields on a blank typed form) |
| deepseek-v4.1-flash (Together) | 0.56 s | 1.07 s | 1.76 s | $0.00009 | 6/6 | called both images "screenshot" |
| gpt-6-luna, reasoning none (OpenAI) | 1.68 s | 2.09 s | 2.79 s | $0.00003 | 6/6 | 1 of 2 (earlier two-image run) |
| mistral-small-2603 | - | - | - | - | - | HTTP 429 upstream rate limit on both attempts |

Another agent in this session ran a similar test on three other page images and got 3/3 capture labels right for Gemini 3.5 Flash-Lite, Gemini 2.5 Flash-Lite, GPT-5-mini and Haiku 4.5, with TTFT medians of 0.82, 1.31, 1.62 and 1.80 s; it also saw Gemini 3.8 Flash and DeepSeek V4.1 Flash return invalid JSON on some calls (5/9 and 3/9 valid) **[measured by a sibling agent, results file /tmp/pdfbench/hosted_results.txt]**.
With nine calls per model, none of this is accuracy evidence; it rules models out (Llama 4 Scout, Gemma 4, Qwen3-VL for capture type) more than it ranks them.

### 4.3 Recommendation

- **Real-time visual arbiter:** Gemini 3.5 Flash-Lite with minimal reasoning, strict `responseSchema`, 768-1024 px JPEG.
  About 1.2 s and $0.0006 per call; fastest of the models that got capture type mostly right, and a batch endpoint exists for the same model.
  Gemini 2.5 Flash-Lite is the cheaper fallback at a quarter of the price and 0.3 s more latency.
  Run the plan's two-sample agreement check in parallel, not in sequence, so it costs no extra wall time.
- **Golden-set pre-labelling:** two different families through batch endpoints (Gemini 3.5 Flash-Lite `:batch` plus GPT-5-mini `:batch` or Haiku 4.5 batch), keep labels where both agree, send the rest to people.
  At about 1,500 input tokens per page, 10,000 pages cost roughly $2-3 for Gemini 3.5 Flash-Lite batch and $2-3 for GPT-5-mini batch **[estimate from list prices]**.
- **Speed-first option to test on the golden set:** Qwen3-VL-8B hosted (0.8 s), for axes it gets right (content type and script) even if it is weak on capture type.
- Always add `maxItems` to arrays and handle `unsure`; route every provider through one OpenAI-compatible client (OpenRouter, Vertex, vLLM and `mlx_vlm.server` all speak it).

---

## 5. Jev latency from Europe and rate limits

- TypeSafe says its published evals were run "from our laptops on the West Coast (this is where our service is currently based)" ([launch blog](https://typesafe.ai/blog/introducing-system-one-models-and-jev)); no EU region is documented ([TrueFoundry writeup](https://www.truefoundry.com/fr/blog/typesafe-ai-jev)).
- **Measured from Finland** (this machine, ipinfo country FI):
  - `api.typesafe.ai` terminates at a Cloudflare edge in Stockholm (`cf-ray ...-ARN`); TCP connect 15 ms, TLS 35 ms; an unauthenticated request returns 403 in 0.24-0.30 s with `x-envoy-upstream-service-time: 9` ms, so about 0.23-0.29 s is the round trip from the edge to the US origin **[measured]**.
    Every Jev call from Europe pays that on top of inference.
  - Through OpenRouter's decisions endpoint (`POST https://openrouter.ai/api/alpha/decisions`, same body as `/v1/systemone`), a two-question request (one choice, one noul; 532 input and 70 output tokens) took **0.367 s median, 0.317 s minimum, 2.81 s maximum over 11 warm calls, 2.03 s cold**; cost $0.000022 per call; the provider reported was TypeSafe and the model `jev-1.13-20260917` **[measured]**.
  - No direct-API key was available, so the direct-path latency with inference is not measured **[unverified]**; expect it to be close to the OpenRouter figure minus OpenRouter's hop.
  - A third-party client author reports, from the Netherlands, cold first calls of 690-714 ms for 3-100 questions per request (521-4,017 input tokens), 1,336 ms for 400 questions, and 250-580 ms on a warm connection ([jevclient on PyPI](https://pypi.org/project/jevclient/1.2.0/), [GitHub](https://github.com/AboveColin/jevclient)) **[source, third party; found by a sibling agent]**.
    That agrees with my figure and says the number of questions per request barely changes latency, so all of a page's text questions belong in one request.
  - A community FAQ says US servers only, with no EU region announced ([learnjev FAQ](https://learnjev.com/faq)) **[source, unofficial]**.
- **Rate limits:** the models page states "250,000 tokens per second / 1,200 requests per minute" for jev-1.13.0, notes limits are adjusted dynamically during a demand surge, and says "higher limits are available on custom and enterprise plans" via sales ([TypeSafe models](https://docs.typesafe.ai/models)).
  No named tiers or self-serve increases are published.
  1,200 RPM is 20 requests/s; at 0.37 s each, 8 concurrent requests reach that limit, so the RPM cap, not latency, bounds Jev throughput **[estimate]**.
  At a 15% arbitration rate, 20 requests/s supports about 130 pages/s of router traffic if each ambiguous page needs one call **[estimate]**.

---

## 6. Cloud cluster deployment

### 6.1 Published throughput for document pipelines

| System | Hardware | Throughput | Source |
|---|---|---|---|
| olmOCR (7B VLM, full conversion) | L40S / H100 | 906 / 3,050 output tokens/s; $176 per million pages on L40S; S3 work queue with work items of about 500 pages | [olmOCR paper](https://arxiv.org/html/2502.18443), [repo](https://github.com/allenai/olmocr) |
| Docling on Ray Data, OpenShift AI | 8 workers x 8 CPUs | 4-8 files/s for 5-20 page business PDFs, OCR off; OCR makes it 2-5x slower | [Red Hat Developer](https://developers.redhat.com/articles/2026/06/30/scale-document-ingestion-docling-and-ray-openshift-ai) |
| Ray Data vs Daft, PDF parse and embed | 8 x g6.xlarge (L4) + head | 10,000 PDFs in 29.4 s for tuned Ray Data (Daft 51.3 s) | [Anyscale](https://www.anyscale.com/blog/ray-data-daft-benchmarking-multimodal-ai-workloads) |
| RayOrch vs Ray Data on a Docling pipeline | NVIDIA H20 | RayOrch 16% faster end to end than Ray Data | [arXiv 2609.18703](https://arxiv.org/abs/2609.18703) |
| Docling full pipeline | L4 GPU | 114 ms/page median; layout model 44 ms | [arXiv 2408.09869v4](https://arxiv.org/html/2408.09869v4) |

None of these is a routing-only workload; the router's per-page cost is a small fraction of any of them.

### 6.2 Architecture that fits

- **Batch path: Ray Data.**
  Ray Data streams across CPU and GPU stages in one plan rather than stopping at stage boundaries ([Ray Data](https://docs.ray.io/en/latest/data/data.html)), and there is a Docling-on-Ray reference ([Anyscale](https://www.anyscale.com/blog/ray-data-docling-rag-document-processing)).
  Shape: `read_binary_files(s3://...)` then S0 (flat-map documents to page records, hash, gates) then S1+S2-CPU+S3 in CPU actors (pdfium, pikepdf, render, IQA, PP-DocLayout-S on ORT CPU) then an optional GPU actor pool for Egret or Heron with batching then S5 in CPU then `write_parquet`.
  The Anyscale benchmark's main lesson was to drop the raw bytes column as soon as it is parsed; that alone made Ray Data 5x faster in their test ([Anyscale](https://www.anyscale.com/blog/ray-data-daft-benchmarking-multimodal-ai-workloads)).
- **Online path: queue plus KEDA.**
  For documents arriving continuously, run S0-S5 as queue workers and scale on queue depth with KEDA, which scales on external signals such as queue length rather than CPU ([Cast AI on KEDA](https://cast.ai/blog/keda-kubernetes-event-driven-autoscaling/)).
  No document-specific KEDA reference architecture was found **[unverified]**.
- **Model serving.**
  Triton's dynamic batcher suits fixed-shape detectors ([Triton batcher](https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/user_guide/batcher.html)); vLLM's continuous batching suits the VLM; Ray Serve or KServe can front both ([kubenatives comparison](https://www.kubenatives.com/p/vllm-vs-triton-vs-kserve-kubernetes), [Anyscale on Ray plus Triton](https://www.anyscale.com/blog/low-latency-generative-ai-model-serving-with-ray-nvidia)).
  For the router specifically: PP-DocLayout-S does not need a GPU at all (15 ms on CPU); if Egret or Heron is chosen, run it inside a Ray Data GPU actor for batch work and behind Triton only if there is an online path.
  The VLM arbiter handles 15% of pages or fewer, so hosted Gemini is the simplest cloud option too; self-hosted Qwen3-VL on vLLM is the fallback for cost or independence.
- **Backend abstraction.**
  ONNX Runtime's execution providers give one model file across CPU, CoreML, CUDA and TensorRT, with per-node fallback ([ORT EPs](https://onnxruntime.ai/docs/execution-providers/)).
  TensorRT EP is 1.5-3x faster than CUDA EP on static shapes but builds engines for minutes, so cache engines ([NVIDIA](https://developer.nvidia.com/blog/end-to-end-ai-for-nvidia-based-pcs-cuda-and-tensorrt-execution-providers-in-onnx-runtime/)).
  My measurements say the right provider differs by model on the M4 (CPU for PP-DocLayout-S, CoreML for DocLayout-YOLO, CoreML failing outright for PP-DocLayout_plus-L), so the provider list must be configuration per model and per host, not a global default.
  Proposed interface: `LayoutDetector.detect(images) -> list[Regions]` with backends `onnx(providers=[...])` and `torch(device=mps|cuda|cpu, dtype)`; `VisionArbiter.ask(image, schema)` with one OpenAI-compatible client whose base URL points at OpenRouter, Vertex, vLLM or `mlx_vlm.server`.
- **Model registry.**
  MLflow has an ONNX flavour and a registry with aliases ([mlflow.onnx](https://www.mlflow.org/docs/latest/api_reference/python_api/mlflow.onnx.html), [registry](https://mlflow.org/docs/latest/ml/model-registry/)); its pyfunc loader needs explicit providers ([mlflow#5308](https://github.com/mlflow/mlflow/issues/5308)).
  A lighter option that is enough for the router: content-addressed model files in object storage, a `models.yaml` mapping logical name to hash, backend and provider list, and the hash written into every `features.v1` row and manifest.
- **Feature store.**
  Parquet partitioned by date and corpus on S3, queried with DuckDB, is a standard pattern and adequate well past a billion rows ([DuckDB Parquet](https://duckdb.org/docs/lts/data/parquet/overview.html), [DuckDB feature store writeup](https://medium.com/@jickpatel611/duckdb-feature-stores-for-people-who-ship-16178b71855e)).
  Move to Iceberg only when several writers need transactions or schema evolution across many files.
- **Arm in the cloud.**
  All CPU stages (pypdfium2, pikepdf, OpenCV, ONNX Runtime CPU, LightGBM) ship arm64 wheels, so the CPU pool can run on Graviton **[measured on arm64 macOS; Linux arm64 wheels not tested here]**.

---

## 7. PDF libraries on arm64

### 7.1 Measured on the M4

pypdfium2 5.13.0, PyMuPDF 1.28.2, pikepdf 10.13.0.
Grayscale renders at 120 dpi to a NumPy array; text extraction is pdfium's text page plus `get_text_range` against PyMuPDF `get_text()`.

| Document | Pages | pypdfium2 render | PyMuPDF render | pypdfium2 text | PyMuPDF text | pikepdf per-page inspection |
|---|---|---|---|---|---|---|
| PDF 32000 spec (22 MB, text) | 200 | 4.1 ms median, 5.4 p95 | 3.2 / 5.2 | 0.8 ms | 3.3 ms | 0.05 ms (open 206 ms) |
| Heron paper (figures) | 11 | 6.4 median, 160 p95 | 4.5 / 357 | 1.2 | 3.5 | 0.1 ms |
| Docling paper | 8 | 9.0 | 8.2 | 1.2 | 5.5 | 0.1 ms |
| IRS Form 1040 (AcroForm) | 2 | 11.2 | 26.2 | 1.6 | 16.3 | 0.1 ms |

- Renders are close between the two libraries on text pages; pages with large embedded images take 100-360 ms in both.
  The p95 is the number to plan for: S2 should render once and cache the bitmap for all visual probes.
- pdfium text extraction is 3-10x faster than PyMuPDF here.
- pikepdf inspection of images, fonts and annotations is negligible; opening a large file costs a one-off 200 ms.
- Published comparisons agree roughly: the py-pdf benchmark puts both libraries at about 0.1 s per document for text, with pypdfium2 slightly more accurate (97% vs 96%) and PyMuPDF faster at image extraction ([py-pdf/benchmarks](https://github.com/py-pdf/benchmarks/blob/main/README.md)); PyMuPDF's own suite omits pypdfium2 from its render test ([PyMuPDF docs](https://github.com/pymupdf/PyMuPDF/blob/main/docs/app4.rst)); pikepdf's content-stream parsing can be slow on heavy streams ([pikepdf#227](https://github.com/pikepdf/pikepdf/issues/227)), which matters for the plan's graphics-operator count gate.
- No third-party arm64 or Graviton render benchmark was found **[unverified]**.

### 7.2 Other S1/S2 CPU costs on the M4

A sibling agent measured these on the same machine on a different corpus (41 born-digital arXiv pages, several with heavy vector figures, and an 11-page synthetic scan) **[measured by sibling agent; scripts in `research/bench_m4/` and `/tmp/jstbench`]**:

| Operation | ms/page | Note |
|---|---|---|
| pypdfium2 render, 120 dpi gray | 38 mean (9-52 by file) | Vector-heavy pages about 50 ms; my text-heavy set gave 4-11 ms |
| PyMuPDF render, same pages | 48 mean (9-105) | Faster on the JPEG scan, 2x slower on the vector-heavy paper |
| Scan fast path: pikepdf extracts the page's single DCT image, PIL `draft()` downscales it | 16 | 3x faster than a full render for single-image scan pages |
| pikepdf structural probe (docinfo, AcroForm, MarkInfo, image filters, fonts, ToUnicode) | 0.2 | |
| OpenCV IQA without Hough (Laplacian variance, RMS contrast, noise, background) | about 10 | |
| Canny plus HoughLinesP (ruling lines, skew) | 49 | Run at 60 dpi, or only where S1 found no vector rulings |
| Parallel pypdfium2 rendering, one process per worker | 25 / 69 / 116 / 122 pages/s at 1 / 4 / 8 / 10 workers | Flattens past 8 because of the 4+6 core split |

Tesseract 5.5.3 `--psm 0` on my pages **[measured]**: 280 ms at 120 dpi on both the paper page and the IRS form, and it reported the English form as **Cyrillic** (script confidence 0.63); at 300 dpi, 380 ms with the right script.
The sibling agent saw 404 ms at 120 dpi and one "Arabic" call on an English page.
So Tesseract OSD at 120 dpi costs more than the rest of S0-S2 together and its script guess is unreliable.
Replace it on the per-page path with a small orientation classifier such as PP-LCNet_x1_0_doc_ori (four classes, 99.06% top-1, 3.24 ms on a Xeon CPU, 7 MB, per [PaddleOCR docs](http://www.paddleocr.ai/main/en/version3.x/module_usage/doc_img_orientation_classification.html)) **[source, not measured here]**, and get script on image pages from a quick OCR sample passed to GlotLID or from the VLM.

---

## 8. Recommendations per stage

### 8.1 M4 demo

| Stage | Choice | Expected cost per page on the M4 |
|---|---|---|
| S0 intake | `puremagic`, sha256, pypdfium2 + pikepdf open as the two-parser check | Under 5 ms, plus a one-off open per file |
| S1 structural | pypdfium2 text page and objects; pikepdf for filters, fonts, AcroForm | 1-2 ms **[measured parts]** |
| S2 render | pypdfium2 grayscale 120 dpi, cached once per page; scan fast path (decode the single embedded image) when S1 finds a one-image page | 4-50 ms, 100-360 ms on image-heavy pages; 16 ms on the fast path **[measured]** |
| S2 layout | **Egret-m ONNX on ORT CoreML EP** (CPUAndGPU), one long-lived GPU process fed in page order | 40 ms, about 25 pages/s for the machine **[measured]** |
| S2 layout, CPU fallback | PP-DocLayout-S on ORT CPU inside each worker, used when the GPU queue backs up or for a quick first pass | 15-32 ms **[measured]** |
| S2 Apple probes | Swift helper: document segmentation and text rectangles on all image pages; `RecognizeDocumentsRequest` on image pages in the ambiguous slice | 5-15 ms; 0.5-0.8 s for documents **[measured]** |
| S2 orientation, IQA, figure classifier | Orientation classifier instead of per-page Tesseract OSD (Tesseract only as an arbiter-time fallback); OpenCV IQA with Hough at 60 dpi | about 10 ms IQA; OSD would have cost 280-400 ms **[measured]** |
| S3 text | As planned; a Vision OCR sample stands in for missing text layers | Accurate OCR 0.5-0.9 s, only where needed **[measured]** |
| S5 | LightGBM plus isotonic, as planned | Under 1 ms |
| S6 text arbiter | Jev through OpenRouter or direct, token bucket at 18-19 requests/s | 0.37 s median from Finland **[measured]** |
| S6 visual arbiter | **Gemini 3.5 Flash-Lite (minimal reasoning) hosted**, two samples in parallel; MLX Qwen3-VL-4B-4bit only as an offline fallback | 1.2 s wall time hosted; 3.7 s of the GPU locally **[measured]** |

Process layout: 8 CPU worker processes for S0-S5 (each with a PP-DocLayout-S session at `intra_op_num_threads=1` as fallback), one GPU process holding the Egret-m CoreML session, one Swift Vision helper shared through a small pool, and an async client pool for Jev and Gemini.
Throughput: the sibling agent's estimate of 50-60 ms of CPU per page for S1+S2 without models gives 80-90 pages/s of CPU probing across the cores; Egret-m on the GPU caps the machine near 25 pages/s; Jev's 1,200 RPM caps router traffic near 130 pages/s at 15% arbitration **[estimate]**.
So the demo should sustain roughly 20-25 pages/s end to end, with the layout detector as the bottleneck, unless PP-DocLayout-S on the CPU is good enough on the golden set to drop Egret-m from the default path.

### 8.2 Cloud cluster

| Stage | Choice |
|---|---|
| Orchestration | Ray Data on KubeRay for batch; queue workers with KEDA for online intake |
| S0-S3, S5 | CPU actor pool (Graviton or x86), same Python code; Apple probes disabled, features imputed |
| S2 layout | The same `egret_m.onnx` in a GPU actor pool on L4-class GPUs with the ORT CUDA or TensorRT EP, batched (published: 24 ms/image on an A100 at batch 200 in PyTorch; TensorRT unmeasured); PP-DocLayout-S on ORT CPU inside the CPU actors if the bake-off shows it is enough, which removes GPUs from the router entirely |
| S6 visual arbiter | Hosted Gemini 3.5 Flash-Lite via Vertex (EU endpoint if wanted, +10%); fallback Qwen3-VL-8B on vLLM with the same OpenAI-compatible client and strict JSON schema |
| S6 text arbiter | Jev with an enterprise rate limit; the 1,200 RPM default caps router throughput near 130 pages/s at 15% arbitration **[estimate]** |
| Storage | S3 Parquet `features.v1`, partitioned; DuckDB for queries and training; Iceberg later |
| Models | ONNX files in object storage by hash, `models.yaml` with provider lists per host class; MLflow if a UI and aliases are wanted |

### 8.3 What to measure next

1. Egret-m, Heron and PP-DocLayout-S on the golden set, scored by how well the region histogram predicts the lane axes, not by mAP.
2. Gemini 3.5 Flash-Lite, Gemini 2.5 Flash-Lite, GPT-5-mini and Qwen3-VL-8B on the ambiguous slice, per axis, with the agreement check.
3. The Swift `.fast` text-recognition result, and whether `RecognizeDocumentsRequest` table detection adds anything over PP-DocLayout-S on image pages.
4. Direct Jev latency with a key, from the same machine.

---

## 9. Method notes

- All [measured] numbers come from scripts in `/tmp/jbench` (copied to `research/bench_m4/jbench/`) on this M4 (macOS 26.3.1, Python 3.12 via `uv run`, Swift from the Command Line Tools).
  Scripts: `bench_pdf.py` (PDF libraries), `bench_layout2.py` (PyTorch detectors), `ort_bench.py` and `ort_check.py` (ONNX Runtime detectors), `swift/vbench.swift` and `swift/vconc.swift` (Vision), `bench_mlx.py`, `srv_test.py` and `srv_conc.py` (MLX), `bench_vlm.py` (hosted VLMs), `bench_jev.py` (Jev).
- Test PDFs: the PDF 32000-2008 specification, arXiv 2408.09869v4 and 2509.11720v1, and IRS Form 1040.
  The "scan" and "photo" images are synthetic (rotation, blur, noise and JPEG artefacts; perspective warp, background and lighting gradient), which is enough for speed and instruction-following checks and not for accuracy.
- Another agent was running MLX and layout benchmarks on the same machine for part of the session.
  Every GPU number in this document comes from a rerun after its processes had exited; CPU and network numbers were not affected in any way I could see.
- That agent had already written an earlier version of this file (2026-09-23 23:25).
  This version replaces it: I kept its unique findings (Egret-m ONNX export and CoreML result, which I reproduced; CPU stage costs; Tesseract OSD; the third-party Jev latency table; the orientation-classifier suggestion) and replaced its MPS timings, which were measured under contention.
- Hosted-model calls went through OpenRouter from Finland on 2026-09-23/24; nine calls per model is a smoke test.
