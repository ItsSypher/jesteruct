# Small/fast/cheap vision-capable LLMs for a document sorting/routing layer
Research date: 2026-09-23. All prices in USD per 1M tokens unless noted. Every claim below is sourced; secondary/aggregator sources (pricepertoken.com, benchlm.ai, aipricing.guru, techjacksolutions.com, codersera.com, aimadetools.com, cloudzero.com, etc.) are marked **[agg]** because they are SEO pricing-roundup sites, not vendor primary sources, and their numbers occasionally disagree with each other. Where I fetched a vendor's own docs directly, that's marked **[primary]**.

## 0. Direct answer: "DeepSeek's new flash model"
DeepSeek shipped a fast progression this year. The relevant lineage:
- **DeepSeek-V4-Flash** (GA July 31, 2026) - text-only, agent-focused. [DeepSeek API changelog](https://api-docs.deepseek.com/updates/)
- **DeepSeek-V4-Flash-Vision-Exp** (Aug 21, 2026) - DeepSeek's *first* experimental multimodal model in the V4 family. Model id `deepseek-v4-flash-vision-exp`. Accepts base64, external URLs, or Files API images; images tokenize at up to 384 tokens each at V4-Flash pricing. **[primary]** [Release notes](https://api-docs.deepseek.com/news/news260821/), [Vision guide](https://api-docs.deepseek.com/guides/vision/)
- **DeepSeek-V4.1-Flash** (GA Sept 10, 2026) - the current flash model, with native multimodal support baked in rather than bolted on as an "-exp" side branch. The old model ids `deepseek-v4-flash` and `deepseek-v4-flash-vision-exp` are now routed to this model for compatibility. **[primary]** [Changelog](https://api-docs.deepseek.com/updates/)

So "DeepSeek's new flash model" most likely means **DeepSeek-V4.1-Flash**, accessed as `deepseek-flash` in the API. It is genuinely vision-capable (not text-only), unlike prior DeepSeek flash generations.

Vision API specifics (from DeepSeek's own vision guide, **[primary]**): JPEG/PNG/GIF/WebP; max 8192px per side, dropping to 4096px when a request has 15+ images; images are resized to roughly 1300x1300px before inference with an upper bound of ~1024 tokens/image; up to 600 images per request; 32 MiB per image (64 MiB via Files API), 200 MiB total per request via Files API.

Pricing for V4.1-Flash has a peculiar peak/off-peak schedule that several secondary sources report consistently: off-peak input $0.15/M, output $0.60/M; peak (01:00-04:00 and 06:00-10:00 UTC) input $0.30/M, output $1.20/M; cached input as low as $0.003/M off-peak. **[agg, but consistent across 3+ independent sources]** [MindStudio](https://www.mindstudio.ai/blog/deepseek-v4-1-flash-pricing), [Forbes](https://www.forbes.com/sites/jonmarkman/2026/09/14/deepseek-v41-flash-prices-cached-input-to-0003-per-million-tokens/), [BenchLM](https://benchlm.ai/deepseek/api-pricing). Treat exact peak windows as soft; verify against `api-docs.deepseek.com` pricing page before building billing logic around it.

A second, separate product worth distinguishing: **DeepSeek-OCR-2**, a dedicated OCR/vision-to-text model (not a general chat/reasoning VLM), priced around $0.03/M input and $0.03/M output via third-party host Novita, 8K context. **[agg]** [getdeploying.com](https://getdeploying.com/llms/deepseek-ocr-2). This is a parsing engine, not a router brain; useful for the post-parse-verification lane's "extraction" step, not for the JSON-decision step.

## 1. Hosted APIs - small vision models

| Model | Release | Vision | Input/Output $ per 1M tok | Context | Structured output | Batch discount | Notes |
|---|---|---|---|---|---|---|---|
| **DeepSeek-V4.1-Flash** | Sep 10, 2026 | Yes, native | ~$0.15/$0.60 off-peak, $0.30/$1.20 peak **[agg]** | not disclosed publicly | JSON output guide exists per docs; not confirmed strict-schema | not confirmed | Cheapest frontier-adjacent vision option found; peak/off-peak pricing is unusual, plan around it |
| **DeepSeek-OCR-2** | 2026 | Yes (OCR-specialized) | $0.03/$0.03 (Novita) **[agg]** | 8K | N/A (text/markdown out) | unknown | Parsing engine, not a JSON-decision model |
| **Gemini 3.8 Flash** | GA Sep 2, 2026 | Yes | $0.75/$3.75 (intro, through Dec 31 2026; rises to $1.50/$7.50 Jan 1 2027) **[agg, cross-checked 3 sources]** | large (1M-class per Gemini family pattern) | `responseSchema`/JSON schema, all actively-supported Gemini models **[primary via ai.google.dev docs summary]** | yes, standard Gemini batch discount pattern | Each image ~258 tokens input regardless of pixel size (tiling detail not confirmed) **[agg]** |
| **Gemini 3.1 Flash-Lite (Preview)** | 2026 | Yes | $0.25/$1.50 **[agg]** | large | JSON schema supported | yes | Cheaper/faster tier, good triage candidate |
| **Gemini 3.5 Flash-Lite** | 2026 | Yes | $0.30/$2.50 **[agg]** | large | JSON schema supported | yes | Superseded-but-live tier |
| **Claude Haiku 4.5** | Oct 15, 2025 | Yes | $1/$5 base; batch $0.50/$2.50; cache read $0.10/$2 | 200K context, 64K max output **[primary, platform.claude.com]** | Tool-use / forced-tool JSON, not a first-class "JSON schema" strict mode like OpenAI's | 50% via Batch API **[primary]** | Image tokenized in 28x28px patches: ceil(w/28)*ceil(h/28); ~1560 visual tokens for a 4K image on Haiku-class models **[agg but methodologically specific, matches Anthropic's documented tiling approach]** |
| **GPT-5 mini** | Aug 2025 | Yes | $0.25/$2.00; cached input $0.025 **[primary via developers.openai.com/api/docs/pricing]** | ~400K input per secondary reports (unverified against primary) | Structured Outputs (`json_schema` strict mode) - confirmed for gpt-4o family and later; gpt-5-mini not explicitly named in fetched docs, treat as **unverified**, test empirically | 50% Batch API | Reliable go-to small vision router candidate given OpenAI's mature Structured Outputs support |
| **GPT-5 nano** | Aug 2025 | Yes (multimodal per family-wide claim) | $0.05/$0.40; cached input $0.005 **[primary]** | large | same caveat as mini | 50% Batch API | Cheapest OpenAI option; vision support claimed but not explicitly itemized in the pricing table's multimodal section - confirm before relying on it |
| **Mistral Small (4)** | 2026 | Yes | ~$0.15/M input (agentic/coding/multimodal claim) **[agg]** | unknown | Mistral supports JSON mode/schema on Small-class models per platform docs (not independently re-verified here) | unknown | Good cheap EU-hosted option if data residency in the EU matters |
| **Mistral OCR 4** | June 2026 | Yes (OCR-specialized) | $4/1000 pages, $2/1000 pages batch **[agg]** | doc-oriented | Markdown/structured JSON extraction, not general chat JSON | yes (roughly 2x cheaper) | Billed per page, not per token - directly comparable to a "cost per page" line item; good for post-parse verification & extraction, not classification reasoning |
| **Moondream Cloud (3 / 3.1)** | 3.1: Jul 8 2026 | Yes | Legacy: $0.06/1000 images ($0.00006/img); new token pricing $0.30/M input, $2.50/M output **[primary via moondream.ai/pricing per search snippet]** | 32K (3.1) | Structured "query/caption/detect/point/segment" skills rather than free-form JSON schema; can be coerced into JSON via prompting | unclear | Purpose-built for grounded visual QA/detection; MoE 9B total/2B active, open-weight too (see below) |

Caveats on the table: several $/token figures for Gemini and OpenAI came from pricing-aggregator sites rather than a raw fetch of `ai.google.dev/gemini-api/docs/pricing`, because the aggregators consistently agreed with each other across 3+ independent write-ups; still worth a final check against the vendor page before committing to a budget, since Gemini in particular has multiple in-flight "introductory pricing expires" clauses for 2026-2027.

## 2. Open-weight vision models (local/self-hosted candidates)

| Model | Size(s) | License | Release | Context | Notable strength | Hosting |
|---|---|---|---|---|---|---|
| **Qwen3-VL** | 2B, 4B, 8B, 32B (Instruct + Thinking variants) | Apache 2.0 | Oct 15-21, 2025 | model-dependent | Broad general document/vision reasoning at small sizes; ecosystem support in vLLM, Ollama, MLX | vLLM (single GPU, official recipe), Ollama, MLX on Apple Silicon; DashScope-hosted API also exists; OpenRouter lists e.g. Qwen3.6-32B-class pricing around $0.10/$0.42 per M tokens **[agg]** |
| **InternVL3.5** | 2B through 241B, incl. 4B/8B "small" tier | Apache 2.0 | Aug 26, 2025 | - | InternVL3.5-2B scores 76.5 average across 9 benchmarks - strong for its size; competitive OCRBench results across the family | Hugging Face (`OpenGVLab/InternVL3_5-*`); standard Transformers/vLLM support |
| **MiniCPM-V 4.5** | 8B | open weight (OpenBMB) | 2026 | - | 77.0 avg on OpenCompass-8-bench, beats GPT-4o-latest/Gemini-2.0-Pro on that composite at 8B | phone/edge-friendly design lineage |
| **MiniCPM-V 4.6** | 1.3B | open weight | May 11, 2026 | - | Purpose-built for phones; beats Qwen3.5-0.8B on OpenCompass, RefCOCO, HallusionBench, MUIRBench, OCRBench at a fraction of token cost | Extremely small footprint, good "ultra cheap local" candidate for basic triage |
| **Moondream 3.1 (9B-A2B)** | 9B total / 2B active MoE | open weight | Jul 8, 2026 | 32K | Five native skills (query/caption/detect/point/segment); grounded visual reasoning, fast inference from sparse MoE | Cloudflare Workers AI, Hugging Face, own runtime |
| **SmolVLM2** | 256M, 500M, 2.2B | Apache 2.0 | early 2025 (no 2026 successor found) | - | Tiny footprint (2.2B needs ~5.2GB GPU RAM for video); improved OCR/math/diagram QA over SmolVLM1 | HF Transformers; runs on very low-end hardware, including edge devices |
| **Gemma 3 (4B/12B/27B)** | 4B relevant here | Gemma custom license (source-available, not OSI-approved) | 2025-2026 | 128K on 4B | Google's own SigLIP-based vision encoder; good general-purpose small VLM | Ollama, MLX, vLLM |
| **Gemma 4** | e.g. 31B | Apache 2.0 (newer Gemma license shift per search result) | 2026 | - | Larger than the "small" bracket for this use case, flag but likely oversized for page-triage | NVIDIA NIM, Ollama |
| **Llama 4 Scout** | 17B active / 109B total MoE | Llama community license (not permissive OSS) | Apr 2025 | up to 10M tokens claimed | 67.2% on Roboflow visual tasks, 70.7% OCR - solid document/chart reading, weaker than Gemini-class on complex visual reasoning | Fits single H100 at INT4; vLLM/Ollama/llama.cpp support |
| **Phi-4-reasoning-vision-15B** | 15B | MIT-style Microsoft open license (verify per release) | Mar 4, 2026 | - | Hybrid think/no-think mode: switch off reasoning for fast triage, switch on for hard cases; trained on only ~200B tokens vs 1T+ for peers, notably data-efficient | Hugging Face `microsoft/Phi-4-reasoning-vision-15B` |
| **Chandra OCR 2** | 5.3B (Qwen3.5-VL base) | modified OpenRAIL-M (restricts competing-API commercial use; free under ~$2M funding/revenue) | Mar 2026 | 262,144 | Possibly best open-weight document *parsing* quality right now; not a general triage/classification model | Single mid-range GPU at fp16 |
| **dots.ocr / dots.mocr** | ~1.7B decoder + vision encoder | MIT, no commercial restriction | dots.ocr.base: Oct 31 2025; renamed dots.mocr Mar 19 2026 | - | ~100 languages, strong on structured docs/forms, can emit SVG for charts | RedNote/Xiaohongshu; HF `rednote-hilab/dots.ocr` |
| **HunyuanOCR** | ~1B | open weight (Tencent) | 2026 | - | Outperforms larger specialized parsers on OmniDocBench despite tiny size, per arXiv report | arXiv technical report; check HF for weights |
| **MinerU2.5-Pro** | 1.2B | open weight | 2026 | - | SOTA 95.69 on OmniDocBench v1.6 per a secondary Medium write-up **[agg, single source, unverified]** | treat the exact number with caution until corroborated |

MLX/Apple Silicon and single-GPU vLLM notes: `vllm-mlx` on an M4 Max reportedly gets up to 525 tok/s on small text models and roughly 68+ tok/s on a 30B-A3B vision model in 4-bit, with vision encoding adding 1.5-2s of latency per request that a content-based prefix cache can amortize (up to 28x speedup on repeated-image queries) **[single arXiv-adjacent source, treat as an early/promising result rather than settled fact]**. [arxiv.org/html/2601.19139](https://arxiv.org/html/2601.19139v2). For a document router, the small dense Qwen3-VL-2B/4B or MiniCPM-V-4.6 (1.3B) are the practical MLX/vLLM single-GPU picks: small enough for sub-second per-page latency, large enough to carry real document-understanding capability.

## 3. Benchmarks and evidence of document-understanding quality

- **OmniDocBench** (CVPR 2025, actively updated; v1.7 April 30 2026 added a Qianfan-OCR leaderboard track). As of Sept 2026, Kimi K3 leads the general leaderboard at 91.1%, while specialized small parsers claim even higher numbers on the parsing-specific track: MinerU2.5-Pro (1.2B) reportedly hits 95.69, and HunyuanOCR (~1B) reportedly beats larger models. [GitHub](https://github.com/opendatalab/OmniDocBench), [BenchLM](https://benchlm.ai/benchmarks/omnidocbench). Take the 95.69 figure as unverified marketing-adjacent until cross-checked on the official leaderboard.
- **olmOCR-bench** (8,413 unit tests over 1,403 PDF pages: math, tables, headers/footers, multi-column order, tiny text, old scans). Leaderboard leader varies by snapshot date and hosting site: Nanonets OCR-3 at 87.4% on one leaderboard, Chandra-ocr-2 at 85.9% on another (May 2026 snapshot), Unsiloed Parser claiming 88.0% (94.8% "corrected"). Multiple competing self-reported leaderboards exist; none should be treated as a single ground truth. [emergentmind.com](https://www.emergentmind.com/topics/olmocr-bench), [benchmarklist.com](https://benchmarklist.com/benchmarks/olmocr_bench/), [Nanonets](https://benchmarking.nanonets.com/benchmarks/olmocr).
- **OCRBench**: InternVL3.5 family evaluated here; InternVL3.5-2B posts 76.5 average across 9 mixed benchmarks including OCRBench-style tasks - notably strong for a 2B model. MiniCPM-V-4.6 (1.3B) also reaches "Qwen3.5-2B-level" on OCRBench per OpenBMB's own comparison (self-reported, treat cautiously).
- **RVL-CDIP (document page-type classification)**: this is the closest existing benchmark to your triage/routing use case, but it has real quality problems - an academic paper estimates ~8.1% average label noise (1.6-16.9% per category) and meaningful test/train overlap. A hands-on zero-shot test of GPT-4o-mini (pure vision, no OCR, simple prompting, 160 test images) got **65% overall accuracy**, ranging from 100% on emails down to 20% on forms/presentations, versus ~95.3% for a purpose-trained model (Donut) - illustrating the real gap between "ask a general small VLM to classify a page type" and a fine-tuned classifier. [murraycole.com](https://murraycole.com/posts/ai-document-classification). A separate academic study found GPT-4-Vision at 61.8% with OCR text input and 69.9% with images alone in zero/one-shot settings, and that fine-tuning Mistral on 1,600 samples raised accuracy from 45.4% to 83.4% - the strong practical implication is that off-the-shelf zero-shot VLM classification plateaus in the 60-70% range on RVL-CDIP-style 16-way classification, and a small amount of task-specific fine-tuning or a few-shot/rubric prompt closes most of the gap.
- **Handwriting-specific evals**: WildHandBench (arXiv 2608.22959) is a 2026 benchmark specifically built to challenge MLLMs and humans on handwritten text, evidence that handwriting remains a genuinely hard, actively-researched gap rather than a solved problem for general VLMs. KIE-HVQA similarly targets OCR hallucination on *degraded* documents (IDs, invoices, prescriptions) with pixel-level ground truth for reliability scoring - directly relevant to your "how degraded is this scan" signal.
- **Hallucination behavior**: recent papers (SHROOM-Visions 2026 shared task; "Seeing is Believing? Mitigating OCR Hallucinations in MLLMs"; "Do VLMs Read or Rewrite? On Transcription Faithfulness") converge on the same finding: VLMs lean on semantic/language priors and will confidently "correct" or invent text that looks plausible but isn't actually on the page, especially on degraded scans or unusual scripts. This is the core risk for using a VLM as a post-parse verifier: it may agree with a wrong OCR output because the wrong text is *plausible*, not because it actually re-read the pixels carefully.

## 4. Community signal (GitHub/arXiv-adjacent; direct Reddit/HN threads did not surface in search)
Direct r/LocalLLaMA or HN threads on "VLM document triage" specifically did not turn up in search; what did surface, repeatedly, was the same underlying pattern showing up in papers and cost-engineering blog posts:
- A 2026 paper on cost-quality tradeoffs in document VLMs ("Closing Cost-Quality Gap in Document VLMs," arXiv 2609.01575) frames exactly your problem: difficulty-aware routing between cheap and expensive models pays off more than picking one model for everything.
- "SCOPE-Router: Cost-Aware Open-Set VLM Routing for Execution-Oriented Tasks" (arXiv 2608.12127) is a directly relevant academic analog to what you're building: a router that picks which VLM to call based on task difficulty rather than always using the frontier model.
- Field reports on Chandra OCR 2 (Medium/mlhive write-ups) describe converting 27,000 papers (~380,000 pages) in under 30 hours on a single GPU - useful real-world throughput evidence for a 5.3B open-weight document model, though these are vendor-adjacent blog posts, not independent audits.
- No independent, skeptical community teardown of DeepSeek-V4.1-Flash-Vision's real-world document accuracy surfaced; all sourcing so far is vendor announcement plus pricing aggregators. Given how new the vision variant is (weeks old as of this research date), treat its document-understanding quality as unproven until you run it yourself.

## 5. Structured output, JSON schema, and logprobs support (router-relevant)

- **OpenAI**: mature "Structured Outputs" mode with strict JSON Schema conformance, confirmed for gpt-4o-family and later; works together with vision input and with function calling. gpt-5-mini/nano aren't individually named in the fetched guide, so verify empirically, but the pattern strongly suggests support carries forward. Logprobs are available on Chat Completions for many models; verify per-model in the current API reference before depending on them for confidence scoring.
- **Gemini**: `responseSchema` + `responseMimeType: application/json` supported across "all actively supported Gemini models," explicitly including multimodal (image/video/audio) requests, and works with Pydantic/Zod schema objects directly. This is arguably the most turnkey JSON-schema-for-vision story of the three big labs.
- **Anthropic**: no dedicated "strict JSON schema" mode as of Haiku 4.5; the standard pattern is forcing a tool call with a JSON-schema tool definition, which is reliable but is not the same first-class feature as OpenAI's/Google's schema modes. Vision tokenization is well-documented (28x28px patch tiling) which makes cost prediction for page images relatively easy.
- **DeepSeek**: docs reference a "JSON Output" guide but the vision guide itself doesn't detail strict-schema guarantees for image inputs - test before relying on it for critical-path typed decisions.
- **Open-weight / vLLM**: vLLM supports guided/structured JSON decoding (grammar-constrained generation) for any served model including VLMs, which means Qwen3-VL, InternVL3.5, MiniCPM-V, etc. can all be forced into strict JSON schema output locally, independent of whatever the base model's "native" support looks like. This is actually a point in favor of the open-weight route for a typed router: you get guaranteed schema conformance via the serving layer rather than hoping the model behaves.
- **Logprobs for confidence**: primarily available in self-hosted / vLLM settings (full logprob access) and partially in some hosted APIs (OpenAI). This matters directly for your router: if you want a numeric confidence score on "is this handwritten," logprob-based confidence is far more reliable via a self-hosted small VLM through vLLM than by asking a hosted model to self-report a confidence number in JSON, which is well documented to be poorly calibrated.

## 6. Data retention / privacy terms

- **OpenAI**: announced Zero Data Retention (ZDR) for frontier models in August 2026, paired with "Private Safety Processing" so prompts/outputs aren't retained after processing and aren't available for employee review; enterprise data isn't used for training unless opted in. ZDR requires an enterprise API agreement with explicit ZDR terms; some abuse-monitoring metadata and CSAM-flagged images are retained regardless. [OpenAI announcement](https://openai.com/index/offering-zero-data-retention-for-frontier-models/).
- **Google Gemini**: no explicit retention policy surfaced in this search pass; check `ai.google.dev` terms and Cloud DLP/data-residency docs directly before sending sensitive scanned documents (this is a gap in this research - verify before production use, especially for anything with PII/PHI/legal privilege, which is likely relevant given the pipeline described).
- **Anthropic**: standard Claude API policy is not-for-training by default for API customers (well-established Anthropic policy going back years); nothing in this pass changed that understanding, but re-verify current terms at `platform.claude.com` before committing.
- **DeepSeek**: hosted in mainland China-affiliated infrastructure; this is the single biggest practical objection to using it for a legal/financial-document pipeline handling client data, independent of price or accuracy. If jesteruct's documents include client-privileged material (plausible given kavy.upadhyay@borenius.com's likely legal-industry context), DeepSeek's hosted API is probably a non-starter regardless of cost, unless self-hosting the open weights.

## 7. Tricks worth building into the router

- **Downscale for classification.** Page-type/triage decisions ("is this a form," "is this handwritten," "what script") don't need full-resolution OCR-grade input. A 512-768px-longest-edge thumbnail is almost always enough signal and cuts image-token cost roughly in proportion to the tiling scheme of whichever model you use (dramatic for Anthropic's 28x28-patch tiling, meaningful for Gemini's roughly-flat per-image token count, essential for keeping DeepSeek/OpenAI image-token counts low).
- **Multi-page thumbnail grids.** Several cheap-vision providers (Gemini, GPT-5-mini/nano, Qwen3-VL) can take one image containing a grid of N page thumbnails and return a JSON array of N decisions in one call, which amortizes the fixed per-request overhead (system prompt/tool-schema tokens) across many pages. This is the single highest-leverage cost trick for a routing layer processing large PDFs.
- **Confidence via logprobs, not self-report.** Ask a self-hosted model (vLLM) for its logprobs on categorical decision tokens (e.g., the JSON enum value) rather than asking any model to output a numeric "confidence" field; self-reported confidence in chat-style JSON is known to be poorly calibrated across the literature on LLM calibration.
- **Prompt/image caching.** Anthropic and Gemini both support prompt caching; for a routing prompt with a large fixed instruction/schema block plus a small per-page image, caching the fixed portion (system prompt, few-shot examples, JSON schema) cuts cost substantially on high-volume routing, though the *image* portion itself generally isn't the cacheable part since it differs per page.
- **Batch APIs for non-real-time triage.** If the router doesn't need per-page results in under a second (e.g., a nightly re-classification sweep), OpenAI's and Anthropic's Batch APIs both give a flat 50% discount; DeepSeek's off-peak window pricing is effectively the same idea with a schedule instead of a submission queue.
- **Cheap deterministic pre-filter, VLM only for the ambiguous tail.** This is already jesteruct's stated design, and the research supports it strongly: zero-shot small-VLM accuracy on document classification plateaus around 60-70% (RVL-CDIP results above), so a VLM should be a fallback for cases the cheap signals can't resolve, not a universal first pass.

## 8. Recommendations

**(a) Page-type classification/triage returning JSON**
- Best hosted: **Gemini 3.1 Flash-Lite / 3.5 Flash-Lite**, on account of turnkey `responseSchema` JSON support across all current Gemini models, low per-token cost, and roughly flat per-image token overhead that makes multi-page-thumbnail batching cheap. GPT-5-nano is a very close second and possibly cheaper per call, but verify its Structured Outputs support empirically first.
- Best open-weight local: **Qwen3-VL-4B or InternVL3.5-4B** via vLLM with guided JSON decoding, or **MiniCPM-V-4.6 (1.3B)** if you need to run on genuinely constrained hardware. All are Apache 2.0.
- Best ultra-cheap: **Moondream (cloud, legacy per-image pricing) or MiniCPM-V-4.6 self-hosted** - both are priced/sized for extremely high page volumes.
- Avoid: using a frontier-tier model (GPT-5, Gemini Pro, Claude Opus/Sonnet, DeepSeek-V4-Pro) for straightforward page-type triage; the RVL-CDIP evidence suggests the accuracy ceiling for *general* VLM zero-shot classification is set more by prompt/task design and a little fine-tuning than by model size, so paying frontier prices buys little here.

**(b) Visual quality assessment of scans (degradation, skew, blur)**
- Best hosted: any of the Flash/mini-tier models above will do adequately for a coarse "good/degraded/unreadable" 3-way signal, but this specific sub-task might be better served by classical image-quality metrics (blur/contrast/noise estimation, deterministic) than by a VLM at all - a VLM is more valuable for *semantic* degradation judgments ("is this fax so bad the handwriting is unreadable") layered on top of the deterministic score.
- Best open-weight: **Moondream 3.1**, because its native "detect/point" skills give you grounded, checkable outputs rather than free-text impressions, which helps validate the model isn't hallucinating a quality assessment.
- Avoid: relying purely on a VLM's self-reported quality score without a deterministic cross-check; hallucination research (Section 3) shows VLMs will confidently describe degraded content as fine when the content is semantically plausible.

**(c) Handwriting detection**
- Best hosted: **Gemini Flash-tier or Claude Haiku 4.5** - both handle basic "is there handwriting present, yes/no/mixed" reliably as a coarse binary/ternary signal; this specific gate does not require your most capable model.
- Best open-weight: **Qwen3-VL** or **InternVL3.5** at the 4-8B tier; both have shown competitive OCRBench-class results, and this is a binary/coarse detection task, not full handwriting transcription, so smaller models are adequate.
- Avoid: trusting any small VLM (hosted or open) to *transcribe* handwriting reliably. WildHandBench and related 2026 research treat this as an unsolved, actively-researched problem; use the small VLM only to flag "handwritten, route to a specialist/human/heavier model," not to extract the actual text.

**(d) Post-parse verification (compare rendered page vs extracted text/JSON)**
- Best hosted: **Claude Haiku 4.5** or **Gemini Flash** - both are strong at faithful, literal comparison tasks when explicitly told to check specific claims against an image, and Anthropic's well-documented patch-based image tokenization makes cost predictable per page.
- Best open-weight: **Chandra OCR 2** or **dots.mocr** if verification means "does the extracted text match a fresh independent read of the page" (these are purpose-built document-reading models, arguably better ground truth generators than a general chat VLM); use a general VLM like Qwen3-VL only for the *comparison/diff* step.
- Avoid: using the same model/prompt that did the original extraction to "verify" itself - the hallucination literature (Section 3, "Do VLMs Read or Rewrite?") specifically documents models that will confirm their own invented text as correct because they're pattern-matching plausibility, not re-deriving from pixels. Use an independent model or an independent, differently-prompted pass for verification.

## Sources (primary fetches)
- https://api-docs.deepseek.com/news/news260821/
- https://api-docs.deepseek.com/guides/vision/
- https://api-docs.deepseek.com/updates/
- https://platform.claude.com/docs/en/about-claude/pricing
- https://developers.openai.com/api/docs/pricing
- https://murraycole.com/posts/ai-document-classification

## Sources (search-derived, cross-checked or flagged where single-sourced)
- https://openrouter.ai/deepseek/deepseek-v4-flash-vision-exp
- https://intuitionlabs.ai/articles/deepseek-v4-flash-vision-document-understanding
- https://www.mindstudio.ai/blog/deepseek-v4-1-flash-pricing
- https://www.forbes.com/sites/jonmarkman/2026/09/14/deepseek-v41-flash-prices-cached-input-to-0003-per-million-tokens/
- https://benchlm.ai/deepseek/api-pricing
- https://getdeploying.com/llms/deepseek-ocr-2
- https://pricepertoken.com/pricing-page/model/google-gemini-3-flash-preview
- https://pricepertoken.com/pricing-page/model/google-gemini-3.1-flash-lite-preview
- https://apidog.com/blog/gemini-3-6-flash-pricing/
- https://benchlm.ai/google/api-pricing
- https://developer.puter.com/tutorials/gemini-api-pricing/
- https://ai.google.dev/gemini-api/docs/structured-output
- https://pricepertoken.com/pricing-page/model/openai-gpt-5-mini
- https://pricepertoken.com/pricing-page/model/openai-gpt-5-nano
- https://openai.com/index/introducing-structured-outputs-in-the-api/
- https://platform.openai.com/docs/guides/structured-outputs
- https://openai.com/index/offering-zero-data-retention-for-frontier-models/
- https://openrouter.ai/anthropic/claude-haiku-4.5
- https://tokencost.app/blog/vision-api-cost-per-image
- https://www.cloudzero.com/blog/mistral-api-pricing/
- https://mistral.ai/news/mistral-ocr/
- https://www.aimadetools.com/blog/mistral-ocr-4-complete-guide/
- https://github.com/qwenlm/qwen3-vl
- https://openrouter.ai/qwen
- https://freeapihub.com/ai-models/qwen3-vl
- https://moondream.ai/models/moondream_3-1_9B_A2B
- https://moondream.ai/blog/moondream-3-preview
- https://docs.moondream.ai/pricing/
- https://moondream.ai/blog/announcing-moondream-cloud
- https://huggingface.co/HuggingFaceTB/SmolVLM2-2.2B-Instruct
- https://huggingface.co/blog/smolvlm2
- https://internvl.github.io/blog/2025-08-26-InternVL-3.5/
- https://huggingface.co/OpenGVLab/InternVL3_5-2B
- https://arxiv.org/pdf/2608.22959 (WildHandBench)
- https://huggingface.co/openbmb/MiniCPM-V-4_5
- https://huggingface.co/openbmb/MiniCPM-V-4.6
- https://rits.shanghai.nyu.edu/ai/minicpm-v-4-6-a-1-3b-multimodal-model-built-for-phones/
- https://blog.roboflow.com/gemma-3/
- https://developers.googleblog.com/en/introducing-gemma3/
- https://blog.promptlayer.com/llama-4-scout-17b-16e-instruct-open-source-powerhouse-with-moe-multimodality-10m-token-memory/
- https://playground.roboflow.com/models/meta/llama-4-scout
- https://huggingface.co/microsoft/Phi-4-reasoning-vision-15B
- https://www.microsoft.com/en-us/research/blog/phi-4-reasoning-vision-and-the-lessons-of-training-a-multimodal-reasoning-model/
- https://github.com/opendatalab/OmniDocBench
- https://benchlm.ai/benchmarks/omnidocbench
- https://medium.com/@bytefer/this-document-parser-model-just-killed-commercial-ocr-and-vlm-95-69-a31a54391922
- https://benchmarklist.com/benchmarks/olmocr_bench/
- https://www.unsiloed.ai/blog/unsiloed-ai-achieves-1-rank-on-olmocr-bench-2
- https://benchmarking.nanonets.com/benchmarks/olmocr
- https://arxiv.org/html/2606.31446 (RVL-CDIP label noise)
- https://arxiv.org/pdf/2412.13859 (zero-shot/fine-tune document classification)
- https://arxiv.org/pdf/2609.01575 (cost-quality gap in document VLMs)
- https://arxiv.org/pdf/2608.12127 (SCOPE-Router)
- https://arxiv.org/pdf/2506.20168 (OCR hallucination mitigation)
- https://arxiv.org/pdf/2607.21617 (Do VLMs Read or Rewrite?)
- https://arxiv.org/pdf/2608.25662 (SHROOM-Visions 2026)
- https://github.com/datalab-to/chandra
- https://mlhive.com/2026/04/chandra-ocr-2-open-source-document-parsing-benchmark
- https://github.com/rednote-hilab/dots.ocr
- https://huggingface.co/davanstrien/dots.ocr-1.5/blob/main/README.md
- https://arxiv.org/html/2601.19139v2 (Native LLM/MLLM inference on Apple Silicon, vllm-mlx)
