# AWS Alpine image remediation — build and scan pending

The supplied local scan of `copilot:ci` on Debian 13.7 found 45 HIGH package
findings representing nine unique CVE IDs. Every listed finding was an OS
package finding with no fixed version listed; the HIGH/CRITICAL-filtered report
showed no Python package findings and zero secret findings.

The base was `python:3.12-slim`. Several Debian advisories remain unresolved in
both Trixie and Bookworm, so changing Debian releases alone is not a complete
remediation. This candidate tests a different supported Python image variant.

## Candidate and verification scope

`aws/Dockerfile` now uses the user-selected official `python:3.12-alpine` base and Alpine
user-management commands. The application still runs as UID/GID 10001. Runtime
dependencies, application files, runbooks, model and startup command are the same.
The original Debian Dockerfile is retained as `aws/Dockerfile.debian`. The user
selected the Alpine change; the rebuilt application still requires verification.

Checks performed during preparation:

* The Trivy 0.76.1 Linux binary archive matched its published release checksum.
* The remote base image was scanned for HIGH/CRITICAL vulnerabilities. Results
  and image digests are recorded in `alpine-base-scan-summary.json`.
* All pinned runtime requirements resolved to prebuilt musllinux wheels for
  Python 3.12 on Linux amd64 and arm64. This checks wheel availability, not actual
  installation or runtime compatibility.
* A Docker daemon is unavailable in the preparation workspace. The complete
  candidate application image has not been built, scanned or smoke-tested here.

Alpine uses musl rather than glibc. A base-image scan is not an application-image
scan or proof of application compatibility. Keep the existing security gate;
do not suppress findings simply to pass it.

## Build and scan on your Mac

From `finserv-ai-platform/aws/`, preserve the original report:

```bash
cp reports/security/trivy-image.json reports/security/trivy-image-debian.json
```

Build the updated Dockerfile, then use the same strict scan script:

```bash
docker build --pull --no-cache -t copilot:ci .
bash scripts/scan-image.sh copilot:ci
```

`--only-binary=:all:` in the candidate prevents unexpected source builds and
compiler installation in the runtime image. If dependency installation fails,
review the actual wheel/platform error before changing the dependency lock.
The scan keeps its HIGH/CRITICAL vulnerability and secret gates. Its report is
still written to `reports/security/trivy-image.json`.

## Verify the application after a passing scan

Keep the original local servers on ports 8000/8001 available for comparison.
Run the candidate on port 8002:

```bash
docker run --rm --name copilot-alpine \
  -p 127.0.0.1:8002:8000 \
  -e AI_PROVIDER=offline \
  copilot:ci
```

From another terminal inside `aws/`, activate the existing Python environment
and check readiness, classification and runbook answering:

```bash
source .venv/bin/activate
python -m scripts.smoke --url http://127.0.0.1:8002
```

This is an offline API compatibility check. Bedrock authentication/inference
must still be checked after cloud deployment by the existing live smoke gate.

## Hosted pipeline and verification status

The existing GitHub Actions workflow uses `docker build ... .`, so it will pick
up the updated default Dockerfile. Build, scan and smoke-test locally before
pushing; then run the hosted pipeline's image scan, DAST and live inference gate.
No security finding has been suppressed and no full application-image result is
claimed by this preparation.

The base scans in alpine-base-scan-summary.json are specifically for
`python:3.12-alpine3.24`; the publisher currently lists the floating
`python:3.12-alpine` tag as its Alpine 3.24 variant. Confirm the actual image
digest/OS in your rebuilt scan report. Pin the tested multi-platform digest once
validation passes and maintain it through reviewed updates.

## Sources

* https://hub.docker.com/_/python
* https://hub.docker.com/_/python/tags?name=3.12&page=1
* https://security-tracker.debian.org/tracker/source-package/util-linux
* https://security-tracker.debian.org/tracker/CVE-2026-54369
* https://security-tracker.debian.org/tracker/CVE-2025-69720
* https://security-tracker.debian.org/tracker/CVE-2026-9538
* https://security-tracker.debian.org/tracker/source-package/sqlite3
* https://security-tracker.debian.org/tracker/source-package/systemd
