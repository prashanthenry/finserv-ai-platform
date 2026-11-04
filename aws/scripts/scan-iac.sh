#!/usr/bin/env bash
set -euo pipefail
mkdir -p reports/security
result=0
run_check() {
  local name="$1"
  shift
  local code=0
  "$@" > "reports/security/${name}.json" 2> "reports/security/${name}.log" || code=$?
  printf '%s\n' "$code" > "reports/security/${name}.exit-code"
  if [[ "$code" -ne 0 ]]; then
    echo "$name failed (exit $code); inspect its report and log."
    result=1
  else
    echo "$name passed."
  fi
}
# Containerized tools keep their Python/SDK dependencies separate from the application.
# Review and pin scanner image digests before using this lab in a production pipeline.
run_check checkov docker run --rm -v "$PWD:/workspace:ro" -w /workspace \
  bridgecrew/checkov:latest --directory infra --framework terraform --output json --compact
run_check tfsec docker run --rm -v "$PWD:/workspace:ro" -w /workspace \
  aquasec/tfsec:latest /workspace/infra --format json --minimum-severity HIGH --no-color
run_check trivy-iac docker run --rm -v "$PWD:/workspace:ro" -w /workspace \
  aquasec/trivy:latest config --exit-code 1 --severity HIGH,CRITICAL --format json /workspace/infra
run_check trivy-filesystem docker run --rm -v "$PWD:/workspace:ro" -w /workspace \
  aquasec/trivy:latest fs --scanners vuln,secret --exit-code 1 --severity HIGH,CRITICAL \
  --skip-dirs /workspace/.venv --skip-dirs /workspace/.terraform --skip-dirs /workspace/infra/.terraform \
  --skip-dirs /workspace/reports --format json /workspace
exit "$result"
