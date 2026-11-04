# Evidence for the mandatory AI/ML and GenAI infrastructure requirement

Each cloud has its own copy of the application, data, training, evaluations and
release scripts under `aws/` or `azure/`. Record deployment evidence separately.

The requirement: hands-on experience supporting or building cloud infrastructure
and deployment pipelines for AI/ML and Generative AI applications, preferably
within financial services, digital advisory or another regulated environment.

This project's domain is payment operations. It uses synthetic data and
regulated-environment design practices; it is not a claim of employment or
production experience operating a regulated financial institution's AI platform.

| Requirement | Hands-on work | Evidence to keep after deployment |
| --- | --- | --- |
| Cloud AI infrastructure | Terraform EKS/AKS, networking, registries, AI service access | Reviewed plan, outputs, healthy cluster nodes |
| AI/ML deployment pipeline | Train incident classifier, gate held-out F1, package model with API | Model JSON, dataset hash, model evaluation build artifact |
| Deep-learning model delivery | Train TensorFlow and PyTorch payment-risk networks, gate holdout metrics, package versioned weights and preprocessing | `.keras` / `.pt` model bundle, split IDs, hashes, test metrics, successful risk workflow URL |
| GenAI deployment pipeline | Release runbook retrieval API; call Bedrock/Azure OpenAI | Live smoke result and an answer with source citation |
| GitHub Actions on AWS | PR checks, image scan, ECR push, EKS deployment | Successful run URL and immutable image tag |
| Azure DevOps on Azure | Quality stage, ACR push, AKS deployment through WIF | ADO Build ID, artifact report and release result |
| Identity and access | GitHub OIDC, AWS IRSA, ADO WIF, AKS workload identity | Explain four independent trust paths; role scopes |
| Release governance | Protected branch/environment, saved Terraform plans, quality gates | PR review and configured approval evidence |
| Operations | Probes, metrics endpoint, live inference failures, Helm rollback | Failure drill and verified restored version |
| Financial-services context | Payment timeout, idempotency, authentication and capacity runbooks | Demonstration using only the included synthetic examples |

## Definition of done

- [ ] Local training, evaluation, tests and API smoke pass.
- [ ] GitHub PR checks run in your repository.
- [ ] AWS Terraform applies successfully in your chosen sandbox account.
- [ ] GitHub release deploys the API to EKS and a real Bedrock request succeeds.
- [ ] Azure Terraform applies successfully in your chosen subscription.
- [ ] ADO release deploys the API to AKS and a real Azure OpenAI request succeeds.
- [ ] A poor model or broken evaluation blocks a release.
- [ ] A failed live inference deployment rolls back and the healthy revision works.
- [ ] You can explain pipeline identity vs kubelet/node identity vs pod identity.
- [ ] You have recorded costs/resources and completed a reviewed teardown.

Until the relevant boxes are complete, call the cloud portions implementation
work in progress. Files alone are not evidence of successful cloud operation.

## Release evidence record

Fill this after each cloud release; do not include tokens or credentials:

```text
Date:
Cloud and region:
Account/subscription alias:
Pipeline run URL / Build ID:
Git commit:
Container image tag or digest:
Dataset SHA256:
Model version:
Prompt version:
Held-out macro F1 and evaluation-set size:
Retrieval evaluation result:
Live inference result (provider, source ID):
Approval / reviewer evidence:
Failure drill and rollback result:
Resources destroyed / retained:
```

## Interview explanation after you complete the cloud runs

Describe what you personally implemented and show the evidence:

"I built a payment-operations AI platform lab on AWS and Azure. I provisioned
the Kubernetes platforms and cloud identity with Terraform, deployed a trained
incident classifier and a runbook-based GenAI API, and used GitHub Actions for
AWS and Azure DevOps for Azure. The pipelines evaluated the model and retrieval,
scanned the image, and verified real managed-model inference after deployment.
I also tested a failed release and restored the last healthy application,
model and prompt together."

Use that wording only once each claimed activity has actually been completed.
For production readiness, discuss the extensions and gaps in the corresponding cloud's OPERATIONS.md:
larger evaluation datasets, vector retrieval, monitoring services, authenticated
ingress, private networking, model registry and separate release environments.
