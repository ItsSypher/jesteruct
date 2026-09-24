#!/usr/bin/env bash
# Smoke test of the local deployment (make deploy-local, then make smoke). It routes 43 real documents, so it spends
# a little OpenRouter credit.
#   1. route a born-digital PDF, a page photo and a handwriting image, and print their lanes
#   2. queue 40 more and watch KEDA add workers
#   3. kill the oldest (busiest) worker without a grace period, so its jobs must be reclaimed, and wait for every job
#   4. check that every job is done and nothing was dead-lettered
set -euo pipefail

CTX=${CTX:-orbstack}
NS=${NS:-jesteruct}
DEVSTACK_NS=${DEVSTACK_NS:-devstack}
PORT=${PORT:-18000}
TIMEOUT_S=${TIMEOUT_S:-1200}
FILES=${FILES:-evalset/files}
MIXED=${MIXED:-"pdf_olmx_02.pdf img_pdb_mathdense_real.jpg img_gnhk_01.jpg"} # born-digital PDF, page photo, handwriting

for tool in kubectl curl jq; do
  command -v "$tool" >/dev/null || { echo "smoke: $tool is required" >&2; exit 1; }
done

fail() { echo "smoke: FAIL: $*" >&2; exit 1; }
k() { kubectl --context "$CTX" -n "$NS" "$@"; }
api="http://127.0.0.1:$PORT"
jobs_file=$(mktemp)

# kubectl itself, not the k function, so that $! is the process to stop
kubectl --context "$CTX" -n "$NS" port-forward svc/jesteruct-api "$PORT:8000" >/dev/null &
forward=$!
cleanup() {
  kill "$forward" 2>/dev/null || true
  wait "$forward" 2>/dev/null || true
  rm -f "$jobs_file"
}
trap cleanup EXIT
for _ in $(seq 30); do
  if curl -sf "$api/readyz" >/dev/null; then break; fi
  sleep 1
done
kill -0 "$forward" 2>/dev/null || fail "port-forward exited; is port $PORT free?"
curl -sSf "$api/readyz" >/dev/null || fail "API is not ready at $api"

submit() { curl -sSf -F "file=@$FILES/$1" "$api/v1/jobs?wait=$2" | jq -r .job_id; }
job() { curl -sSf "$api/v1/jobs/$1"; }
worker_replicas() { k get deploy jesteruct-worker -o jsonpath='{.status.replicas}'; }
deadline=$((SECONDS + TIMEOUT_S))

# Wait for every job in $jobs_file while tracking the worker count. With "kill", delete the oldest worker once KEDA
# has added a second one.
peak=0
killed=""
wait_all() {
  while :; do
    local replicas left=0
    replicas=$(worker_replicas)
    replicas=${replicas:-0}
    if ((replicas > peak)); then peak=$replicas; fi
    if [[ $1 == kill && -z $killed && $replicas -gt 1 ]]; then
      killed=$(k get pods -l app.kubernetes.io/component=worker --field-selector=status.phase=Running \
        --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[0].metadata.name}')
      if [[ -n $killed ]]; then
        echo "workers: $replicas; killing $killed"
        k delete pod "$killed" --grace-period=1 --wait=false >/dev/null
      fi
    fi
    while read -r id; do
      case $(job "$id" | jq -r .status) in
        done | failed) ;;
        *) left=$((left + 1)) ;;
      esac
    done <"$jobs_file"
    if ((left == 0)); then return; fi
    ((SECONDS < deadline)) || fail "$left job(s) unfinished after ${TIMEOUT_S}s"
    echo "waiting: $left job(s), $replicas worker(s)"
    sleep 5
  done
}

echo "== 1. three mixed documents"
for f in $MIXED; do submit "$f" 60 >>"$jobs_file"; done
wait_all watch
while read -r id; do
  job "$id" | jq -r '.documents[] | "\(.name): \(.lanes | to_entries | map("\(.key)×\(.value)") | join(" "))"'
done <"$jobs_file"

echo "== 2. forty more"
queued=0
for path in "$FILES"/*; do
  f=${path##*/}
  if [[ " $MIXED " == *" $f "* ]]; then continue; fi
  submit "$f" 0 >>"$jobs_file"
  queued=$((queued + 1))
  if ((queued == 40)); then break; fi
done
wait_all kill
[[ -n $killed ]] || fail "workers never scaled past 1"
echo "peak workers: $peak"

echo "== 3. outcomes"
failed=0
while read -r id; do
  status=$(job "$id" | jq -r .status)
  if [[ $status != "done" ]]; then
    echo "not done: $id $status $(job "$id" | jq -c .error)"
    failed=$((failed + 1))
  fi
done <"$jobs_file"
dead=$(kubectl --context "$CTX" -n "$DEVSTACK_NS" exec deploy/valkey -- valkey-cli XLEN jst:dead)
echo "jobs: $(wc -l <"$jobs_file" | tr -d ' '), not done: $failed, dead letters: $dead"
((failed == 0)) || fail "$failed job(s) did not finish"
((dead == 0)) || fail "$dead dead letter(s) in jst:dead"
echo "smoke: OK"
