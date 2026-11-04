#!/usr/bin/env bash
set -euo pipefail
image="${1:?Supply the local Docker image tag}"
suffix="${RANDOM}-$$"
network="copilot-dast-${suffix}"
target="copilot-target-${suffix}"
cleanup() {
  docker rm -f "$target" > /dev/null 2>&1 || true
  docker network rm "$network" > /dev/null 2>&1 || true
}
trap cleanup EXIT
mkdir -p reports/security/zap
# ZAP's container user needs write access to this generated report directory only.
chmod 777 reports/security/zap
docker network create "$network" > /dev/null
# Use the release image with offline AI on an isolated Docker network.
# Active DAST must not fuzz a production API or invoke paid LLMs for every payload.
docker run -d --name "$target" --network "$network" --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m -e AI_PROVIDER=offline "$image" > /dev/null
ready=false
for attempt in {1..30}; do
  if docker exec "$target" python -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/readyz", timeout=2)' > /dev/null 2>&1; then
    ready=true
    break
  fi
  sleep 1
done
if [[ "$ready" != true ]]; then
  docker logs "$target" > reports/security/zap/target.log 2>&1
  echo 'DAST target failed readiness.'
  exit 1
fi
# ZAP exits 1 for FAIL alerts, 2 for WARN alerts, and 3 for operational errors.
# All nonzero statuses fail this gate. No blanket ignore or soft-fail is applied.
docker run --rm --network "$network" -v "$PWD/reports/security/zap:/zap/wrk:rw" \
  ghcr.io/zaproxy/zaproxy:stable zap-api-scan.py \
  -t "http://${target}:8000/openapi.json" -f openapi \
  -r zap.html -J zap.json -w zap.md -T 5
