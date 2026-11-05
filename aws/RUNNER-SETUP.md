# Private EKS deployment runner

This completes the payment-risk release path: GitHub prepares model artifacts,
then a Linux x64 runner inside the existing VPC builds the deployment image,
pushes it to ECR, deploys with Helm, and smoke-tests both models.

The optional Terraform resources create one Ubuntu 24.04 `t3.large` EC2 instance,
a 60 GiB encrypted gp3 root volume, an SSM-only host IAM role/profile and security
groups. The existing NAT gateway supplies outbound access. There is no public IP
or inbound SSH port. The EKS endpoint stays private.

The host role has SSM permissions only. The workflow obtains ECR and EKS
deployment credentials through the existing GitHub OIDC role. Registration
tokens are entered on the runner; never put them in Terraform, Git or chat.
This is a persistent lab runner; use it for trusted main-branch releases only.
The workflow keeps PR checks on GitHub-hosted runners.

## 1. Create the optional runner from the Mac

Keep `DEPLOY_RISK_AWS` unset/false until registration and bootstrap finish.
From the repository root:

```bash
git pull --ff-only origin main
cd aws/infra
```

Add this line once to your existing, ignored `terraform.tfvars`:

```hcl
enable_github_runner = true
```

Then:

```bash
terraform init
terraform validate
terraform plan -out=runner.tfplan
```

Review the plan. The runner addition should not replace EKS, its node group or
the ECR repositories. If Terraform proposes replacing any of those, resolve the
difference before applying. The optional runner adds EC2, EBS and monitoring
charges. State remains in your local `aws/infra/terraform.tfstate`.

```bash
terraform apply runner.tfplan
terraform output -raw github_runner_instance_id
```

The Ubuntu AMI is resolved from Canonical's public SSM parameter. A future AMI
change can propose replacing the runner; review plans before future applies.
Cloud-init installs Docker, AWS CLI v2, Python 3.12, Git and the verified GitHub
runner package. Creating the instance does not register it with GitHub.

## 2. Register the runner through Session Manager

AWS Console -> EC2 -> select `genai-lab-github-runner` -> Connect ->
Session Manager -> Connect. The instance needs to appear SSM-online first.

In that EC2 terminal, wait for initialization and inspect failures if necessary:

```bash
sudo cloud-init status --wait
sudo test -f /var/lib/github-runner-ready
```

If cloud-init fails, inspect `sudo tail -n 100 /var/log/cloud-init-output.log`.
Do not register until the readiness file exists.

In GitHub open Repository Settings -> Actions -> Runners -> New self-hosted
runner, select Linux / x64. The package is already installed and checksum
verified. Use the fresh registration token from the displayed Configure command
only in the EC2 terminal. It expires; do not send it to anyone.

Switch to the runner account:

```bash
sudo -iu gha-runner
cd /opt/actions-runner
./config.sh --url https://github.com/prashanthenry/finserv-ai-platform --name genai-lab-aws-vpc --labels aws-vpc --work _work
```

Enter the registration token when prompted, then accept the remaining defaults.
The automatic labels include `self-hosted`, `linux` and `x64`; the extra label
is `aws-vpc`. Exit that user shell and start the runner service:

```bash
exit
cd /opt/actions-runner
sudo ./svc.sh install gha-runner
sudo ./svc.sh start
sudo ./svc.sh status
```

GitHub Settings -> Actions -> Runners should show the runner online/idle with
all four required labels. The workflow installs kubectl, Helm and Docker Buildx.

## 3. Bootstrap the Kubernetes namespace using the Mac's administrator identity

The deployment role has edit access inside `genai`; it cannot create the
namespace. The host SSM role intentionally has no EKS administrator permissions.

Use the same AWS identity on your Mac that created the cluster. Install the AWS
Session Manager plugin if `session-manager-plugin --version` is unavailable.
AWS's macOS installation instructions are linked below.

From the repository root:

```bash
bash aws/scripts/bootstrap-eks-namespace.sh
```

The helper uses the runner as a private SSM tunnel to the EKS API, authenticates
with your Mac's AWS identity, verifies the EKS TLS certificate against its actual
hostname, creates `genai` idempotently and lists nodes. It then removes its
temporary kubeconfig and closes the tunnel. Your normal kubeconfig is untouched.
It needs the administrator's SSM StartSession access and cluster administrator
access. Set `EKS_TUNNEL_PORT` to another unused local port if 18443 is occupied.

## 4. Set GitHub repository variables

Settings -> Secrets and variables -> Actions -> Variables:

