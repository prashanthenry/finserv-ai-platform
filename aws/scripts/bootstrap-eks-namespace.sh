#!/usr/bin/env bash
# Run on the Mac with the cluster-creator AWS identity, after the runner is SSM-online.
# The tunnel provides connectivity; Kubernetes authentication still uses your Mac's AWS identity.
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for command in terraform aws kubectl python3 session-manager-plugin; do
  command -v "$command" >/dev/null || { echo "Missing required command: $command" >&2; exit 1; }
done

region=$(terraform -chdir="$root/infra" output -raw deployment_region)
cluster=$(terraform -chdir="$root/infra" output -raw cluster_name)
instance=$(terraform -chdir="$root/infra" output -raw github_runner_instance_id)
endpoint=$(aws eks describe-cluster --region "$region" --name "$cluster" --query cluster.endpoint --output text)
host="${endpoint#https://}"
port="${EKS_TUNNEL_PORT:-18443}"
[[ "$port" =~ ^[0-9]+$ ]] && (( port >= 1024 && port <= 65535 )) || { echo 'Invalid EKS_TUNNEL_PORT' >&2; exit 1; }
python3 - "$port" <<'PY'
import socket
import sys
with socket.socket() as listener:
    listener.bind(("127.0.0.1", int(sys.argv[1])))
PY

temp_dir=$(mktemp -d)
tunnel_pid=''
cleanup() {
  if [[ -n "$tunnel_pid" ]]; then
    kill "$tunnel_pid" 2>/dev/null || true
    wait "$tunnel_pid" 2>/dev/null || true
  fi
  rm -rf "$temp_dir"
}
trap cleanup EXIT
parameters=$(python3 - "$host" "$port" <<'PY'
import json
import sys
print(json.dumps({"host": [sys.argv[1]], "portNumber": ["443"], "localPortNumber": [sys.argv[2]]}))
PY
)
aws ssm start-session --region "$region" --target "$instance" \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters "$parameters" > "$temp_dir/tunnel.log" 2>&1 &
tunnel_pid=$!

aws eks update-kubeconfig --region "$region" --name "$cluster" \
  --kubeconfig "$temp_dir/config" >/dev/null
cluster_entry=$(kubectl --kubeconfig "$temp_dir/config" config view -o jsonpath='{.contexts[0].context.cluster}')
kubectl --kubeconfig "$temp_dir/config" config set-cluster "$cluster_entry" \
  --server="https://127.0.0.1:$port" --tls-server-name="$host" >/dev/null

connected=false
for attempt in {1..30}; do
  if ! kill -0 "$tunnel_pid" 2>/dev/null; then
    cat "$temp_dir/tunnel.log" >&2
    exit 1
  fi
  if kubectl --kubeconfig "$temp_dir/config" --request-timeout=3s get namespace default >/dev/null 2>&1; then
    connected=true
    break
  fi
  sleep 1
done
if [[ "$connected" != true ]]; then
  cat "$temp_dir/tunnel.log" >&2
  echo "Cannot reach/authenticate to EKS. Check SSM, security groups and the Mac's AWS identity." >&2
  exit 1
fi
kubectl --kubeconfig "$temp_dir/config" create namespace genai --dry-run=client -o yaml |
  kubectl --kubeconfig "$temp_dir/config" apply -f -
kubectl --kubeconfig "$temp_dir/config" get nodes
echo "genai namespace ready; temporary tunnel and kubeconfig will be removed."
