#!/usr/bin/env bash
set -euo pipefail
previous=$(helm history payment-risk -n genai -o json 2>/dev/null | python -c '
import json,sys
rows=json.load(sys.stdin)
healthy=[x for x in rows if x["status"] in ("deployed","superseded")]
print(healthy[-1]["revision"] if healthy else "")
' || true)
forward_pid=''
cleanup() {
  if [[ -n "$forward_pid" ]]; then kill "$forward_pid" 2>/dev/null || true; fi
}
trap cleanup EXIT
# The namespace is bootstrapped by the local infrastructure administrator.
helm upgrade --install payment-risk deploy/chart -n genai --atomic --wait --timeout 10m "$@"
kubectl -n genai port-forward service/payment-risk 8002:8000 > /tmp/payment-risk-forward.log 2>&1 &
forward_pid=$!
ready=false
for attempt in {1..60}; do
  if python -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8002/readyz", timeout=2)' > /dev/null 2>&1; then
    ready=true
    break
  fi
  sleep 1
done
if [[ "$ready" == true ]] && python -m risk_ai.smoke --url http://127.0.0.1:8002; then
  echo 'Payment-risk deployment verified with both framework models.'
else
  if [[ -n "$previous" ]]; then
    helm rollback payment-risk "$previous" -n genai --wait --timeout 10m
  else
    helm uninstall payment-risk -n genai
  fi
  exit 1
fi
