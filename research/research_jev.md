# Research notes: TypeSafe Jev as a document/page routing brain

Compiled 2026-09-23.
Model under study: `jev-1.13.0` (aliases `jev-latest` and `jev-preview` both point to it).
Raw scrapes used for these notes are in `/Users/kavy/.claude/jobs/a2799e74/tmp/jev/`.

Legend for claim strength:
- **[official]** TypeSafe docs, blog or legal pages.
- **[vendor-claim]** TypeSafe marketing numbers that nobody has independently reproduced.
- **[independent]** third-party measurement, usually one person, small budget, launch week.
- **[unverified]** community speculation or a claim I could not confirm.

---

## 0. One-paragraph answer

Jev is a hosted, proprietary, text-only decision model.
You send one `state` (string, JSON object, or array of text) plus a map of typed questions (Choice, Score, Noul), and get back probabilities per option in roughly 100-700 ms, for $0.042 per million input tokens with output free.
It cannot look at a page image, so for a Docling/Marker routing layer it has to sit behind a cheap feature-extraction step (text layer, OCR sample, layout statistics turned into words), and it should only be asked the questions that deterministic code cannot answer.
Two public projects already do almost exactly this (DocJev for classification/splitting, doc-router for "does this page need OCR").
Its probabilities are useful as a ranking signal and for review gating, but independent audits say they are not reliably calibrated out of distribution, so thresholds have to be fitted on your own labelled pages, per question, against a pinned model version.

---

## 1. API shape

### 1.1 Endpoint and request

