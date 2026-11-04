# Validation — separate cloud folders and security integration

Updated November 3, 2026. AWS and Azure are independently runnable projects.

| Check | AWS | Azure |
| --- | --- | --- |
| Application unit tests | 12 passed | 12 passed |
| pytest coverage | 93% rounded | 94% rounded |
| Coverage XML for SonarQube Cloud | Generated | Generated |
| Model gate | F1 1.0000 on 9 synthetic held-out examples | Same dataset and result |
| Retrieval gate | 6/6 synthetic cases | 6/6 synthetic cases |
| Ruff | Passed | Passed |
| Bandit application scan | Passed at medium/high severity threshold | Passed at medium/high severity threshold |
| Runtime dependency audit | No known vulnerabilities reported at check time | No known vulnerabilities reported at check time |
| Other cloud AI dependencies | Excluded | Excluded |
| Terraform module source | Updated to infra/modules/platform | Updated to infra/modules/platform |
| Pipeline paths | AWS directory and artifact paths updated | Azure directory and artifact paths updated |
| Security release dependencies | Requires quality, IaC and Sonar jobs | Requires Quality and Security stages |

Local HTTP smoke, Helm lint/rendering, shell syntax and Terraform formatting are
checked for each reorganized cloud folder before packaging. Pipeline YAML is
parsed locally, which is not a substitute for server-side pipeline validation.

## Integrated but not executed here

* SonarQube Cloud needs organization/project keys and a GitHub token or ADO
  service connection. Quality-gate waiting is configured; no analysis was uploaded.
* Docker builds, Trivy container scans, Checkov, tfsec and OWASP ZAP use supplied
  containerized commands. Docker is unavailable here, so no clean scanner result
  is claimed for these new checks.
* Terraform schema validation remains unverified. Earlier checks hit provider
  package checksum mismatches and an Azure provider startup/handshake error.
  Formatting checks do not prove provider schema correctness.
* AWS/Azure Terraform plans/applies, hosted pipeline runs, real managed-model
  inference and Kubernetes rollback have not been executed in your accounts.

Run clean terraform init, terraform validate and a reviewed account-specific
plan before applying. Do not disable integrity checks to work around provider
errors. Strict security scans may fail on existing lab configuration choices;
review and remediate their reports before deployment.

Generated model version: 73b60cfde38a. The JSON stores the dataset hash. Sample
local evidence is included in each cloud reports/ and artifacts/ directories.
CI regenerates these files and publishes reports; Git ignores generated evidence.

Synthetic evaluation scores demonstrate workflow mechanics, not production
accuracy, regulatory compliance or model safety. Use JD-EVIDENCE.md to record
actual cloud deployments and failure drills as you complete them.

## Local-state update

Both Terraform roots now use the local backend with terraform.tfstate in their
own infra directories. Infrastructure CI is validation/security-only and has no
plan/apply or state upload steps. No existing cloud state was migrated and no
cloud operations were performed by this update. Application code, model data,
Helm charts and application pipeline definitions were preserved.

Local-state checks passed: Terraform formatting, local-backend declarations, validation-only pipeline YAML, backup creation/missing-state behavior/file permissions, and documentation links. No application regression run was needed because application code/tests and application pipeline files were byte-for-byte unchanged.

## Alpine image candidate

The AWS Dockerfile now uses the selected Alpine base and Alpine user commands; its Debian version is retained as Dockerfile.debian. Remote-base vulnerability scan results are in alpine-base-scan-summary.json. Runtime wheel resolution passed for musllinux amd64 and arm64. Full image build, image scan, API smoke, DAST and Bedrock integration remain pending; security gates were preserved. The full Alpine application image remains to be built, scanned and tested on the user workstation.

## TensorFlow and PyTorch payment-risk addition — November 4, 2026

The independent AWS component is `aws/payment-risk/`. Its synthetic dataset has
6,000 payments (1,000 positive), split into 3,600 training, 1,200 validation and
1,200 test rows. Scaling is fit only on training data. Validation loss selects
weights; fixed holdout gates apply to both engines. TensorFlow 2.21.0 and PyTorch
2.15.0 CPU were executed on Linux/Python 3.12.14.

| Check | Result |
| --- | --- |
| Real TensorFlow and PyTorch training and serialization round trip | Passed |
| TensorFlow test ROC-AUC / F1 / recall | 0.98432 / 0.83854 / 0.805 |
| PyTorch test ROC-AUC / F1 / recall | 0.98513 / 0.84184 / 0.825 |
| Automated tests | 20 passed, one existing FastAPI TestClient/httpx deprecation warning |
| Coverage including the executed training/gate sequence | 90% rounded |
| HTTP API smoke with both model engines | Passed on both low-risk and review examples |
| Ruff / Bandit medium-high gate | Passed |
| Fully pinned Linux runtime dependency audit | 52 packages, zero reported vulnerabilities, zero skipped |
| Fully pinned training/dev dependency audit | 48 packages, zero reported vulnerabilities |
| macOS ARM64 lock resolution and advisory audit | Passed; native execution on a Mac remains pending |
| Helm lint/render, YAML parsing, shell syntax, Terraform formatting | Passed |
| Standard Debian Python base scan, not selected for new image | 36 HIGH, 2 CRITICAL package findings; 13 distinct CVEs |
| Selected hardened runtime | `dhi.io/python:3.12`, with `3.12-dev` build stage; registry authentication required |

The runtime audit maps the official PyTorch `+cpu` build to the same upstream
release for advisory lookup, and rejects skipped packages. The full image must
also pass Trivy; dependency audit results alone do not establish image security.
The standard Debian base findings were not suppressed. The replacement hardened
base could not be pulled anonymously (registry returned HTTP 401). This workspace
has no Docker daemon or registry credentials. Its build/import/load preflight,
full image scan and DAST remain pending in an authenticated Docker environment.

The new GitHub Actions workflow, SonarQube Cloud project, ECR push, EKS rollout and
rollback are implemented but have not run in an account. Terraform adds a risk
ECR repository and updates only the pipeline's repository permissions/output; no
apply occurred. Its state backend remains local. Terraform provider schema
validation remains subject to the earlier recorded environment limitation.
See `aws/payment-risk/README.md` for configuration and the full walkthrough.
