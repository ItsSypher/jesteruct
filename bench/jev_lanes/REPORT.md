# Jev as the lane classifier, 2026-09-24

Question: how well does TypeSafe Jev sort pages into processing lanes, given the evidence a router can compute cheaply?

## Setup

- **Cases.** 98 in total (`cases.jsonl`, built by `probe.py`):

  | Group | Count | What it is |
  |---|---|---|
  | `img` | 60 | The bake-off page images, as image inputs with no text layer |
  | `pdf` | 25 | One-page PDFs with real text layers: olmOCR-Bench tables, math, multi-column and 12 extra pages, plus two code pages. It also holds book scans and two scans carrying an OCR layer, found while building. |
  | `ocr` | 8 | Page images wrapped by Tesseract into PDFs with an invisible OCR text layer |
  | `garb` | 5 | Born-digital pages whose text layer is replaced with garbled text (cid codes, glyph shifts, mojibake). The evidence is synthetic. |

- **Lanes.**

  | Lane | Meaning | Cases |
  |---|---|---|
  | L1 | Born-digital, simple | 6 |
  | L2 | Born-digital, complex (tables, math, code, two or more columns) | 13 |
  | L3 | Clean scan or image | 41 |
  | L4 | Degraded, photo or fax | 20 |
  | L5 | Mostly handwritten | 11 |
  | L3 or L4 | Borderline | 7 |

  Ground truth comes from a fixed written mapping from the page labels (`gt_lanes()` in `probe.py`).
- **Evidence the router computes.** It is put into words for Jev (`build_state()` in `run_jev.py`):
  - PDF structure: image coverage, invisible OCR layer, producer, math and monospace fonts, a column estimate from a projection profile.
  - Image quality: sharpness, contrast, page-edge surroundings, paper tint, colour, noise.
  - Text-layer and OCR statistics: amount, share of common English words, cid codes, odd symbols, script.
  - Apple Vision OCR confidence.
  - Optionally a text sample and the vision model's answers.
- **Jev calls.** Model `typesafe/jev-1.13` through OpenRouter's decisions endpoint. Most setups ran twice.
- **Comparisons:**
  - rules only;
  - rules plus the vision model's answers;
  - GPT-6-luna and Gemini 3.8 Flash given exactly the same evidence text.
- **Spend.** $0.77, most of it the Gemini text baseline.

## Results

"Too weak" is the share of pages sent to a lower lane than any acceptable one. These fail silently, so it is the number that matters most.

| System | Lane acc | Too weak | Too strong | Text-layer acc | p50 s | $ per 1k pages |
|---|---|---|---|---|---|---|
| Jev decomposed, vision Gemini 3.5 Flash-Lite, vision skipped on rule-trusted PDFs | **0.939** | **0.031** | 0.031 | 0.990 | 0.30 + vision | 0.041 + vision |
| Jev decomposed, vision Gemini 3.8 Flash | 0.929 | 0.041 | 0.031 | 0.990 | 0.31 + vision | 0.041 + vision |
| GPT-6-luna, exclusive lane descriptions, same evidence | 0.929 | 0.031 | 0.041 | 0.990 | 3.23 + vision | 0.183 + vision |
| Jev decomposed, vision Gemini 3.8 Flash (second copy of the same setup) | 0.918 | 0.051 | 0.031 | 0.990 | 0.29 | 0.041 |
| Jev decomposed, vision Gemini 3.5 Flash-Lite on every page | 0.908 | 0.051 | 0.041 | 0.990 | 0.30 | 0.041 |
| Gemini 3.8 Flash (text), same evidence | 0.904 | 0.032 | 0.064 | 0.979 | 4.12 | 2.435 |
| Jev decomposed, vision Claude Haiku | 0.888 | 0.061 | 0.051 | 0.990 | 0.31 | 0.041 |
| Jev decomposed, vision GPT-6-luna | 0.888 | 0.082 | 0.031 | 0.990 | 0.30 | 0.041 |
| Rules plus vision answers (no Jev) | 0.888 | 0.082 | 0.031 | 0.980 | 0 | 0 |
| Jev one lane choice, exclusive descriptions | 0.80-0.83 | 0.14-0.16 | 0.03-0.04 | 0.959 | 0.30 | 0.057 |
| Jev one lane choice, first descriptions | 0.80-0.81 | 0.16-0.17 | 0.031 | 0.96-0.97 | 0.30 | 0.056 |
| Jev decomposed, no vision evidence | 0.78-0.79 | 0.143 | 0.07-0.08 | 0.990 | 0.30 | 0.040 |
| Jev one lane choice, probes and text sample | 0.724 | 0.235 | 0.041 | 0.97-0.98 | 0.30 | 0.055 |
| Jev one lane choice, probes only | 0.643 | 0.25 | 0.10-0.11 | 0.93-0.94 | 0.30 | 0.035 |
| Rules only | 0.643 | 0.235 | 0.122 | 0.980 | 0 | 0 |

