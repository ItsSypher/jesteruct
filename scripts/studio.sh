#!/usr/bin/env bash
# The Studio on this machine: Valkey in Docker, one worker, and the API serving web/dist at http://localhost:$PORT.
# Ctrl-C stops all three. Provider responses are cached in .jst-studio, so a repeated demo costs nothing.
set -euo pipefail
cd "$(dirname "$0")/.."

PORT=${PORT:-8000}
VALKEY_PORT=${VALKEY_PORT:-6379}
[[ -f web/dist/index.html ]] || { echo "web/dist is missing: run make web" >&2; exit 1; }

export JST_VALKEY_URL="redis://127.0.0.1:$VALKEY_PORT/0"
export JST_STORE_URL=${JST_STORE_URL:-file://.jst-studio}
export JST_WEB_DIR=web/dist
export OPENROUTER_API_KEY=  # empty, so the key is read from .env; the shell may export a stale one

docker run -d --rm --name jst-studio-valkey -p "127.0.0.1:$VALKEY_PORT:6379" valkey/valkey:8 >/dev/null
trap 'kill $(jobs -p) 2>/dev/null; docker rm -f jst-studio-valkey >/dev/null' EXIT

uv run jst worker --metrics-port 9090 &
uv run jst serve --port "$PORT" &
echo "Studio: http://localhost:$PORT"
# Stop everything when either exits (a missing key stops the worker) rather than serve jobs no one will route;
# a loop, because macOS ships bash 3.2, which has no `wait -n`.
while [[ $(jobs -rp | wc -l) -eq 2 ]]; do sleep 1; done
exit 1
