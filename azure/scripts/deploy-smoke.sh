#!/usr/bin/env bash
set -euo pipefail
# Helm --atomic handles rollout failure. This also rolls back a failed LIVE inference smoke test.
previous_revision="$(helm history copilot -n genai -o json 2>/dev/null | python -c 'import json,sys; a=[r for r in json.load(sys.stdin) if r["status"] in ("deployed","superseded")]; print(a[-1]["revision"] if a else "")' || true)"
helm upgrade --install copilot deploy/chart -n genai --atomic --wait --timeout 10m "$@"
kubectl -n genai port-forward svc/copilot 8000:8000 > /tmp/copilot-port-forward.log 2>&1 &
forward_pid=$!
trap 'kill "$forward_pid" 2>/dev/null || true' EXIT
for attempt in {1..30}; do
  if curl -fsS http://127.0.0.1:8000/readyz > /dev/null; then break; fi
  sleep 1
done
if ! python -m scripts.smoke --require-live; then
  if [[ -n "$previous_revision" ]]; then
    helm rollback copilot "$previous_revision" -n genai --wait --timeout 10m
  else
    helm uninstall copilot -n genai
  fi
  exit 1
fi
