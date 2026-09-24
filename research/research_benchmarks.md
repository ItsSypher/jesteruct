# Benchmark datasets for unstructured document pipelines

Research compiled 2026-09-23.
Goal: find data for testing pipelines that ingest unstructured documents of mixed type and quality (born-digital, scanned, handwritten, photographed, degraded, malformed) and optionally feed RAG.

## Verification status

Every dataset in the Tier 1 and Tier 2 sections, plus the vendor benchmarks, was confirmed to exist on 2026-09-23 through the GitHub API or the Hugging Face API.
License values marked "(checked)" come from the repo license field or the HF `license:` tag, not from memory.
Everything else comes from subagent web research against dataset cards, READMEs and papers; treat those counts as likely but not re-checked.
Items marked "unverified" could not be confirmed.

## Recommended test ladder

1. Smoke test for format coverage: Unstructured example-docs + Docling test data.
2. Parsing accuracy: olmOCR-Bench, plus a slice of OmniDocBench.
3. Degradation robustness: PureDocBench (all three image versions of the same pages).
4. Forms, receipts and handwriting: FUNSD, SROIE, GNHK.
5. Schema extraction: ExtractBench.
6. RAG answer quality: OHR-Bench, MMLongBench-Doc.
7. Throughput and crash resistance: GovDocs1, PDF Association Stressful Corpus, UNSAFE-DOCS.

## Tier 1: start here

