# Architecture

jesteruct decides, page by page, which processing lane a document belongs in.
It does not process documents.
It writes a versioned route manifest that the processing lanes consume.

## Lanes

| Lane | Meaning |
|---|---|
| L0 | Native office or text format, no rendering needed |
| L1 | Born-digital, simple layout |
| L2 | Born-digital with tables, equations, code or columns |
| L3 | Clean scan or image, needs OCR |
| L4 | Degraded scan, camera photo or fax |
| L5 | Mostly handwritten |
| LQ | Quarantine: encrypted, corrupt, unsupported or over limits |
| LH | Human review: the router is not confident |

Each page also carries modifiers (table, math, code, form, handwriting, multi_column, script, rtl), a degradation score and a continuation probability.
Runs of pages form segments, so a lane receives page ranges instead of single pages.

## How a page is routed

```
file ──► intake ──► per page: probes ──► [OCR + vision] ──► evidence ──► Jev ──► policy ──► segments ──► manifest
          │                 (process pool)  (untrusted pages)   (words)    (1 call)  (rule table)
          └─ containers expand into child documents; bad inputs go to LQ
```

1. `intake.py` sniffs each file by its bytes, expands zip and email containers into child documents, and applies limits.
2. `probes/` measure the page cheaply:
   - the PDF text layer and structure (image coverage, invisible OCR text, fonts, producer);
   - a 1024 px render with image-quality measures;
   - a small layout model's regions: tables, formulas, figures and a column estimate;
   - text statistics.
3. `policy.text_layer_trusted` is a cheap rule.
   When a page has no trustworthy text layer, it gets a quick OCR pass and a Gemini 3.8 Flash vision check, run in parallel.
   On a PDF page the fresh OCR is also compared with the embedded layer.
4. `evidence.py` turns the measurements into short descriptions.
5. One Jev request asks six routing questions, plus modifier, degradation and continuation questions.
6. `policy.py` maps the routing answers to a lane with a fixed rule table.
   The product of the answers along the rule path is the page's raw confidence.
   The shipped calibration turns it into the probability that the lane is right, and below the threshold the page goes to LH, keeping its candidate lane.
7. `segment.py` groups pages, and the manifest is written to the object store.

## Measured

`jst evaluate` on both labelled sets with the shipped settings: evidence e3, policy p3, one page per Jev request and calibration `c2-b7e43e4002` (M4 laptop, Apple Vision OCR, Gemini 3.8 Flash, 2026-09-24).
`evalset/` holds the 98 cases the evidence was first tuned on; `evalset/fresh/` holds 396 cases labelled later from nine public benchmarks, disjoint from the first.

| Metric | `evalset/` | `evalset/fresh/` |
|---|---|---|
| Candidate lane right | 0.959 | 0.939 |
| Sent to review (LH) | 10.2% | 15.9% |
| Silent wrong lane (kept, and wrong) | 0.0% | 1.0% |
| Silent under-routing (kept, and too weak) | 0.0% | 0.3% |
| Page latency, born-digital PDF | p50 0.4 s | p50 0.4 s |
| Page latency, all pages | p50 5.4 s, p95 14 s | p50 5.1 s, p95 14 s |
| Cost per 1,000 pages | about $2.80 | about $2.70 |

The vision call dominates both latency and cost.
The calibration was fitted on both sets, so its review numbers are in-sample; fitted on the fresh set alone it sent 10.2% of `evalset/` to review and left 1.0% silently wrong (decision 7).
The fresh set also showed where the evidence was weak, so its lane accuracy is optimistic for unseen documents.

Measured on evidence e1, the Linux container with RapidOCR in place of Apple Vision routed as well as the Mac (0.939 against 0.929 candidate accuracy), so the OCR backend does not change routing quality.
CPU OCR is slower: about 5 s per page at p50 on image pages.

`make smoke` on OrbStack Kubernetes (router v1 with evidence e1):
- 43 real documents went through the API.
- KEDA took the workers from 0 to 6.
- A worker killed mid-job without a grace period had its jobs reclaimed.
- All 43 jobs finished, with 0 dead letters.

## Runtime

One library, two ways to run it.

- **Native** (`jst route`, `jst evaluate`): everything in one process plus a process pool. Apple Vision OCR is used on macOS.
- **Service:** a stateless API and stateless workers, one container image and two roles.

```
client ─► API ─► object store (inputs/)            workers ─► object store (manifests/, thumbs/, cache/)
            └──► Valkey stream jst:jobs ──────────► ▲  scaled by KEDA on stream lag
```

The object store holds everything durable: inputs, manifests, thumbnails and the provider response cache.
Valkey holds only coordination: the job stream, job status and the shared rate limiter.
Kubernetes resources come from two Helm charts: `deploy/helm/jesteruct` for the app, and `deploy/helm/devstack` with Valkey and SeaweedFS for local use.
Terraform installs them onto any cluster (`infra/terraform/envs/local` for OrbStack, `envs/cloud` for managed services).

