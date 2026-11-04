# Operate the AZURE project

Run commands from `finserv-ai-platform/azure/`.
The teardown commands below apply to this cloud folder only.

## Run a real request

After selecting the appropriate EKS/AKS kubeconfig context:

```bash
kubectl config current-context
kubectl -n genai get pods,svc
kubectl -n genai port-forward svc/copilot 8000:8000
```

In another terminal in the project folder:

```bash
curl -fsS http://127.0.0.1:8000/version
curl -fsS http://127.0.0.1:8000/metrics
python -m scripts.smoke --require-live
```

The API is intentionally ClusterIP-only. Port forwarding provides a working
private lab session without publishing an unauthenticated paid-inference API.
Application ingress authentication, TLS, rate limiting and an API gateway are
future platform work; do not expose this API directly to the public internet.

## Release and MLOps drills

1. Change one synthetic training example in `data/incidents.json` on a feature
   branch. Open a PR and inspect the model version and evaluation report.
2. Break a held-out label to observe a failing evaluation gate. Fix the data
   rather than lowering the threshold to make the pipeline green.
3. Change a runbook or the prompt. Inspect the retrieval report, then verify
   answer grounding manually after a real inference call.
4. Merge an approved change and release the same code to each cloud. Record
   commit, image tag, model hash and prompt version from `/version`.
5. Test a bad model ID in the dev deployment. The live smoke test must fail and
   restore the previous Helm revision. First-install failure uninstalls the
   failed release instead.

The datasets are tiny and synthetic. A 1.0 F1 score here shows the mechanics of
the evaluation gate; it does not demonstrate production model accuracy or
generalization. The retrieval gate also does not prove an LLM answer is true.
The live smoke test checks reachability, real inference and an expected citation,
not full factuality, safety or prompt-injection resistance.

## Metrics

The application exports:

* `copilot_requests_total{route,result}`
* `copilot_inference_seconds_bucket`
* `copilot_tokens_total{direction}`

Useful PromQL once a Prometheus/Grafana stack is installed and scraping:

```promql
sum(rate(copilot_requests_total{route="ask",result="error"}[5m]))
/
clamp_min(sum(rate(copilot_requests_total{route="ask"}[5m])), 0.001)
```

```promql
histogram_quantile(0.95, sum by (le) (rate(copilot_inference_seconds_bucket[5m])))
```

This kit exposes metrics but does not deploy Prometheus, Grafana or alerts.
Annotations alone do not configure a scraper. If the scraper runs outside
`genai`, add its namespace selector to the chart's ingress NetworkPolicy.
HPA is disabled by default; install/verify the Kubernetes metrics API before
enabling `autoscaling.enabled`. EKS CNI network-policy enforcement is requested
through the VPC CNI add-on; verify it in the deployed cluster.

## Rollback and hotfix

```bash
helm history copilot -n genai
helm rollback copilot REPLACE_HEALTHY_REVISION -n genai --wait --timeout 10m
python -m scripts.smoke --require-live
```

Image, JSON model and prompt code are packaged together, so a Helm image rollback
restores them together. Dataset/retrieval documents in the image also return to
that release. External managed-model version changes require separate controls.
For a hotfix, branch from the deployed commit, fix and test, then PR into `main`;
this kit permits deployment from `main`, preserving the same quality gates.

No staging/production promotion pipeline or blue/green infrastructure is claimed
here. Add those as a later exercise with explicit approvals and independent
environment state.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| GitHub AssumeRoleWithWebIdentity denied | Exact OIDC subject, audience, repo IDs, selected environment |
| EKS forbidden | EKS access entry, namespace `genai`, matching deploy role |
| Bedrock 502 | Regional model ID, provider onboarding, InvokeModel policy, IRSA annotation, egress |
| ACR push denied | WIF app object ID and `AcrPush` scope; role propagation |
| AKS image pull denied | Kubelet identity `AcrPull`, image name/tag; not pod OpenAI identity |
| AKS forbidden | Credential-retrieval role plus namespace RBAC Writer; correct tenant/subscription |
| Azure OpenAI 502 | Deployment name, model quota, client-ID annotation, pod workload label, RBAC propagation |
| Terraform authorization failure | Correct local state folder, operator login and resource/role-assignment permissions |
| VM quota failure | Regional SKU-family quota and availability; choose a supported system-pool SKU |
| Smoke test fails with offline output | Wrong `AI_PROVIDER`; cloud release cannot use offline mode |

Do not log prompts, provider error bodies or access tokens while debugging.
The basic regex redactor only covers selected identifier patterns; it is not a
complete financial-data classification or DLP control. Source documents here are
synthetic. Production needs stronger data handling and a threat model.

## Teardown

Disable `DEPLOY_AWS` and leave ADO's `deployAzure` false before cleanup so a push
does not recreate workloads. Confirm the kubeconfig context before uninstalling:

```bash
kubectl config current-context
helm uninstall copilot -n genai
```

AWS: Terraform intentionally does not force-delete a populated ECR repository.
Remove the lab repository images explicitly after reviewing their names, or
delete only this lab's ECR repository before the destroy. Do not run a broad
account-wide registry cleanup. Then:

```bash
terraform -chdir=infra plan -destroy -out=destroy.tfplan
terraform -chdir=infra show destroy.tfplan
terraform -chdir=infra apply destroy.tfplan
bash scripts/backup-state.sh
```

For Azure, use the same reviewed destroy sequence from its own `azure/` folder.

Preserve the local state file and protected local backups. Check separately
for retained EKS CloudWatch logs, soft-deleted Azure OpenAI accounts and any
resources created manually during extensions. Cluster deletion ends API access;
it does not prove every external billable resource has been removed.

## Production-oriented extensions

After both dev releases work, add these in order:

1. A vector-backed RAG index, versioned ingestion and external object storage.
2. Larger labeled evaluation sets, answer-grounding review, prompt-injection
   tests, drift monitoring and scheduled retraining with human review.
3. A managed model registry/experiment service instead of build artifacts alone.
4. Prometheus/Grafana/OTel, SLOs, error budgets and actionable alerts.
5. Private networking with hosted managed pools that can reach the clusters;
   authenticated ingress, quotas, rate limits, provenance/signing and digest pins.
6. Separate staging/production, backup/restore exercises, data residency review
   and tested recovery objectives. Pods spread across nodes/AZs and resilient
   egress are required before claiming high availability.

Keep interview claims precise: you built a hands-on lab until you have operated
it under real production responsibilities.

Run all infrastructure operations on the same Mac project folder. Hosted infrastructure CI is validation-only.
