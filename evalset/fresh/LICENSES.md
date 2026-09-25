# Fresh set sources and licences

Blind-labelled pages for calibrating the review threshold and checking evidence changes (issues #3 and #6), disjoint from `evalset/` by source page and by file hash.
Part v1 is the first build's pages, relabelled; part v2 adds new pages, weighted towards the L3/L4 and L1/L2 boundaries.
Every v1 case is in the `tune` split, because v1 shaped evidence e3; v2 is split once, half `tune` and half `holdout`, by source document within each source family and lane (`split.json`).
Per-case attribution is in `cases.jsonl` (`source`), and `pages.jsonl` says where every page comes from.
Licences are listed for information; the set is built from the most useful public sources, whatever their terms.

The page files are not in git.
`uv run evalset/fresh/build.py fetch` downloads them from the private release `evalset-fresh-v2` and checks every file against the sha256 in `cases.jsonl`; `uv run evalset/fresh/build.py` rebuilds them from the public sources.

## Labelling

Every page is labelled blind, from the 1024 px JPEG the router sees, shuffled under a random id, with nothing that names its source.
Born-digital pages are judged on layout (simple, complex or borderline, which map to L1, L2 or L1/L2); every other page on capture (clean, degraded, borderline or handwritten: L3, L4, L3/L4 or L5).
A PDF page is born-digital unless it is a page-sized image (with or without an OCR layer), has a garbled layer, or holds no text (`sources.text_layer`).
The first build's test also asked for 200 characters, 30 words and under 1% odd characters, which sent 35 born-digital pages (TeX delimiters and bullets extract as private-use characters; covers, slides and short tables fail the length) to the capture rubric, where they could only be clean scans.
They were relabelled blind on the layout rubric (issue #9); their capture opinions stay in `labels.jsonl` but no longer count.
Labeller A is Claude; labeller B is `openai/gpt-6-luna-pro` at high reasoning effort (`label_model.py`), chosen on agreement with `evalset/`'s curated labels.
When A and B agree, that is the label; otherwise adjudicator C, also blind, decides by majority.
Opinions that differ only across one boundary (L3 against L4, L1 against L2, or borderline against either) give the set label, and a page that two labellers call unusable, or on which all three differ, is dropped.
Every opinion is kept in `labels.jsonl`, with the rubric it was given under.
A and B gave the same code to 73.9% of the capture pages and 93.7% of the layout pages.
On the 361 pages they split, C sided with A 234 times, with B 73 times and with neither 54 times, which gave 244 set labels, 89 single lanes and 28 drops.
The source metadata (a camera photo, a handwriting dataset, a born-digital category) and v1's single labels are a sanity check only: `build.py` lists every final label that contradicts them.

## Sources

Pages in the set, after labelling:

| Source | Licence | v1 | v2 | What the pages are |
|---|---|---|---|---|
| olmOCR-Bench (`allenai/olmOCR-bench`) | ODC-By 1.0 | 92 | 242 | Single-page PDFs: arXiv maths, tables, multi-column, headers and footers, tiny text, and old scans from the Library of Congress |
| DocLayNet v1.2 (`docling-project/DocLayNet-v1.2`) | CDLA-Permissive-1.0 | 55 | 51 | Single-page PDFs of financial reports, manuals, patents, laws, tenders and scientific articles, and a few scans |
| PureDocBench (`zhihengli-casia/puredocbench`) | CC BY 4.0 | 66 | 107 | Clean, digital-degraded and real-degraded (phone photo, photocopy, screen photo, screenshot) renders of synthetic documents, mostly Chinese |
| OmniDocBench (`opendatalab/OmniDocBench`) | Research use only, not commercial | 47 | 121 | Page images of books, exams, newspapers, textbooks, slides and reports, fuzzy or deformed scans, watermarks and handwritten notes, English and Chinese |
| RVL-CDIP (`jordyvl/rvl_cdip_100_examples_per_class`) | Research use; Truth Tobacco Industry Documents | 30 | 142 | Low-resolution business scans in 12 classes (forms, reports, invoices, specifications, budgets and others) and handwritten pages |
| DocVQA (`HuggingFaceM4/DocumentVQA`) | DocVQA terms, research use; UCSF Industry Documents Library | | 55 | Scans of industry documents, one page per document |
| UCSF Industry Documents Library faxes | UCSF copyright and fair-use statement; public availability | | 23 | Bitonal fax transmissions, one page each |
| FUNSD (train split, `nielsr/funsd`) | Non-commercial research, evaluation only | 11 | 29 | 1990s business forms |
| ICDAR 2019 SROIE (`jsdnrs/ICDAR2019-SROIE`) | CC BY 4.0 per the mirror; competition data for research | 14 | 17 | Scanned shop receipts |
| CORD v2 (`naver-clova-ix/cord-v2`) | CC BY 4.0 | 21 | 33 | Phone photos of shop receipts |
| WildReceipt (OpenMMLab) | Research use, not commercial | | 19 | Phone photos of receipts |
| SmartDoc 2015 challenge 1 | Research use, citation required | | 26 | Tablet photos of datasheets, letters, magazines, papers, tax forms and receipts |
| DocUNet benchmark | No licence stated; citation required | | 25 | Phone photos of curved, folded and crumpled pages |
| Inv3D real | No data licence stated; code MIT | | 4 | Phone photos of crumpled, folded and curled printed invoices (fictitious content) |
| GNHK (`Berzerker/gnhk_ocr_dataset`, test split via `bhavya777/GNHK-test-dataset`) | CC BY 4.0 | 30 | 45 | Phone photos of handwritten notes |
| IAM Handwriting Database forms (HF mirror `zikotone/iam-form`) | Non-commercial research after registration with the FKI; the mirror skips it | | 17 | Handwritten copies of printed sentences |
| CHURRO-DS (`stanford-oval/churro-dataset`, test split) | Research use only; each collection keeps its own terms | | 103 | Historical handwriting (Arabic, Chinese, Japanese, Hebrew, Greek, Latin) and printed pages (Cyrillic, Chinese, Japanese, Devanagari, Fraktur, Latin) |
| Ukrainian handwritten full pages (`JustQuiteMadMax/ukrainian-handwritten-text-full-pages`) | CC BY 4.0 | | 20 | Handwritten Cyrillic copies of literary text |
| Bentham papers (Bentham Dataset R0, HF mirror `staghado/Bentham`) | Research use, tranScriptorium and READ | | 8 | Jeremy Bentham's manuscripts |
| George Washington papers (GW20, UMass CIIR) | Research use; no redistribution | | 3 | 18th-century letter books |
| Internet Archive | Public-domain scans (1850 to 1925); Internet Archive terms of use | | 45 | Book pages in Russian, Arabic, Chinese, Japanese and English, and column blocks of old newspapers |
| Software manuals | Per manual: GFDL, PostgreSQL, PSF, CC BY-NC-SA 3.0, FreeBSD documentation, R Core, CC BY-SA, Open Publication, Oracle, IETF Trust, BSD-3-Clause | | 35 | Code and configuration listings, command references and prose from GNU, PostgreSQL, Python, Pro Git, FreeBSD, R, Debian, TLDP, the Java specification, RFC 9110 and Django |
| arXiv (cs.SE, cs.PL, cs.DB) | Per paper; arXiv licence at least | | 30 | Paper pages with code listings, one per paper |
| US government publications | Public domain | | 17 | Federal Register rules, the Economic Report of the President, the Budget, the Congressional Record, NIST SP 800-53 |
| Financial and statistical reports | IMF and UN free for research; World Bank CC BY 3.0 IGO; ECB with attribution; Federal Reserve public domain; TI free for reference | | 15 | Statistical tables and report pages, and a datasheet |
| SEC EDGAR annual reports (form ARS) | Public filings | | 14 | Financial statement pages |
| IRS forms | Public domain | | 7 | Blank tax forms and instructions |
| UN official documents | UN copyright, free for research | | 18 | General Assembly, Human Rights Council and Security Council documents in Arabic, Chinese and Russian |
| Synthetic (own construction) | Own construction, over the sources above | 9 | 30 | Fax and phone-photo simulations and rotated renders of born-digital pages outside the set (`bench/vision_bakeoff/data/scripts/synth_degrade.py`) |

## Composition

Cases by lane and split:

| Part | Split | L1 | L1/L2 | L2 | L3 | L3/L4 | L4 | L5 | All |
|---|---|---|---|---|---|---|---|---|---|
| v1 | tune | 45 | 9 | 46 | 110 | 52 | 75 | 58 | 395 |
| v2 | tune | 48 | 9 | 140 | 155 | 83 | 135 | 98 | 668 |
| v2 | holdout | 41 | 9 | 135 | 144 | 86 | 134 | 105 | 654 |
| All | | 134 | 27 | 321 | 409 | 221 | 344 | 261 | 1,717 |

The 1,717 cases are 1,676 pages (375 in v1; 654 `tune` and 647 `holdout` in v2) and 41 variants of them: 24 garbled text layers over born-digital PDFs (evidence-level, no new file, lane L3) and 17 Tesseract OCR-layer PDFs of image pages (their image's lanes).
Of the 1,755 labelled pages, 79 were dropped: 65 that show personal data, 9 blank or nearly blank, 4 that are not documents (folder covers, black pages) and 1 on which all three labellers differed.
The release tarball also holds the files of the 5 nearly blank DocLayNet pages dropped by the relabelling; `fetch` checks only the files cases name.
Nine drawn pages were taken out before the merge as duplicates: a scan that is in both FUNSD and RVL-CDIP, two CORD photos that repeat another CORD photo (one of them a v1 page from another split), and six more pages of the GNU licence text.
`build.py` now fails on near-identical pages of different documents.
By their source metadata, about 230 new pages are in Chinese or Japanese (110 of them PureDocBench pages, which are mostly Chinese), 51 in Cyrillic, 34 in Arabic script and 15 in Hebrew, Greek or Devanagari.
Own synthetic captures are 30 of the 1,306 new pages (2.3%); with PureDocBench's digital-degraded track, which its authors made synthetically, they are 74 (5.7%).

Pages with personal data about private individuals were left out where the source metadata shows it: RVL-CDIP's letter, memo, email and resume classes, UCSF faxes filed as cover sheets or letters, SROIE receipts that print a cashier, staff or customer name, and GNHK notes whose transcription names people or gives contact details.
The labellers mark the remaining pages that show such data as unusable, and those pages are dropped.

This set is for internal evaluation only.
It is not redistributed outside this repository and its private release, and none of it is used to train or fine-tune a model.
