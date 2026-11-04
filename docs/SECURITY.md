# Security scans for both cloud projects

The AWS and Azure folders each contain the same scanner entry points, scoped to
their own code, Terraform and container image. All reports are pipeline artifacts.

| Tool | What it checks here | Blocking behavior |
| --- | --- | --- |
| SonarQube Cloud | Python code analysis, quality gate and imported pytest coverage | Scanner waits for the quality gate; failure or timeout blocks release |
| Trivy filesystem | Dependency vulnerabilities and repository secrets | HIGH/CRITICAL findings or scanner errors fail |
| Trivy config | Terraform misconfigurations | HIGH/CRITICAL findings or scanner errors fail |
| Trivy image | Vulnerabilities and secrets in the built container image | HIGH/CRITICAL findings or scanner errors fail |
| Checkov | Terraform policy checks across the cloud root and local module | Any failed policy or scanner error fails |
| tfsec | Terraform security checks | HIGH/CRITICAL findings or scanner errors fail |
| OWASP ZAP | Active API DAST using the application's OpenAPI specification | WARN, FAIL and operational errors all fail |

Bandit and pip-audit from the original project remain enabled. Model evaluation
and retrieval checks also remain release requirements.

tfsec and Trivy config overlap. Aqua recommends migration toward Trivy; tfsec is
included here because it was explicitly requested and provides useful comparison
practice. Do not count overlapping scanner findings as independent vulnerabilities.

## GitHub Actions / AWS setup

Create a SonarQube Cloud organization and a distinct AWS project, such as
`finserv-ai-aws`, using CI-based analysis. For this monorepo, use the supported
manual/monorepo setup offered by your SonarQube Cloud plan. Configure its quality
gate in the SonarQube Cloud UI. Disable automatic analysis for this project when
using CI-based analysis.

Add the following GitHub repository settings:

| Setting | Type | Value |
| --- | --- | --- |
| `SONAR_TOKEN` | Secret | Analysis token with access to the AWS SonarQube Cloud project |
| `SONAR_ORGANIZATION` | Variable | Organization key from SonarQube Cloud |
| `SONAR_PROJECT_KEY` | Variable | AWS project's key |
| `SONAR_HOST_URL` | Variable | Exact Cloud URL from your project's setup tutorial |

The hosted SonarQube Cloud service replaces the old local
`http://localhost:9000` lab endpoint for these pipelines. Do not paste tokens into
YAML, property files, source code or terminal output shared in a chat.

The app workflow has separate quality, IaC-security and Sonar jobs. Release
depends on all three. A missing Sonar configuration fails the Sonar job; it is
not silently skipped on trusted pushes. Fork PRs do not receive the Sonar token
and cannot deploy. Keep required PR status checks aligned with this trust model.

The infrastructure workflow also runs IaC gates during validation-only CI. Review all
published JSON reports and logs when a gate fails.

## Azure DevOps / Azure setup

1. Create a separate SonarQube Cloud project, such as `finserv-ai-azure`, so its
   analysis history is independent of AWS. Use the appropriate manual/monorepo
   setup and confirm your plan supports the required analysis type.
2. Install the official SonarQube Cloud extension in the ADO organization.
   These definitions use `SonarCloudPrepare@4`, `SonarCloudAnalyze@4` and
   `SonarCloudPublish@4`; match the installed extension's supported task major.
3. Create a SonarQube Cloud service connection named `sonarqube-cloud` using an
   authorized analysis token. Authorize it for the intended pipeline.
4. Add `SONAR_ORGANIZATION` and `SONAR_PROJECT_KEY` to `genai-azure-dev`. Use the
   Azure project's key. The service connection retains the token and Cloud region.
5. Select `azure/azure-pipelines.yml` in ADO. Keep its `sonarServiceConnection`
   parameter set to the connection name. Keep fork builds from accessing secrets.

