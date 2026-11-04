# AZURE Payment Operations AI Copilot

This self-contained project uses **Azure OpenAI** for live GenAI inference and serves a
trained incident classifier. Its application, dependencies, Terraform, Helm
chart, tests, data and scripts are contained in this folder.

Pipelines: `azure/azure-pipelines.yml` and `azure/azure-infra.yml` in ADO.

## Run locally

Open a terminal inside `finserv-ai-platform/azure/` and use Python 3.12:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m scripts.train
python -m scripts.evaluate
python -m pytest -q
AI_PROVIDER=offline python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --no-access-log
```

Open <http://127.0.0.1:8001/docs>. Test `/ask` with:

```json
{"question":"How should we investigate payment API timeout latency?"}
```

Test `/predict` with:

```json
{"description":"payment timeout downstream bank latency"}
```

In a second terminal in this cloud folder, activate its environment and run:

```bash
source .venv/bin/activate
python -m scripts.smoke --url http://127.0.0.1:8001
```

Local offline output is explicitly marked and does not call an LLM. For a cloud
release, the pipeline sets `AI_PROVIDER=azure` and requires a successful
live inference smoke check. This project rejects the other cloud provider.

## Cloud setup and operations

Follow [SETUP.md](SETUP.md) for identity, local state, infrastructure, pipeline
configuration and deployment. Run Terraform from this folder with
`terraform -chdir=infra ...`. The reusable module is `infra/modules/platform/`.

Follow [OPERATIONS.md](OPERATIONS.md) for metrics, release drills, troubleshooting,
rollback and teardown. Cloud apply and inference have not been run by preparing
these files; resolve the Terraform validation limitations recorded in
[the validation report](../docs/VALIDATION.md) before provisioning.

## Optional experiment tracking

Build artifacts provide the default model/evaluation evidence. To explore MLflow
locally in this cloud folder (optional and not cloud-deployed by this project):

```bash
python -m pip install mlflow
MLFLOW_TRACKING_URI=./mlruns python -m scripts.train
mlflow ui --backend-store-uri ./mlruns --host 127.0.0.1 --port 5000
```

The classifier and retrieval examples use tiny synthetic datasets. Treat their
scores as workflow checks. Maintain the evidence checklist in
[JD-EVIDENCE.md](../docs/JD-EVIDENCE.md) as you complete actual deployments.

## Security scanning

Both pipelines integrate SonarQube Cloud, Trivy, Checkov, tfsec and OWASP ZAP API DAST.
Configure the service connections and project keys using [SECURITY.md](../docs/SECURITY.md)
before running CI. Scanner findings and errors block release.

## Terraform state location

Keep state on your Mac in `azure/infra/terraform.tfstate`. Infrastructure
pipelines validate and scan only. Run infrastructure plan/apply/destroy locally;
application CI/CD remains hosted. See [LOCAL-STATE.md](../docs/LOCAL-STATE.md).