| Dataset | What it tests | Quality mix | License |
|---|---|---|---|
| [OmniDocBench](https://github.com/opendatalab/OmniDocBench) ([HF](https://huggingface.co/datasets/opendatalab/OmniDocBench)) | Full parsing: text, LaTeX formulas, HTML/LaTeX tables, reading order, boxes. About 1,650 pages, 10 doc types, EN/ZH | Born-digital, scanned, handwritten notes, `fuzzy_scan` attribute | Repo Apache-2.0 (checked); HF card has no license tag and a notice restricting use to research |
| [PureDocBench](https://github.com/zhihengli-casia/PureDocBench) (2026, [arXiv 2605.07492](https://arxiv.org/abs/2605.07492)) | Parsing on 1,475 pages rendered from HTML/CSS, so ground truth is exact. Each page in three versions: clean, digitally degraded, and photographed on a phone | Photocopy generations, fax/thermal, ink bleed, JPEG, lighting, geometric distortion | Data CC BY 4.0, code MIT (checked from README badges) |
| [olmOCR-Bench](https://huggingface.co/datasets/allenai/olmOCR-bench) | 1,403 PDFs, 7,010 pass/fail unit tests (presence, order, table cells). Cheap and easy to interpret | Born-digital arXiv plus genuine old scans, tables, multi-column, tiny text | ODC-By (checked) |
| [OHR-Bench](https://github.com/opendatalab/OHR-Bench) ([HF](https://huggingface.co/datasets/opendatalab/OHR-Bench)) | How OCR errors carry through into RAG answers. 8.5k PDF pages, 8.5k QA pairs, 7 domains, raw PDFs included | OCR noise at mild, moderate and severe levels | CC BY 4.0 (checked) |
| [ExtractBench](https://github.com/run-llama/ExtractBench) (2026) | Schema-guided JSON extraction with evidence. See the deep dive below | 134 scanned, 55 handwritten, 38 clean-versus-degraded pairs | Apache-2.0 code and data (checked) |

## Tier 2: end-to-end RAG on raw documents

- [MMLongBench-Doc](https://github.com/mayubo2333/MMLongBench-Doc): 135 long real PDFs (about 47.5 pages each), 1,091 expert questions. About 33% need several pages and 22.5% are deliberately unanswerable, which tests hallucination.
- [REAL-MM-RAG](https://huggingface.co/datasets/ibm-research/REAL-MM-RAG_FinReport) (IBM): four subsets (FinReport, FinSlides, TechReport, TechSlides), about 8k pages. The same questions are reworded several ways to test retrieval robustness. CDLA-Permissive-2.0 (checked).
- [ViDoRe V3](https://huggingface.co/blog/QuentinJG/introducing-vidore-v3): 10 datasets, 26k+ pages, 3k+ human-checked queries with bounding boxes and reference answers, 6 languages. Ships page images, not PDFs. License unverified.
- [MMDocIR](https://huggingface.co/datasets/MMDocIR/MMDocIR_Evaluation_Dataset): 313 long documents (average 65 pages, up to 843), 1,685 expert questions, answer locations at page and layout-element level. Apache-2.0 (checked).
- [UniDoc-Bench](https://huggingface.co/datasets/Salesforce/UniDoc-Bench) (Salesforce): 70k page images, 8 domains, 1,600 QA pairs, and a harness comparing text-only, image-only and fused retrieval. CC BY-NC 4.0 (checked), so non-commercial only.
- Others:
  - [DocVQA / MP-DocVQA](https://rrc.cvc.uab.es/?ch=17): scanned UCSF industry documents; the original terms are research-only.
  - [SlideVQA](https://huggingface.co/datasets/NTT-hil-insight/SlideVQA).
  - [TAT-DQA](https://huggingface.co/datasets/next-tat/TAT-DQA): financial table and text reasoning.
  - [FinanceBench](https://github.com/patronus-ai/financebench): only a 150-question sample is open.
  - [LongDocURL](https://github.com/dengc2023/LongDocURL).
  - [DUDE](https://github.com/duchallenge-team/dude): license unverified.
  - [M3DocVQA](https://github.com/bloomberg/m3docrag): Wikipedia pages rendered to PDF; license unverified.
  - [Vectara Open RAG Bench](https://huggingface.co/datasets/vectara/open_ragbench): arXiv PDFs; CC BY-NC 4.0 (checked).
  - [FinRAGBench-V](https://github.com/zhaosuifeng/FinRAGBench-V): Chinese and English, with visual citation.
- Poor fit, excluded: Docmatix (LLM-generated QA), CRAG (web and knowledge-graph sources, not documents), BRIGHT (text only).

## Tier 3: handwriting, scans, phone photos

These are full-page datasets unless noted; datasets of cropped lines or words are much less useful for pipeline testing.

Forms and receipts:
- [FUNSD](https://guillaumejaume.github.io/FUNSD/): 199 noisy scanned forms with entity and relation labels. Non-commercial.
- [XFUND](https://github.com/doc-analysis/XFUND): FUNSD-style forms in 7 languages. CC BY-NC-SA 4.0.
- [CORD](https://github.com/clovaai/cord): Indonesian receipts. CC BY 4.0.
- [SROIE](https://rrc.cvc.uab.es/?ch=13): 1,000 scanned receipts with 4-field key-information extraction.
- [WildReceipt](https://huggingface.co/datasets/Theivaprakasham/wildreceipt): 1,740 receipts with unseen templates.
- [DocILE](https://github.com/rossumai/docile): 6.7k real business documents plus about 1M unlabeled.
- [Kleister NDA / Charity](https://github.com/applicaai/kleister-nda): long multi-page documents, a mix of scanned and born-digital. License unverified.
- [NIST SD2 / SD6](https://www.nist.gov/srd/nist-special-database-2): hand-printed tax forms, fairly clean scans.

Handwriting:
- [IAM](https://fki.tic.heia-fr.ch/databases/iam-handwriting-database): 1,539 pages. Registration required, non-commercial.
- [GNHK](https://github.com/GoodNotes/GNHK-dataset): handwriting photographed on phones in the wild. CC BY 4.0.
- [RIMES](https://zenodo.org/records/10812725): French handwritten letters and faxes.
- [CVL](https://cvl.tuwien.ac.at/research/cvl-databases/an-off-line-database-for-writer-retrieval-writer-identification-and-word-spotting/): mixed print and handwriting. CC BY-NC 3.0.
- [NorHand](https://zenodo.org/records/6542056): Norwegian historical letters.
- Bentham / READ 2016 (via Transkribus).
- [HTR-United catalog](https://htr-united.github.io/catalog.html): an index of many historical handwriting sets.
- CROHME: handwritten math.

Real archival scans:
- [DocVQA / UCSF Industry Documents](https://rrc.cvc.uab.es/?ch=17): 1900 to 2018 typewriter, fax, stamps, handwriting.
- [RVL-CDIP](https://huggingface.co/datasets/aharley/rvl_cdip): 400k low-quality scans with class labels only. Known label noise and embedded PII.
- Tobacco-3482: documented label errors.
- [ICDAR 2019 cTDaR](https://github.com/cndplab-founder/ICDAR2019_cTDaR): handwritten historical tables.
- [Chronicling America](https://chroniclingamerica.loc.gov/ocr/) and American Stories: historical newspapers.

Camera capture and physical damage:
- DIR300 and DocUNet: warped phone photos with flat references.
- [UVDoc](https://github.com/tanguymagne/UVDoc): synthetic warps, for training only.
- [SmartDoc 2015 / SmartDoc-QA](http://smartdoc.univ-lr.fr/).
- [MIDV-2020](https://l3i-share.univ-lr.fr/MIDV2020/midv2020.html): ID cards.
- NoisyOffice (UCI): coffee stains and folds.
- DIBCO / H-DIBCO: binarization of degraded historical pages.
- [racineai/ocr-pdf-degraded](https://huggingface.co/datasets/racineai/ocr-pdf-degraded): synthetic degradation with per-image parameters. Apache-2.0 (checked).

## Tier 4: raw mixed-format corpora (no ground truth)

These are for format coverage, throughput and crash resistance.

- [Unstructured example-docs](https://github.com/Unstructured-IO/unstructured/tree/main/example-docs) + [Docling test data](https://github.com/docling-project/docling/tree/main/tests/data): small but broad. EML/MSG with attachments, ODT, RTF, odd encodings (UTF-16/32, ISO-8859-8), password-protected files, malformed files, a 1,200-page PDF. Best first smoke test.
- [GovDocs1](https://digitalcorpora.org/corpora/file-corpora/files/): about 1M files (PDF, DOC, XLS, PPT, HTML, images), 308GB, freely redistributable, on S3 or HTTPS.
- [NapierOne](https://registry.opendata.aws/napierone/): 44 file types with 5,000 files each, including modern Office formats and ransomware-encrypted variants.
- [PDF Association Stressful Corpus](https://pdfa.org/stressful-pdf-corpus/): about 32.5k PDFs from 35 bug trackers, 31GB.
- [Apache Tika regression corpus](https://corpora.tika.apache.org/base/packaged/pdfs/): about 3M mixed files.
- [UNSAFE-DOCS](https://digitalcorpora.org/corpora/file-corpora/unsafe-docs-cc-main-2021-31-unsafe/): about 5.3M deliberately malformed or malicious PDFs.
- [openpreserve format-corpus](https://github.com/openpreserve/format-corpus): govdocs1-error-pdfs (about 130k PDFs that broke tools) and pdfCabinetOfHorrors.
- [veraPDF corpus](https://github.com/veraPDF/veraPDF-corpus): PDF/A and PDF/UA conformance files with known pass or fail labels. The Isartor suite is usable but not redistributable.
- pdf.js `test/pdfs` and the pdfium test corpus: edge-case regression PDFs.
- [SafeDocs CC-MAIN-2021-31-PDF-UNTRUNCATED](https://digitalcorpora.org/corpora/file-corpora/cc-main-2021-31-pdf-untruncated/): about 8M full-length web PDFs (about 8TB). A realistic production mix.
- [pixparse/pdfa-eng-wds](https://huggingface.co/datasets/pixparse/pdfa-eng-wds) (about 2.1M PDFs) and [pixparse/idl-wds](https://huggingface.co/datasets/pixparse/idl-wds) (UCSF industry documents; heavily scanned, faxes, handwriting).
- [FinePDFs](https://huggingface.co/datasets/HuggingFaceFW/finepdfs): about 475M documents of PDF-derived text. Check whether raw PDFs are included.
- [arXiv bulk S3](https://info.arxiv.org/help/bulk_data_s3.html): requester-pays, clean born-digital scientific PDFs.
- [PubMed Central OA](https://www.ncbi.nlm.nih.gov/pmc/tools/ftp/): JATS XML gives structural ground truth.
- [SEC EDGAR](https://www.sec.gov/Archives/edgar/full-index/): public domain HTML, text, XBRL and exhibits.
- [CourtListener RECAP](https://www.courtlistener.com/help/api/bulk-data/bulk-legal-data): court PDFs, many scanned.
- Email: [Enron](https://enrondata.readthedocs.io/en/latest/data/edo-enron-email-pst-dataset/) (the PST version includes attachments; contains real PII) and [Avocado LDC2015T03](https://catalog.ldc.upenn.edu/LDC2015T03) (gated behind LDC license agreements).

## Parsing and OCR benchmarks beyond Tier 1

- [Dr.DocBench](https://github.com/2077AI/DrDocBench) (2026): 4,514 hard pages, chosen where current top parsers disagree. 14 languages, including handwriting, music notation and chemistry. Repo is MIT (checked); data is reported as CC0.
- [DP-Bench](https://huggingface.co/datasets/upstage/dp-bench) (Upstage): 200 documents, MIT (checked). A fast regression check, already wired into [docling-eval](https://github.com/docling-project/docling-eval).
- [getomni-ai/benchmark](https://github.com/getomni-ai/benchmark): 1,000 documents with explicit quality tags (HIGH_QUALITY, CLEAN, PHOTO, LOW_QUALITY) and JSON extraction ground truth. MIT (checked).
- [ParseBench](https://github.com/run-llama/ParseBench) (LlamaIndex): about 2,000 enterprise pages. Apache-2.0 (checked). Vendor-built.
- [SCORE-Bench](https://huggingface.co/datasets/unstructuredio/SCORE-Bench) (Unstructured): 224 documents with explicit counts (54 scanned, 33 with handwriting, 39 degraded). Annotations are CC BY 4.0; some source PDFs keep their original non-commercial terms. Vendor-built.
- [RD-TableBench](https://huggingface.co/datasets/reducto/rd-tablebench) (Reducto): 1,000 hard tables. CC BY-NC-ND 4.0 (checked), so not commercially usable or redistributable.
- [CC-OCR v1/v2](https://github.com/AlibabaResearch/AdvancedLiterateMachinery): multilingual, with photographed, handwritten and degraded tracks. License conflict: MIT on GitHub, CC BY-NC-SA in the paper.
- [KITAB-Bench](https://github.com/mbzuai-oryx/KITAB-Bench): Arabic, MIT.
- [OCRBench v2](https://github.com/Yuliang-Liu/MultimodalOCR): broad OCR VQA, research use only.
- [READoc](https://github.com/icip-cas/READoc): born-digital PDF to Markdown, MIT.
- [Fox](https://github.com/ucaslcl/Fox): data CC BY-NC.
- Layout: [DocLayNet](https://github.com/DS4SD/DocLayNet) (80k pages, CDLA-Permissive-1.0, mostly born-digital) and [M6Doc](https://github.com/HCIILAB/M6Doc) (64% PDF, 31% scanned, 5% photographed; CC BY-NC-ND; the full set requires an application).
- Tables: [PubTables-1M](https://huggingface.co/datasets/bsmock/pubtables-1m) (CDLA-Permissive-2.0), [FinTabNet.c](https://huggingface.co/datasets/bsmock/FinTabNet.c) (CDLA-Permissive-2.0), PubTabNet (the original IBM host is gone; use an HF mirror), and SciTSR. All born-digital.

## ExtractBench deep dive

Links: [repo](https://github.com/run-llama/ExtractBench), [dataset](https://huggingface.co/datasets/llamaindex/ExtractBench), [paper arXiv 2607.29677](https://arxiv.org/abs/2607.29677), [site](https://www.extractbench.ai/).
Made by LlamaIndex, released August 2026.
Apache-2.0 for both code and data; the dataset isn't gated.
Checked 2026-09-23: 97 stars, last push 2026-09-22, about 20k dataset downloads.

### Task

Input is a PDF plus a JSON Schema; output must be schema-valid JSON.
The output must capture every record of repeated structures, set blank fields to `null` instead of inventing values, and cite evidence (page, optionally a word-level box) for each value.
There is one schema per document type (67 types), shared across all layouts of that type, so template tuning doesn't help.

### Data

| Split | Documents | Pages | Length |
|---|---:|---:|---|
| short | 252 | 615 | up to 10 pages |
| medium | 98 | 2,438 | 11 to 50 pages |
| long | 20 | 1,816 | over 50 pages |
| total | 370 | 4,869 | |

- 325 real public documents and 45 synthetic long lists rendered from real layouts. PDF metadata is stripped.
- Sources: SEC filings and 13F holdings, Texas Railroad Commission energy forms, CBP 7501 and SF-1449 government forms, tax forms (W-2, 1040, K-1, 1099-B), bankruptcy filings (including FTX), receipts, utility bills, spec sheets.
- Quality: 134 documents with scanned page images and 55 with handwriting. 38 degraded re-captures of clean documents keep the same expected values, which gives a paired clean-versus-degraded measurement.
- Domains: finance 145, energy 98, government 49, automotive 27, supply chain 20, healthcare 15, legal 10, real estate 6.
- It does NOT use a list of named degradation recipes (fax, carbon copy and similar). An earlier summary claimed that, and it was wrong. Use PureDocBench for systematic degradation sweeps.

### Tag axes

- Task challenge:
  - T1 long-list completeness: truncated, merged or invented rows.
  - T2 needle-in-a-haystack: the right occurrence among many plausible ones.
  - T3 dense documents: checkboxes, blank fields, handwriting, scan artifacts; the typical failure is inventing values for blank fields.
- Perception: P1 rotated or image-only, P2 scanned, P3 handwriting.
- Table structure: S1 merged headers, S2 header not above its data, S3 table spanning pages, S4 table over 1,000 rows, S5 table inside a single cell.
- Length (L1 to L3) and domain (D1 to D8). Also delivery requirements G1 to G4, and a real or synthetic flag.

### Record format (one JSONL row per document and schema)

Fields: `id`, `category`, `pdf` (relative path under `docs/`), `data_schema`, `expected_output`, `field_rules`, `repeated_structure`, `tags`.
`data_schema`, `expected_output`, `field_rules` and `repeated_structure` are JSON-encoded strings; decode them with `json.loads`.
`field_rules` maps each schema path to a comparator (`exact`, `case_insensitive`, `number`, `date`, `boolean`, `enum`, and others), an evidence list of `{page, bbox, quote, value}` entries where any listed reading is accepted, a `source_policy`, and `evidence_required` / `verified` flags.
On the largest document, `field_rules` reaches 21MB.
`repeated_structure` gives the key used to align records in each array, for example `(description, amount)` for invoice lines.

### Metrics

- Unified value F1 (the headline metric): output is flattened into cells, and repeated records are aligned with the Hungarian algorithm, so order doesn't matter. Dates are normalized across eight formats; strings are compared exactly after collapsing whitespace; there is no numeric tolerance and no LLM judge. A correct `null` on a blank field counts as correct. Failed documents score zero rather than being dropped.
- Word-level grounding F1: the value must be accepted and the predicted box must overlap an accepted box at IoU 0.5.
- Page-level grounding F1: the value must be accepted and the cited page must be correct.
- Both grounding metrics are scored only on fields with human-checked boxes.

### Leaderboard snapshot (2026-09-11, 44 systems)

| System | Value F1 overall | Short | Medium | Long | Cents per page |
|---|---:|---:|---:|---:|---:|
| LlamaExtract Agentic Plus | 95.91 | 96.94 | 94.45 | 90.18 | 8.11 |
| Pulse (Effort) | 95.91 | 96.46 | 95.01 | 93.51 | 10.50 |
| LlamaExtract Agentic | 94.77 | 96.04 | 92.11 | 91.83 | 3.31 |
| Codex (GPT-5.5) | 93.57 | 95.68 | 91.15 | 78.88 | 27.83 |
| OpenAI GPT-6 Astra | 91.91 | 97.22 | 90.56 | 31.70 | 11.09 |

Grounding is much harder: the best word-level grounding F1 is 58.11 (LlamaExtract Agentic Plus).
Single-shot vision-language models collapse on long documents, as the GPT-6 Astra long score of 31.70 shows.

### Caveats

- Vendor-built: LlamaIndex's own product ranks first.
- The answer key for real documents comes from agreement across independent extraction systems, not full human annotation, which may favour pipelines similar to those systems. Forms have human-verified values and boxes.
- US-centric, English, business-focused, mostly born-digital; no historical archives or free-form handwritten letters.
- A full run costs roughly $10 to $1,677 in API fees depending on the system. Start with `--test` (6 documents).
- The `claude_code_extract_*` and `codex_code_extract_*` pipelines run shell commands locally; run them in a container.

### Usage

```bash
git clone https://github.com/run-llama/ExtractBench && cd ExtractBench
uv sync --extra runners              # or: pip install "llama-extract-bench[runners]"
uv run extract-bench download --test # 6-doc sample; drop --test for all 370
uv run extract-bench pipelines       # list registered systems
uv run extract-bench run <pipeline> --test
uv run extract-bench run <pipeline> --group short   # one split
uv run extract-bench run <pipeline> --skip_inference # re-score existing results
uv run extract-bench serve <pipeline>  # HTML report with PDFs side by side
uv run extract-bench compare <a> <b>
```

```python
from datasets import load_dataset
import json
ds = load_dataset("llamaindex/ExtractBench", split="short")
case = ds[0]
schema = json.loads(case["data_schema"])
expected = json.loads(case["expected_output"])
```

API keys go in `.env` (`LLAMA_CLOUD_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `CODEX_API_KEY`); see `.env.example`.
To evaluate a custom pipeline, add a provider under `src/extract_bench/inference/providers/` and register it in `inference/pipelines/`.
The repo includes a Claude Code command for this: `/integrate-pipeline <name> <API docs or SDK link>` (defined in `.claude/commands/integrate-pipeline.md`).
The request and result types are in `src/extract_bench/schemas/pipeline_io.py`.
It is unverified whether results produced outside the harness can be scored with `--skip_inference` without registering a provider.
Outputs land in `output/<pipeline>/<split>/`: `*.result.json`, `_evaluation_report.json`, `_evaluation_results.csv` and an HTML report.

## License quick reference

Commercial use OK (checked): PureDocBench (data CC BY 4.0), olmOCR-Bench (ODC-By), OHR-Bench (CC BY 4.0), ExtractBench (Apache-2.0), REAL-MM-RAG (CDLA-Permissive-2.0), MMDocIR (Apache-2.0), DP-Bench (MIT), getomni-ai ocr-benchmark (MIT), ParseBench (Apache-2.0), racineai/ocr-pdf-degraded (Apache-2.0).
Commercial use OK (from research, not re-checked): DocLayNet, PubTables-1M, FinTabNet.c, CORD, GNHK, GovDocs1, SEC EDGAR, CourtListener RECAP.
Non-commercial only: UniDoc-Bench, Vectara Open RAG Bench, RD-TableBench (also no derivatives), FUNSD, XFUND, M6Doc, Fox data, IAM, CVL.
Ambiguous, check before use: OmniDocBench (Apache-2.0 repo, but the dataset card says research use only), CC-OCR (MIT versus CC BY-NC-SA), SCORE-Bench (mixed per document), DocVQA and RRC datasets (HF mirrors say Apache-2.0, original terms are research-only).
PII warning: Enron, Avocado, RVL-CDIP (embedded SSNs reported), UCSF Industry Documents.

## Known gaps

- There is no good public corpus of HEIC or multi-page TIFF files. Generate your own by converting pages from OmniDocBench or PureDocBench, and consider the Augraphy library for realistic scan degradation.
- Unverified: ViDoRe V2 exact sizes and license, the DUDE license and file hosting, the M3DocVQA license, and whether FinePDFs includes the raw PDFs.
