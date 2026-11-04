#!/usr/bin/env bash
set -euo pipefail
mkdir -p reports
python -m ruff check risk_ai tests
python -m bandit -r risk_ai -ll -f json -o reports/bandit.json
if [[ "$(uname -s)" == Darwin ]]; then
  python -m risk_ai.audit --requirements requirements-macos-arm64.txt
else
  python -m risk_ai.audit
fi
python -m risk_ai.audit --requirements requirements-dev.txt --report reports/dependencies-training.json
python -m coverage run --source=risk_ai -m risk_ai.generate
python -m coverage run --append --source=risk_ai -m risk_ai.train | tee reports/training.log
python -m pytest -q --junitxml=reports/tests.xml --cov=risk_ai --cov-append --cov-report=xml:reports/coverage.xml --cov-report=term
