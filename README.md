# Payment Operations AI Platform — separate AWS and Azure projects

Two independently runnable cloud projects in one repository. Each cloud folder
contains its own application, AI integration, dependency locks, Terraform root
and module, Helm chart, tests, synthetic data, model artifacts and scripts.

| Component | AWS | Azure |
| --- | --- | --- |
| Project folder | `aws/` | `azure/` |
| Application | `aws/app/` | `azure/app/` |
| AI integration | Amazon Bedrock through Boto3 | Azure OpenAI through OpenAI + Azure Identity |
| Containers / Kubernetes | ECR / EKS | ACR / AKS |
| Terraform | `aws/infra/` | `azure/infra/` |
| Reusable module | `aws/infra/modules/platform/` | `azure/infra/modules/platform/` |
| Helm chart | `aws/deploy/chart/` | `azure/deploy/chart/` |
| App pipeline | `.github/workflows/aws-app.yml` | `azure/azure-pipelines.yml` |
| Infrastructure validation pipeline | `.github/workflows/aws-infra.yml` | `azure/azure-infra.yml` |
| Start guide | [AWS README](aws/README.md) | [Azure README](azure/README.md) |
| Cloud setup | [AWS setup](aws/SETUP.md) | [Azure setup](azure/SETUP.md) |

GitHub workflow definitions stay in the repository-root `.github/workflows/`
directory, where GitHub discovers them. They use `working-directory: aws` and
cloud-specific artifact paths. AWS application CI watches `aws/**` and its own
workflow file. ADO definitions live inside `azure/`, explicitly use the Azure
working directory, and application CI watches `azure/**`.

Each project is self-contained: neither application imports code or dependencies
from the other folder. Common learning examples are copied into each project so
you can practice the clouds independently. Future fixes to common code should
be reviewed for both copies. Use independent virtual environments as shown in
the cloud READMEs.

## Start with AWS

The AWS project now also includes an independent
[TensorFlow/PyTorch payment-risk component](aws/payment-risk/README.md), with
training, holdout gates, a separate API/container and a dedicated
`.github/workflows/aws-payment-risk.yml` workflow. Its guide includes Apple
Silicon and Intel Mac implementation paths. See its verification boundary before
attempting container or cloud release.

After extracting the archive, enter `finserv-ai-platform/aws` and follow its
README. Run local training, evaluation and tests before using the AWS setup
guide to create infrastructure. Work on Azure afterwards, from
`finserv-ai-platform/azure`.

Use Python 3.12 for the supplied lockfiles. The API provides `/ask`, `/predict`,
`/version`, `/healthz`, `/readyz` and `/metrics`. `/ask` uses lexical TF-IDF
retrieval over synthetic payment runbooks and calls the selected cloud LLM.
The incident classifier is a small trained Multinomial Naive Bayes model.
The managed LLM is not hosted inside these Kubernetes clusters.

Offline mode is for local retrieval practice and reports `live_inference=false`.
Cloud release smoke checks require a real inference call to their own provider.
Both cloud projects include quality gates, workload identity and rollback scripts.
They use hosted pipeline runners; a local Mac agent is not required.

## Deployment and validation status

This is a development lab using synthetic financial-services examples. Cloud
deployments, live inference, Docker image scans and Kubernetes rollback remain
to be verified in your accounts. Terraform schema validation was blocked by
provider checksum/startup errors in the preparation workspace. Run a clean
`terraform init`, `terraform validate` and reviewed plan before any apply.

See [validation evidence](docs/VALIDATION.md) and the
[mandatory job-requirement checklist](docs/JD-EVIDENCE.md). The small dataset
scores demonstrate the evaluation workflow, not production accuracy.

Review resource charges before provisioning and follow each cloud's operations
guide for teardown. Use a sandbox account/subscription. No resources were created
or deployed as part of this folder reorganization.

If you split this into two Git repositories later, copy the top-level AWS
workflows into the AWS repo's `.github/workflows/`, remove their `aws/` working
directory/artifact prefixes, and remove the `aws/**` path prefix in triggers.
Update ADO source paths similarly if `azure/` becomes its own repository root.

## Security gates

Both projects integrate SonarQube Cloud, Trivy, Checkov, tfsec and OWASP ZAP DAST.
Read [SECURITY.md](docs/SECURITY.md) to configure tokens/connections and understand
the blocking policies and report locations. Deployment requires these gates to pass.

## Local Terraform state

Terraform infrastructure runs on your Mac. AWS state stays in
`aws/infra/terraform.tfstate` and Azure state in `azure/infra/terraform.tfstate`.
The hosted infrastructure pipelines validate configuration and run security
scans only; hosted application pipelines continue deployment to EKS/AKS.
State and local backups are excluded from Git and pipeline artifacts.
Follow [LOCAL-STATE.md](docs/LOCAL-STATE.md) for commands and backup/migration guidance.
