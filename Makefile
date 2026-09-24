SHA := $(shell git rev-parse --short HEAD)
TF_LOCAL := terraform -chdir=infra/terraform/envs/local

.PHONY: sync lint test image deploy-local smoke destroy-local

sync:
	uv sync

lint:
	uv run ruff check
	uv run ruff format --check

test:
	uv run pytest

image:
	docker build -f deploy/Dockerfile -t jesteruct:$(SHA) .

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
