# syntax=docker/dockerfile:1
# One image for the API and the workers: `jst serve` (default) or `jst worker`. The API also serves the Studio.

# The Studio is static files, the same on every architecture, so it is built once on the build platform.
FROM --platform=$BUILDPLATFORM node:24-slim AS web
RUN npm install --global pnpm@11
WORKDIR /web
COPY web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml ./
RUN --mount=type=cache,target=/root/.local/share/pnpm/store pnpm install --frozen-lockfile
COPY web/ ./
RUN pnpm build

FROM ghcr.io/astral-sh/uv:0.11-python3.12-trixie-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0
WORKDIR /app

# Dependencies first, so source edits reuse this layer.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --frozen --no-dev --no-editable --no-install-project

# RapidOCR and the layout model download their weights on first use. Fetch them before the source is copied, so they
# are downloaded again only when the dependencies change.
RUN /app/.venv/bin/python - <<'EOF'
from rapid_layout import RapidLayout
from rapidocr import ModelType, RapidOCR

# The engines of jesteruct.probes.ocr._rapid and jesteruct.probes.layout.MODEL; the offline check below catches drift.
RapidOCR(params={"Global.use_cls": False, "Det.model_type": ModelType.TINY, "Rec.model_type": ModelType.TINY})
RapidLayout(model_type="yolov8n_layout_general6")
EOF

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable
# The text-layer language model, from the `models` build context (`make models`: the release openlid-v3-pq1). One
# file everywhere: quantising it again on another platform changes its last bits and a few pages' evidence.
COPY --from=models openlid-v3.ftz /app/models/openlid-v3.ftz
RUN echo "e7b1dff1f38f2e940ac8c3e6c1ee0f33660a31bfa03127098a8ffd879cdf374a  /app/models/openlid-v3.ftz" | sha256sum -c

# The engines as the router builds them, with the network off: containers must never reach out for weights at runtime.
RUN --network=none /app/.venv/bin/python - <<'EOF'
import cv2
import numpy as np

from jesteruct.probes import language, layout, ocr

image = np.full((64, 320, 3), 255, np.uint8)
cv2.putText(image, "jesteruct", (10, 44), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 0), 3)
print("rapidocr check:", ocr._rapid()(image).txts)
print("layout check:", layout.detect(np.full((1024, 768, 3), 255, np.uint8)))
sentence = "All human beings are born free and equal in dignity and rights, and should act towards one another.\n" * 2
print("language check:", language.identify(sentence, "/app/models/openlid-v3.ftz"))
EOF


FROM python:3.12-slim-trixie
LABEL org.opencontainers.image.source=https://github.com/ItsSypher/jesteruct

RUN useradd --uid 10001 --user-group --create-home --home-dir /home/jst jst
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/models /app/models
COPY --from=web /web/dist /app/web

ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    JST_OCR_BACKEND=rapid \
    JST_LID_MODEL=/app/models/openlid-v3.ftz \
    JST_WEB_DIR=/app/web

USER 10001:10001
WORKDIR /home/jst
EXPOSE 8000 9090
ENTRYPOINT ["jst"]
CMD ["serve"]
