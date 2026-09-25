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
file ──► intake ──► per page: probes ──► [vision (+ OCR check)] ──► evidence ──► Jev ──► policy ──► segments ──► manifest
          │                 (process pool)  (pages without a trusted layer)  (words)   (1 call)  (rule table)
          └─ containers expand into child documents; bad inputs go to LQ
```

1. `intake.py` sniffs each file by its bytes, expands zip and email containers into child documents, and applies limits.
2. `probes/` measure the page cheaply, in about 50 ms of CPU:
   - the PDF text layer and structure (image coverage and hidden OCR text at any form depth, fonts, producer);
   - a 1024 px render with image-quality measures;
   - a small layout model's regions: tables, formulas, figures and a column estimate;
   - text statistics, and the text layer's language and readability in any language (decision 18).
3. `policy.text_layer_trusted` is a cheap rule: a layer that reads as language and is not an OCR layer over a scan.
   Every other page gets a Gemini 3.8 Flash vision check.
   A PDF page whose untrusted layer has text also gets a quick OCR pass, in parallel, compared with that layer; image files and scans without text get none (decision 14).
4. `evidence.py` turns the measurements into short descriptions.
5. One Jev request asks six routing questions, plus modifier, degradation and continuation questions.
6. `policy.py` maps the routing answers to a lane with a fixed rule table.
   The product of the answers along the rule path is the page's raw confidence.
   The shipped calibration turns it into the probability that the lane is right, and below the threshold the page goes to LH, keeping its candidate lane.
7. `segment.py` groups pages, and the manifest is written to the object store.

## Measured

`jst evaluate` on the cloud path with the shipped settings: evidence e4, policy p4, one page per Jev request, calibration `c2-8a88087037`, RapidOCR for the layer check and Gemini 3.8 Flash (2026-09-25).
`evalset/` holds the 98 cases the evidence was first tuned on; `evalset/fresh/` holds 1,717 cases labelled later, and its holdout split was never fitted on or looked at while e4 was developed (decision 8).

| Metric | `evalset/` | `evalset/fresh/` holdout | e3 on the same holdout |
|---|---|---|---|
| Candidate lane right | 0.949 | 0.945 | 0.907 |
| Candidate too weak | 2.0% | 2.4% | 5.1% |
| Sent to review (LH) | 24.5% | 21.4% | 24.6% |
| Silent wrong lane (kept, and wrong) | 1.0% | 2.8% | 4.3% |
| Silent under-routing (kept, and too weak) | 1.0% | 1.4% | 1.8% |

The e3 column is e3's RapidOCR run with its own calibration, scored on the corrected labels.
On holdout, e4 gets 25 more candidate lanes right, halves the candidates that are too weak, and leaves a third fewer pages silently wrong while sending fewer to review.
The gains come from reading text layers in any language (decision 18), from finding the OCR layers the e3 probe missed, from a rule table that uses Jev's own code, table, form and maths answers, and from dropping OCR evidence on image pages (decision 14).

Per page, the probes take about 50 ms of CPU, and the 7% of PDF pages whose layer is checked add about 1 s of OCR; under e3 every image page also ran OCR, 4-5 CPU-seconds.
Latency and cost were last measured on a cold cache on 2026-09-24: born-digital pages take 0.4 s at p50, and pages that need the vision check about 5 s at p50 and 14 s at p95, for about $2.70-2.80 per 1,000 pages; the vision call dominates both, and e4 makes it on about 5% fewer pages.

Sent through the OrbStack deployment with `jst evaluate --api`, all 1,717 fresh pages got the same candidate lane on the Linux workers as in the local run.
With provider responses cached, so that only the router itself is measured, two workers routed about 7.7 pages a second over the run and 13 at peak; under e3, eight workers managed two, bound by OCR's CPU.

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

Version e4 (issue #9), with policy p4, closes the gaps the grown fresh set exposed, and was developed on its tune split alone:
- OCR text no longer reaches Jev (decision 14).
  RapidOCR reads handwritten Chinese as fluently as print, and a fluent read outvoted the vision check's own finding of handwriting.
- The vision check is put in plain phrases, such as "some characters are harder to read", "a flatbed scan, not a camera photo or fax" and "a printed page with only handwritten notes", where raw values like `mild_issues` and `annotations_only` let Jev hedge.
  Soft defects (copy grain, show-through, speckle, fading) are left out when the vision check reads the text as clean, as the labelling rubric counts them clean.
- The PDF probe finds OCR layers at any form depth and under a covering image, with image coverage in page space, and says when a page has no mathematical fonts or symbols.
  When the layout model finds no text, the text layer's own column estimate stands.
- Text layers are described by the language they read as, in any language, instead of by English words (decision 18).
- Policy p4 counts Jev's code, table and form answers as complex layout, and words `heavily_degraded`, `camera_or_fax` and `mostly_handwritten` after the labelling rubric.

On the 1,161 tune and `evalset/` pages, candidate accuracy rose from 0.920 to 0.945 and too-weak candidates fell from 4.8% to 3.4%; holdout agreed (Measured).

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
Since e4 the rule trusts layers in any language (decision 18); on the tune set that saved the vision call on 5% of pages, and on a corpus in another language it saves it on nearly every born-digital page.

**5. One provider gateway, cached and rate limited.**
Jev and Gemini both go through OpenRouter in `providers.py`.
Every response is cached in the object store under a hash of its request, so replays are free and deterministic.
A GCRA limiter in Valkey shares each provider's request budget across all replicas.

**6. Capacity is bounded by the providers' request limits.**
At 1,000 Jev requests a minute (below its 1,200) the whole system routes about 16 pages a second, and the vision model's 600 a minute bound pages that need it to 10 a second.
A page needs about 50 ms of CPU and then waits seconds on those calls, so a worker holds 32 pages in flight (`JST_PAGE_CONCURRENCY`, and as many documents), three to six workers reach the limits, and KEDA caps workers at 6.
Under e3 every image page also ran OCR, 4-5 CPU-seconds, and eight workers on OrbStack's 10-CPU VM routed about two pages a second.
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
| Raw product below 0.5 | 1.4% | 5.2% | 2.3% |
| Calibrated, r = 5 | 2.5% | 4.9% | 2.1% |
| Calibrated, r = 10 (shipped) | 21.4% | 2.8% | 1.4% |
| Calibrated, r = 20 | 24.6% | 2.6% | 1.2% |

Under e3 the same rule reviewed 24.6% of holdout and left 4.3% silently wrong.
Five-fold cross-validation on tune found no curve shape that generalises better; per lane or pooled, isotonic or logistic, all cost 0.62-0.70 per page at r = 10 under e3, counting a review as 1 and a silent wrong lane as 10.
Calibration cannot catch a confident mistake, so the gains came from the evidence (decision 2).
Under e3 the raw product hardly separated right from wrong on L2 candidates (AUC 0.56), but mostly because 16 born-digital pages had been labelled as scans (decision 8); counted right, their AUC was 0.83.
`jst calibrate --cost-ratio` refits for a different trade-off.
A calibration records the answer basis it was fitted on: evidence and policy versions, question set, models and batch size.
The router applies it only on the same basis and otherwise falls back to `review_threshold` with a warning, so an evidence change never runs under a stale curve.
The OCR backend is left out of the basis because it does not change routing, so one curve serves the Linux containers and a Mac.

**8. Two labelled sets, labels that can be sets, and a holdout.**
`evalset/` (98 cases) tuned evidence e1 and e2.
`evalset/fresh/` (1,717 cases from public benchmarks and web documents, rebuilt byte for byte by `evalset/fresh/build.py`) was labelled afterwards, disjoint from it, to calibrate review and to check evidence changes (issues #3 and #6).
Every page is labelled blind, from the image the router sees and with nothing that names its source.
Born-digital PDF pages are judged on layout and every other page on capture; the rule is structural (`sources.text_layer`), since the first one also asked for 200 characters and under 1% odd characters, and sent 35 born-digital pages with TeX glyphs or little text to the capture rubric as clean scans (issue #9).
They were relabelled blind on the layout rubric, and each opinion records the rubric it was given under.
Labeller A is Claude and labeller B a model of another family (`openai/gpt-6-luna-pro`); where they disagree, adjudicator C, also blind, decides.
Where a lane is genuinely arguable, the label is a set such as L3/L4, and either lane counts as right: opinions that differ across only one boundary give the set.
A and B agreed on 73.9% of the capture pages and 93.7% of the layout pages (`evalset/fresh/LICENSES.md` has the rest).
The set is split once, by source document, and `split.json` never changes.
`tune` (1,063 cases) holds all of the first build's pages, which shaped e3, and half of the new ones; the calibration is fitted on it and evidence is developed against it.
`holdout` (654 new cases, drawn towards the L3/L4 and L1/L2 boundaries) is never fitted on or studied, so its numbers are the ones that count.
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
Each process loads the language model (about 200 MB) when it first reads a text layer.

**14. OCR only checks an untrusted PDF text layer, and differs by platform behind one function.**
On image pages OCR evidence did not help: without it, 736 tune and `evalset/` image pages routed as accurately (0.920 against 0.921) and too-weak candidates fell from 4.5% to 2.9%, because a fluent read of handwriting outvoted the vision check.
Image files and scans without a text layer therefore get no OCR, which was 4-5 CPU-seconds a page.
On a PDF page whose layer is not trusted it still earns its keep: without the check, Jev trusted 3 of 33 garbled layers, so the page is read again and compared with its layer, word by word in any script.
PP-OCRv6's tiny models, without the text-angle classifier, route those pages exactly as the small ones did at a fifth of the CPU (about 1 s a page).
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
A page's preview opens large and zooms with a trackpad pinch; `GET /v1/pages/{sha}/{page}` renders it the first time it is asked for, from the stored document (PDFs at 2400 px, images at their own resolution up to 4096 px), and keeps it, so routing never pays for it.
The API stores what it is given, and the router stores the PDFs and images it finds inside containers, so every page has a view.

**18. Text layers are read in any language.**
The cheap rule used to ask for English common words, so a born-digital page in any other language paid for the vision check (issue #7), and the evidence told Jev such a layer had few recognisable words.
`probes/language.py` asks OpenLID-v3 (HPLT; GPL-3.0) which of about 190 languages a layer reads as, in chunks of about 80 characters weighted by their letters.
The model has a label for text that is no language, so the letter-weighted probability of real language is near 0 for a garbled layer in any script and near 1 for text; a layer reads at 0.2 or more.
Two guards come first: control or undefined characters, and, in scripts written with spaces, words that are single letters or run together.
A language is named only when it holds most of the weight: source code, say, reads as text but scatters over languages.
Measured on the tune split and `evalset/` against 11 other methods, including lid.176, CLD2, CLD3, GlotLID, lingua and Datalab's text-error model, it trusted the most born-digital layers and the fewest garbled ones:

| Readability rule | Born-digital layers distrusted (of 299) | Real garbled layers trusted (of 34) | Synthetic garbles trusted (of 2,690) |
|---|---|---|---|
| English common words (e3) | 44 | 1 | 252 |
| Structural heuristics | 7 | 0 | 428 |
| lid.176 confidence | 6 | 0 | 304 |
| OpenLID-v3 readability (e4) | 1 | 0 | 72 |

It costs about 5 ms of CPU a page.
HPLT publishes the model at 1.2 GB, so `scripts/openlid.py` quantises it without retraining to 159 MB, keeping every word, since a 200k-word cut let twice as many garbles through.
Quantising on another platform changes its last bits and changed the evidence on 7 of 422 dev layers, so every environment uses one file: the release asset `openlid-v3-pq1`, which `make models` fetches and the image checks by sha256.

**19. Deliberately not in v1:**
- lane executors (the processing itself);
- a learned router: Jev is the classifier, and its terms bar training on its outputs.
