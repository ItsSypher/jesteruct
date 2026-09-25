SHA := $(shell git rev-parse --short HEAD)
TF_LOCAL := terraform -chdir=infra/terraform/envs/local
MODELS ?= $(HOME)/.cache/jesteruct

.PHONY: sync models lint test web studio studio-cluster image deploy-local smoke destroy-local

sync:
	uv sync

# The text-layer language model (scripts/openlid.py built it; the router's default JST_LID_MODEL), checked by sha256.
models:
	mkdir -p $(MODELS)
	gh release download openlid-v3-pq1 --pattern 'openlid-v3.ftz*' --dir $(MODELS) --clobber
	cd $(MODELS) && shasum -a 256 -c openlid-v3.ftz.sha256

lint:
	uv run ruff check
	uv run ruff format --check

test:
	uv run pytest

web:
	pnpm -C web install --frozen-lockfile
	pnpm -C web build

# The Studio natively: Valkey in Docker, a worker and the API at http://localhost:8000 (Ctrl-C stops them).
studio: web
	scripts/studio.sh

# The Studio of the OrbStack deployment (make deploy-local), at http://localhost:8000.
studio-cluster:
	kubectl --context orbstack -n jesteruct port-forward svc/jesteruct-api 8000:8000

image: models
	docker build --build-context models=$(MODELS) -f deploy/Dockerfile -t jesteruct:$(SHA) .

# The OpenRouter key comes from .env only (the shell may export a stale one) and reaches Terraform through the
# environment, so it is never echoed.
deploy-local: image
	$(TF_LOCAL) init -input=false
	TF_VAR_openrouter_api_key="$$(sed -n 's/^OPENROUTER_API_KEY=//p' .env | tr -d "\"'")" \
		$(TF_LOCAL) apply -auto-approve -var image_tag=$(SHA)

smoke:
	scripts/smoke.sh

# Destroy never reads the key, but the variable must be set.
destroy-local:
	TF_VAR_openrouter_api_key=unused $(TF_LOCAL) destroy -auto-approve -var image_tag=$(SHA)
