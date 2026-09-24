# Vision arbiter bake-off, 2026-09-24

Question: which hosted vision model should be the router's visual arbiter, judged on quality against cost and latency?

## Setup

- **Pages.** 60 labelled pages (`data/`, built by `data/build.py`):

  | Source | Pages | Label basis |
  |---|---|---|
  | PureDocBench | 21 (7 pages in 3 versions each) | construction, dataset ground truth |
  | olmOCR-Bench | 17 | dataset category, then a visual check |
  | FUNSD | 5 | visual check |
  | GNHK | 5 | construction |
  | Arabic primer | 3 | visual check |
  | Synthetic (code, fax, screenshot, camera photo, rotated) | 9 | construction |

  Labels were reviewed against contact sheets; 26 pages carry recorded overrides in `data/label_overrides.json`.
- **Models.** 20 of the newest vision models on OpenRouter, each the latest in its family, plus three mid-tier references.
- **Equal footing.** Same image (1024 px JPEG), same system prompt, same strict JSON schema. No output-token cap, no reasoning overrides; every model ran at its provider defaults. Cost is OpenRouter's reported per-call cost.
- **Axes scored.** Capture type, handwriting (none, some, mostly), content flags (table, math, form, code, chart, photo) and main script. The composite is the mean of the four axis accuracies. Invalid JSON counts as wrong.
- **Excluded axis.** Legibility is reported but kept out of the composite. Its labels describe image degradation while the prompt asked about OCR difficulty, so handwritten letters disagree by definition.
- **Consistency run.** A second full run for five finalists.
- **Spend.** $2.65 in total (OpenRouter usage figure), including the $0.125 pilot.

## Results

Composite on the corrected labels, with a 95% page-bootstrap interval, on the 56+ pages every model answered.
The "orig" column scores the same outputs against the labels as first built, before any correction.

| Model | Composite | 95% CI | Orig labels | p50 s | p95 s | $ per 1k calls | Reasoning tokens |
|---|---|---|---|---|---|---|---|
| openai/gpt-6-sol | 0.985 | 0.969-0.996 | 0.967 | 4.81 | 7.56 | 5.08 | 93 |
| google/gemini-3.8-flash | 0.979 | 0.962-0.993 | 0.946 | 4.15 | 8.72 | 2.75 | 284 |
| anthropic/claude-sonnet-5 | 0.966 | 0.943-0.987 | 0.939 | 2.96 | 4.28 | 5.23 | 0 |
| bytedance-seed/seed-2-1-turbo | 0.963 | 0.941-0.984 | 0.940 | 32.6 | 117.3 | 6.97 | 2,329 |
| meta/muse-spark-1.3-contributor | 0.960 | 0.935-0.981 | 0.928 | 12.1 | 23.4 | 0.40 | 1,183 |
| x-ai/grok-4.7 | 0.953 | 0.928-0.975 | 0.926 | 8.43 | 26.5 | 5.43 | 585 |
| openai/gpt-6-luna-pro | 0.950 | 0.920-0.976 | 0.922 | 5.90 | 14.1 | 0.52 | 406 |
| openai/gpt-6-luna | 0.941 | 0.910-0.969 | 0.913 | 3.97 | 7.54 | 0.26 | 130 |
| deepseek/deepseek-v4.1-flash | 0.927 | 0.895-0.958 | 0.895 | 4.63 | 18.5 | 1.53 | 1,046 |
| z-ai/glm-5.3-flash | 0.919 | 0.889-0.950 | 0.895 | 6.23 | 30.3 | 0.44 | 408 |
| ~anthropic/claude-haiku-latest | 0.912 | 0.873-0.948 | 0.902 | 2.75 | 3.62 | 2.31 | 0 |
| google/gemini-3.5-flash-lite | 0.909 | 0.872-0.944 | 0.882 | 1.64 | 2.18 | 0.79 | 0 |
| xiaomi/mimo-v2.6-flash | 0.908 | 0.875-0.942 | 0.886 | 10.7 | 41.0 | 0.28 | 401 |
| inclusionai/ling-3.0-flash-vl | 0.907 | 0.874-0.940 | 0.871 | 15.9 | 31.3 | 0.19 | 635 |
| stepfun/step-3.7-flash | 0.873 | 0.831-0.913 | 0.849 | 10.4 | 19.1 | 1.64 | 0 |
| nex-agi/nex-n2.5-mini | 0.840 | 0.781-0.896 | 0.809 | 2.59 | 8.76 | 0.51 | 332 |
| qwen/qwen3.8-flash | 0.824 | 0.740-0.902 | 0.797 | 7.93 | 12.3 | 0.43 | 511 |
| qwen/qwen3.8-omni-flash | 0.292 | 0.178-0.408 | 0.270 | 15.1 | 41.1 | 0.56 | 637 |

