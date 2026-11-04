# Apply the reviewed VEX integration

Your models and local API are already working. This update brings the reviewed
image assessment into the payment-risk CI and release jobs.

## Files to merge

Extract the updated archive separately. Merge these paths into your existing
project; retain your `.venv`, `data`, `artifacts` and local reports:

| Path from repository root | Change |
| --- | --- |
| `.github/workflows/aws-payment-risk.yml` | Quality and release call the new payment-risk scanner |
| `aws/payment-risk/Dockerfile` | Pins the reviewed runtime digest and Python 3.12.16 builder tag |
| `aws/payment-risk/risk_ai/vex.py` | Checks vendor data, base layers and scan decisions |
| `aws/payment-risk/scripts/scan-image.sh` | Runs unfiltered and VEX-aware scans, then enforces the gate |
| `aws/payment-risk/security/` | Original exported vendor VEX and checksum/base/CVE review record |
| `aws/payment-risk/tests/test_vex.py` and `tests/fixtures/` | Tests accepted decisions and blocking conditions |
| `aws/payment-risk/README.md` and `VEX-UPDATE.md` | Updated instructions |

There is no model retraining requirement for this source/security update. Keep
your local bundle `9464eedc6ade4e84`. CI continues to generate and train its own
bundle as part of its normal quality sequence.

## Run locally

From your existing `aws/payment-risk/` folder, with its environment active:

```bash
python -m pytest -q
docker build --platform linux/amd64 --target ci --pull -t payment-risk:ci .
bash scripts/scan-image.sh payment-risk:ci
```

The scanner uses your existing authenticated DHI registry session. It requires
only Python's standard library on the host and Docker; Docker Scout is not needed
for routine runs after importing the reviewed VEX file. The existing registry
credentials in the GitHub workflow remain sufficient. No new pipeline secrets or
repository variables were introduced.

The expected local test count is now 32. A successful checked scan prints:

```text
Payment-risk image gate passed; raw findings and reviewed VEX decisions saved.
```

## What the scanner enforces

1. Checks the exported VEX file against its reviewed SHA-256 and expected author.
2. Confirms the nine approved CVEs have versioned package entries bound to the
   reviewed immutable base digest.
3. Pulls that exact Linux/amd64 base and compares its root-filesystem layer prefix
   with the application image. An unrelated or changed base blocks the scan.
4. Saves the unfiltered HIGH/CRITICAL vulnerability and secret scan as evidence.
5. Runs Trivy again using the same database snapshot and the vendor VEX file,
   preserving suppressed findings in the JSON output.
6. Blocks scanner errors, remaining HIGH/CRITICAL findings, secrets, missing OS or
   Python analysis, changed image identity, missing findings and suppressions
   outside the reviewed CVE/package-version/justification combinations.

The raw scan is evidence collection; the assessed scan plus decision validator is
the blocking gate. Neither `.trivyignore` nor `--ignore-unfixed` is used. Vendor
assessment changes do not automatically enter this policy.

## Evidence retained

Both quality and release upload their security evidence from `reports/`:

| File under `reports/security/` | Purpose |
| --- | --- |
| `trivy-image-raw.json` | Original HIGH/CRITICAL findings and secrets |
| `trivy-image-vex.json` | Active findings and vendor-assessed suppressions |
| `trivy-vex-decision.json` | Counts, each decision, approval checks and errors |
| `vex-app-inspect.json`, `vex-base-inspect.json` | Image identity, platform and base layers |
| `dhi-python-vex.json`, `vex-review.json` | Exact assessed vendor file and review/checksum record |

The vendor document was exported by the user with Docker Scout `--verify`, which
reported successful signature, claims and transparency-log checks. This project
records that import evidence and pins the reviewed document's checksum. CI does
not claim to repeat online cryptographic signature verification on every run.

## Meaning of the reviewed decisions

The prior 12 package findings contained nine distinct CVEs. Docker's document
marks all nine `not_affected` for the reviewed base. Three include explicit
backport notes: Expat CVE-2026-117610 and CVE-2026-118370, and SQLite
CVE-2026-119373. The other six use vendor applicability assessments citing Debian
no-DSA decisions. A no-DSA classification is not evidence that code was patched;
these remain recorded vendor applicability decisions, not independent patch tests.
Review those assumptions when changing the application or exposing new interfaces.

## Updating the base or vendor assessments later

Export new vendor data with signature verification, retain the full image digest,
and review the CVEs, exact package versions, platform and applicability reasons.
Update the Dockerfile base and `security/vendor-vex/review.json` together; retain
the original exported vendor document unchanged. Verify the new document checksum
and run all tests plus a complete image scan. Newly suppressed CVEs are blocked
until added to the reviewed decision set. A new base layer prefix is also blocked
until the review and Dockerfile agree.

## Validation boundary

Native tests exercise the real Trivy 0.76.1 suppression format with a **synthetic
Debian package-metadata fixture**. In the local database snapshot it produced 11
raw HIGH findings, all accounted for as reviewed suppressions, with zero active
findings. This tests the matching and decision logic; it is not a complete Docker
image scan. Both model gates, all 32 tests, Ruff, Bandit, shell syntax and workflow
parsing were checked during preparation. A Docker daemon is unavailable in the
preparation workspace, so the complete checked script and hosted workflow still
need execution in your environment.

References:

- https://docs.docker.com/dhi/how-to/scan/
- https://docs.docker.com/dhi/explore/security-concepts/vex/
- https://github.com/docker-hardened-images/catalog/blob/main/image/python/debian-13/3.12-dev.yaml
