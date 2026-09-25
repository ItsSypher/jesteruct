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

`jst evaluate` with the shipped settings: evidence e3, policy p3, one page per Jev request and calibration `c2-2ecc2176bc` (M4 laptop, Apple Vision OCR, Gemini 3.8 Flash, 2026-09-25).
`evalset/` holds the 98 cases the evidence was first tuned on; `evalset/fresh/` holds 1,722 cases labelled later, and its holdout split was never fitted on (decision 8).

| Metric | `evalset/` | `evalset/fresh/` holdout |
|---|---|---|
| Candidate lane right | 0.959 | 0.891 |
| Sent to review (LH) | 17.3% | 24.0% |
| Silent wrong lane (kept, and wrong) | 0.0% | 6.2% |
| Silent under-routing (kept, and too weak) | 0.0% | 3.5% |

The grown set is harder than the first 396 fresh pages suggested.
Those reach 0.929, while the pages added for issue #6, drawn towards the lane boundaries, reach 0.880 in tune and 0.891 in holdout.
Born-digital PDFs are the weakest group, at 0.849 against 0.918 for image pages: 21 L2 pages go to L1, 17 L1 pages go to L2, and Jev trusts the text layer of 33 scanned pages.
Most of the remaining mistakes are confident ones, which review cannot catch (decision 7); issue #9 collects them for the next evidence version.

Latency and cost were measured on a cold cache on 2026-09-24, on the 98 cases and the first 396 fresh ones.
Born-digital pages take 0.4 s at p50, and all pages 5.1-5.4 s at p50 and 14 s at p95, for about $2.70-2.80 per 1,000 pages; the vision call dominates both.

The same 1,722 pages sent through the OrbStack deployment with `jst evaluate --api`, where Linux workers use RapidOCR, routed as well as the Mac: 0.895 candidate accuracy on both, and 6.1% silently wrong on holdout against 6.2%.
Their candidate lanes differed on 43 pages, 19 of which Apple Vision had right and 18 RapidOCR, so the OCR backend still does not change routing quality.
Which pages differ is telling.
RapidOCR reads handwritten Chinese notes fluently, and Jev then takes them for clean print (L3 rather than L5); Apple Vision's English-only pass fails on them, and that failure is what sends them to L5.
KEDA took the workers from 0 to 8 on OrbStack's 10-CPU VM, where each used about one core and together they routed about two pages a second: on image pages the bound was CPU OCR, not Jev's request limit (decision 6).

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
            └──► Valkey stream jst:jobs ──────────► ▲  scaled by KEDA on stream length