- **qwen3.8-omni-flash.** Wraps its answer in a one-element list, which breaks the schema: only 17/59 valid under strict parsing. Unwrapped leniently it scores 0.928, so it knows the task but ignores the schema.
- **mistral-small-2603.** Answered only 30 of 60 pages before upstream rate limits (0.839 on those; low coverage).
- **cohere/command-a-plus.** Rate-limited on every call and untested.

Per-axis accuracies, legibility and validity are in `scores.csv`; the original-label scores are in `scores_origlabels.csv`.

### Consistency (two independent runs)

| Model | All axes identical | Accuracy when runs agree | Accuracy when runs disagree | Pages disagreeing |
|---|---|---|---|---|
| google/gemini-3.8-flash | 0.93 | 0.974 | 0.990 | 4 |
| openai/gpt-6-luna | 0.90 | 0.944 | 0.951 | 6 |
| openai/gpt-6-luna-pro | 0.88 | 0.961 | 0.893 | 7 |
| ~anthropic/claude-haiku-latest | 0.88 | 0.907 | 0.887 | 7 |
| google/gemini-3.5-flash-lite | 0.85 | 0.931 | 0.815 | 9 |

## What this means for the router

1. **Default visual arbiter: Gemini 3.8 Flash.**
   - It is within the interval of the best score at about half GPT-6-sol's price, and was the most consistent model tested.
   - Arbitration touches at most about 15% of pages, so its cost is about $0.41 per 1,000 routed pages. Cost is not a reason to pick a weaker model.
2. **Second family, and the confidence signal: GPT-6-sol.**
   - Self-agreement does not flag errors on the strongest models; their mistakes repeat across runs.
   - Instead, ask a second family when the first answer conflicts with probe evidence, and use cross-family disagreement as the review trigger.
   - GPT-6-sol also supplies silver labels for RouteBench, keeping pre-labels in a different family from the live arbiter.
3. **Low-latency option: Claude Sonnet 5.** It has the tightest tail (p95 4.3 s) with no reasoning tokens, at about 2x Gemini 3.8 Flash's cost.
4. **Budget option: GPT-6-luna.** It scores 0.941 at $0.26 per 1,000 calls, about ten times cheaper than the default.
5. **Gemini 3.5 Flash-Lite is fastest, not best.** At 1.6 s it is a good first pass only where latency dominates. It labels Chinese pages with Latin formulas "mixed" instead of "cjk".
6. **Too slow for routing:** Seed-2.1-turbo (p95 117 s) and the long-reasoning flash models (MiMo, Ling, GLM, Grok tails).

## Caveats

- 60 pages is small. The top three intervals overlap, so the data does not separate GPT-6-sol, Gemini 3.8 Flash and Claude Sonnet 5 on quality. Cost and latency separate them.
- Labels were made by construction, from dataset metadata, and by visual checks from an agent and from me, not by two independent humans.
  - Eight overrides were added after the first scoring. They are applied the same way to all models, and the original-label scores keep the same top group.
- Capture type on PureDocBench's digitally degraded pages accepts render, scan or fax, because the degradation is synthetic.
- Legibility needs a better definition before it can be scored: image degradation and OCR difficulty are different questions.
- `meta/muse-spark-1.3-contributor` is a variant that is probably priced for sharing data with the provider.
- Latency was measured from one laptop in Finland through OpenRouter; direct provider APIs and batch endpoints will differ.

## Reproduce

```bash
uv run --no-project --with httpx python run.py --models all.txt --pages all --budget 3.5
uv run --no-project python apply_overrides.py && uv run --no-project python score.py && uv run --no-project python consistency.py
```
