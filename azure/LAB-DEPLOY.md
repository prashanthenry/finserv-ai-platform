# Azure lab deployment without security scans

In Azure DevOps, select the pipeline using `azure/azure-pipelines.yml`, choose
Run pipeline on `main`, select **labBypassChecks=true** and **deployAzure=true**.
This skips Sonar, Checkov, tfsec, Trivy, Bandit, dependency auditing and DAST for
that manual run. The model is still prepared, the image is built and pushed to
ACR, and Helm deploys the copilot to AKS. The deployment smoke test requires a
real Azure OpenAI answer; offline output cannot pass.

Prerequisites remain the existing AKS/ACR/Azure OpenAI resources, `genai`
namespace, `azure-genai-wif` service connection, `genai-azure-dev` variable group
and `azure-dev` environment described in [SETUP.md](SETUP.md). The bypass does
not create Azure resources or assign permissions. Azure uses Azure OpenAI;
AWS uses Bedrock. There is no TensorFlow/PyTorch payment-risk component in the
current Azure folder.

For `azure/azure-infra.yml`, select **labBypassChecks=true** on a manual `main`
run to skip its IaC scanners. Terraform formatting and validation still run;
infrastructure apply continues locally with the existing local state.

Unselected/default push and PR runs retain their existing checks. The bypass
does not remove scanner scripts or require configuring Sonar in the bypass run.
