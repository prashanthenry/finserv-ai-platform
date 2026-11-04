#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
case "$(uname -s)-$(uname -m)" in
  Linux-x86_64) requirements=requirements-linux.txt ;;
  Darwin-arm64)
    if [[ "$(sw_vers -productVersion | cut -d. -f1)" -lt 14 ]]; then
      echo 'The pinned PyTorch wheel needs macOS 14+. Use the Docker route in README.md.'
      exit 1
    fi
    requirements=requirements-macos-arm64.txt ;;
  *) echo 'Use the linux/amd64 Docker route in README.md on this architecture.'; exit 1 ;;
esac
"${PYTHON:-python3.12}" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r "$requirements" -r requirements-dev.txt
echo 'Installed. Next: source .venv/bin/activate'