## Decisions

**1. Jev is the classifier, asked narrow questions.**
One multi-option lane question reached 0.80 accuracy in the benchmark.
Five yes/no questions with a rule table in code reached 0.92-0.94, with 3% of pages sent too low, at a tenth of the latency of general LLMs given the same evidence (`bench/jev_lanes/REPORT.md`).
The rule table and question wording live in `policy.py` under `POLICY_VERSION`, because changing either changes behaviour and needs an eval run.

**2. Evidence is described in words, with frozen bins.**
Jev reasons poorly over raw numbers.
The phrases in `evidence.py` are versioned (`EVIDENCE_VERSION`), and each version changes only together with an eval run.
Version e1 reproduced the benchmark's evidence exactly; a test still holds the e1 part of every born-digital page to it.
Version e2 closed two gaps the benchmark left (issue #4).
It adds the layout model's regions, and on PDF pages it says whether the text layer agrees with a fresh OCR pass, because a layer that disagrees is usually OCR run over handwriting.
Version e3 closes the gaps the fresh set exposed:
- Inline mathematics.
  The layout model finds only displayed formulas, so e2's "no formulas" talked Jev out of L2 on pages full of inline notation.
  e3 says "formula blocks", and adds a clause when mathematical symbols pass 8 in every 1,000 characters; born-digital L1 pages stay below 5.2.
  Jev then recognised the notation (`has_math`) but still read the equations of `complex_layout` as displayed ones, so policy p3 sends a page with mathematical notation to L2 as well.
- Degraded flatbed scans.
  Photocopies, bleed-through and book spreads were called flatbed scans with mild issues, and went to L3.
  The vision check now names the defects that make characters harder to read, and Jev answers a matching `capture_defects` question (policy p2).

Born-digital pages improved on both sets: 15 to 16 of 17 right on `evalset/`, and 76 to 82 of 88 on the fresh set.
On vision-checked pages the fresh set's too-weak candidates fell from 17 to 8 of 308, while `evalset/` lost 3 of 81; e2 was perfect there, having been tuned on it.
Across all 494 labelled pages, 466 candidate lanes are right against 458, and too-weak candidates fall from 28 to 12.

**3. A small layout model, not a large one.**
The projection-profile column estimate e1 used read slide bullets as columns.
360LayoutAnalysis's YOLOv8n "general6" detector, run through rapid-layout on ONNX Runtime, takes about 20 ms a page on one CPU thread.
Of the models tried it came closest to PP-DocLayoutV3 on columns and tables, and V3 takes about 600 ms.
Columns come from body-text regions that sit side by side over at least a fifth of the text's own height; titles are left out, because slide bullets often come out as titles.
Measured against the page height, as e2 did, a newsletter's banner, photo and white space hid its columns; no born-digital L1 page in either labelled set has any side-by-side text at all.
The weights are baked into the image.
Licence: the code is Apache-2.0, but the weights carry 360's own model licence, which asks commercial users to apply first, and they were trained with Ultralytics YOLOv8 (AGPL-3.0).
Licences are not a constraint for now; this one needs settling before commercial use.

**4. Vision only where the text layer cannot be trusted.**
Skipping the vision check on pages whose text layer passes the cheap rule cost no accuracy in the benchmark.
On real corpora, most pages are born-digital, and those pages then cost one Jev call.

**5. One provider gateway, cached and rate limited.**
Jev and Gemini both go through OpenRouter in `providers.py`.
Every response is cached in the object store under a hash of its request, so replays are free and deterministic.
A GCRA limiter in Valkey shares each provider's request budget across all replicas.

**6. Capacity is bounded by Jev's request limit.**
At 1,000 requests a minute (below Jev's 1,200), the whole system routes about 16 pages a second, so KEDA caps workers at 6.
`JST_JEV_BATCH_SIZE` packs several pages into one request, which multiplies that ceiling, but it costs quality, so the default is one page (issue #2).
Three cold runs of the 98 cases at each size measured it:

| Pages per request | Candidate accuracy | Cases whose lane changed between runs |
|---|---|---|
| 1 | 0.980, 0.980, 0.980 | 0 |
| 2 | 0.949, 0.969, 0.959 | 7 |
| 4 | 0.949, 0.949, 0.980 | 4 |

A page's answers move only a little in a shared request (median 0.01), but they move with whichever pages share it, and that is enough to flip borderline pages.
One page per request is the only setting where a route depends on nothing but its page.
Past 16 pages a second, the clean lever is a higher Jev limit; batching is there for bulk backfills that can give up about two points of accuracy (0.959 on average at 2 or 4 pages, against 0.980).

**7. Review comes from calibrated probabilities.**
Jev never abstains, and the product of its answers along the rule path is not a probability: at a raw threshold of 0.5, review caught only 5 of the 24 wrong candidate lanes on the fresh set.
`calibrate.py` fits an isotonic curve per candidate lane on `jst evaluate` results, mapping that product to the probability that the lane is right.
Review is the cheaper choice when the probability is below 1 - 1/r, where r is what one silent wrong lane costs in reviews.
The shipped calibration uses r = 10, so pages below 0.9 go to LH (issue #3).
Fitted on the fresh set and checked on `evalset/`:

| Review rule | Sent to review | Silent wrong lane | Silent under-routing |
|---|---|---|---|
| Raw product below 0.5 | 2.0% | 4.1% | 1.0% |
| Calibrated, r = 5 | 7.1% | 2.0% | 0.0% |
| Calibrated, r = 10 (shipped) | 10.2% | 1.0% | 0.0% |
| Calibrated, r = 20 | 17.3% | 0.0% | 0.0% |

Per-lane curves sent fewer pages to review than one curve for all lanes, for the same or fewer errors, at every r (10.2% against 16.3% at r = 10).
`jst calibrate --cost-ratio` refits for a different trade-off.
A calibration records the answer basis it was fitted on: evidence and policy versions, question set, models and batch size.
The router applies it only on the same basis and otherwise falls back to `review_threshold` with a warning, so an evidence change never runs under a stale curve.
The OCR backend is left out of the basis because it does not change routing, so the curve fitted on the Mac also serves the Linux containers.

**8. Two labelled sets, and labels that can be sets.**
`evalset/` (98 cases) tuned evidence e1 and e2.
`evalset/fresh/` (396 cases from nine public benchmarks, rebuilt byte for byte by `evalset/fresh/build.py`) was labelled afterwards, disjoint from it, to calibrate review and to check the evidence (issue #3).
Where a lane is genuinely arguable, the label is a set such as L3/L4, and either lane counts as right.
A page gets a set label when two labellers disagree.
The L4 pages the router sent to L3 had a blind second look, mixed with as many pages it routed to L4, and the 17 that the second labeller saw as clean or borderline now accept either lane; every control page kept its label.
An evidence or policy change is judged on both sets together, because the first is the set the old bins were tuned on.
Issue #3 asked for 1,500 pages; at about 140 KB a page that is 200 MB in git, so the set stops at 396 until its files move out of the repository.

**9. Failures degrade; they never crash a job or flood review.**

| Failure | Handling |
|---|---|
| Transient provider errors | Retried with jitter until a deadline |
| Provider still unavailable, or credentials or billing rejected (401/402/403) | The job is redelivered; after 3 deliveries it is dead-lettered |
| A rejected request (4xx, invalid output) | That page goes to LH with the reason |
| A probe that crashes or times out | Retried once; then that page goes to LQ |
| A hostile or broken file | LQ with a reason code |

**10. Idempotent by construction.**
The route key hashes everything that can change a route: the answer basis (evidence and policy versions, question set, models, Jev batch size), the code version, OCR backend, calibration version and review threshold.
Job ids combine the input hash with the route key, so duplicate submissions collapse into one job.
Manifests live at `manifests/{doc_sha}/{route_key}.json`, and existing ones are reused.

**11. Valkey Streams with a small consumer, not a task framework.**
KEDA can scale on stream lag; arq's sorted set cannot be scaled on.
Celery fights asyncio, and NATS would add a second stateful service.
The consumer is about 150 lines: heartbeats, reclaiming stalled messages, dead-lettering.

**12. No synchronous route endpoint.**
`POST /v1/jobs?wait=20` returns the manifest when it finishes in time, and 202 otherwise.
All work flows through the queue, so API pods stay light and KEDA sees every page of work.

**13. CPU work in a pebble process pool.**
pdfium is not thread-safe, and a hostile PDF can crash its process.
pebble gives per-task timeouts, replaces crashed workers and recycles processes.
The pool size comes from the container's CPU limit.

**14. OCR differs by platform, behind one function.**
Apple Vision runs natively on macOS, and RapidOCR (ONNX) runs in Linux containers.
The backend is part of the route key.

**15. Cloud-agnostic deployment.**
Storage is addressed by URL (`s3://`, `gs://`, `az://`, `file://`), and Valkey is any Redis-protocol service.
The charts know nothing about where those come from.
Terraform deploys onto any kubeconfig; creating the cluster itself is left to each cloud.

Constraints:
- Valkey must run without cluster mode, because the queue's scripts touch the job hash and the stream together.
- The local environment passes the OpenRouter key to Terraform, so its gitignored state file holds it. Cloud environments reference an existing secret instead.

**16. Deliberately not in v1:**
- lane executors (the processing itself);
- a learned router: Jev is the classifier, and its terms bar training on its outputs.
