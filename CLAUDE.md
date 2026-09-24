# jesteruct: working instructions

jesteruct routes unstructured documents, page by page, into processing lanes and writes a versioned route manifest.
Read `docs/ARCHITECTURE.md` before changing anything; it holds the design and the reasons behind each decision.

## How to build

- Build it the way a principal engineer would: clean code, clean orchestration, a system that is easy to follow.
- Prefer small obvious modules, typed code and few moving parts.
- No dead code, and no speculative abstraction.
- Match the surrounding style: short docstrings, comments only where the reason is not obvious.
- Optimise for quality, simplicity and long-term maintainability over development cost.
- Keep documentation minimal:
  - `README.md` is the quickstart;
  - `docs/ARCHITECTURE.md` is the overview plus the decisions and why they were taken.
  - Add a decision there when you make one; do not add other docs.
- Keep tests lean: a few focused unit tests, one end-to-end test with a fake provider, and the real evaluation.
- Do not over-invest in tests.

## Design rules that are not up for casual change

- **TypeSafe Jev is the lane classifier.**
  - It answers narrow yes/no questions about each page.
  - The rule table in `policy.py` maps the answers to a lane.
  - Probes, OCR and the vision model only produce evidence for Jev.
- **Gemini 3.8 Flash (`google/gemini-3.8-flash`)** is the vision model. It runs only when a page has no trustworthy text layer.
- **Evidence wording is frozen** at `EVIDENCE_VERSION`, and the question set and rule table at `POLICY_VERSION`. Change either only with a version bump and a `jst evaluate` run that does not regress lane accuracy or silent under-routing.
- **Failures degrade and never flood review.** Provider outages and auth or billing errors fail the job (it is redelivered). A single rejected request sends that page to LH.
- **Quality comes first, then latency and cost:** pick the best quality-to-speed ratio. Confidentiality is not a constraint for now, so hosted models are fine.

## Where it runs

- Natively on Apple Silicon (`jst route`, `jst evaluate`). Apple Vision OCR is used on macOS.
- On any Kubernetes cluster, cloud-agnostic:
  - Helm charts in `deploy/helm/`;
  - Terraform in `infra/terraform/`, kept OpenTofu-compatible;
  - KEDA scaling workers on Valkey stream lag.
- Test the cluster locally on OrbStack Kubernetes: `make deploy-local`, then `make smoke`.
- CI publishes multi-arch images to GHCR from `main`.

## Working rules

- Use `uv` for everything Python.
- Use `gh-axi` for GitHub.
- The labelled data lives in `evalset/`. Avoid the bare word "eval" in shell commands, because this harness's guard rejects them.
- Git:
  - work on feature branches with draft PRs;
  - never push to `main`;
  - commits carry no agent attribution.
- Secrets: the OpenRouter key lives only in `.env`, which is gitignored. The user's shell may export a stale `OPENROUTER_API_KEY`; prefix local runs with `OPENROUTER_API_KEY=` so the `.env` value wins. Never print the key.
- Spend: a full `jst evaluate` costs about $0.20 on a cold cache. Keep experiment runs to a few dollars, and reuse the provider cache (`JST_STORE_URL=file://.jst-fresh`) when only Jev inputs change.
- When parallel agents help, give each one this file, the plan and clear file ownership; only the lead commits.
