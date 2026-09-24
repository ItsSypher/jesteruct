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
   - the PDF text layer and structure (image coverage, invisible OCR text, fonts, producer, a column estimate);
   - a 1024 px render with image-quality measures;
   - text statistics.
3. `policy.text_layer_trusted` is a cheap rule. When a page has no trustworthy text layer, it gets a quick OCR pass and a Gemini 3.8 Flash vision check, run in parallel.
4. `evidence.py` turns the measurements into short descriptions.
5. One Jev request asks five routing questions, plus modifier, degradation and continuation questions.
6. `policy.py` maps the five answers to a lane with a fixed rule table. The product of the answers along the rule path is the page's confidence; below `review_threshold` the page goes to LH, keeping its candidate lane.
7. `segment.py` groups pages, and the manifest is written to the object store.

## Measured

`jst evaluate` on the 98 labelled cases in `evalset/` (M4 laptop, Apple Vision OCR, Gemini 3.8 Flash, 2026-09-24):

| Metric | Value |
|---|---|
| Lane accuracy (candidate lane) | 0.929 |
| Silent under-routing (final lane too weak) | 2.0% |
| Sent to review (LH) | 5.1%, and 4 of those 5 had a wrong candidate lane |
| Page latency, born-digital PDF | p50 0.4 s |
| Page latency, all pages | p50 3.9 s, p95 14 s (the vision call dominates) |
| Cost | about $2.10 per 1,000 pages, nearly all vision |

The same evaluation inside the Linux container, with RapidOCR in place of Apple Vision, gives:
- 0.939 candidate accuracy;
- 2.0% silent under-routing;
- 4.1% sent to review.

So the OCR backend does not change routing quality.
CPU OCR is slower: about 5 s per page at p50 on image pages.

`make smoke` on OrbStack Kubernetes:
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
The phrases in `evidence.py` are versioned (`EVIDENCE_VERSION`) and reproduce the benchmark's evidence exactly (tested).
They were tuned on 98 cases, so retuning needs a fresh labelled set.

**3. Vision only where the text layer cannot be trusted.**
Skipping the vision check on pages whose text layer passes the cheap rule cost no accuracy in the benchmark.
On real corpora, most pages are born-digital, and those pages then cost one Jev call.

**4. One provider gateway, cached and rate limited.**
Jev and Gemini both go through OpenRouter in `providers.py`.
Every response is cached in the object store under a hash of its request, so replays are free and deterministic.
A GCRA limiter in Valkey shares each provider's request budget across all replicas.

**5. Capacity is bounded by Jev's request limit.**
At 1,000 requests a minute (below Jev's 1,200), the whole system routes about 16 pages a second, so KEDA caps workers at 6.
The levers beyond that are an enterprise limit, or packing several pages into one request (to be measured first).

**6. Review comes from probabilities.**
Jev never abstains.
The product of its answers along the rule path gives a confidence, and pages below `review_threshold` go to LH.
The raw answers are kept in the manifest for later calibration.

**7. Failures degrade; they never crash a job or flood review.**

| Failure | Handling |
|---|---|
| Transient provider errors | Retried with jitter until a deadline |
| Provider still unavailable, or credentials or billing rejected (401/402/403) | The job is redelivered; after 3 deliveries it is dead-lettered |
| A rejected request (4xx, invalid output) | That page goes to LH with the reason |
| A probe that crashes or times out | Retried once; then that page goes to LQ |
| A hostile or broken file | LQ with a reason code |

**8. Idempotent by construction.**
The route key hashes everything that can change a route: code, evidence and policy versions, question set, models, OCR backend and review threshold.
Job ids combine the input hash with the route key, so duplicate submissions collapse into one job.
Manifests live at `manifests/{doc_sha}/{route_key}.json`, and existing ones are reused.

**9. Valkey Streams with a small consumer, not a task framework.**
KEDA can scale on stream lag; arq's sorted set cannot be scaled on.
Celery fights asyncio, and NATS would add a second stateful service.
The consumer is about 150 lines: heartbeats, reclaiming stalled messages, dead-lettering.

**10. No synchronous route endpoint.**
`POST /v1/jobs?wait=20` returns the manifest when it finishes in time, and 202 otherwise.
All work flows through the queue, so API pods stay light and KEDA sees every page of work.

**11. CPU work in a pebble process pool.**
pdfium is not thread-safe, and a hostile PDF can crash its process.
pebble gives per-task timeouts, replaces crashed workers and recycles processes.
The pool size comes from the container's CPU limit.

**12. OCR differs by platform, behind one function.**
Apple Vision runs natively on macOS, and RapidOCR (ONNX) runs in Linux containers.
The backend is part of the route key.

**13. Cloud-agnostic deployment.**
Storage is addressed by URL (`s3://`, `gs://`, `az://`, `file://`), and Valkey is any Redis-protocol service.
The charts know nothing about where those come from.
Terraform deploys onto any kubeconfig; creating the cluster itself is left to each cloud.

Constraints:
- Valkey must run without cluster mode, because the queue's scripts touch the job hash and the stream together.
- The local environment passes the OpenRouter key to Terraform, so its gitignored state file holds it. Cloud environments reference an existing secret instead.

**14. Deliberately not in v1:**
- lane executors (the processing itself);
- a layout model: 0.94 without one;
- a learned router: Jev is the classifier, and its terms bar training on its outputs.
