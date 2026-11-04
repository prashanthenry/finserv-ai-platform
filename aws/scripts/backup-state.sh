#!/usr/bin/env bash
set -euo pipefail
umask 077
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
state_file="$project_dir/infra/terraform.tfstate"
if [[ ! -f "$state_file" ]]; then
  echo 'No local Terraform state found; no backup created.'
  exit 1
fi
mkdir -p "$project_dir/.state-backups"
chmod 700 "$project_dir/.state-backups"
backup_file="$(mktemp "$project_dir/.state-backups/terraform-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX.tfstate")"
cp "$state_file" "$backup_file"
chmod 600 "$backup_file"
echo "Local backup created: $backup_file"
