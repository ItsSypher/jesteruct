# Document Sorting/Routing Layer - Research Landscape (2026-09-23)

Combined notes from parallel Track A (parser/OCR landscape) and Track B (cheap triage/routing signals) research passes.

---

# TRACK A: Parser/OCR Landscape

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

---

# TRACK B: Cheap Triage Signals and Routing Techniques

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
