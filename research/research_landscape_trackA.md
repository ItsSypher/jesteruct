# Track A: 2026 Document-Parsing / OCR Tool Landscape - Research Notes

Compiled 2026-09-23. All claims sourced inline; anything I could not verify with a citable
source is marked **UNVERIFIED**. Several sources are low-quality SEO/content-farm blogs
(explainx.ai, tech-insider.org, enterprisedna.co, digitalapplied.com, aiproductivity.ai,
checkthat.ai, xpay.sh, codesota.com, imagetotable.ai) that publish suspiciously specific
"2026 verdict" numbers with no primary source. I've flagged those as **LOW-CONFIDENCE
SOURCE** rather than citing their numbers as fact, and cross-checked against official
vendor pages, GitHub/HF READMEs, and arXiv papers wherever possible.

---

## 1. Tool Landscape

### MinerU (2.x / 2.5 / 2.5-Pro / 3.4)
- Two operating modes: **pipeline** (classic multi-model layout+OCR+formula+table pipeline,
  speed-first, stable defaults) and **VLM backend** (single VLM decodes the whole page,
  higher fidelity on complex layout/tables/formulas but slower). MinerU 3.4 exposes five
  backends: `pipeline`, `hybrid-engine`, `vlm-engine`, `hybrid-http-client`, `vlm-http-client`.
  [knightli.com](https://knightli.com/en/2026/06/26/mineru-34-backend-modes-pipeline-hybrid-vlm/)
- Reported pipeline-backend throughput ~0.54 pages/sec at 72.7% (older benchmark run) vs.
  VLM backend scoring higher accuracy but slower — **LOW-CONFIDENCE SOURCE** (aggregated
  blog claim, exact benchmark/version unclear). [ivugangingo.com](https://ivugangingo.com/2026/07/25/datalab-marker-v2-vs-mineru-docling-and-liteparse-benchmark-breakdown/)
- MinerU 2.6-2.7 (Oct 2025-Feb 2026) added a hybrid pipeline+VLM backend, MLX acceleration
  for Apple Silicon (+100-200% speed), and upgraded to PP-OCR-v5 OCR models (+40% accuracy
  claimed) — **LOW-CONFIDENCE SOURCE**, but plausible given official changelog exists.
  [Changelog](https://opendatalab.github.io/MinerU/reference/changelog/), [GitHub Releases](https://github.com/opendatalab/MinerU/releases)
- **MinerU2.5-Pro** (1.2B) is the current flagship pipeline model: arXiv:2604.04771
  "Pushing the Limits of Data-Centric Document Parsing at Scale." On OmniDocBench v1.6 it
  scores **Overall 95.75, TextEdit 0.036, Formula CDM 97.45, Table TEDS 93.42, TEDS-S 95.92,
  ReadOrder 0.120** (per HPD-Parsing paper's comparison table, arXiv:2607.18839 Table 1).
  Inference: 1890.3 TPS / 1.58 PPS at BS=512 (same source, Table 2).
- MinerU is trained/used as an annotation source for other 2026 papers (WeVisDoc, HPD-Parsing
  use MinerU2.5-Pro output as pseudo-labels), evidence it's treated as a strong reference
  parser industry-wide in 2026.
- Weaknesses: GitHub issue #4128 - "Pipeline backend incorrectly merges multi-line table
  columns into a single flattened row" [github.com/opendatalab/MinerU/issues/4128](https://github.com/opendatalab/MinerU/issues/4128).
  Community reports MinerU2.5 (pipeline) fails to reconstruct cross-page table structure and
  sometimes drops embedded images — see Community section.

### PaddleOCR-VL / PP-StructureV3
- **PaddleOCR-VL-1.5** (0.9B), open-sourced 2026-01-29: 94.5% on OmniDocBench v1.5, claimed
  to beat general VLMs and other specialized parsers on that benchmark; adds irregular-shaped
  bounding-box localization for scanning/skew/warping/screen-photo/illumination robustness.
  [pub.towardsai.net](https://pub.towardsai.net/paddleocr-vl-1-5-a-deep-dive-into-the-0-9b-model-that-outperforms-gpt-4o-on-document-parsing-c93bac97ac1f), arXiv:2601.21957.
- **PaddleOCR-VL-1.6**, open-sourced 2026-05-28: 96.3% new SOTA on OmniDocBench v1.6, also new
  SOTA on v1.5 and Real5-OmniDocBench. On the HPD-Parsing comparison table it scores
  **Overall 96.3, TextEdit 0.032, CDM 97.5, TEDS 94.8, TEDS-S 97.11, ReadOrder 0.127** —
  the single highest "pipeline" score reported by any paper I found (arXiv:2607.18839 Table 1).
  Inference throughput 1533.8 TPS / 1.25 PPS at BS=512.
- PP-StructureV3 remains the classical (non end-to-end-VLM) layout+table+formula pipeline
  underneath PaddleOCR; actively maintained alongside the VL series but I could not find a
  distinct 2026 PP-StructureV3-only benchmark number separate from PaddleOCR-VL.
  [paddleocr.ai PP-StructureV3 docs](http://www.paddleocr.ai/main/en/index.html)
- Weaknesses reported in GitHub issues: table structure not recognized in some layouts
  (issue #11892), Markdown vs JSON table output diverging (issue #17894), false extra empty
  columns detected and header cells lost in complex tables, and PaddleOCR-VL fails to
  reconstruct cross-page table continuity (see Community section).
  [PaddlePaddle/PaddleOCR#11892](https://github.com/PaddlePaddle/PaddleOCR/issues/11892), [#17894](https://github.com/PaddlePaddle/PaddleOCR/issues/17894)

### dots.ocr (rednote-hilab / dots-studio)
- Single VLM (~1.7-3B) doing joint layout detection + content recognition, strong on
  multilingual/low-resource-language documents. Claims SOTA on OmniDocBench for text, table,
  and reading order among specialized models, with formula recognition "comparable to much
  larger models like Doubao-1.5 and Gemini 2.5 Pro."
  [GitHub](https://github.com/rednote-hilab/dots.ocr), [HF](https://huggingface.co/rednote-hilab/dots.ocr)
- OmniDocBench v1.5 scores (per BenchmarkList aggregation): Overall 88.41, TextEdit 0.048,
  Formula CDM 83.22, Table TEDS 86.78, TEDS-S 90.62, ReadOrder 0.053.
  [benchmarklist.com](https://benchmarklist.com/models/rednote-hilab-dots-ocr/)
- On OmniDocBench v1.6 (HPD-Parsing Table 1, "Unified" category): Overall 90.77, TextEdit
  0.048, CDM 89.95, TEDS 87.18, TEDS-S 90.58, ReadOrder 0.138 — notably behind the newer
  pipeline-style models (MinerU2.5-Pro, PaddleOCR-VL-1.6) but still competitive among
  end-to-end unified parsers.
- Known bug (official repo docs): continuous special characters (ellipses `...`, underscores)
  can cause the model to loop/repeat output indefinitely; workaround is switching prompt mode
  (`prompt_layout_only_en`, `prompt_ocr`, `prompt_grounding_ocr`).
  [dots.ocr blog.md](https://github.com/rednote-hilab/dots.ocr/blob/master/assets/blog.md)

### olmOCR (Allen AI), v2 and later
- **olmOCR 2** (olmOCR-2-7B-1025), released ~Oct 2025, trained with RLVR/GRPO "unit test
  rewards" specifically to improve math equations, tables and tricky OCR cases.
  [Ai2 blog](https://allenai.org/blog/olmocr-2), arXiv:2510.19817.
- Scores **82.4** on olmOCR-Bench, up from 78.5 in the prior release, with gains "across every
  document category." [Ai2 on X](https://x.com/allen_ai/status/1981029163394797618)
- On OmniDocBench v1.6 (HPD-Parsing Table 1, unified category): Overall 85.74, TextEdit 0.139,
  CDM 88.10, TEDS 83.00, TEDS-S 87.17, ReadOrder 0.216 — one of the weaker ReadOrder scores
  among unified models, suggesting multi-column reading-order is a relative weak point.
- Uses dynamic temperature scaling (0.1 up to 0.8) at inference specifically to break
  repetition loops when the model fails to emit an EOS token — an explicit, documented
  mitigation for a known hallucination/loop failure mode.
  [arxiv.org/html/2510.19817v1](https://arxiv.org/html/2510.19817v1)
- Available via API on DeepInfra, Parasail, Cirrascale; weights in FP8 and full precision on
  HF. [allenai/olmOCR-2-7B-1025](https://huggingface.co/allenai/olmOCR-2-7B-1025)
- A third-party ("Unsiloed AI") claims #1 rank on olmOCR-Bench with their own system —
  **UNVERIFIED**, self-reported vendor claim. [unsiloed.ai blog](https://www.unsiloed.ai/blog/unsiloed-ai-achieves-1-rank-on-olmocr-bench-2)

### DeepSeek-OCR and successor
- **DeepSeek-OCR** (Oct 2025): "Contexts Optical Compression" — renders long text as an image
  and decodes it with a VLM to compress context; 97% decode accuracy at 10x compression,
  ~60% at 20x compression. arXiv:2510.18234, [GitHub](https://github.com/deepseek-ai/DeepSeek-OCR).
- **DeepSeek-OCR-2**, released 2026-01-27: new "DeepEncoder V2" with "Causal Visual Flow"
  replacing rigid raster-scan ordering with dynamic semantics-aware segment reordering;
  needs 256-1,120 visual tokens per page; scored 91.09% on OmniDocBench v1.5 (+3.73pp over
  v1) — **LOW-CONFIDENCE SOURCE** for the exact figure (aggregated blog), but direction
  confirmed by arXiv-cited papers. [intuitionlabs.ai](https://intuitionlabs.ai/articles/deepseek-ocr-optical-compression)
- Independently confirmed via HPD-Parsing's OmniDocBench v1.6 comparison table: DeepSeek-OCR-2
  (3B-A0.5B MoE) scores Overall 90.25, TextEdit 0.050, CDM 91.84, TEDS 83.89, TEDS-S 87.75,
  ReadOrder 0.144; very high inference throughput (2932.1 TPS / 2.05 PPS at BS=512) due to
  visual-token compression — among the fastest unified models tested. (arXiv:2607.18839 Table 2)
- A cited "successor lineage" from Baidu called **Unlimited OCR** (3B-A0.5B) builds on a
  DeepSeek-OCR checkpoint and adds "Reference Sliding Window Attention" (R-SWA) to bound the
  KV cache for long multi-page documents in one forward pass — confirmed independently by
  both the HPD-Parsing paper (arXiv:2607.18839, ref [20]) and WeVisDoc (arXiv:2609.20423),
  which both cite it as a genuine paper/model, not just a blog claim. It scores Overall 93.92
  on OmniDocBench v1.6 (TextEdit 0.042, CDM 95.79, TEDS 90.16, TEDS-S 93.32, ReadOrder 0.129)
  and 2901.5 TPS / 2.03 PPS. This is a different, more solid citation than the WebSearch
  snippet I originally got ("GOT-OCR's successor is Baidu's Unlimited-OCR") — that specific
  lineage claim (i.e., that it succeeds GOT-OCR rather than DeepSeek-OCR) is **UNVERIFIED**.

### Mistral OCR (3, 4, 4.1)
- **Mistral OCR 3**: earlier 2026 release. [mistral.ai/news/mistral-ocr-3](https://mistral.ai/news/mistral-ocr-3/)
- **Mistral OCR 4**: announced 2026-06-23 per official Mistral post — adds bounding boxes,
  block classification, inline confidence scores, 170-language support; deploys as a single
  container on customer infrastructure; claims 72% win rate in blind head-to-head evals vs.
  competing systems, and "roughly 8x lower cost and 17x lower latency" than leading agentic
  parsers on a chart/figure-dense financial QA set at equivalent accuracy.
  [mistral.ai/news/ocr-4](https://mistral.ai/news/ocr-4/)
- **Mistral OCR 4.1**: GA/Premier release 2026-07-16, current generation in the model catalog.
  [Multiple secondary sources report this; treat exact date as LOW-CONFIDENCE SOURCE but the
  4.1 designation itself is corroborated across several independent write-ups.]
- Pricing: **$4/1,000 standard pages, $5/1,000 annotated pages** via API for OCR 4.1
  (50% batch-API discount reduces standard pages to ~$2/1,000). Document AI (agentic
  extraction) priced separately at $5/1,000 pages. [cloudprice.net](https://cloudprice.net/models/mistral-ocr), official mistral.ai pricing pages.
- On the OmniDocBench v1.5 leaderboard (nanonets aggregation), smaller Mistral models score
  much lower than the flagship OCR product: Ministral-8B 78.3, Mistral Small 4 76.4,
  Pixtral-12B 42.3 — these are general open Mistral VLMs, not the hosted OCR API product, so
  they are not directly comparable to "Mistral OCR 4" scores, which Mistral does not appear
  to have submitted to the open OmniDocBench leaderboard. **Gap**: no independent OmniDocBench
  number exists for Mistral OCR 4/4.1 itself — its accuracy claims are vendor-benchmarked only.

### Nanonets-OCR (OCR2, OCR2-Plus, OCR-3)
- Nanonets-OCR2 (3B): trained on 3M+ pages spanning invoices, tax forms, handwriting, charts,
  equations, flowcharts, org charts, multilingual docs; converts printed/handwritten math to
  LaTeX. [nanonets/Nanonets-OCR2-3B on HF](https://huggingface.co/nanonets/Nanonets-OCR2-3B)
- Nanonets-OCR2-Plus: #1 on the IDP-Leaderboard (idp-leaderboard.org), average score 81.16
  across Nanonets-KIE, DocILE, and Handwritten-Forms datasets.
  [GitHub NanoNets/docext](https://github.com/NanoNets/docext)
- **Nanonets OCR-3** appears as the actual top model on the OmniDocBench v1.5 leaderboard I
  scraped (see Benchmarks section): Overall 90.0, second place behind Gemini-3-Flash (90.1),
  and Nanonets OCR2+ close behind at 89.5 — this is a very strong, verifiable result since it
  comes directly from the OmniDocBench-affiliated leaderboard, not a vendor blog.
  [benchmarking.nanonets.com/benchmarks/omnidocbench](https://benchmarking.nanonets.com/benchmarks/omnidocbench)
  (Note: Nanonets runs this leaderboard itself, so some house-brand advantage bias is
  possible, but the benchmark methodology and full model list, including many
  non-Nanonets frontier models scoring above/near it, is public.)

### Qwen-VL family for OCR (Qwen3-VL, Qwen3.5)
- Qwen3-VL-235B-A22B (MoE flagship) evaluated on OCR-Bench, OCRBench_v2, CC-OCR, and
  OmniDocBench in its technical report (arXiv:2511.21631).
- On OmniDocBench v1.6 (HPD-Parsing Table 1, general VLM category): Qwen3-VL-235B scores
  Overall 89.78, TextEdit 0.063, CDM 92.55, TEDS 83.07, TEDS-S 86.75, ReadOrder 0.166 —
  strong for a general-purpose (non document-specialized) VLM, but still behind sub-1B
  dedicated parsers like PaddleOCR-VL-1.6 (96.3) and GLM-OCR (95.22).
- Smaller Qwen3.5 variants (9B/4B/2B/0.8B) score much lower on OmniDocBench v1.5 (76.7, 67.6,
  48.7, 47.3 respectively per the Nanonets leaderboard) — a big cliff below the ~0.9-4B
  specialized OCR models, showing document-parsing skill doesn't transfer well down the size
  ladder for general-purpose Qwen checkpoints.
- Base Qwen-VL-OCR (older/legacy model) is the weakest entry on the current OmniDocBench v1.5
  leaderboard at 34.1 overall — a useful "don't use this" baseline for a router.
- Roboflow's community ranking piece: "Best Open-Source OCR Models in 2026, Ranked by
  Benchmark" [blog.roboflow.com](https://blog.roboflow.com/best-open-source-ocr-models/) — a
  useful secondary source but treat specific numbers there as **LOW-CONFIDENCE SOURCE**
  pending direct verification against OmniDocBench.

### GOT-OCR (2.0) and lineage
- GOT-OCR2.0 (2024 original): "General OCR Theory," unified end-to-end OCR-2.0 model
  targeting formatted-text recognition (equations, tables, music sheets, geometric diagrams,
  multi-column academic papers). arXiv:2409.01704, [GitHub](https://github.com/Ucas-HaoranWei/GOT-OCR2.0)
- I could not find a credible, arXiv-backed direct "GOT-OCR successor" model launched in
  2026 by the original GOT-OCR authors (StepFun/UCAS team). The "successor is Baidu's
  Unlimited-OCR" claim from one blog search snippet does **not** match what the primary
  papers say (they trace Unlimited OCR's lineage from DeepSeek-OCR, not GOT-OCR) — marking
  that specific claim **UNVERIFIED/likely incorrect**.
- Blog-level claims that "GOT-OCR 2.0 is the best choice for maximum accuracy on complex
  documents... as of April 2026" are **LOW-CONFIDENCE SOURCE** and contradicted by the fact
  that GOT-OCR2.0 does not appear at all in the 2026 OmniDocBench leaderboards or in the
  HPD-Parsing/WeVisDoc/FinixDoc comparison tables — by 2026 it reads as effectively
  superseded/legacy relative to PaddleOCR-VL, MinerU2.5-Pro, dots.ocr, DeepSeek-OCR-2, etc.

### Unstructured.io (hi_res / fast / ocr_only / auto)
Confirmed directly from official docs:
[docs.unstructured.io/api-reference/how-to/choose-partitioning-strategy](https://docs.unstructured.io/api-reference/how-to/choose-partitioning-strategy)
- **fast**: default strategy; extracts embedded text directly, works well for
  non-image-embedded-text documents; no CV model.
- **hi_res**: treats every page as an image, runs a layout-detection CV model (currently
  `layout_v1.0.0`) to find tables/columns/complex layout; necessary for scanned PDFs and
  complex layouts; 5-10x slower than fast.
- **ocr_only**: runs the document through Tesseract.
- **auto** (routing logic): if the file is an image → use hi_res. If it's a PDF → check for
  embedded tables/images; if none found → use fast (no CV model); if at least one embedded
  table or image is found → use hi_res.
This is directly useful as a reference "routing layer" design pattern: Unstructured's own
`auto` mode is essentially a cheap structural heuristic (presence of embedded images/tables)
gating between a fast text-extraction path and an expensive CV/layout path — a similar
two/three-tier gating design likely fits this project's own router.

### LlamaParse
- **LlamaParse v2**: major update replacing manual "mode" selection with four pricing/quality
  tiers: **Fast, Cost Effective, Agentic, Agentic Plus**.
  [llamaindex.ai/blog/introducing-llamaparse-v2](https://www.llamaindex.ai/blog/introducing-llamaparse-v2-simpler-better-cheaper)
- Pricing: Cost-effective tier ~$0.00375/page; Agentic Extract tier ~$0.01875/page; general
  credit system where 1,000 credits = $1.25.
  [developers.llamaindex.ai/llamaparse/general/pricing](https://developers.llamaindex.ai/llamaparse/general/pricing/)
- LlamaIndex published **ParseBench** in June 2026: 2,078 human-verified pages, 1,211
  enterprise documents (insurance/finance/government), 90+ pipelines scored across 5
  dimensions. LlamaParse Agentic scored **84.88** overall, ranking #1 — but this benchmark
  was designed, curated, and scored by LlamaIndex itself evaluating its own product, and I
  found no independent replication. Treat the #1 ranking as vendor-self-reported.
  [makefun.ai cost calculator references ParseBench tiers](https://makefun.ai/llamaparse-auto-mode-agentic-parse-credit-cost-calculator/)

### Reducto
- Maintains **RD-TableBench**, an open benchmark (human-labeled, partially public) for
  complex tables, multilingual content, and handwriting.
- Reducto also authored **ParseBench** (arXiv:2604.08538) — note this appears to be a
  *different* ParseBench than LlamaIndex's own internal one of the same name; worth
  disambiguating carefully if reused downstream.
- Reported: "Reducto's standard mode scored 88.5% overall" on an unspecified benchmark; on
  some corpora "Extend Parse 2.0 led Reducto Standard by 7.2 points and Reducto Agentic by
  4.6 points" — i.e., a competitor (Extend) beats Reducto on at least some evaluations,
  per Extend's own comparison page — **LOW-CONFIDENCE SOURCE** (competitor-authored).
  [llms.reducto.ai/reducto-vs-google-document-ai](https://llms.reducto.ai/reducto-vs-google-document-ai), [extend.ai/resources](https://www.extend.ai/resources/extend-vs-reducto-document-ai-comparison)
- Reducto announced a "frontier parsing model" at **1 cent/page** around 2026-09-01 (per
  Morningstar/PR Newswire syndication) — press release, **LOW-CONFIDENCE SOURCE** for
  independent accuracy verification, but pricing claim is a primary company announcement.
  [morningstar.com PR Newswire item](https://www.morningstar.com/news/pr-newswire/20260901sf37626/reducto-unveils-a-frontier-parsing-model-that-makes-the-worlds-hardest-documents-ai-ready-for-1-a-page)
- micro1's **LongExtractionBench** (June 2026): 225 documents, avg 358 pages, ~88,700
  ground-truth leaf values; measures precision/recall/leaf-accuracy on long table-heavy
  extraction — good candidate benchmark for a routing layer that needs to test long-document
  behavior specifically (silent omission vs. invented rows).

### Cloud baselines: Azure Document Intelligence, Google Document AI, AWS Textract
- Textract has "historically had a slight edge on handwriting recognition, though that gap
  has narrowed" — general industry consensus claim, **LOW-CONFIDENCE SOURCE** for the
  specific framing, but directionally consistent across several 2026 comparison posts.
- One head-to-head cited: **Google Document AI 74.8%** vs **AWS Textract 71.2%** on
  handwritten-content accuracy — **LOW-CONFIDENCE SOURCE** (single blog, no methodology
  given, could not verify independently).
- Azure Document Intelligence supports handwriting recognition in 9 languages (English,
  French, German, Italian, Japanese, Korean, Portuguese, Spanish, Simplified Chinese).
- General consensus across multiple 2026 comparison posts: all three cloud OCR baselines are
  "insufficient for production workflows with legally/financially significant handwritten
  fields without a custom fine-tuned model or human-in-the-loop layer," with real-world
  production accuracy commonly landing at 80-95% vs. 95-99% advertised on curated benchmark
  sets — this is a recurring, cross-source theme even though individual numbers are
  low-confidence.
- Google Document AI 2026 update: new Gemini-backed layout parser models —
  `pretrained-layout-parser-v1.6-2026-01-13` (Gemini 3 Flash-powered, Preview) and
  `pretrained-layout-parser-v1.6-pro-2025-12-01` (Gemini 3 Pro-powered, Preview) — this is
  from Google's own official release notes, high confidence.
  [docs.cloud.google.com/document-ai/docs/release-notes](https://docs.cloud.google.com/document-ai/docs/release-notes)

### New 2026 entrants (beyond the above)
Found via targeted arXiv search, several credible 2026 document-parsing model papers beyond
the ones explicitly requested:
- **GLM-OCR** (Zhipu AI), 0.9B, "best-in-class table and math formula recognition" per
  community summary; strong OmniDocBench v1.6 score of **95.22** Overall in the HPD-Parsing
  table (CDM 97.18, TEDS 92.83, TEDS-S 95.39) — but notably it scores very poorly on the
  *v1.5* leaderboard for table structure (TEDS 37.4! TEDS-S 39.3, per the Nanonets v1.5
  table) despite decent Overall (69.2) — a big inconsistency between v1.5 and v1.6 table
  scores for the same model family that's worth independent verification before trusting it
  for table-heavy routing. [zai-org/GLM-OCR on HF](https://huggingface.co/zai-org/GLM-OCR)
- **FireRed-OCR** (arXiv:2603.01840): 2B unified parser, OmniDocBench v1.6 Overall 93.26.
- **Qianfan-OCR** (Baidu, arXiv:2603.13398): 4B unified end-to-end model, OmniDocBench v1.6
  Overall 93.90.
- **Logics-Parsing-v2** (arXiv reference in HPD-Parsing table): 4B, Overall 93.33.
- **HunyuanOCR-1.5** (Tencent, arXiv:2607.04884): 1B, Overall 94.74, TEDS 93.67/94.71 —
  strong table numbers relative to its size; explicitly optimized for speed via a
  "DFlash"-adapted parallel draft-generation decoding scheme.
- **OvisOCR2** (arXiv:2607.13639) and **MonkeyOCRv2** (arXiv:2607.11562): additional 2026
  entrants; MonkeyOCR-pro-3B appears in HPD-Parsing's table at Overall 88.57.
- **Jina-OCR-v1** (arXiv:2609.03181): built for low-budget/consumer GPUs, compressed-vision
  encoder + 3B MoE decoder with speculative decoding, aimed at cheap self-hosted deployment.
- **Youtu-Parsing** (Tencent, cited across multiple 2026 papers): pipeline-style parser using
  query/token-level parallelism for region-wise recognition; scores very well on tables
  specifically — Overall 93.74, **TEDS 92.02, TEDS-S 95.00** (best table score of any
  pipeline model in the HPD-Parsing comparison table) but is also the *slowest* — only
  315.4 TPS / 0.39 PPS at BS=512, by far the lowest throughput of any model in that table.
  This is a genuinely useful "high table accuracy, low throughput" data point for a routing
  layer that has to trade off speed vs. table fidelity.
- **HPD-Parsing** (arXiv:2607.18839, PaddlePaddle/Baidu team): not a new "product" so much
  as a new *decoding paradigm* — Hierarchical Parallel Decoding, which forks page-layout
  decoding into concurrent per-block content-decoding branches with a lightweight
  main-layout coordinator, plus "Progressive Multi-Token Prediction." At only 1B params it
  reaches OmniDocBench v1.6 Overall 94.91 while achieving **4,752 TPS / 2.68 PPS at BS=512**
  — 2.62x the throughput of the fastest prior model and 3.06x the vanilla autoregressive
  baseline, with the efficiency advantage growing with document length (up to 18x fewer
  decoding steps, 3.67x throughput, 5.8x lower single-request latency on the longest-output
  bucket). This looks like the most throughput-relevant new technique for a
  latency-sensitive router to know about, even though it isn't (yet) a shipped product.
- **WeVisDoc** (Tencent WeChat Vision, arXiv:2609.20423): 2B/4B end-to-end parsers built on
  Qwen3-VL-Instruct, using a two-stage "coverage then capability" data curation method.
  WeVisDoc-4B: OmniDocBench v1.6 Overall **95.38** (highest reported among directly-compared
  end-to-end/unified parsers in that paper), and it introduces **PureDocBench**, a
  three-track robustness benchmark (Clean / Digital / Real-degraded) — WeVisDoc-4B's mean
  Avg3 PureDocBench score is 75.54, "ranking first among compared end-to-end parsers in all
  four settings," with Stage II (capability-aware data refinement) giving the largest single
  gain (+4.03 points) specifically on the *Real Degraded* track — i.e., their targeted
  refinement helps robustness to real-world degradation more than it helps clean-page scores.
  [Project page](https://tencent.github.io/WeVisDoc), [GitHub](https://github.com/Tencent/WeVisDoc)
- **FinixDoc / FinixDoc-VL** (Ant Group, arXiv:2608.22842): 4B financial-document specialist
  built on Qwen3-VL-4B, notable for (a) explicitly naming and designing around a
  "Document Parsing Capability Matrix" (document quality x document scale) with four zones:
  Benchmark-Converged, Low-Quality, Underexplored Large-Scale, and Ambiguous-Unrecoverable;
  (b) a "better omission than error" design principle for the Ambiguous-Unrecoverable zone,
  i.e., explicitly engineering the model to prefer silence over hallucinated financial
  numbers; (c) homoglyph-aware contrastive learning specifically to reduce visually-similar
  character confusions (e.g. "1" vs "l", amount/ID-number digit swaps) common in financial
  documents; (d) a split-then-merge strategy for ultra-large pages that exceed a single VLM
  forward pass. On their own FinixDocBench, FinixDoc-VL scores **81.43** overall (macro-avg
  of FinixDigital/FinixPhoto/FinixInner), beating the next-best open-source baseline by 5.13
  points, with the largest gain on internal financial workflows (FinixInner: 84.08 vs.
  78.73 for the next best, which appears to be a large general Qwen3.5-397B/Qwen3-VL-235B
  model based on the chart). This paper is the strongest evidence I found that
  general-purpose large VLMs (235B+) can out-robust smaller document-specialist models
  specifically in the "Low-Quality Zone" (blurry, camera-captured, real-world financial
  scans) even though the specialists win on clean benchmark pages — directly relevant to a
  routing layer design: document *quality/degradation* may matter more than document *type*
  for choosing a big general VLM vs. small specialist.

---

## 2. Benchmarks

### OmniDocBench v1.5 — live leaderboard (scraped 2026-09-23)
Source: [benchmarking.nanonets.com/benchmarks/omnidocbench](https://benchmarking.nanonets.com/benchmarks/omnidocbench)
(v1.5, 1,355 pages: papers/books/slides/exams/newspapers/magazines; Overall =
((1-TextEdit)*100 + TableTEDS + FormulaCDM)/3)

Top 15 of 29 evaluated models (Overall / TextEdit↓ / CDM↑ / TEDS↑ / TEDS-S↑ / ReadOrder↓):

| # | Model | Overall | TextEdit | CDM | TEDS | TEDS-S | ReadOrder |
|---|---|---|---|---|---|---|---|
| 1 | Gemini-3-Flash | 90.1 | 0.077 | 90.2 | 87.7 | 92.6 | 0.081 |
| 2 | Nanonets OCR-3 | 90.0 | 0.068 | 87.7 | 88.9 | 93.3 | 0.100 |
| 3 | Nanonets OCR2+ | 89.5 | 0.056 | 90.3 | 79.1 | 83.6 | 0.090 |
| 4 | Gemini-3-Pro | 88.8 | 0.078 | 87.3 | 87.0 | 91.7 | 0.084 |
| 5 | GPT-5.2 | 88.0 | 0.111 | 90.1 | 84.9 | 89.5 | 0.098 |
| 6 | Claude Sonnet 4.6 | 86.9 | 0.165 | 90.2 | 87.1 | 91.2 | 0.149 |
| 7 | Claude Opus 4.6 | 85.9 | 0.151 | 88.5 | 84.4 | 89.1 | 0.136 |
| 8 | Datalab Marker | 85.5 | 0.109 | 88.3 | 79.1 | 83.7 | 0.106 |
| 9 | Gemini 3.1 Pro | 85.3 | 0.082 | 83.3 | 80.8 | 85.4 | 0.073 |
| 10 | GPT-5.4 | 85.3 | 0.089 | 83.4 | 81.3 | 86.7 | 0.077 |
| 11 | Qwen3-VL-Plus | 82.5 | 0.157 | 76.6 | 86.6 | 90.7 | 0.099 |
| 13 | Qwen3-VL-235B | 81.9 | 0.162 | 75.1 | 86.8 | 90.6 | 0.101 |
| 19 | GLM-OCR | 69.2 | 0.144 | 84.7 | 37.4 | 39.3 | 0.141 |
| 29 | Qwen-VL-OCR | 34.1 | 0.823 | 22.6 | 62.1 | 67.7 | 0.810 |

Notable pattern: on this v1.5 cut, closed frontier models (Gemini 3 Flash, Nanonets OCR-3/2+,
GPT-5.x, Claude 4.x) dominate the top of the table, ahead of open specialized parsers.
This *contradicts* the framing in some other sources (e.g. a Roboflow-style "dedicated OCR
models occupy many of the top positions" claim referencing PaddleOCR-VL 96.34%/MinerU2.5-Pro
95.75%/GLM-OCR 95.22% at the top) — those higher numbers are from OmniDocBench **v1.6**, not
v1.5, and the two leaderboards are not directly comparable (different page sets / harder v1.6
revision). **Be careful not to conflate v1.5 and v1.6 numbers** — I've kept them separated
throughout this document. GLM-OCR is the clearest example: 69.2 Overall on v1.5 vs. 95.22 on
v1.6, driven almost entirely by table TEDS collapsing from 92.83 (v1.6) to 37.4 (v1.5) —
strongly suggests GLM-OCR's table-structure recognition is brittle/version-sensitive and
should be validated directly rather than trusted from either number alone.

### OmniDocBench v1.6 — comparison table from HPD-Parsing paper (arXiv:2607.18839, Table 1)
This is the most complete single side-by-side table I found spanning General VLMs,
Specialized-Pipeline, and Specialized-Unified categories (see full detail already inlined
above in Section 1). Category-level takeaways:
- **Best table structure (TEDS)**: Youtu-Parsing (92.02) and PaddleOCR-VL-1.6 (94.8) lead;
  HunyuanOCR-1.5 (93.67) close behind despite being only 1B.
- **Best formula (CDM)**: PaddleOCR-VL-1.6 (97.5), MinerU2.5-Pro (97.45), HPD-Parsing (97.28).
- **Best text (TextEdit, lower better)**: Ovis2.6-30B-A3B (0.035, general VLM), PaddleOCR-VL-1.6
  (0.032), MinerU2.5-Pro (0.036) — general large VLMs can match/beat specialists on raw text
  edit distance, but lag badly on reading order and often on table/formula.
- **Best reading order (lower better)**: Gemini 3 Pro (0.165) and Ovis2.6-30B-A3B (0.135)
  among general VLMs; MinerU2.5-Pro (0.120) and HPD-Parsing (0.124) among specialists —
  reading-order remains one of the harder categories even for top models; olmOCR (0.216) and
  Nanonets-OCR-s (0.213) are comparatively weak here among unified specialists.
- **Fastest at scale (TPS/PPS, BS=512)**: HPD-Parsing itself (4752 TPS / 2.68 PPS) >
  DeepSeek-OCR-2 (2932/2.05) ≈ Unlimited OCR (2901/2.03) > GLM-OCR (2134/1.86) >
  MinerU2.5-Pro (1890/1.58) > PaddleOCR-VL-1.6 (1534/1.25) >> Youtu-Parsing (315/0.39, slowest
  despite best table TEDS — a clear accuracy/throughput tradeoff outlier worth flagging for
  a routing layer).

### Real5-OmniDocBench (arXiv:2603.04205, v2 revised 22 Jun 2026)
"A Full-Scale Physical Reconstruction Benchmark for Robust Document Parsing in the Wild."
Performs a full one-to-one physical reconstruction of *all 1,355* OmniDocBench v1.5 images
across five real-world degradation scenarios: **Scanning, Warping, Screen-Photography,
Illumination, Skew**. Key finding (from abstract): VLMs that look "near-perfect" on clean
digital OmniDocBench show a large, previously-hidden "reality gap" once the same content is
physically reconstructed and re-captured under these five conditions — the paper's whole
point is that clean-benchmark scores are not a reliable proxy for real-world scanned/
photographed document performance. I could not extract the actual per-model, per-scenario
score table from the abstract/HTML view (would need the PDF body); the abstract itself is
the strongest citable claim: "the reality gap in document parsing is far from closed."
Authors are from PaddlePaddle/Baidu (Cheng Cui et al.), same team behind PaddleOCR-VL, which
explains why PaddleOCR-VL-1.6's marketing claims "new SOTA on Real5-OmniDocBench" specifically.
[arxiv.org/abs/2603.04205](https://arxiv.org/abs/2603.04205)

### HPD-Parsing (arXiv:2607.18839) — see Section 1, full detail already captured above.
Key non-accuracy finding: decoder latency, not vision-encoder latency, dominates VLM OCR
inference cost, and grows roughly linearly with output length under standard autoregressive
decoding — "for samples with long outputs, decoding can take nearly 500x longer than visual
encoding." This is a structurally important fact for a routing layer's cost model: page
*content density* (how much text/table content is on the page, i.e., expected output token
count) predicts inference cost far better than input image resolution/token count alone.

### WeVisDoc (arXiv:2609.20423) — see Section 1. Introduces PureDocBench (Clean/Digital/Real
tracks) as a robustness benchmark distinct from OmniDocBench; useful second robustness
benchmark alongside Real5-OmniDocBench for routing-layer degradation testing.

### FinixDoc / FinixDocBench (arXiv:2608.22842) — see Section 1. FinixDocBench has four
subsets: FinixDigital, FinixPhoto (camera-captured), FinixInner (internal workflow docs), and
FinixHuge (ultra-large pages, evaluated separately under a system-level protocol). Numbers
from Figure 1 of the paper (main score = macro-avg of FinixDigital/FinixPhoto/FinixInner):
FinixDoc-VL 81.43 > next-best open model ~76.3 > ... down to Qwen3-VL-4B ~65-67 range.
On FinixPhoto specifically (camera-captured, the hardest/most realistic subset), absolute
scores drop into the 54-67 range across all evaluated models (vs. 86-93 on FinixDigital) —
a very large, well-documented quality-degradation cliff (roughly 25-35 points) that's a
strong, citable, quantified argument for why a router needs a distinct "camera-captured /
low-quality" branch separate from "born-digital PDF."

### Parser-Oriented Structural Refinement (arXiv:2604.02692)
A layout-interface stabilization module inserted between a DETR-style layout detector and
the downstream content parser, to fix "unstable layout hypotheses" (retained-instance-set
inconsistency) that cause severe downstream parsing errors on dense/overlapping-region pages.
Reports **Reading Order Edit of 0.024** on OmniDocBench when integrated into a standard
end-to-end pipeline — notably lower (better) than any ReadOrder score in the HPD-Parsing
comparison table (best there was 0.120, MinerU2.5-Pro), though it's unclear if this is the
same OmniDocBench version/subset, so treat as encouraging but not directly comparable.
[arxiv.org/abs/2604.02692](https://arxiv.org/abs/2604.02692)

### Handwriting-specific benchmarks
- **aimultiple "Handwriting Recognition Benchmark with 14 LLMs & OCRs"**: average handwriting
  OCR accuracy across tools ~64% aggregate; print-style handwriting 10-15% higher accuracy
  than cursive; mixed styles hardest. [aimultiple.com/handwriting-recognition](https://aimultiple.com/handwriting-recognition) — **LOW-CONFIDENCE SOURCE** for exact
  percentages (methodology not independently verified) but a widely-cited industry benchmark.
- Cursive-specific 100-sample/10-writer test: Gemini 3 Pro Preview "achieved a perfect
  score," DeepSeek-OCR 79%; GPT-5, Gemini 3 Pro, olmOCR-2-7B-1025-FP8 rank as top performers
  by semantic similarity — **LOW-CONFIDENCE SOURCE** (small n=100 sample, single blog).
- **IAM benchmark**: frontier VLMs now top the leaderboard — GPT-5 ~1.22% CER, with Claude
  Opus 4.7 and Gemini 3 also near the top — **LOW-CONFIDENCE SOURCE** for the exact CER figure.
- **WildHandBench** (arXiv:2608.22959): "A Benchmark for Handwritten Text Understanding that
  Challenges MLLMs and Humans" — exists and is a credible 2026 academic handwriting benchmark,
  but I did not extract per-model numbers from it (title/existence only, would need a follow-up
  scrape of the PDF body for actual scores).
- **OmniHandwritingOCR** (arXiv:2608.18586): "Diagnostic Benchmark for Evaluating Multimodal
  LLMs in Handwritten OCR Scenarios" — exists, same caveat (title/abstract only, no scores
  extracted).
- Google Cloud Vision handwriting on English cursive: independent estimates ~70-75% general,
  better on clear print-style — **LOW-CONFIDENCE SOURCE**.

### Other 2026 arXiv papers on document parsing found along the way (not explicitly requested
but relevant to a router design)
- **MDPBench** (arXiv:2603.28130) and **MORE** (arXiv:2607.02956): multilingual document
  parsing benchmarks — relevant if the pipeline needs non-English/non-Chinese coverage.
- **PP-OCRv6** (arXiv:2606.13108): "From 1.5M to 34.5M Parameters, Surpassing Billion-Scale
  VLMs on OCR Tasks" — a tiny classical (non-VLM) OCR model claiming to beat billion-parameter
  VLMs on some OCR tasks; potentially very relevant as an ultra-cheap first-tier router option
  for simple/clean text pages where a full VLM is overkill.
- **RAGOCR** (arXiv:2608.00765): optical compression specifically for RAG-oriented text
  retrieval via visual representation — adjacent technique to DeepSeek-OCR's approach, aimed
  at retrieval rather than transcription.
- **GlotOCR Bench** (arXiv:2604.12978): "OCR Models Still Struggle Beyond a Handful of Unicode
  Scripts" — important caveat for any router assuming broad language coverage; most SOTA
  numbers above are English/Chinese-centric.
- **RealDocBench** (arXiv:2606.07401) and **LongExtractionBench** (micro1, June 2026,
  referenced via Reducto): both focused on field-level QA / structured extraction fidelity
  on long, real-world regulated documents — closer to the "downstream extraction accuracy"
  concern than pure OCR/parsing fidelity.
- **MinerU-Popo** (arXiv:2605.24973): "Universal Post-Processing Model for Structured
  Document Parsing" — a post-processing correction layer, potentially relevant as a
  cheap accuracy-boosting stage after any base OCR/parsing tool in a pipeline.

---

## 3. Community Reports (failure modes, real-world complaints)

### Hallucination — general
- Academic framing (arXiv:2607.24077, "When Low CER is Not Enough," Uruguayan historical
  archive study, ICDAR 2026 workshop, revised through Sep 2026): VLM-based OCR systems beat
  traditional OCR on CER/WER but hide "systematic failure modes invisible to standard
  metrics," including orthographic normalization, spurious content generation, and semantic
  substitutions that preserve fluency while altering meaning — with named-entity errors
  singled out as most dangerous because they "introduce substantial semantic distortions with
  minimal impact on CER and WER." This is a strong, citable academic source directly
  supporting the general concern that "the model can look right on aggregate metrics while
  being wrong on the exact numbers/names a routing/extraction pipeline actually cares about."
  [arxiv.org/abs/2607.24077](https://arxiv.org/abs/2607.24077)
- Hacker News, "LLM based OCR is a disaster, great potential for hallucinations and no
  estimate of confidence. Results might seem promising but you'll always be wondering."
  (user deadbabe, on the Mistral OCR launch thread, HN item 43283483). A reply from user
  utkarshphirke: "we tried estimating LLM confidence and the results are not great. Any
  process that requires reliability will struggle with LLM OCR." Another reply (menaerus)
  counters that classical CNN-based OCR also hallucinates and this is "a problem solved with
  domain specific post-processing." A third reply (leumon) notes traditional OCR already had
  this exact problem historically: Xerox scanners in ~2013 were found to silently alter
  numbers in scanned documents by default (a well-known real incident, referenced here as
  informal corroboration that this is not a new, LLM-only failure mode).
  [news.ycombinator.com/item?id=43283483](https://news.ycombinator.com/item?id=43283483)
- General industry framing repeated across multiple 2026 sources: "generative OCR shifts the
  core risk from misrecognition to hallucination," and production deployments needing >97%
  accuracy find this a hard bar to clear without hybrid fallback to strict/classical OCR for
  critical fields (e.g., dollar amounts, IDs). [photes.io OCR trend piece](https://photes.io/blog/posts/ocr-research-trend) — **LOW-CONFIDENCE SOURCE** for the framing, but consistent
  with the FinixDoc paper's explicit "better omission than error" design principle above,
  which is a much stronger, primary-source echo of the same concern.

### Repetition-loop failures (a specific, well-documented hallucination subtype)
- **dots.ocr**: continuous special characters (ellipses, underscores) can trigger infinite
  output repetition; official mitigation is switching prompt templates.
  [dots.ocr blog.md](https://github.com/rednote-hilab/dots.ocr/blob/master/assets/blog.md)
- **olmOCR**: documented and mitigated at the framework level via dynamic temperature scaling
  (0.1→0.8) specifically to recover from repetition loops when EOS generation fails.
  [arxiv.org/html/2510.19817v1](https://arxiv.org/html/2510.19817v1)
- A related but distinct Ollama-ecosystem bug report: "[Bug]: OCR failures ('token repeat
  limit reached') caused by Ollama prompt-cache collisions across different images" —
  [github.com/vorojar/Folio-OCR/issues/12](https://github.com/vorojar/Folio-OCR/issues/12) —
  this is a deployment/serving-stack bug rather than a model-quality issue, but worth noting
  since it can masquerade as a model hallucination/repetition problem when it's actually a
  KV-cache/prompt-cache bug in the serving layer.

### Table structure errors (merging/splitting)
- **MinerU** GitHub issue #4128: "Pipeline backend incorrectly merges multi-line table
  columns into a single flattened row," losing original column structure.
  [github.com/opendatalab/MinerU/issues/4128](https://github.com/opendatalab/MinerU/issues/4128)
- Community-reported comparison (via search aggregation, exact source thread not directly
  scraped but consistent across multiple hits): "MinerU's reading order and recognition
  accuracy decrease with complex layouts, primarily because it incorrectly merges multiple
  columns during recognition," "PaddleOCR-VL falsely detects an extra empty column and loses
  header cells," and "both MinerU2.5 and PaddleOCR-VL failed to restore the complete
  structure of cross-page tables" — **LOW-CONFIDENCE SOURCE** for exact wording/attribution,
  but directionally corroborated by the two concrete GitHub issues below.
- **PaddleOCR** GitHub issue #11892: "Table structure not recognized."
  [github.com/PaddlePaddle/PaddleOCR/issues/11892](https://github.com/PaddlePaddle/PaddleOCR/issues/11892)
- **PaddleOCR** GitHub issue #17894: "Extracted Table from PDF to Markdown is different from
  one in JSON" — i.e., inconsistent table structure depending on output format requested,
  a subtle but real production gotcha (don't assume Markdown and JSON outputs agree).
  [github.com/PaddlePaddle/PaddleOCR/issues/17894](https://github.com/PaddlePaddle/PaddleOCR/issues/17894)
- Cross-page table continuity (a table that spans a page break) is repeatedly flagged as a
  weak point across multiple tools/sources — none of the mainstream open pipelines I found
  claim to solve this well; likely needs explicit multi-page-aware post-processing (see
  MinerU-Popo, arXiv:2605.24973, as a candidate for this).

### Handwriting failure cases
- Cursive consistently 10-15+ points worse than print-style handwriting across virtually
  every source reviewed (aimultiple aggregate benchmark, cloud-vendor comparison posts).
- Cloud OCR vendors (Textract/Document AI/Azure) explicitly flagged across multiple 2026
  comparison posts as "insufficient for production workflows with legally or financially
  significant handwritten fields without a custom fine-tuned model or human-in-the-loop
  review layer" — a recurring, consistent theme even though the underlying blog sources are
  individually low-confidence.
- DeepSeek-OCR notably underperforms frontier general VLMs on cursive specifically (79% vs.
  Gemini 3 Pro's reported "perfect score" on a small 100-sample cursive test) — suggests
  optical-compression-style OCR architectures may trade off worse on messy/ambiguous
  handwriting than they do on clean printed text, though this is from a small, low-confidence
  sample and should be validated on a bigger benchmark (e.g. WildHandBench,
  OmniHandwritingOCR) before being trusted for routing decisions.

### Speed / cost complaints
- Youtu-Parsing: best-in-class table TEDS but by far the slowest model benchmarked in the
  HPD-Parsing efficiency table (315 TPS vs. 1500-4750 TPS for others) — a concrete,
  quantified accuracy-vs-throughput tradeoff a router needs to model explicitly rather than
  assume "best accuracy" and "best throughput" tools are the same.
- HN commentary and general community sentiment (from search aggregation, not a single
  scraped thread): repeated complaints that LLM/VLM-based OCR pipelines are meaningfully more
  expensive and slower than classical OCR at scale, especially for long documents, which is
  exactly the failure mode HPD-Parsing's paper quantifies technically (decoder cost scaling
  ~linearly, sometimes worse, with output length, up to ~500x the vision-encoder cost for
  long outputs).
- Mistral's own OCR 4 marketing explicitly targets this complaint, claiming "~8x lower cost
  and ~17x lower latency" versus "leading agentic document parsers" at equivalent accuracy on
  a chart/figure-dense financial QA set — a vendor claim, but notable that cost/latency
  (not just accuracy) is the headline differentiator Mistral chose to market against.
  [mistral.ai/news/ocr-4](https://mistral.ai/news/ocr-4/)

---

## Gaps / things I could not verify
- No independent (non-vendor) OmniDocBench-style score exists for Mistral OCR 4/4.1 as a
  hosted product — its accuracy claims are all vendor-benchmarked.
- Could not extract per-scenario (Scanning/Warping/Screen-Photo/Illumination/Skew) numeric
  breakdown from Real5-OmniDocBench (arXiv:2603.04205) — only got the abstract; the PDF body
  would need a follow-up scrape for the actual degradation-factor attribution table.
- Could not find per-model scores for WildHandBench (arXiv:2608.22959) or
  OmniHandwritingOCR (arXiv:2608.18586) beyond their existence/abstracts.
- The claim "GOT-OCR's successor is Baidu's Unlimited-OCR" appears to be an incorrect/garbled
  lineage from one low-confidence blog aggregation; the primary-source papers (HPD-Parsing,
  WeVisDoc) consistently trace Unlimited OCR's lineage from DeepSeek-OCR instead. Flagged
  **UNVERIFIED / likely incorrect** above.
- Could not find a dedicated, separate 2026 PP-StructureV3 benchmark distinct from the
  PaddleOCR-VL numbers.
- GOT-OCR 2.0 itself has no 2026 OmniDocBench/leaderboard entry I could find — treat any
  claim that it's still "best for complex documents in 2026" as unverified marketing framing
  from secondary blogs, contradicted by its absence from every 2026 benchmark table reviewed.
