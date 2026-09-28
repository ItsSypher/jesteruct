# jesteruct

jesteruct reads unstructured documents page by page and decides which processing lane each page belongs in.
A born-digital report can go straight to text extraction, while a faxed page needs OCR that copes with noise, and a page of handwriting needs a handwriting model.
Sending every page to the most expensive pipeline wastes money, and sending a hard page to a cheap one silently loses its content.
jesteruct makes that call for every page, explains it, and writes a versioned route manifest that the processing lanes consume.

It decides; it does not extract.
The lanes themselves are out of scope for now ([issue #1](https://github.com/ItsSypher/jesteruct/issues/1)).

![The Studio: routed documents, their lanes and the evidence behind each page](docs/images/studio-dark-results.png)

## What it decides

| Lane | Meaning |
|---|---|
| L0 | Native office or text format (docx, email body, txt), no rendering needed |
| L1 | Born-digital, simple layout |
| L2 | Born-digital with tables, equations, code or columns |
| L3 | Clean scan or image, needs OCR |
| L4 | Degraded scan, camera photo or fax |
| L5 | Mostly handwritten |
| LQ | Quarantine: encrypted, corrupt, unsupported or over limits |
| LH | Human review: the router is not confident enough |

Each page also gets modifiers (table, math, code, form, handwriting, multi_column, script, rtl), a degradation score, the language of its text layer and the probability that it continues the previous page.
Consecutive pages form segments, so a lane receives page ranges rather than single pages.
Zip archives and emails are expanded, and every file inside is routed as its own document; a multi-page TIFF is one document with a page per frame.

This is a real manifest for `web/public/samples/mixed-report.pdf`, trimmed:

```json
{
  "doc": {"name": "mixed-report.pdf", "kind": "pdf", "page_count": 3, "sha256": "6b56cd86..."},
  "versions": {"evidence": "e4", "policy": "p4", "jev_model": "typesafe/jev-1.13",
               "vision_model": "google/gemini-3.8-flash", "ocr_backend": "apple"},
  "pages": [
    {"index": 0, "lane": "L1", "confidence": 0.979, "modifiers": [],
     "reasons": ["trusted text layer (0.93)", "simple layout (0.97)"]},
    {"index": 1, "lane": "L2", "confidence": 1.0, "modifiers": ["table"],
     "reasons": ["trusted text layer (0.88)", "complex layout (0.99)"]},
    {"index": 2, "lane": "L4", "confidence": 0.967, "modifiers": ["table"], "degradation": 2.01,
     "vision": {"capture": "fax", "legibility": "mild_issues", "handwriting": "none"},
     "reasons": ["no trusted text (0.92)", "degraded or photo/fax (0.95)"]}
  ],
  "segments": [{"start": 0, "end": 0, "lane": "L1"}, {"start": 1, "end": 1, "lane": "L2", "modifiers": ["table"]},
               {"start": 2, "end": 2, "lane": "L4", "modifiers": ["table"]}],
  "cost_usd": 0.003731
}
```

## How it works

```
file ─► intake ─► per page: probes ─► [vision check] ─► evidence ─► Jev ─► rule table ─► segments ─► manifest
          │                  ~50 ms CPU   only without a      in words    one call   lane + review
          └─ containers expand;           trusted text layer
             bad files go to LQ
```

1. **Intake** sniffs each file by its bytes, expands containers and applies limits; encrypted, corrupt or oversized files go to LQ with a reason code.
2. **Probes** measure each page cheaply: the PDF text layer and its structure, a 1024 px render with image-quality measures, a small layout model's tables, formulas and columns, and the language the text layer reads as (any of about 190).
3. **A vision check** with Gemini 3.8 Flash runs only on pages whose text layer cannot be trusted, such as scans, photos, faxes and PDFs with an old OCR layer.
   Born-digital pages skip it and cost a single cheap call.
4. **Evidence** is put into short phrases, because the classifier reasons better over words than raw numbers.
5. **TypeSafe Jev** answers narrow yes/no questions about the page in one request.
   Six decide the lane: can the text layer be used as it is, is the page mostly handwritten, is it a camera photo or fax, is it heavily degraded, does the capture have defects that make characters harder to read, and is the layout complex.
   The rest give the modifiers, a degradation score and whether the page continues the previous one.
6. **A fixed rule table** in `policy.py` turns the answers into a lane.
   A shipped calibration turns the answers' confidence into the probability that the lane is right, and a page below 0.9 goes to LH for review, keeping its candidate lane.

Jev is the classifier, and everything before it only gathers evidence.
Asking it one multiple-choice lane question reached 0.80 accuracy; narrow yes/no questions with a rule table in code reach about 0.94, and the rule table makes every route explainable.
Every decision, and why it was taken, is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## How well it works

Measured with `jst evaluate` on 1,815 labelled pages from public benchmarks (olmOCR-Bench, DocLayNet, OmniDocBench, FUNSD, SROIE, CORD, GNHK, CHURRO and others) and web documents such as SEC filings, IRS forms and arXiv papers.
The holdout split was never fitted on or studied while the router was developed, so its column is the honest one.

| | Holdout (654 pages) | All 1,815 pages |
|---|---|---|
| Candidate lane right | 94.5% | 94.5% |
| Sent to review (LH) | 21.4% | 22.4% |
| Kept pages whose lane is right | 96.5% | 97.6% |
| Silently wrong (kept, and wrong) | 2.8% | 1.9% |
| Silently under-routed (kept, and too weak a lane) | 1.4% | 1.1% |

The review rate is a dial: `jst calibrate --cost-ratio` trades review volume against silent mistakes (decision 7 in the architecture doc).

**Latency.** A born-digital page takes about 0.4 s at p50.
A page that needs the vision check takes about 5 s at p50 and 14 s at p95, almost all of it waiting on the vision model.

**Cost.** Jev costs about $0.00005 a page and the vision check about $0.0033 a page, both through OpenRouter.
A million pages therefore cost roughly $50, plus about $33 for every percent of them that need the vision check: about $380 if a tenth do, and about $2,440 at the benchmark's mix, where about 72% do.
Every provider response is cached in the object store, so re-routing a document costs nothing.

## Run it locally

### What you need

- macOS or Linux.
- [uv](https://docs.astral.sh/uv/getting-started/installation/); it installs Python 3.12 by itself.
- An [OpenRouter API key](https://openrouter.ai/settings/keys) with a little credit.
  That one key reaches both models: TypeSafe Jev (`typesafe/jev-1.13`) and Gemini 3.8 Flash (`google/gemini-3.8-flash`), with no other sign-up.
- For the Studio: [Docker](https://docs.docker.com/get-docker/) (or OrbStack) for Valkey, and Node.js 22 or newer with pnpm (`corepack enable` gives the pinned version).

OCR uses Apple Vision on macOS and RapidOCR everywhere else; both come with the install.

### The Studio demo

```bash
git clone https://github.com/ItsSypher/jesteruct.git
cd jesteruct
cp .env.example .env    # then paste your key after OPENROUTER_API_KEY=
make studio             # fetches the language model, builds the web app, starts Valkey, a worker and the API
```

Open http://localhost:8000 and press **Run demo**.
The Studio routes 15 sample documents while you watch: each page moves through probes, OCR, the vision check, Jev and the rule table, with the time and result of every step.
Click a page for its evidence, answers and reasons; click its preview to open it at full resolution, and pinch to zoom.
Drop any PDF, image, office file, email or zip on the page to route your own.

The demo's 20 pages cost about 3 cents the first time, and nothing after that: provider responses are cached in `.jst-studio/`.
Ctrl-C stops everything.

| Sample (in `web/public/samples/`) | Expected lane | What it shows |
|---|---|---|
| `born-digital-report.pdf` | L1 | A trusted text layer, so OCR and vision are skipped |
| `math-paper.pdf` | L2 | Born-digital, but full of mathematical notation |
| `source-listing.pdf` | L2 | A code page: complex layout behind a clean text layer |
| `bank-report-clean.jpg` | L3 | A sharp, flat image with no text layer |
| `bank-report-banded.jpg` | L4 | The same page lightly degraded; borderline, so review may catch it |
| `bank-report-photo.jpg` | L4 | The same page photographed on a desk |
| `notice-board-photo.jpg` | L4 | A phone photo: perspective, vignette and blur |
| `memo-fax.jpg` | L4 | A fax: dithered, skewed and speckled |
| `handwritten-notes.jpg` | L5 | Handwritten notes |
| `arabic-lesson.jpg` | L3 | Arabic script, with the script and right-to-left modifiers |
| `mixed-report.pdf` | L1, L2, L4 | Three pages, three segments in one manifest |
| `meeting-notes.docx` | L0 | A native office file |
| `scans-bundle.zip` | L4, L3, L0 | A container: each file inside is its own document |
| `newsletter-email.eml` | L0, L2 | An email body and its two-column PDF attachment |
| `locked.pdf` | LQ | Encrypted, so it is quarantined with a reason |

Served without an API (`pnpm -C web dev` on its own), the Studio replays a recorded demo, so it can be shown offline.

### From the command line

No Docker or Node needed:

```bash
uv sync
make models                               # the text-layer language model (159 MB), checked by sha256
uv run jst route web/public/samples       # one manifest per document in out/
uv run jst view out                       # out/report.html: thumbnails, lanes and reasons
uv run jst probe web/public/samples/memo-fax.jpg   # the evidence for one page, without calling any model
```

### As a service

The same code runs as a stateless API and stateless workers around a Valkey stream:

```bash
docker run -d -p 6379:6379 valkey/valkey:8
export JST_VALKEY_URL=redis://localhost:6379/0
uv run jst worker &
uv run jst serve                          # http://localhost:8000, OpenAPI docs at /docs
curl -F file=@web/public/samples/mixed-report.pdf 'localhost:8000/v1/jobs?wait=30'
```

| Endpoint | Returns |
|---|---|
| `POST /v1/jobs?wait=N` | Queues the uploaded `file`; the finished job if it is done within N seconds (at most 60), otherwise 202 and a job link |
| `GET /v1/jobs/{id}` | The job's status and its documents (a container yields one per file inside), each with its lanes and manifest key |
| `GET /v1/manifests/{sha}` | A document's manifest |
| `GET /v1/thumbs/{sha}/{page}`, `GET /v1/pages/{sha}/{page}` | A page's thumbnail, or its full-resolution view |
| `GET /v1/events` | Live progress of every job as Server-Sent Events; `?job=` for one |
| `GET /healthz`, `GET /readyz`, `GET /metrics` | Liveness, readiness (Valkey reachable) and Prometheus metrics |

Submitting the same file twice returns the same job, and when the backlog passes `JST_MAX_BACKLOG` the API answers 503 with `Retry-After`.

## Deploy to Kubernetes

jesteruct is built to scale out on any Kubernetes cluster, with nothing tied to one cloud.

### Why it scales horizontally

- **Every pod is stateless.**
  Durable data (inputs, manifests, thumbnails and the provider cache) lives in an object store, and coordination (the job stream, job status and rate limits) lives in any Redis-protocol service.
- **Workers scale on the queue.**
  KEDA watches the stream's length, which is exactly the unfinished work, and adds a worker for every 32 unfinished documents, from zero when idle up to `keda.maxReplicas`.
- **Work is idempotent.**
  A job id is the hash of the input and of everything that can change its route, so duplicates collapse into one job, and a worker that dies mid-job loses nothing: another reclaims its messages after two minutes, and a job that fails three times is dead-lettered rather than retried forever.
- **Limits are shared.**
  One rate limiter in Valkey spans every replica, so adding workers never overruns a provider.
- **The API scales on its own.**
  It is light (all routing goes through the queue), and it has its own replica count behind a Service and an optional Ingress.

The ceiling is the providers' request limits rather than CPU: at the default limits the system routes about 16 pages a second (about 1.4 million a day), and pages that need the vision check about 10 a second.
A page needs about 50 ms of CPU and then waits seconds on the models, so each worker keeps 32 pages in flight, and three to six workers reach those limits.
With higher limits from the providers, raise `JST_JEV_RPM`, `JST_VISION_RPM` and `keda.maxReplicas`; nothing else changes.

```
                    ┌──────────────── Kubernetes, any cluster ────────────────┐
client ─► Ingress ─►│ API pods (N)  ─► object store: inputs/                   │
Studio ◄── SSE ◄────│      │                                                  │
                    │      └─► Valkey stream jst:jobs ─► worker pods (0..6) ──┼─► OpenRouter: Jev + Gemini
                    │                   ▲                   │                 │
                    │           KEDA ScaledObject           └─► object store: manifests/, cache/
                    └─────────────────────────────────────────────────────────┘
```

### Infrastructure as code

| Path | What it is |
|---|---|
| `deploy/Dockerfile` | One multi-arch image (amd64 and arm64) for both roles, with the models baked in; non-root |
| `deploy/helm/jesteruct` | The app: API and worker Deployments, the KEDA ScaledObject, ConfigMap, Secret or an existing one, ServiceAccount with workload-identity annotations, optional Ingress |
| `deploy/helm/devstack` | Valkey and SeaweedFS (S3-compatible), for local clusters only |
| `infra/terraform/modules/` | `platform` (KEDA), `devstack` and `app` |
| `infra/terraform/envs/local` | OrbStack Kubernetes on a Mac: everything in-cluster |
| `infra/terraform/envs/cloud` | Any kubeconfig, with a managed Redis-protocol service and a bucket |

The Terraform needs version 1.6 or newer, and the HCL is kept OpenTofu-compatible (both environments validate with OpenTofu 1.12).
The charts know nothing about where their dependencies come from; storage is a URL and Valkey is a URL, so moving clouds means changing two values.
CI publishes multi-arch images to `ghcr.io/itssypher/jesteruct` from every commit on `main`, tagged with the short git SHA and `main`.

### On your laptop

With [OrbStack](https://orbstack.dev) (`orb config set k8s.enable true`), Terraform or OpenTofu, Helm and kubectl:

```bash
make deploy-local            # builds the image, then installs KEDA, Valkey, SeaweedFS and the app (TF=tofu for OpenTofu)
make smoke                   # 43 documents through the API: workers scale 0 → 6, one is killed mid-job, nothing is lost
make studio-cluster          # the cluster's Studio at http://localhost:8000
make destroy-local
```

The last recorded smoke run took the workers from 0 to 6, reclaimed the jobs of a worker killed without a grace period, and finished all 43 jobs with none dead-lettered.

### On any cloud

| | Kubernetes | Redis-protocol service (no cluster mode) | Object store | Workload identity annotation |
|---|---|---|---|---|
| AWS | EKS | ElastiCache | S3, `s3://` | `eks.amazonaws.com/role-arn` |
| Google Cloud | GKE | Memorystore | Cloud Storage, `gs://` | `iam.gke.io/gcp-service-account` |
| Azure | AKS | Azure Cache for Redis | Blob Storage, `az://` | `azure.workload.identity/client-id` |
| Your own | any | Valkey or Redis | MinIO, SeaweedFS or Ceph, `s3://` with an endpoint | a credentials Secret (`storeCredentialsSecret`) |

Create the cluster, the Redis-protocol service and the bucket the way your cloud does, then:

```bash
kubectl create namespace jesteruct
kubectl -n jesteruct create secret generic jesteruct-openrouter --from-env-file=.env   # the key, from your .env
cp infra/terraform/envs/cloud/cloud.example.tfvars infra/terraform/envs/cloud/cloud.tfvars   # fill it in; gitignored
terraform -chdir=infra/terraform/envs/cloud init
terraform -chdir=infra/terraform/envs/cloud apply -var-file=cloud.tfvars
```

`cloud.example.tfvars` documents every value: the kube context, the image tag, the Valkey URL (`rediss://` turns on TLS), the bucket, the Secret, workload identity and an optional Ingress host.
The key stays in a Kubernetes Secret, so it never reaches Terraform state.

Without Terraform, the chart installs on its own when the cluster runs KEDA:

```bash
helm install jesteruct deploy/helm/jesteruct -n jesteruct \
  --set image.tag=<git sha> \
  --set valkeyUrl=rediss://my-cache.example.com:6380/0 \
  --set storeUrl=s3://my-bucket \
  --set openrouter.existingSecret=jesteruct-openrouter
```

Set `keda.enabled=false` and `worker.replicas` for a fixed number of workers instead.

## Evaluate and tune

```bash
uv run jst evaluate                                   # the 98 cases in evalset/, about $0.20 on a cold cache
uv run evalset/fresh/build.py fetch                   # the 1,717-case fresh set (281 MB), checked against every sha256
uv run jst evaluate --cases evalset/fresh/cases.jsonl --out out/fresh
uv run jst calibrate out/fresh/results.jsonl          # refit when to send a page to review; never fits on holdout
uv run jst evaluate --api http://localhost:8000       # the same cases through a running service
```

`build.py` can also rebuild the fresh set byte for byte from its public sources (it needs the tesseract CLI for a few variants).
The evidence wording (`EVIDENCE_VERSION`) and the question set and rule table (`POLICY_VERSION`) are frozen: change either only with a version bump and an evaluation run that does not lose accuracy or add silent under-routing.

## Configuration

Settings are environment variables named `JST_<NAME>`, read from `.env` as well; [src/jesteruct/config.py](src/jesteruct/config.py) lists them all.

| Setting | Default | Meaning |
|---|---|---|
| `OPENROUTER_API_KEY` | none | The only required one |
| `JST_STORE_URL` | `file://.jst` | Object store for inputs, manifests and the cache: `file://`, `s3://`, `gs://`, `az://` |
| `JST_VALKEY_URL` | none | Redis-protocol URL; required for `jst serve` and `jst worker` |
| `JST_OCR_BACKEND` | `auto` | `apple` (macOS), `rapid` (anywhere), or `auto` |
| `JST_PAGE_CONCURRENCY` | 32 | Pages in flight per worker |
| `JST_JEV_RPM`, `JST_VISION_RPM` | 1000, 600 | Request budgets shared by every replica |
| `JST_USE_CALIBRATION` | true | Review on the shipped calibration, or on `JST_REVIEW_THRESHOLD` when false |
| `JST_MAX_FILE_MB`, `JST_MAX_PAGES` | 200, 2000 | Intake limits; beyond them a file goes to LQ |

## Repository layout

| Path | Contents |
|---|---|
| `src/jesteruct/` | The router: intake, probes, evidence, policy, providers, pipeline, API and worker |
| `web/` | The Studio: Svelte 5 and WebGPU, served by the API |
| `evalset/` | Labelled pages for `jst evaluate`, and the recipe for the fresh set |
| `deploy/`, `infra/terraform/` | The image, Helm charts and Terraform |
| `scripts/` | The Studio launcher, the cluster smoke test and the language-model recipe |
| `docs/ARCHITECTURE.md` | How it works, what was measured, and every design decision with its reasons |
| `bench/`, `research/` | The experiments behind the design |

Development: `make lint`, `make test`, and `pnpm -C web dev` for the Studio against a running API (Vite proxies `/v1` to port 8000).

## Licences

The jesteruct code has no licence file yet, so all rights are reserved until one is added.
The models and data it uses keep their own terms, recorded as information:

- **OpenLID-v3** (the text-layer language model, fetched by `make models`): GPL-3.0; `scripts/openlid.py` builds the quantised file from HPLT's release.
- **360LayoutAnalysis** layout weights: 360's model licence, which asks commercial users to apply first; the code around them is Apache-2.0.
- **RapidOCR and PP-OCRv6** models: Apache-2.0.
- **TypeSafe Jev and Gemini 3.8 Flash** are hosted models, used under OpenRouter's and their providers' terms.
- **Evaluation pages** come from public datasets under their own terms, some for research use only; [evalset/LICENSES.md](evalset/LICENSES.md) and [evalset/fresh/LICENSES.md](evalset/fresh/LICENSES.md) list each source.
  The Studio samples come from CC BY 4.0 and ODC-By sources or were made for this project, as `web/public/samples/samples.json` records.
