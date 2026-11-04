#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
image="${1:?Supply the local Docker image tag}"
scanner_image='aquasec/trivy:0.76.1'
mkdir -p reports/security
# Validate the reviewed vendor document before any VEX filtering is permitted.
base=$(python -m risk_ai.vex base)
cp security/vendor-vex/dhi-python-vex.json reports/security/dhi-python-vex.json
cp security/vendor-vex/review.json reports/security/vex-review.json
docker pull --platform linux/amd64 "$base"
docker image inspect "$base" > reports/security/vex-base-inspect.json
docker image inspect "$image" > reports/security/vex-app-inspect.json
python -m risk_ai.vex layers
# Shared cache also lets both scans use the same vulnerability database snapshot.
mounts=(--rm -v /var/run/docker.sock:/var/run/docker.sock
  -v finserv-ai-trivy-cache:/root/.cache/trivy
  -v "$PWD/security/vendor-vex:/vendor-vex:ro")
# First pass is unfiltered evidence. Operational errors still fail this command.
docker run "${mounts[@]}" "$scanner_image" image --image-src docker \
  --scanners vuln,secret --severity HIGH,CRITICAL --ignorefile '' --exit-code 0 \
  --format json "$image" > reports/security/trivy-image-raw.json
# The second pass remains a blocking gate; retain suppressed findings for review.
scan_status=0
docker run "${mounts[@]}" "$scanner_image" image --image-src docker --skip-db-update \
  --scanners vuln,secret --severity HIGH,CRITICAL --ignorefile '' --exit-code 1 \
  --vex /vendor-vex/dhi-python-vex.json --show-suppressed \
  --format json "$image" > reports/security/trivy-image-vex.json || scan_status=$?
python -m risk_ai.vex gate --scan-exit "$scan_status"
echo 'Payment-risk image gate passed; raw findings and reviewed VEX decisions saved.'