- Endpoint: `POST https://api.typesafe.ai/v1/systemone`, `Authorization: Bearer <API_KEY>` **[official]** ([API reference](https://docs.typesafe.ai/api)).
- Required body fields: `state` (string | object | array), `model` (e.g. `"jev-latest"`), `questions` (map of id to Question) **[official]** ([API reference](https://docs.typesafe.ai/api)).
- Question ids are yours; "The key is not sent to the underlying model and is not used in inference" **[official]** ([API reference](https://docs.typesafe.ai/api)).
  One independent fuzzing study still found six decision changes in 100 mutations that renamed question ids and reordered options/JSON keys **[independent]** ([yottayoshida/jevfuzz via awesome-jev-robustness](https://github.com/Yifan-Lan/awesome-jev-robustness)).
- `GET /v1/models` lists aliases **[official]** ([Models](https://docs.typesafe.ai/models)).

### 1.2 The three primitives

| Primitive | `type` | `criteria` | Answer fields | Limits |
|---|---|---|---|---|
| Choice | `"choice"` | map option to description (string/object/array/null) | `choice`, `probabilities` (sum to 1), `confidence` | max 255 options |
| Score | `"score"` | ordered array of level descriptions | `score` (probability-weighted, can sit between levels), `legend`, `probabilities`, `confidence` | 2 to 10 levels |
| Noul | `"noul"` | optional `{true: ..., false: ...}` | `noul` (0..1) | no `confidence` field |

Sources: [API reference](https://docs.typesafe.ai/api), [Choice](https://docs.typesafe.ai/primitives/choice), [Introduction](https://docs.typesafe.ai/introduction).
"Noul" is short for Bernoulli, confirmed by the CEO on HN ([HN comment 49718407](https://news.ycombinator.com/item?id=49718407)).
`instructions` and every criterion can be a string, object or array; you can reference state fields by name in backticks **[official]** ([API reference](https://docs.typesafe.ai/api), [Advanced: structure](https://docs.typesafe.ai/primitives/advanced)).
A TypeSafe cookbook says "a Choice works reliably up to roughly 240 options" **[official]** ([Classification using confidence](https://docs.typesafe.ai/cookbooks/classification_using_confidence)).
For higher cardinality the launch post says they score candidates independently first and then make an explicit choice (two-stage) **[official]** ([launch blog](https://typesafe.ai/blog/introducing-system-one-models-and-jev)).

`confidence` is derived from the probability shape.
The docs' own interactive demo approximates it as `(N * p_max - 1) / (N - 1)` for N options **[official]** ([Confidence](https://docs.typesafe.ai/confidence)), and independent traces report the same formula for Choice **[independent]** ([primeline.cc pre-registered test](https://primeline.cc/blog/typesafe-jev-pre-registered-test), listed in [awesome-jev-robustness](https://github.com/Yifan-Lan/awesome-jev-robustness)).
So it adds no information beyond `probabilities`; one audit recommends not thresholding on it at all **[independent]** ([scienthoon/jev-ood-calibration](https://github.com/scienthoon/jev-ood-calibration)).

### 1.3 Example request and response (verbatim from docs)

```json
{
  "state": "Hi, I've been trying to connect my Stripe account for 3 days and the integration keeps failing. I'm losing sales. Please help ASAP.",
  "model": "jev-latest",
  "questions": {
    "department": {"type": "choice", "instructions": "Which team should handle this",
      "criteria": {"billing": "Payment or subscription issues",
                   "technical": "Bugs or integration problems",
                   "sales": "Pricing or account questions"}},
    "frustration": {"type": "score", "instructions": "How frustrated the customer appears",
      "criteria": ["Calm, just stating facts", "Frustrated but civil", "Very angry, strong language"]},
    "is_urgent": {"type": "noul", "instructions": "The message conveys urgency or time-sensitivity"}
  }
}
```

```json
{
  "model": "jev-1.13.0",
  "answers": {
    "department": {"type": "choice", "choice": "technical", "confidence": 0.78,
                   "probabilities": {"technical": 0.85, "sales": 0.0, "billing": 0.15}},
    "frustration": {"type": "score", "score": 1.0, "confidence": 1.0,
                    "legend": {"0": "Calm, just stating facts", "1": "Frustrated but civil", "2": "Very angry, strong language"},
                    "probabilities": {"0": 0.0, "1": 1.0, "2": 0.0}},
    "is_urgent": {"type": "noul", "noul": 1.0}
  },
  "usage": {"input_tokens": 392, "output_tokens": 65}
}
```

Source: [Quick start](https://docs.typesafe.ai/introduction/quickstart).
Output tokens are reported but not billed.

### 1.4 How state is passed

- String, JSON object, or array of text values **[official]** ([State](https://docs.typesafe.ai/concepts/state)).
- TypeSafe recommends an object with named fields so questions can point at parts of it (e.g. "Does `refund_policy` support ... given `order.charges`?") **[official]** ([State](https://docs.typesafe.ai/concepts/state), [Cloudflare model page examples](https://developers.cloudflare.com/ai/models/typesafe/jev/)).
- "Jev ingests the `state` once and evaluates every question against it in parallel" **[official]** ([Models](https://docs.typesafe.ai/models)).

### 1.5 Questions per call and batching behaviour

- No explicit cap on question count; the limit is the token budget (below) **[official]** ([Models](https://docs.typesafe.ai/models)).
- Questions are evaluated "in parallel and in isolation"; "adding questions barely changes the response time" **[official]** ([Introduction](https://docs.typesafe.ai/introduction)).
- TypeSafe's GDPR cookbook: 13 questions in one call vs 13 calls gave identical answers, 12.2x cheaper and 10.0x faster **[official]** ([Parallel questions](https://docs.typesafe.ai/cookbooks/parallel_questions)).
- Independent check: 16 questions vs 1 moved confidence by 0.008 on average, flipped 0.4% of answers, added 14 ms, and held with adversarial neighbour questions **[independent]** ([jujumilk3/jev-calibration-audit](https://github.com/jujumilk3/jev-calibration-audit)).
- Important distinction: many questions over one state is fine, but many *items* inside one state is not the same thing.
  One study found 40 rows per request broke a ranking gate that one row per request passed **[independent]** ([yodablocks/jev-orderby-bench](https://github.com/yodablocks/jev-orderby-bench)); another reported 40/40 Korean sentences correct one per call vs 62% when the whole document went in one call **[independent, social post]** ([Threads post via awesome-jev-robustness](https://github.com/Yifan-Lan/awesome-jev-robustness)).

### 1.6 Context window

- TypeSafe docs: "64k tokens per request; 32k tokens for `state` plus the longest question" **[official]** ([Models](https://docs.typesafe.ai/models)).
- Cloudflare and OpenRouter list 32,000 tokens **[third-party listing]** ([Cloudflare](https://developers.cloudflare.com/ai/models/typesafe/jev/), [OpenRouter](https://openrouter.ai/typesafe)).
  I read this as the 32k state-plus-longest-question limit, but the discrepancy is not explained anywhere.
- Accuracy falls as state grows with irrelevant content ("Jev suffers from context rot") **[official]** ([Jev 1.13 jaggedness](https://docs.typesafe.ai/model-jaggedness/jev-1.13)).

### 1.7 Rate limits

- 250,000 tokens per second and 1,200 requests per minute; 429 on breach; limits "adjusting dynamically" and can change without notice; higher limits on enterprise plans **[official]** ([Models](https://docs.typesafe.ai/models)).
- Errors: 401, 422, 429, 529 (overloaded); SDKs retry with backoff and honour `retry-after` **[official]** ([API reference](https://docs.typesafe.ai/api)).
- Through Vercel AI Gateway the free tier rate-limits Jev "to a handful of requests per minute", and concurrency 32 caused retry storms **[independent]** ([scienthoon/jev-ood-calibration](https://github.com/scienthoon/jev-ood-calibration)).
- Implication for us: 1,200 RPM is 20 requests per second.
  At one page per request that caps you near 72,000 pages per hour per account, regardless of the token limit.
  This is the real throughput constraint, not price.

### 1.8 SDKs and integrations

- Python: `typesafe-sdk` (Python >= 3.10), `TypeSafeClient` and `AsyncTypeSafeClient`, `Choice`, `Noul`, `Score` classes, `client.system_one(state=..., questions=...)`; reads `TYPESAFE_API_KEY`; default model `jev-latest`; `uv add typesafe-sdk` **[official]** ([Python SDK](https://docs.typesafe.ai/sdk/python), [GitHub](https://github.com/typesafe-ai/typesafe-sdk-python)).
  SDK 0.7.0 (Sept 18) switched serialization from msgspec to Pydantic and added `response_model` **[community list]** ([cobanov/awesome-jev](https://github.com/cobanov/awesome-jev)).
- JavaScript: `@typesafe-ai/sdk` **[official]** ([Models](https://docs.typesafe.ai/models)).
- LangChain: `langchain-typesafe` with `TypeSafeClassifier` and model-routing middleware ([LangChain blog](https://www.langchain.com/blog/building-a-harness-with-jev)).
- Simon Willison's `llm-typesafe` plugin ([Simon Willison](https://simonwillison.net/2026/Sep/21/jev/), [repo](https://github.com/simonw/llm-typesafe)).
- Community listings also mention LiteLLM, Pydantic AI, R, Kotlin, Ruby and PHP clients ([cobanov/awesome-jev](https://github.com/cobanov/awesome-jev)); I did not verify each.

Python SDK example (official):

```python
from typesafe_sdk import AsyncTypeSafeClient, Choice, Noul, Score

async def main() -> None:
    async with AsyncTypeSafeClient() as client:
        response = await client.system_one(
            state={"document": "I was charged twice. Please fix this ASAP."},
            questions={
                "billing": Noul(instructions="Is this ticket about billing?"),
                "tone": Choice(instructions="What is the customer's tone?",
                               criteria={"calm": None, "frustrated": None, "angry": None}),
                "urgency": Score(instructions="How urgent is this ticket?",
                                 criteria=["can wait", "this week", "today"]),
            },
        )
    print(response.nouls["billing"].noul)
    print(response.choices["tone"].choice)
    print(response.scores["urgency"].score)
```

Source: [Python SDK](https://docs.typesafe.ai/sdk/python).

### 1.9 Pricing

- $0.042 per million input tokens ($42 per billion); output tokens free **[official]** ([Models](https://docs.typesafe.ai/models)).
- Same price on OpenRouter ([OpenRouter](https://openrouter.ai/typesafe)).
- Cloudflare pricing only shown in dashboard ([Cloudflare](https://developers.cloudflare.com/ai/models/typesafe/jev/)).
- TypeSafe: "We can't prove it isn't subsidized" **[official]** ([launch blog](https://typesafe.ai/blog/introducing-system-one-models-and-jev)).
- Worked example for us: a page state of about 1,000 tokens is about $0.000042 per page, so roughly $42 per million pages.
  JevBench measured about 950 input tokens per decision, $0.0399 per 1,000 decisions ([JevBench](https://github.com/fstandhartinger/jevbench)).
- Credits model: prepaid credits that expire after 12 months, with optional auto-refill **[official]** ([Master Customer Agreement](https://typesafe.ai/legal/mca)).

### 1.10 Latency

- Vendor: 70-500 ms end to end, 40-200x faster than frontier LLMs **[vendor-claim]** ([launch blog](https://typesafe.ai/blog/introducing-system-one-models-and-jev)); their evals were "run from our laptops on the West Coast".
- Independent measurements:
  - Classmethod (Tokyo, OCR'd trade pages): median about 650 ms per page ([Classmethod](https://dev.classmethod.jp/en/articles/typesafe-jev-doc-type-classification/)).
  - DocJev: classification median 138.6 ms, splitting median 209.6 ms (decision time only, OCR excluded) ([DocJev](https://github.com/jerryjliu/docjev)).
  - AY Automate via OpenRouter: median 0.33 s, slowest of 791 calls 1.42 s ([AY Automate](https://www.ayautomate.com/blog/jev-typesafe-system-one-model)).
  - Seoul: p50 280 ms, p95 397 ms for one question ([jev-calibration-audit](https://github.com/jujumilk3/jev-calibration-audit)).
  - An on-call alert router: p50 418 ms, p95 1,477 ms ([jev-oncall via yibie/awesome-jev](https://github.com/yibie/awesome-jev/blob/main/categories/classification-routing.md)).
  - doc-router: about 156 ms added per document over a local heuristic ([doc-router guide](https://github.com/misbahsy/doc-router/blob/main/docs/GUIDE.md)).
- Plan for 150-700 ms per call with a long tail over 1 s.

### 1.11 Availability

- Released 15 Sept 2026 in "early access"; "bringing developers off the waitlist as quickly as we can" **[official]** ([launch blog](https://typesafe.ai/blog/introducing-system-one-models-and-jev)).
  Developers reported getting in "within a day or two" ([Flavio Copes](https://flaviocopes.com/jev/)); I could not verify current waitlist status.
- OpenRouter: `typesafe/jev-1.13` and `~typesafe/jev-latest`, listed Sept 18, 32K context ([OpenRouter](https://openrouter.ai/typesafe)).
  It is not the chat-completions API: it uses `POST https://openrouter.ai/api/alpha/decisions` with the same body as `/v1/systemone`; OpenRouter adds `usage.cost`, `id`, `provider` ([OpenRouter blog](https://openrouter.ai/blog/insights/what-is-jev/), [OpenRouter Go SDK docs](https://openrouter.ai/docs/client-sdks/go/sdks/decisions/README), [jev-doc-classification](https://github.com/lucassarcanjo/jev-doc-classification)).
  The `/alpha/` path "may move" ([jev-doc-classification](https://github.com/lucassarcanjo/jev-doc-classification)).
- Cloudflare Workers AI: `typesafe/jev`, third-party model ([Cloudflare](https://developers.cloudflare.com/ai/models/typesafe/jev/)).
- Vercel AI Gateway: `typesafe-ai/jev` via AI SDK `experimental_evaluate`; the gateway does not expose the model version ([scienthoon/jev-ood-calibration](https://github.com/scienthoon/jev-ood-calibration), [Vercel](https://vercel.com/ai-gateway/models/jev)).
- AWS Bedrock / Azure / GCP: no evidence of availability. An HN commenter asked for Bedrock ([HN 49718111](https://news.ycombinator.com/item?id=49718111)).

---

## 2. Input modalities (critical)

**Text only. Jev cannot look at a page image or a PDF.**

- "Input: Text only. String, JSON object, or array of text values. No image, audio, or video input." **[official]** ([Models](https://docs.typesafe.ai/models)).
- "Pre-process non-text inputs (images, audio, video, binaries) into text or structured fields before sending them as `state`." **[official]** ([Models](https://docs.typesafe.ai/models)).
- "Images, audio, and video are not supported (yet)." **[official]** ([State](https://docs.typesafe.ai/concepts/state), [System One](https://docs.typesafe.ai/concepts/system-one)).
- TypeSafe staff on HN: "just JSON... for now :)" ([HN 49718414](https://news.ycombinator.com/item?id=49718414)). No roadmap date anywhere.
- The Doom demo "is on structured state as a data structure with text, not on images" ([launch blog](https://typesafe.ai/blog/introducing-system-one-models-and-jev)).
- Classmethod: "you need to first extract text using OCR before passing it along" ([Classmethod](https://dev.classmethod.jp/en/articles/typesafe-jev-doc-type-classification/)).
- Every document project I found extracts text first: DocJev (LiteParse or LlamaParse) ([DocJev](https://github.com/jerryjliu/docjev)), jev-doc-classification (`unpdf`, and "A scanned PDF yields no text") ([repo](https://github.com/lucassarcanjo/jev-doc-classification)), doc-router (pdf-inspector evidence plus extracted text) ([doc-router](https://github.com/misbahsy/doc-router)), tax-doc-classifier ("scanned pages need OCR") ([cobanov/awesome-jev](https://github.com/cobanov/awesome-jev)).

What this means for lanes:
- Born-digital vs scanned vs degraded text layer: Jev can help, but only from evidence you compute (text layer present, char counts, encoding damage flags, OCR garble).
  doc-router shows Jev catching cases rules miss: "a scan carrying a bad pre-existing OCR layer, a page whose only text is a watermark, a broken `ToUnicode` map" ([doc-router](https://github.com/misbahsy/doc-router)).
- Table-heavy, forms, code, math: plausible from extracted text plus layout statistics, since these leave textual traces (column patterns, `$`/LaTeX-like glyphs, field labels, indentation).
- Handwriting and image-heavy: weak fit, because the signal is visual.
  Jev only sees whatever your OCR or feature extractor reports (e.g. low OCR confidence, image-area ratio).
  A small vision classifier is the honest choice for those lanes.
- Numeric features: pass them as named buckets, not raw numbers (see section 4).
- Coordinates did not help in the one test that tried: Textract bounding boxes gave no accuracy gain and 3.6x more tokens ([Classmethod §2.6](https://dev.classmethod.jp/en/articles/typesafe-jev-doc-type-classification/)).

Experimental open alternatives with image input exist (Laya Vision on SmolVLM, OpenJev on DiffusionGemma with optional images, PlayJev 0.8B VLM), but they are not Jev and their probabilities are described as uncalibrated or untested ([AbdelStark/awesome-typesafe-jev](https://github.com/AbdelStark/awesome-typesafe-jev)).

---

## 3. Calibration and the "never hallucinates" claim

### 3.1 What TypeSafe claims

- Trained with "Reinforcement Learning for Calibrated Decisions (RLCD)", probabilities "optimized against outcomes" **[official]** ([AI primer](https://docs.typesafe.ai/introduction/machine-learning-primer)).
- "Calibration is measured across groups of predictions; it does not guarantee that an individual answer is correct." **[official]** ([System One](https://docs.typesafe.ai/concepts/system-one)).
- TypeSafe publishes no reliability curve and no ECE numbers; the `confidence` field is only loosely documented ([jev-calibration-audit](https://github.com/jujumilk3/jev-calibration-audit)).
- Architecture, weights and paper are unpublished; described as transformer-based and trained on synthetic data per Wikipedia ([Wikipedia](https://en.wikipedia.org/wiki/Jev_(AI_model))), while the blog says "a new model architecture, parallel sampler" ([launch blog](https://typesafe.ai/blog/introducing-system-one-models-and-jev)).
  Outside guesses (open-weight LLM base, diffusion LM) are **[unverified]** ([Wikipedia](https://en.wikipedia.org/wiki/Jev_(AI_model)), [HN 49721012](https://news.ycombinator.com/item?id=49721012)).

### 3.2 Independent evidence (mixed)

In-distribution or public benchmarks, near calibrated:
- OpenBookQA ECE 0.024, CommonsenseQA 0.032, HellaSwag 0.029, but these are probably in the training mix ([scienthoon/jev-ood-calibration](https://github.com/scienthoon/jev-ood-calibration)).
- MMLU probe ECE 0.031 (cited in [jev-calibration-audit](https://github.com/jujumilk3/jev-calibration-audit)).
- CLINC150 ECE 0.020 but Banking77 0.094 ([jourdanlabs/assay-001 via awesome-jev-robustness](https://github.com/Yifan-Lan/awesome-jev-robustness)).
- 544 legal documents, 109 yes/no judgments: Brier 0.030, all 96 answers outside 0.2-0.8 correct ([X article via awesome-jev-robustness](https://github.com/Yifan-Lan/awesome-jev-robustness)).

Out of distribution or harder, miscalibrated:
- 900 synthetic support tickets: overall ECE 0.107, 4.4x the noise floor; on a label defined by a hidden organisational rule, 44.7% accuracy at mean stated probability 0.74 ([scienthoon](https://github.com/scienthoon/jev-ood-calibration)).
- Direction differs by primitive: Noul tends under-confident, Choice and Score over-confident on the same inputs ([scienthoon](https://github.com/scienthoon/jev-ood-calibration), [awesome-jev-robustness](https://github.com/Yifan-Lan/awesome-jev-robustness)).
- 8,801 sentiment examples: Noul ECE 0.117, Choice worse; isotonic regression brought ECE to 0.008 ([AnthusAI/Jev-Calibration via awesome-jev-robustness](https://github.com/Yifan-Lan/awesome-jev-robustness)).
- Phishing (2,000 emails): 62.6% accuracy as one question, ECE 0.154 vs Haiku 4.5 at 0.097; decomposed into five signal questions combined in code, 95.0% ([anisselbd/jev-phishing-bench via awesome-jev-robustness](https://github.com/Yifan-Lan/awesome-jev-robustness), [beri.net](https://www.beri.net/article/typesafe-jev-typed-decision-model-calibration-decomposition-shadow-eval)).
- Conformal thresholding on CLINC150 floors at 1.95% risk because 56.4% of answers come back at confidence exactly 1.0, nine of them wrong ([nikkoxgonzales/jev-certify via awesome-jev-robustness](https://github.com/Yifan-Lan/awesome-jev-robustness)).
- Dependency auto-merge: AUROC 0.851 in distribution, but the tuned threshold did not transfer OOD ([scarif-labs via awesome-jev-robustness](https://github.com/Yifan-Lan/awesome-jev-robustness)).
- Output quantised to 0.01, frequently exactly 0 or 1; at least one case put 0.00 on the correct answer with confidence 0.99 ([scienthoon](https://github.com/scienthoon/jev-ood-calibration)).

Practical consensus among the auditors: treat probabilities as a monotone ranking score, calibrate locally per question, and do not reuse a threshold across question types or versions ([scienthoon](https://github.com/scienthoon/jev-ood-calibration), [SamuelSacco/jev-exploration via awesome-jev-robustness](https://github.com/Yifan-Lan/awesome-jev-robustness)).
TypeSafe itself says: "Don't carry a threshold tuned on a Noul over to a Choice" ([jaggedness](https://docs.typesafe.ai/model-jaggedness/jev-1.13)) and "pin that version's ID" if you tuned thresholds ([Models](https://docs.typesafe.ai/models)).

### 3.3 Abstention and "never hallucinates"

- The claim is about types: output is always one of your options, so no malformed or invented values.
  TypeSafe marks its 0% type-error figure as "not empirical" but guaranteed by schema ([launch blog](https://typesafe.ai/blog/introducing-system-one-models-and-jev)).
  Independent runs saw 0 invalid responses in 4,621 calls and 8,576 calls ([scienthoon](https://github.com/scienthoon/jev-ood-calibration), [awesome-jev-robustness](https://github.com/Yifan-Lan/awesome-jev-robustness)).
- It does not mean correct: the CEO agrees "it's also possible to be confidently wrong" ([HN 49718780](https://news.ycombinator.com/item?id=49718780)); The Register and TS2 make the same point ([The Register](https://www.theregister.com/ai-and-ml/2026/09/16/typesafe-ai-debuts-model-for-machines-that-plays-doom/5296711), [TS2](https://ts2.tech/en/typesafe-ai-raises-40-million-for-jev-but-its-445x-cost-claim-is-still-self-tested/)).
- There is no built-in abstain. You must add it as an option.
  - Removing the "unknown" option on KoBBQ took accuracy on unanswerable items from 0.950 to 0.000 at 0.79 confidence ([jev-calibration-audit](https://github.com/jujumilk3/jev-calibration-audit)).
  - 0 of 30 out-of-scope inputs flagged without an explicit none option ([priorbench/jev via awesome-jev-robustness](https://github.com/Yifan-Lan/awesome-jev-robustness)).
  - With an explicit abstain option, AbstentionBench F1 0.855, first among 20 systems ([sshariqali via awesome-jev-robustness](https://github.com/Yifan-Lan/awesome-jev-robustness)).
  - TypeSafe also says to add `other` / `none of the above` ([Choice](https://docs.typesafe.ai/primitives/choice)).
- DataCamp headlines "Never Hallucinates" and calls it "mathematically impossible" ([DataCamp](https://www.datacamp.com/blog/system-one-models-jev)); treat that as marketing framing.

---

## 4. Where it works well and where it fails

### 4.1 Works well (reported)

- Common-sense semantic classification with clear, well-described options: support routing, intents, spam, moderation ([jaggedness](https://docs.typesafe.ai/model-jaggedness/jev-1.13), [Simon Willison](https://simonwillison.net/2026/Sep/21/jev/)).
- Document-type classification from extracted text: 40/40 on real public-sector PDFs ([DocJev](https://github.com/jerryjliu/docjev)); 20/20 OCR'd trade pages with previous-page context ([Classmethod](https://dev.classmethod.jp/en/articles/typesafe-jev-doc-type-classification/)); 10 clean synthetic financial PDFs at 98-99% ([jev-doc-classification](https://github.com/lucassarcanjo/jev-doc-classification)).
- Robust to OCR noise and missing titles in the Classmethod test (e.g. "C0MMERC1AL INV0ICE"), with probabilities of 0.99+ on those pages.
- Typos and OCR corruption in loan identity matching: 100% precision, 97.5% recall held out ([KiishiAD via awesome-jev-robustness](https://github.com/Yifan-Lan/awesome-jev-robustness)).
- No option-order bias (0 of 400 argmax flips) ([jev-calibration-audit](https://github.com/jujumilk3/jev-calibration-audit)); but see the conflicting RINNECODER result below.
- Reranking and relevance filtering ([Re-ranking cookbook](https://docs.typesafe.ai/cookbooks/rerank_typesafe), [Simon Willison](https://simonwillison.net/2026/Sep/21/jev/)).

### 4.2 Weak or failing (official list)

From [Jev 1.13 jaggedness](https://docs.typesafe.ai/model-jaggedness/jev-1.13):
1. Literal reading: "answers the question you wrote, not the one you meant."
2. Math and numbers: no counting, weak on numeric representations; "Keep the arithmetic in code". Score interpolation is not numerically calibrated.
3. Date and time comparison.
4. Indirection / multi-hop.
5. Large state full of irrelevant detail (context rot).
6. Adversarial content in state.
7. Contradictory instructions vs criteria.
8. Structural invariants: a Noul and a two-option Choice on the same question disagree (0.22 vs 0.01 in their example); P(x) + P(not x) = 1.19 in another.
9. Generation.

### 4.3 Weak or failing (independent)

- Criteria wording is the largest lever: rewrites moved accuracy 70% to 96% and 83% to 100% ([awesome-jev-robustness](https://github.com/Yifan-Lan/awesome-jev-robustness)).
- Many items in one state degrade answers (section 1.5).
- Adding an unrelated option shifts log-odds between untouched options by about 0.3-0.5, so Choice is not independent of irrelevant alternatives ([jev-wide, audio-jevlike via awesome-jev-robustness](https://github.com/Yifan-Lan/awesome-jev-robustness)).
- Option position mattered on arithmetic: 88% correct option first vs 57% last ([RINNECODER via awesome-jev-robustness](https://github.com/Yifan-Lan/awesome-jev-robustness)).
  This conflicts with the "no order bias" audit; likely task-dependent.
- Hidden rules not in the text: wrong 19 of 24 times at high confidence on an invoice house rule ([phuryn/experiments via awesome-jev-robustness](https://github.com/Yifan-Lan/awesome-jev-robustness)); same pattern in the 900-ticket priority task.
- Sequential state and counting: 13.2% on sequential state mutation, 33.3% on exact counting ([etsabary via awesome-jev-robustness](https://github.com/Yifan-Lan/awesome-jev-robustness)).
- Prompt injection that reads as evidence (a fake approval, an editor's note) moves verdicts; blunt commands mostly fail ([awesome-jev-robustness](https://github.com/Yifan-Lan/awesome-jev-robustness)).
  One-line injected instruction took a Wikipedia-deletion task from 96.5% to 26.5% ([zkousama/jagged](https://github.com/Yifan-Lan/awesome-jev-robustness)).
  Relevant for us because document text is untrusted input.
- Multilingual: English is primary **[official]** ([Models](https://docs.typesafe.ai/models)); Russian -11 pp on XNLI, Spanish -3 to -6 pp, Korean -6.5 pp, with calibration usually worse; only the state's language matters, not the instruction's ([awesome-jev-robustness](https://github.com/Yifan-Lan/awesome-jev-robustness)).
  Persian parity reported by one study.
  Classmethod wrote questions in English because "Jev has the highest accuracy in English".
- Accuracy vs frontier LLMs on TypeSafe's own workflow evals: Jev 67.8% vs GPT-5.6 Terra 67.9%, Sol 74.1%, Opus 5 73.1%, where "accuracy" means agreement with the average of two frontier models **[vendor-claim]** ([DataCamp](https://www.datacamp.com/blog/system-one-models-jev), [launch blog](https://typesafe.ai/blog/introducing-system-one-models-and-jev)).
- JevBench (independent, but items written by frontier LLMs): Jev 1.13.0 ranks first at 63.29, closely followed by open models JevK5 at 62.04 ([JevBench](https://github.com/fstandhartinger/jevbench)).
- Early wrong claims to ignore: an HN commenter said Choice allows only 10 options ([HN 49720680](https://news.ycombinator.com/item?id=49720680)); the API allows 255 (10 is the Score level limit).
  DataCamp's code sample uses `"options"` and `"min"/"max"` fields that do not exist in the API ([DataCamp](https://www.datacamp.com/blog/system-one-models-jev) vs [API reference](https://docs.typesafe.ai/api)).

---

## 5. Document classification / routing examples

### 5.1 Classmethod: OCR'd trade documents, page type (read in full)

Source: [Classmethod DevelopersIO, 2026-09-21](https://dev.classmethod.jp/en/articles/typesafe-jev-doc-type-classification/).

Setup:
- `jev-latest` resolved to `jev-1.13.0`; compared with Claude Sonnet 4.6 on Bedrock.
- 5 fictional PDFs, 20 pages, as Textract-like LINE text (only the `Text` of each line passed).
- Hard cases on purpose: no titles, continuation pages (only line items and totals), cover sheets, blank pages, OCR misreads ("C0MMERC1AL INV0ICE"), stamps, handwriting notes, junk characters.
- One request per page, one run per condition, four conditions: previous page yes/no by classification rules in state yes/no.
- English questions and rules.

State shape:

```json
{
  "classification_guide": "<only when rules are used>",
  "previous_page": ["<lines of the previous page, null for page 1>"],
  "page": ["<lines of the page to classify>"]
}
```

Question (one Choice, 7 options, option descriptions kept to bare names so they are not hints):

```json
{
  "doc_type": {
    "type": "choice",
    "instructions": "`page` holds the OCR result of one page of a scanned PDF, line by line from top to bottom. Decide which type of trade document this page belongs to.",
    "criteria": {
      "invoice": "Commercial invoice.",
      "packing_list": "Packing list.",
      "bill_of_lading": "Bill of lading.",
      "certificate_of_origin": "Certificate of origin.",
      "insurance_policy": "Cargo insurance policy or certificate.",
      "blank": "Blank page.",
      "other": "None of the above."
    }
  }
}
```

With previous page, appended to instructions: "`previous_page` is the page immediately before it in the same PDF (null for the first page). Use it only as context, for example to recognise a continuation page that has no title or header. Classify `page`, not `previous_page`."

The `classification_guide` rules describe each type by fields rather than titles (e.g. invoices have unit price and amount columns; packing lists have carton numbers, net/gross weight, M3 and no prices; blank includes pages with only stray `|`, `_`, `.` characters) and add OCR noise hints (0/O, 1/I/L).

Results:

| Condition | Correct | Needs review (p < 0.8) | Median latency | Input tokens (20 pages) | Cost (20 pages) |
|---|---|---|---|---|---|
| Single page, no rules | 19/20 | 2 | 649 ms | 13,827 | $0.0006 |
| Single page, rules | 19/20 | 2 | 654 ms | 22,427 | $0.0009 |
| With previous, no rules | 20/20 | 1 | 630 ms | 19,070 | $0.0008 |
| With previous, rules | 20/20 | 0 | 660 ms | 27,670 | $0.0012 |
| Sonnet 4.6 (all conditions) | 20/20 | n/a | 1,116-1,179 ms | 21,062-35,253 | $0.074-$0.117 |

Per-page detail worth knowing:
- Failures were a garbage-characters-only page classified `other` at 0.49 (single, no rules) and a header-less packing-list continuation classified `invoice` at 0.71 (single, with rules).
- The same garbage page scored `blank` at only 0.50 even with the previous page and no rules (correct but flagged), 0.83 with rules.
- A noisy continuation page scored 0.63 / 0.70 single and 1.00 with the previous page.
- Every page at or above 0.8 was correct in all four conditions, so a 0.8 threshold caught every error on this data.
- Writing rules in state did not change the correct count; passing OCR coordinates gave no gain and 3.6x tokens.
- Sonnet 4.6 was perfect even single-page; Jev matched it only with the previous page, at about 1/100 the cost and half the latency.

Caveats: 20 synthetic pages, one run each, no repeat-stability check.

### 5.2 DocJev (Jerry Liu, LlamaIndex): classify and split

Source: [jerryjliu/docjev](https://github.com/jerryjliu/docjev), [architecture](https://github.com/jerryjliu/docjev/blob/main/docs/architecture.md), [limitations](https://github.com/jerryjliu/docjev/blob/main/docs/limitations.md), [boundary review](https://github.com/jerryjliu/docjev/blob/main/docs/boundary-review.md).

- LiteParse extracts page text locally; optional LlamaParse for cloud OCR; Jev decides category and boundaries.
- Rules are YAML categories with descriptions of document purpose; `other` is added automatically.
- Builds "typed category and boundary questions over ordered page text. A whole packet normally fits one request. Larger packets use overlapping context windows with exactly one output owner per page."
- 40 real PDFs (116 pages): classification 40/40 for Jev and GPT-5.6 Luna; splitting 7/8 exact packets for Jev vs 8/8 for Luna; Jev median 138.6 ms vs Luna 794.3 ms.
- The one Jev error was an extra cut before an attachment, with boundary score 0.76, which the default review band (0.4-0.6) did not catch.
  A confident wrong answer, in other words.
- Review reasons: `boundary_near_threshold`, `category_uncertain`, `category_boundary_conflict`, `other_category`.
- The author explicitly says: "Neither is claimed to be calibrated."
- Empty OCR only counts as blank after a visual blank check; nonblank pages with unreadable text fail loudly.

### 5.3 doc-router: which pages need OCR

Source: [misbahsy/doc-router](https://github.com/misbahsy/doc-router), [GUIDE](https://github.com/misbahsy/doc-router/blob/main/docs/GUIDE.md).

This is the closest public analogue to our scanned vs born-digital lane decision.
- Rust; pdf-inspector computes per-page evidence (text layer, amount, tables, columns, encoding damage); lopdf splits pages; OCR via LiteLLM (Mistral OCR in the benchmark).
- Judge trait gets `PageEvidence` (page index, optional extracted text, inspector reasons, `flagged_by_inspector`, `has_tables`, `has_columns`, `has_encoding_issues`) and returns `needs_ocr`, `confidence`, `reason`.
- `jev` judge sends every page's text and asks whether it is actually readable.
  `jev_gated` only calls Jev when structural evidence is ambiguous (encoding issues, some-but-not-all pages flagged, or a flag without reason), and deliberately not on tables or columns.
- Batches up to 50 pages per call, 256 KiB per request, 2,000 chars per page; circuit breaker; 30 s timeout; strict mode for benchmarks so fallbacks do not masquerade as Jev results.
- 19 docs / 155 pages: routed 87 pages to OCR instead of 155, 1.72x faster, 1.74x cheaper; missed 9 pages that needed OCR vs 28 for the rules judge.
  An earlier run missed 11, so results vary run to run.
  The Jev judge cost 2.5% of the OCR bill it authorised.

### 5.4 Other document projects

- jev-doc-classification: per-document one Noul per type (multi-label) plus one Choice across all types; filename excluded from state; truncates at 60,000 chars; invoice stamped PAID split receipt 83% / invoice 70%; sparse notice stayed under 20% everywhere ([repo](https://github.com/lucassarcanjo/jev-doc-classification)).
- tax-doc-classifier: 261 IRS forms, text-bearing pages only, confidence gate; no wrong labels on two corpora but 38 low-confidence pages, no committed page-level results ([AbdelStark/awesome-typesafe-jev](https://github.com/AbdelStark/awesome-typesafe-jev)).
- SEC 10-K industry classification: 75-option Choice; confidence >= 0.9 half was 90% right, the other half 40% right, rising to 70% when reported one hierarchy level up **[official cookbook, jev-1.12]** ([Classification using confidence](https://docs.typesafe.ai/cookbooks/classification_using_confidence)).
- Hierarchical classification via beam search over Choice probabilities, path score `product(edge_probabilities) ** (1/decisions)` **[official]** ([Hierarchical classification](https://docs.typesafe.ai/cookbooks/hierarchical_classification)).
- Structure recovery: Noul per adjacent line pair to stitch hard-wrapped lines, then Choice per block (heading, paragraph, list, quote, code, callout) **[official]** ([Structure recovery](https://docs.typesafe.ai/cookbooks/autoformat)).
  Useful if we ever want a text-only block classifier.

---

## 6. Limitations, licensing, data, self-hosting, determinism

### 6.1 Licensing and terms

- Proprietary model, hosted only ([Wikipedia](https://en.wikipedia.org/wiki/Jev_(AI_model))).
- Same weights for every account; no fine-tuning or LoRA with customer data; customise through state, instructions and criteria **[official]** ([Models](https://docs.typesafe.ai/models)).
- MCA prohibits using the Services "or any Output to perform model distillation, train a model to imitate the output of the Services, or develop a similar or competing product" ([MCA](https://typesafe.ai/legal/mca)).
  Consequence: using Jev labels to train our own replacement router is likely a breach.
  TypeSafe's own docs encourage training a downstream classical model (CatBoost) on Jev probabilities as features ([Models](https://docs.typesafe.ai/models), [AutoResearch cookbook](https://docs.typesafe.ai/cookbooks/autoresearch_feature_discovery)); where that line sits needs legal review.
- Output ownership assigned to customer ([MCA](https://typesafe.ai/legal/mca)).
- Services provided "AS IS"; credits expire after 12 months ([MCA](https://typesafe.ai/legal/mca)).

### 6.2 Data retention and privacy

- "We will not train or fine tune any artificial intelligence or machine learning models on your prompts or other Input." ([Privacy Policy](https://typesafe.ai/legal/privacy-policy)).
- Zero data retention only for enterprise customers, by contacting privacy@typesafe.ai ([Legal](https://docs.typesafe.ai/legal)).
- Retention otherwise "as long as reasonably necessary"; no day count published ([Privacy Policy](https://typesafe.ai/legal/privacy-policy), [DPA](https://typesafe.ai/legal/data-processing)).
- Services hosted in the United States; EU/UK transfers under SCCs and UK Addendum; Irish supervisory authority named for EEA ([DPA](https://typesafe.ai/legal/data-processing), [Privacy Policy](https://typesafe.ai/legal/privacy-policy)).
- TypeSafe may process "Telemetry" (logs, hashes, summary statistics, classifications) "without restriction" ([MCA](https://typesafe.ai/legal/mca)).
- Subprocessors at trust.typesafe.ai/subprocessors (not checked).
- No SOC 2 or ISO mention found in docs.
- Via Vercel you can request `zeroDataRetention: true` at the gateway level ([scienthoon](https://github.com/scienthoon/jev-ood-calibration)); I did not verify what that guarantees upstream.

For a law firm pipeline (Borenius), US hosting and the telemetry clause are the points to check before sending client documents.

### 6.3 Self-hosting

- Not possible for Jev itself.
- Open-weight lookalikes with the same `/v1/systemone` API:
  - Kev (Apache-2.0, Qwen3.5 0.8B/4B/9B, runs on CUDA/ROCm/MLX; 4B and 9B fit a 32 GB Mac; Kev-9B 0.822 vs Jev 0.857 on the author's dev set) ([jaredpalmer/kev](https://github.com/jaredpalmer/kev)).
  - JevK5, SemIf, djev (DiffusionGemma), Winnow-12B, Laya, Bosun ([JevBench](https://github.com/fstandhartinger/jevbench), [AbdelStark/awesome-typesafe-jev](https://github.com/AbdelStark/awesome-typesafe-jev)).
  - Small open models are very sensitive to option order (one scored 21% vs 72% with reversed yes/no order) ([JevBench](https://github.com/fstandhartinger/jevbench)).
- Because the API shape is shared, you can code against it once and swap Jev for a local model later.

### 6.4 Determinism

- Not deterministic, but close.
  - TypeSafe GDPR cookbook: most answers identical over 5 repeats, two Nouls carried "a little run-to-run sampling noise" ([Parallel questions](https://docs.typesafe.ai/cookbooks/parallel_questions)).
  - Noul cookbook: std 0.0102; one borderline answer spanned 0.43-0.53 across the 0.5 threshold ([awesome-jev-robustness](https://github.com/Yifan-Lan/awesome-jev-robustness)).
  - Choice cookbook: 90.8% plurality-label agreement over 15 repeats of a borderline post, flips on 2 of 8 questions; 99.2% after adding an `uncertain` outcome below top probability 0.60 **[official]** ([Self-consistency: choices](https://docs.typesafe.ai/cookbooks/consistency_choice_cookbook)).
  - 50 identical requests gave 15 distinct answer sets; no caching of identical requests ([jev-calibration-audit](https://github.com/jujumilk3/jev-calibration-audit)).
  - Repeat std 0.001-0.015, larger option sets move more; up to 0.13 in one study ([awesome-jev-robustness](https://github.com/Yifan-Lan/awesome-jev-robustness)).
- No seed or temperature parameter in the API ([API reference](https://docs.typesafe.ai/api)).
- Aliases move silently; pin `jev-1.13.0` and log the response `model` field ([Models](https://docs.typesafe.ai/models)).
  Vercel does not expose the version at all ([scienthoon](https://github.com/scienthoon/jev-ood-calibration)).

### 6.5 Other limitations

- No explanations; Simon Willison flags the black-box and bias concern ([Simon Willison](https://simonwillison.net/2026/Sep/21/jev/)).
- Rate limits change without notice (section 1.7).
- Vendor is a seed-stage startup ($40M seed, DCVC); pricing sustainability unproven ([Wikipedia](https://en.wikipedia.org/wiki/Jev_(AI_model)), [TS2](https://ts2.tech/en/typesafe-ai-raises-40-million-for-jev-but-its-445x-cost-claim-is-still-self-tested/)).

---

## 7. Recommended patterns for a page/document router

These combine TypeSafe's own patterns ([Speculative fan-out](https://docs.typesafe.ai/patterns/fan-out), [Confidence-gated routing](https://docs.typesafe.ai/patterns/confidence-routing), [Intent routing](https://docs.typesafe.ai/patterns/intent-routing), [How to build](https://docs.typesafe.ai/concepts/how-to-build-with-system-one)) with what the document projects and audits found.

1. **Deterministic first, Jev for the ambiguous remainder.**
   Text-layer presence, char counts, image-area ratio, vector-drawing density, font names (e.g. math fonts), encoding damage and table-line heuristics are code.
   Only call Jev when evidence conflicts, like doc-router's `jev_gated` ([GUIDE](https://github.com/misbahsy/doc-router/blob/main/docs/GUIDE.md)).
2. **Turn numbers into words before they reach Jev.**
   E.g. `"text_layer": "present, about 2,400 characters"` or `"image_coverage": "most of the page"`, because Jev is weak at numeric comparison ([jaggedness](https://docs.typesafe.ai/model-jaggedness/jev-1.13)).
3. **One page per state, many questions per request.**
   State = `{page_text_sample, previous_page_text_sample, page_evidence, document_evidence}`.
   Batch all lane questions in the same request (no interference); avoid packing many pages into one state if accuracy matters, and accept the 1,200 RPM ceiling or negotiate enterprise limits.
   If throughput forces multi-page states, measure the accuracy loss first; doc-router does 50 pages per call but only asks a narrow readability question.
4. **Pass the previous page.** It fixed every continuation-page error in the Classmethod test.
5. **Ask two kinds of question about lanes.**
   One Choice over the primary lane (with `mixed` and `uncertain`/`other` options), plus one Noul per lane-relevant property (has tables, has math, is a form, has handwriting per OCR evidence, text layer untrustworthy).
   TypeSafe: "the Choice is relative ... each Noul is absolute and can be low for all of them" ([jaggedness](https://docs.typesafe.ai/model-jaggedness/jev-1.13)); jev-doc-classification uses exactly this pairing.
   Nouls give multi-label signals (a scanned table-heavy page), which a single Choice cannot.
6. **Always include an abstain option** and route it to a fallback; without it Jev answers anyway, confidently.
7. **Write criteria as observable evidence**, not conclusions ("unit price and amount columns"), and put boundary cases in criteria ([jaggedness](https://docs.typesafe.ai/model-jaggedness/jev-1.13), [jev-doc-classification](https://github.com/lucassarcanjo/jev-doc-classification)).
   Criteria wording moved accuracy by 15-30 points in several audits.
8. **Keep document text from steering the router.**
   Put page text in a clearly named field, say in instructions that it is content to be classified, and keep the filename out ([jev-doc-classification](https://github.com/lucassarcanjo/jev-doc-classification)).
   Injection that looks like evidence can still move answers.
9. **Thresholds: fit them yourself.**
   Build a labelled page set, pin `jev-1.13.0`, fit isotonic or Platt calibration per question, pick thresholds per lane by the cost of a wrong lane (a scanned page sent to the born-digital fast path is a silent quality failure; the reverse only costs OCR money).
   Use `probabilities`, not `confidence`.
   Re-run a fixed probe set daily to detect drift ([jev-calibration-audit drift ledger](https://github.com/jujumilk3/jev-calibration-audit)).
10. **Cascade.** Low-confidence or `uncertain` pages go to a stronger router (a VLM that sees the page image) or human review; high-confidence ones go straight to the lane ([SDE cascade](https://docs.typesafe.ai/cookbooks/sde_cascade), [OpenRouter verified cascade](https://openrouter.ai/docs/cookbook/evaluate-and-optimize/jev-verified-cascade)).
11. **Hierarchical taxonomy** if lanes grow: coarse lane then sub-lane with beam search, and fall back to the parent level when confidence is low ([Hierarchical classification](https://docs.typesafe.ai/cookbooks/hierarchical_classification), [Classification using confidence](https://docs.typesafe.ai/cookbooks/classification_using_confidence)).
12. **Design for vendor swap.** The `/v1/systemone` shape is also served by Kev and other open models, so the router can be moved in-house later without code changes, subject to the MCA distillation clause.

Sketch of a per-page request for our lanes (my proposal, untested):

```json
{
  "model": "jev-1.13.0",
  "state": {
    "page_evidence": {
      "text_layer": "present, about 1,800 characters, no encoding problems",
      "images": "one image covering most of the page",
      "vector_lines": "dense ruled grid",
      "fonts": "Times, Courier",
      "first_pass_ocr_quality": "not run"
    },
    "page_text_sample": ["<first ~60 lines from text layer or fast OCR>"],
    "previous_page_text_sample": ["<first ~30 lines>", "or null"]
  },
  "questions": {
    "lane": {"type": "choice",
      "instructions": "`page_text_sample` and `page_evidence` describe one PDF page. Which processing lane fits this page best? Use `previous_page_text_sample` only as context.",
      "criteria": {
        "born_digital": "Reliable text layer, ordinary prose or simple layout.",
        "scanned_ocr": "No usable text layer or the text layer looks like a bad earlier OCR.",
        "table_heavy": "Most content is rows and columns of values.",
        "form": "Labelled fields, boxes or checkboxes to fill.",
        "math_heavy": "Equations or mathematical notation dominate.",
        "code": "Source code or configuration listings dominate.",
        "image_heavy": "Mostly figures or photos with little text.",
        "degraded": "Text present but garbled, fragmentary or noisy.",
        "mixed": "Several of the above in substantial amounts.",
        "uncertain": "The evidence is not enough to decide."
      }},
    "has_tables": {"type": "noul", "instructions": "Does the page contain at least one table?"},
    "has_math": {"type": "noul", "instructions": "Does the page contain mathematical equations?"},
    "text_layer_trustworthy": {"type": "noul", "instructions": "Is `page_text_sample` readable text that matches a normal document, rather than garbage, a watermark only, or broken encoding?"},
    "is_continuation": {"type": "noul", "instructions": "Does `page_text_sample` continue the same document as `previous_page_text_sample`?"}
  }
}
```

---

## 8. What I could not verify

- Current waitlist status and time-to-access as of today.
- Actual retention period for non-enterprise API traffic, and the subprocessor list.
- Whether the 64k vs 32k context figures describe the same limit.
- Any independent calibration study on page-lane routing specifically (none found; the closest are DocJev, doc-router and Classmethod, all small).
- Any image/PDF input roadmap date.
- Architecture claims (transformer vs diffusion vs "new architecture"), and TypeSafe's collapsed launch-FAQ answers (not in the static HTML).
- TechCrunch and Forbes articles (fetch failed); I relied on Wikipedia's summary of them.
- Most independent studies are one-person, launch-week, often n < 1,000; several conflict (e.g. option-order effects).
