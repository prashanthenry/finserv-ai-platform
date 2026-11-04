#!/usr/bin/env bash
set -euo pipefail
image="${1:?Supply the local Docker image tag}"
mkdir -p reports/security
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  aquasec/trivy:latest image --scanners vuln,secret --exit-code 1 --severity HIGH,CRITICAL \
  --format json "$image" > reports/security/trivy-image.json
echo 'Trivy image scan passed; JSON report saved.'
