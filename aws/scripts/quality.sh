#!/usr/bin/env bash
set -euo pipefail
mkdir -p reports
python -m ruff check app scripts tests
python -m bandit -r app -ll -f json -o reports/bandit.json
python -m pip_audit -r requirements.txt -f json -o reports/dependencies.json
python -m scripts.train
python -m scripts.evaluate
python -m pytest -q --junitxml=reports/tests.xml --cov=app --cov-report=xml:reports/coverage.xml --cov-report=term