| Variable | Value |
| --- | --- |
| AWS_REGION | us-east-1 (or Terraform output deployment_region) |
| EKS_CLUSTER | Terraform output cluster_name |
| ECR_RISK_REPOSITORY | Terraform output ecr_risk_repository |
| AWS_DEPLOY_ROLE_ARN | Terraform output pipeline_role_arn |
| KUBECTL_VERSION | v1.37.2 for the current 1.37 cluster |

Keep the existing DOCKERHUB_USERNAME variable and DOCKERHUB_TOKEN secret for DHI.
Create/verify the GitHub environment `aws-dev` and allow deployment from `main`.

Before enabling release, verify `github_subject` in your local tfvars matches
the actual repository/environment OIDC subject. This repository's expected
default immutable subject is:

```text
repo:prashanthenry@37638315/finserv-ai-platform@1446326195:environment:aws-dev
```

This assumes the default subject configuration. If the repository opted out or
customized its claims, use the actual subject instead and review/apply the
Terraform trust-policy change. Do not broaden trust to all repositories.
An OIDC failure at configure-aws-credentials occurs before pushing/deploying.

## 5. Run release

After the cluster/node group are ACTIVE, namespace exists, variables are set and
runner is online, set repository variable `DEPLOY_RISK_AWS=true`.

Actions -> AWS TensorFlow and PyTorch payment risk -> Run workflow -> main ->
select Lab bypass checks for the temporary lab exception -> Run workflow.
A new manual run is required to select this input; rerunning a previous push
does not select it.

The quality job still generates/trains the models and uploads their artifacts.
The release job now checks Kubernetes authorization before building, then
builds, pushes and runs `scripts/deploy.sh`. That script waits for readiness
and invokes the payment-risk smoke check. It rolls back on a failed smoke check.
The bypass is recorded in the job summary and does not apply to push/PR runs.
The payment-risk workflow validates TensorFlow/PyTorch inference. Use the separate
AWS application release workflow below to validate live Bedrock inference.

## Troubleshooting and cleanup

- Release skipped: check DEPLOY_RISK_AWS is exactly `true`, branch main and model
  preparation success. For regular runs all prerequisite checks must pass.
- Release queued: verify all required runner labels and that its service is online.
- SSM offline: check cloud-init, instance profile, NAT route and HTTPS egress.
- EKS timeout: check the runner-to-EKS HTTPS rule and private endpoint DNS.
- OIDC denied: compare the exact token subject, environment and IAM trust policy.
- Kubernetes forbidden: check the EKS access entry and namespace-scoped policy.
- Namespace not found: complete the administrator bootstrap step.
- ImagePullBackOff: check the pushed ECR tag and worker-node ECR permissions.
- Pending/OOMKilled Pods: inspect node capacity and Pod requests/limits.
- Runner replacement: remove its old registration in GitHub before registering
  the new host with the same name.

To remove only the runner, first set DEPLOY_RISK_AWS=false and remove its GitHub
registration, then set `enable_github_runner=false` in tfvars and review/apply a
new Terraform plan. This deletes the optional runner resources and preserves
the cluster. Keep local state for all subsequent infrastructure changes.

## References

- https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/add-runners
- https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-getting-started-instance-profile.html
- https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-sessions-start.html
- https://docs.aws.amazon.com/systems-manager/latest/userguide/install-plugin-macos-overview.html
- https://documentation.ubuntu.com/aws/aws-how-to/instances/find-ubuntu-images/

## 6. Deploy the separate AWS GenAI copilot and test Bedrock

After payment-risk is working, add these GitHub repository variables:

| Variable | Value |
| --- | --- |
| ECR_REPOSITORY | Terraform output ecr_repository |
| AWS_POD_ROLE_ARN | Terraform output pod_role_arn |
| BEDROCK_MODEL_ID | The same model ID as local tfvars: amazon.nova-micro-v1:0 |
| DEPLOY_AWS | true once ready to deploy the copilot |

The copilot uses the same runner, cluster, namespace, AWS_REGION,
AWS_DEPLOY_ROLE_ARN and KUBECTL_VERSION. Run **AWS application release** manually
on main and select **Lab bypass checks**. This prepares the incident classifier,
builds and pushes the copilot image to ECR, deploys it to EKS with the Bedrock
Pod role, and requires a live Bedrock answer in its smoke test. Sonar, Trivy,
Checkov, tfsec, dependency audits and DAST are skipped in that manual lab run.
Model access or quota errors from Bedrock still fail the inference test, because
that test is what confirms the requested live deployment actually works.

For **AWS Terraform validation**, the same manual **Lab bypass checks** input
skips its IaC security scans while retaining formatting and Terraform validation.
The Azure equivalents are documented in `../azure/LAB-DEPLOY.md`.
