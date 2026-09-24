# syntax=docker/dockerfile:1
# One image for the API and the workers: `jst serve` (default) or `jst worker`.

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
from rapidocr import RapidOCR

RapidOCR()
RapidLayout(model_type="yolov8n_layout_general6")  # jesteruct.probes.layout.MODEL; the check below catches drift
EOF

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

# The engines as the router builds them, with the network off: containers must never reach out for weights at runtime.
RUN --network=none /app/.venv/bin/python - <<'EOF'
import cv2
import numpy as np
from rapidocr import RapidOCR

from jesteruct.probes import layout

image = np.full((64, 320, 3), 255, np.uint8)
cv2.putText(image, "jesteruct", (10, 44), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 0), 3)
print("rapidocr check:", RapidOCR()(image).txts)
print("layout check:", layout.detect(np.full((1024, 768, 3), 255, np.uint8)))
EOF


FROM python:3.12-slim-trixie
LABEL org.opencontainers.image.source=https://github.com/ItsSypher/jesteruct

RUN useradd --uid 10001 --user-group --create-home --home-dir /home/jst jst
COPY --from=builder /app/.venv /app/.venv

ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    JST_OCR_BACKEND=rapid

USER 10001:10001
WORKDIR /home/jst
EXPOSE 8000 9090
ENTRYPOINT ["jst"]
CMD ["serve"]