Studio ◄── API ◄── Valkey stream jst:events ◄──────── workers report each page's progress
```

The object store holds everything durable: inputs, manifests, thumbnails and the provider response cache.
Valkey holds only coordination: the job stream, job status, the shared rate limiter and the capped stream of progress events.
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
Version e3 closes the gaps the fresh set's first 396 pages exposed:
- Inline mathematics.
  The layout model finds only displayed formulas, so e2's "no formulas" talked Jev out of L2 on pages full of inline notation.
  e3 says "formula blocks", and adds a clause when mathematical symbols pass 8 in every 1,000 characters; born-digital L1 pages stay below 5.2.
  Jev then recognised the notation (`has_math`) but still read the equations of `complex_layout` as displayed ones, so policy p3 sends a page with mathematical notation to L2 as well.
- Degraded flatbed scans.
  Photocopies, bleed-through and book spreads were called flatbed scans with mild issues, and went to L3.
  The vision check now names the defects that make characters harder to read, and Jev answers a matching `capture_defects` question (policy p2).

Born-digital pages improved on both sets: 15 to 16 of 17 right on `evalset/`, and 76 to 82 of 88 on those 396.
On vision-checked pages their too-weak candidates fell from 17 to 8 of 308, while `evalset/` lost 3 of 81; e2 was perfect there, having been tuned on it.
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
Jev never abstains, and the product of its answers along the rule path is not a probability.
`calibrate.py` fits an isotonic curve per candidate lane on `jst evaluate` results, mapping that product to the probability that the lane is right.
Review is the cheaper choice when the probability is below 1 - 1/r, where r is what one silent wrong lane costs in reviews.
The shipped calibration uses r = 10, so pages below 0.9 go to LH (issue #3).
It is fitted on the fresh set's tune split alone, and on its holdout split:

| Review rule | Sent to review | Silent wrong lane | Silent under-routing |
|---|---|---|---|
| Raw product below 0.5 | 3.3% | 9.4% | 5.0% |
| Calibrated, r = 5 | 8.7% | 8.1% | 4.6% |
| Calibrated, r = 10 (shipped) | 24.0% | 6.2% | 3.5% |
| Calibrated, r = 20 | 54.7% | 1.4% | 0.8% |

The previous calibration, fitted on the first 494 labelled pages, reviewed 13.4% of holdout and left 7.3% silently wrong: the same cost at r = 10, with more of it silent.
Five-fold cross-validation on tune found no curve shape that generalises better; per lane or pooled, isotonic or logistic, all cost 0.62-0.70 per page at r = 10, counting a review as 1 and a silent wrong lane as 10.
Calibration cannot catch a confident mistake, and most of the remaining ones are confident.
For L2 candidates the raw product hardly separates right from wrong (AUC 0.56, against 0.74-0.89 for the other lanes), so the next gain has to come from the evidence (issue #9).
`jst calibrate --cost-ratio` refits for a different trade-off.
A calibration records the answer basis it was fitted on: evidence and policy versions, question set, models and batch size.
The router applies it only on the same basis and otherwise falls back to `review_threshold` with a warning, so an evidence change never runs under a stale curve.
The OCR backend is left out of the basis because it does not change routing, so the curve fitted on the Mac also serves the Linux containers.

**8. Two labelled sets, labels that can be sets, and a holdout.**
`evalset/` (98 cases) tuned evidence e1 and e2.
`evalset/fresh/` (1,722 cases from public benchmarks and web documents, rebuilt byte for byte by `evalset/fresh/build.py`) was labelled afterwards, disjoint from it, to calibrate review and to check evidence changes (issues #3 and #6).
Every page is labelled blind, from the image the router sees and with nothing that names its source.
Labeller A is Claude and labeller B a model of another family (`openai/gpt-6-luna-pro`); where they disagree, adjudicator C, also blind, decides.
Where a lane is genuinely arguable, the label is a set such as L3/L4, and either lane counts as right: opinions that differ across only one boundary give the set.
A and B agreed on 74.5% of the capture pages and 93.4% of the layout pages (`evalset/fresh/LICENSES.md` has the rest).
The set is split once, by source document, and `split.json` never changes.
`tune` (1,064 cases) holds all of the first build's 396, which shaped e3, and half of the new pages; the calibration is fitted on it and evidence is developed against it.
`holdout` (658 new cases, drawn towards the L3/L4 and L1/L2 boundaries) is never fitted on, so its numbers are the ones that count.
An evidence or policy change is judged on `evalset/` and both splits.
The page files (281 MB) are the release asset `evalset-fresh-v2`, which `build.py fetch` downloads and checks against every case's sha256.

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
KEDA scales workers on the stream's length: acked messages are deleted, so it is exactly the unfinished work, whereas Valkey stops reporting the group's lag once entries are deleted. arq's sorted set cannot be scaled on.
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
`auto` first checks, once and in a child process, that Apple Vision answers, and falls back to RapidOCR when it does not.
The check allows 180 s because after a macOS update Vision recompiles its Neural Engine models (26-59 s on an M4), and it keeps them only for a caller that outlives the compile.
A shorter deadline, like the probe pool's 60 s task timeout on ten cold workers at once, kills every caller first: the cache never fills, and the compiler keeps a core busy for callers that are already dead.

**15. Cloud-agnostic deployment.**
Storage is addressed by URL (`s3://`, `gs://`, `az://`, `file://`), and Valkey is any Redis-protocol service.
The charts know nothing about where those come from.
Terraform deploys onto any kubeconfig; creating the cluster itself is left to each cloud.

Constraints:
- Valkey must run without cluster mode, because the queue's scripts touch the job hash and the stream together.
- The local environment passes the OpenRouter key to Terraform, so its gitignored state file holds it. Cloud environments reference an existing secret instead.

**16. Live progress is a capped Valkey stream, relayed as Server-Sent Events.**
Workers append one event per step to `jst:events`: the job's lifecycle, each document found, and each page's probe, OCR, vision, Jev and policy steps with their timings and what each measured.
The stream is capped at 20,000 events, a few minutes at full throughput and about 30 MB of Valkey memory, because it is a live feed; manifests remain the record.
Each API process reads the stream once and fans it out at `GET /v1/events`, replaying recent history first, so a viewer can join late, and resuming by `Last-Event-ID` after a dropped connection.
Server-Sent Events rather than WebSockets, because the flow is one way, it is plain HTTP through any ingress, and browsers reconnect and resume on their own.
Events are advisory: emitting is one XADD, a failure to emit is logged and never fails a job, and events never carry page text.

**17. The Studio is static files that the API serves.**
It is built into the same image and served at `/` from `JST_WEB_DIR`, so there is one origin, no CORS and nothing new to deploy or scale; an Ingress (optional in the chart) exposes both.
It is Svelte 5 with no component library, and the flow is drawn by hand-written WGSL on WebGPU in two instanced draws a frame, falling back to Canvas 2D when WebGPU is missing or its device is lost.
Text and controls are HTML over the canvas, so they stay crisp and accessible.
Measured in headless Chrome during a demo: 0.07 ms of script per frame at p50 with WebGPU (0.10 ms with Canvas 2D), 17.7 ms frame interval at p99, and 36 kB of JavaScript gzipped.
The flow is fed by the event stream of decision 16; a document routed before is replayed from its manifest's recorded timings, and with no API it replays a recorded demo.

**18. Deliberately not in v1:**
- lane executors (the processing itself);
- a learned router: Jev is the classifier, and its terms bar training on its outputs.