- "Vision" means the vision model's cost and latency on the pages it is called for:
  - Gemini 3.5 Flash-Lite: about 1.6 s and $0.79 per 1,000 calls.
  - Gemini 3.8 Flash: about 4.2 s and $2.75 per 1,000 calls.
- With 98 cases, one case is one point. The same Jev setup differed by one case between two copies, so the top four rows are a statistical tie. Latency and cost separate them.

## What we learned

1. **Ask Jev narrow questions, not the whole lane.**
   - One multi-option lane choice tops out around 0.80, with 14-17% of pages sent too weak.
   - Five yes/no questions with a fixed rule table in code reach 0.91-0.94 on the same evidence: text layer real, mostly handwritten, camera photo or fax, heavily degraded, complex layout.
   - The choice version failed where lane descriptions overlapped: a phone photo of handwriting fits both "degraded" and "handwriting". Choice scores each option separately, so precedence rules written into the descriptions only partly helped (0.80 to 0.83).
   - This matches the plan's route-vector design: Jev supplies the vector and a policy table picks the lane.
2. **Decomposed, Jev matches general LLMs at about a tenth of the latency.** GPT-6-luna on the same evidence reached 0.929 at 3.2 s; Jev reached 0.918-0.939 at 0.3 s and about a quarter of the decision cost. Jev never failed a call or returned malformed output.
3. **Jev is very repeatable.** Across two runs, the decomposed setup gave the same lane on 100% of cases and the choice setups on 95-100%. That is more stable than the launch-week audits suggested for these inputs.
4. **Vision evidence carries the image pages.**
   - Without the vision check, decomposed Jev drops to 0.78 because handwriting and photo capture are hard to infer from image statistics and OCR alone.
   - The cheap Gemini 3.5 Flash-Lite is as useful as Gemini 3.8 Flash here, because Jev needs only coarse visual facts.
5. **Skip the vision call on PDFs whose text layer passes the cheap checks.** It lost nothing: 0.939 with Flash-Lite. In a real corpus most pages are born-digital, so most pages would need only Jev (0.3 s) and the structural probes.
6. **Text-layer trust is Jev's strongest question.**
   - It was 99% right on whether a text layer can be used directly.
   - It caught Tesseract OCR layers over images and all five garbled layers (cid codes, glyph shifts, mojibake).
   - The one-choice version once trusted a (cid:NN) layer on a math page; the decomposed version did not.
7. **Calibration is usable but needs its own step.**
   - The product of answers along the decision path is under-confident (ECE about 0.14-0.19), but it separates right from wrong.
   - At a path probability of 0.7 or more, the decomposed setups were 95-97% right on about 75% of pages.
   - Fitting isotonic calibration on RouteBench should turn this into a review threshold.
   - Jev never chose "uncertain" in the choice setups, so the review signal has to come from the probabilities.
8. **Remaining errors point at specific fixes.**
   - **Handwriting behind a Tesseract OCR layer** was missed twice, though the same pages as plain images were right. An OCR layer over handwriting pulls Jev towards "clean scan". A probe fact such as "OCR confidence on the layer is low" or "the layer's text is mostly nonsense" should help.
   - **The column estimate** misread slide bullets as two columns. A real layout model should replace the projection-profile stand-in.
   - **Mildly degraded PureDocBench pages** go to the clean-scan lane in every system. That is a label question for RouteBench: do mildly degraded digital pages need the degraded lane?
   - **One yellowed book photo** went to the clean lane. The page-edge signal missed it because the book filled the frame.

## Caveats

- 98 cases is a pilot. Intervals at this size are roughly ±5 points, so read the top rows as tied.
- The lane truth is derived from attribute labels, not from running lanes. RouteBench's outcome matrix (which lane actually succeeds) is still the right final test.
- The column estimate and verbal thresholds were set while looking at these cases; a fresh set is needed to confirm them.
- The garbled cases are evidence-level synthetic: we replaced the extracted text, not the PDF's font tables.
- OCR ran in English mode only, as a quick single-pass probe would. Chinese and Arabic pages relied on the vision check for script.
- The vision answers for page images came from the bake-off run, so vision cost and latency are not in the Jev timings.

## Files

- `probe.py`: builds the cases and evidence.
- `run_jev.py`: the systems and prompts.
- `run_evidence_sweep.py`: vision source and skip policy.
- `score_jev.py`: writes `report.md`.
- `results/<system>/run<N>/`: every request's answer.
- `states_v3.jsonl`: the exact evidence text Jev saw.