Prepare configures the source and coverage paths, Analyze uploads the analysis,
and Publish shows the result in ADO. Blocking is implemented by
`sonar.qualitygate.wait=true`, not by assuming a published summary alone blocks a
release. The Release stage depends on both Quality and Security stages.

The infrastructure pipeline at `azure/azure-infra.yml` validates configuration
and runs IaC gates. Live Terraform plans/applies run on your Mac with local state.

## Run scanners locally

Use Docker Desktop and a terminal inside the chosen `aws/` or `azure/` folder:

```bash
bash scripts/scan-iac.sh
```

To build and scan a running API, first activate that folder's Python environment
and generate the model:

```bash
python -m scripts.train
docker build -t copilot:security-lab .
bash scripts/scan-image.sh copilot:security-lab
bash scripts/scan-dast.sh copilot:security-lab
```

`scan-iac.sh` attempts all four static scans, records each exit code, and returns
a failing overall result if any scan fails. It does not suppress scanner errors.
Image tags in this learning kit use the official scanner distribution channels;
review and pin tested image digests for reproducible production use.

## DAST target and reports

ZAP starts against a temporary running container of the application image on an
isolated Docker network. The application uses `AI_PROVIDER=offline` so active
payloads do not generate paid provider calls. The API definition is read from
`/openapi.json`; the target has no public port mapping. Containers and the
temporary network are cleaned up afterwards.

The same scanner script is used by both CI pipelines and again for the exact
release image before deployment. DAST does not target a production cluster,
test cloud IAM, or prove resistance to prompt injection. Those require separate
authorized tests and GenAI evaluation datasets.

Artifacts include:

| Path inside each cloud folder | Contents |
| --- | --- |
| `reports/coverage.xml` | Python coverage imported by SonarQube Cloud |
| `reports/security/checkov.json` | Checkov findings |
| `reports/security/tfsec.json` | tfsec findings |
| `reports/security/trivy-iac.json` | Terraform misconfiguration findings |
| `reports/security/trivy-filesystem.json` | Dependency and secret findings |
| `reports/security/trivy-image.json` | Built-image findings |
| `reports/security/zap/zap.html` | Human-readable DAST report |
| `reports/security/zap/zap.json` | DAST findings as JSON |
| `reports/security/*.log`, `*.exit-code` | Static scanner diagnostics and status |

GitHub and ADO upload security reports even when scanner steps fail. SonarQube
Cloud retains the code analysis and quality-gate results in its project UI.

## Handling initial failures

The infrastructure still contains documented lab choices such as public
authenticated cluster APIs and minimal capacity. IaC scanners can flag these
and other gaps. No blanket ignores or soft-fail mode have been added to make the
build green. A first strict run may therefore fail until you remediate findings
or approve narrowly scoped, documented exceptions with expiry and an owner.

Do not weaken the gates simply to complete a deployment. Treat scanner download,
authentication, database and network errors as failed checks requiring repair.
SonarQube Cloud access, scanner Docker execution, DAST results and cloud release
results have not been verified in this workspace; see VALIDATION.md.

## Official references

* SonarQube Cloud/GitHub: https://docs.sonarsource.com/sonarqube-cloud/analyzing-source-code/ci-based-analysis/github-actions-for-sonarcloud/
* SonarQube Cloud/ADO: https://docs.sonarsource.com/sonarqube-cloud/advanced-setup/ci-based-analysis/azure-pipelines/adding-analysis-to-build-pipeline/js-ts-go-python-php
* Checkov CLI: https://www.checkov.io/2.Basics/CLI%20Command%20Reference.html
* tfsec-to-Trivy: https://github.com/aquasecurity/tfsec/blob/master/tfsec-to-trivy-migration-guide.md
* Trivy configuration scan: https://trivy.dev/docs/dev/guide/references/configuration/cli/trivy_config/
* ZAP API scan: https://www.zaproxy.org/docs/docker/api-scan/

Local Terraform state and backups are never published as security/build artifacts.
