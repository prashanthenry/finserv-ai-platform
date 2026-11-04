# AWS: GitHub Actions → ECR → EKS → Bedrock

> Run application and Terraform commands from `finserv-ai-platform/aws/`.
> Run the repository creation commands in section 3 from the parent `finserv-ai-platform/` folder so GitHub discovers `.github/workflows`. Then return to `aws/`.

## 1. Confirm access and model availability

Use your SSO profile, not a root-user access key. The earlier lab profile was
`eks-lab`; confirm that it still targets the intended sandbox account:

```bash
aws sso login --profile eks-lab
export AWS_PROFILE=eks-lab
export AWS_REGION=us-east-1
aws sts get-caller-identity
aws eks describe-cluster-versions --region "$AWS_REGION"
aws bedrock list-foundation-models --region "$AWS_REGION" --by-inference-type ON_DEMAND \
  --query 'modelSummaries[?contains(outputModalities, `TEXT`)].{ID:modelId,Name:modelName}' --output table
```

Choose an EKS version in standard support and a regional on-demand model that
supports the Converse API, temperature and maxTokens parameters. Verify model
access in Bedrock. Some model providers require first-use details or additional
permissions/subscriptions. Inference-profile IDs and ARNs are not interchangeable
with the single-region foundation-model ID expected by this lab's IAM policy.

The bootstrap operator needs permissions for VPC, EKS, ECR, IAM, EC2, CloudWatch
and `iam:PassRole`. Use a
dedicated lab account and your approved platform-provisioning role.

## 2. Keep Terraform state locally

The configured local backend stores this project's state in
`aws/infra/terraform.tfstate` relative to the repository root. Use the same
project folder on your Mac for every infrastructure operation. No state-storage
cloud resources or state-storage pipeline variables are required.

Run one infrastructure operation at a time. Keep a protected local backup after
each successful apply or destroy using `bash scripts/backup-state.sh`. State and
backups are ignored by Git. See [LOCAL-STATE.md](../docs/LOCAL-STATE.md), including
the migration instructions if you already applied the older backend configuration.

## 3. Create the GitHub repository and OIDC provider

Create a private repo named `finserv-ai-platform`, initialized without a README.
From this project folder, with GitHub CLI signed in:

```bash
git init -b main
git add .
git commit -m 'Add two-cloud GenAI and MLOps platform lab'
gh repo create finserv-ai-platform --private --source=. --remote=origin --push
```

GitHub Settings → Environments: create `aws-dev`, restrict deployment branches to
`main`, and configure a reviewer if your plan supports it. Leave repository
variable `DEPLOY_AWS` unset for now, so initial pushes run validation only.

In IAM → Identity providers, create or reuse:

* Provider URL: `https://token.actions.githubusercontent.com`
* Audience: `sts.amazonaws.com`

Do not create a duplicate if the account already has this provider. Copy its ARN
into Terraform inputs. The project creates a separate app deployment role that
trusts an **exact** GitHub OIDC subject.

GitHub's documentation states that repositories created after July 15, 2026 can
use immutable IDs in subjects. Verify this repository's actual configuration.
With environment `aws-dev`, the documented subject formats are:

```text
repo:OWNER/REPO:environment:aws-dev
repo:OWNER@OWNER_ID/REPO@REPO_ID:environment:aws-dev
```

Get the IDs with `gh api user --jq .id` and
`gh api repos/prashanthenry/finserv-ai-platform --jq .id`. If the owner is an
organization, get its ID instead. A custom OIDC subject template can change the
format further. Never broaden the trust to `repo:*` to work around a mismatch.

## 4. Provision the infrastructure

```bash
cp infra/terraform.tfvars.example infra/terraform.tfvars
```

Fill every `REPLACE` value. `github_subject` must match `aws-dev`. Then:

```bash
terraform -chdir=infra init
terraform -chdir=infra validate
terraform -chdir=infra plan -out=release.tfplan
terraform -chdir=infra show release.tfplan
terraform -chdir=infra apply release.tfplan
bash scripts/backup-state.sh
terraform -chdir=infra output
```

This creates private worker nodes in two subnets/AZs, one NAT gateway, an EKS
cluster, two worker nodes, ECR, IRSA for Bedrock and a namespace-scoped pipeline
role. A single NAT gateway is a lab cost/design tradeoff, not resilient multi-AZ
egress. The API is publicly reachable with IAM authentication to accommodate
rotating hosted-runner addresses. Restrict `api_cidrs` if you have a controlled
runner egress range; runners must still be able to reach the API.

Using the same operator identity that created EKS:

```bash
aws eks update-kubeconfig --name genai-lab --region "$AWS_REGION"
kubectl create namespace genai --dry-run=client -o yaml | kubectl apply -f -
kubectl get nodes
```

The app pipeline intentionally cannot create namespaces. If infrastructure was
created by a different role, grant your operator an EKS access entry before this
step. Keep using the configured operator identity for infrastructure changes.

## 5. Configure the GitHub app pipeline

Set repository variables in Settings → Secrets and variables → Actions:

| Variable | Value |
| --- | --- |
| `AWS_REGION` | Chosen region |
| `EKS_CLUSTER` | `terraform output -raw cluster_name` |
| `ECR_REPOSITORY` | `terraform output -raw ecr_repository`, full registry/repository |
| `AWS_DEPLOY_ROLE_ARN` | `terraform output -raw pipeline_role_arn` |
| `AWS_POD_ROLE_ARN` | `terraform output -raw pod_role_arn` |
| `BEDROCK_MODEL_ID` | Same regional foundation-model ID used in Terraform |
| `KUBECTL_VERSION` | Exact available kubectl version matching the cluster minor |
| `DEPLOY_AWS` | Set to `true` after infrastructure and namespace are ready |

All outputs above are read from `infra`; use `terraform -chdir=infra ...`.
Do not store AWS access keys. The deploy job uses GitHub OIDC; the running pod
uses IRSA. These are separate trust relationships and permissions.

Open Actions → AWS application release → Run workflow on `main`. Verify:

1. Quality reports and model artifact are published.
2. The image is scanned before pushing to immutable ECR tags.
3. Helm rolls out the image with the Bedrock service account role.
4. The live smoke check returns `live_inference: true` and a source citation.

## 6. Infrastructure CI validates; your Mac provisions

The infrastructure pipeline checks Terraform formatting/schema and runs IaC
security scanners. It does not run a live plan or apply, read the workstation's
state, or upload state as an artifact. It needs no cloud provisioning connection
or state-storage variables. Configure the pipeline from its existing YAML path.

Run `terraform -chdir=infra plan`, review the saved plan, and apply locally from
this cloud folder using your authenticated operator identity. Preserve the local
state for subsequent updates and teardown. The application pipeline continues
to build, scan and deploy with its existing restricted cloud identity.

The supplied `.terraform.lock.hcl` should remain in Git; state, backups, local
variable files and saved plans must stay out of Git.

## Configure security checks before the first CI run

Follow [the security setup guide](../docs/SECURITY.md) for SonarQube Cloud credentials,
ADO extension tasks, scanner reports and DAST. Strict gates may identify findings
in this lab infrastructure that need remediation before deployment.
