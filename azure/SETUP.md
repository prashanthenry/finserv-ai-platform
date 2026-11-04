# Azure: Azure DevOps → ACR → AKS → Azure OpenAI

> Run application and Terraform commands from `finserv-ai-platform/azure/`.

## 1. Confirm the intended subscription and quota

```bash
az login
az account list --query '[].{Name:name,ID:id,Default:isDefault}' --output table
az account set --subscription 'REPLACE_CONFIRMED_SUBSCRIPTION_ID'
az account show --query '{Name:name,Subscription:id,Tenant:tenantId}' --output json
az ad signed-in-user show --query id -o tsv
az vm list-usage --location eastus2 --output table
```

The earlier lab used a subscription named `prashanthdevops`; verify it rather
than assuming the display name or default is still correct. These files create
a new `rg-genai-lab`; they do not modify your payment-lab ACR or AKS resources.

Register required providers if necessary:

```bash
az provider register --namespace Microsoft.ContainerService --wait
az provider register --namespace Microsoft.ContainerRegistry --wait
az provider register --namespace Microsoft.CognitiveServices --wait
az provider register --namespace Microsoft.ManagedIdentity --wait
az provider register --namespace Microsoft.Network --wait
az provider register --namespace Microsoft.Compute --wait
```

Check that your selected region supports your chosen Azure OpenAI chat model,
version and `GlobalStandard` SKU, and that the subscription has token quota.
The chosen model must support chat completions, temperature and
`max_completion_tokens`. For residency-sensitive deployments, choose and
validate an appropriate deployment type instead of assuming GlobalStandard
meets your policy. Model names/versions are required inputs, not guessed here.

Confirm VM quota for `Standard_D2s_v3` (or change `node_size` to an available AKS
system-pool-compatible SKU). The node pool has one node for lab cost control;
this is not a highly available cluster.

## 2. Keep Terraform state locally

The configured local backend stores this project's state in
`azure/infra/terraform.tfstate` relative to the repository root. Use the same
project folder on your Mac for every infrastructure operation. No state-storage
cloud resources or state-storage pipeline variables are required.

Run one infrastructure operation at a time. Keep a protected local backup after
each successful apply or destroy using `bash scripts/backup-state.sh`. State and
backups are ignored by Git. See [LOCAL-STATE.md](../docs/LOCAL-STATE.md), including
the migration instructions if you already applied the older backend configuration.

## 3. Create the application WIF service connection

In Azure DevOps, create a project or use an existing appropriate lab project.
Project settings → Service connections → New → Azure Resource Manager →
Workload identity federation. Name it `azure-genai-wif`. Copy its service
principal **object ID** (not the app/client ID) for `pipeline_object_id`.

Use the issuer and subject shown by the actual service connection when setting
up federation; do not hardcode older `sc://...` examples. Let the connection
create the supported federation settings where available. Authorize only the
intended pipeline. Terraform assigns its runtime roles once the resources exist.

If automatic connection creation initially grants Contributor broadly, narrow
it after setup to the roles Terraform grants: `AcrPush`, cluster credential
retrieval and namespace-scoped AKS writer. The app pipeline does not need Owner.
The operator applying Terraform needs permission to create role assignments,
in addition to resource provisioning permissions.

## 4. Provision AKS, ACR and Azure OpenAI

```bash
cp infra/terraform.tfvars.example infra/terraform.tfvars
```

Fill all placeholders, including the operator and pipeline object IDs and
globally unique ACR/OpenAI names. Then:

```bash
terraform -chdir=infra init
terraform -chdir=infra validate
terraform -chdir=infra plan -out=release.tfplan
terraform -chdir=infra show release.tfplan
terraform -chdir=infra apply release.tfplan
bash scripts/backup-state.sh
terraform -chdir=infra output
```

Your local Terraform operator must be able to create the target resource group
and role assignments. Reader/Contributor alone cannot create role assignments.

Terraform enables Azure CNI Overlay/Cilium, managed Entra access, disables local
AKS accounts, enables workload identity, assigns the kubelet `AcrPull`, and gives
the pod identity `Cognitive Services OpenAI User`. OpenAI local/API-key auth is
disabled. The ACR uses legacy registry RBAC (not ABAC repository permissions).

The Kubernetes API remains publicly reachable with Entra authentication so
Microsoft-hosted agents can access it. Empty `api_cidrs` is deliberate for this
lab. For a restricted/private API, provide a network path from managed runners
or another suitable agent pool before applying restrictions.

Using the configured operator identity, wait for RBAC propagation and create
the namespace once:

```bash
az aks install-cli
az aks get-credentials --resource-group rg-genai-lab --name genai-lab --overwrite-existing
kubelogin convert-kubeconfig -l azurecli
kubectl create namespace genai --dry-run=client -o yaml | kubectl apply -f -
kubectl get nodes
```

If you changed `name`, substitute the resulting resource group and cluster name.

## 5. Configure Azure DevOps

Create variable group `genai-azure-dev` under Pipelines → Library, authorize the
app pipeline, and add:

| Variable | Value from `terraform -chdir=infra output` |
| --- | --- |
| `RESOURCE_GROUP` | `resource_group` |
| `AKS_CLUSTER` | `cluster_name` |
| `ACR_NAME` | `acr_name` |
| `ACR_LOGIN_SERVER` | `acr_login_server` |
| `WORKLOAD_CLIENT_ID` | `workload_client_id` |
| `OPENAI_ENDPOINT` | `openai_endpoint` |
| `OPENAI_DEPLOYMENT` | `openai_deployment` |
| `KUBECTL_VERSION` | Exact available kubectl version matching AKS cluster minor |

Create environment `azure-dev`; add an approval check and limit pipeline
permissions. YAML naming an environment does not itself create an approval.

Pipelines → New pipeline → GitHub → select the same private repo → Existing YAML
→ `azure/azure-pipelines.yml`. Authorize the GitHub connection, variable group,
environment and WIF service connection when prompted by ADO. Microsoft-hosted
parallel jobs must be available for the organization; check entitlement if jobs
remain queued.

Run once with `deployAzure=false` to validate. Then manually run on `main` with
`deployAzure=true`. Subsequent automatic runs continue to validate only, unless
you deliberately change that parameter default after reviewing the setup.

The pipeline uses `ubuntu-latest`, pushes an image tagged with commit and Build
ID, authenticates to AKS through WIF/Azure CLI/kubelogin, deploys with Helm, then
requires a real Azure OpenAI inference answer. Provider errors fail the release;
there is no silent offline fallback.

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
