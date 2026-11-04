# Payment risk with TensorFlow and PyTorch — step by step

This second AWS AI component predicts whether a **synthetic payment should be
flagged for review**. It uses six numeric features. The existing copilot classifies
incident text and retrieves runbooks; this component learns from payment attributes.

We train **two independent neural networks for the same task**, one with TensorFlow
and one with PyTorch. Comparing them teaches both frameworks without changing the
dataset, feature definitions or evaluation rules. Both models really train and run
inference. This is supervised deep learning. The existing Bedrock integration
remains the project's Generative AI component.

The data and labels are invented for this lab. Scores are uncalibrated model outputs,
not validated fraud probabilities. The API does not approve or decline transactions.

## 1. Add the files to your project

Extract the updated ZIP into a separate location first. Merge these additions into
your existing project so your local changes and virtual environment stay available:

| Path from repository root | Purpose |
| --- | --- |
| `aws/payment-risk/` | New independent AI service, training code, models, tests and guide |
| `.github/workflows/aws-payment-risk.yml` | Dedicated training, security and optional AWS release workflow |
| `aws/infra/modules/platform/main.tf` | Adds a separate risk ECR repository and includes it in pipeline IAM access |
| `aws/infra/main.tf` | Exposes the new `ecr_risk_repository` output |

The README files also have links to this guide. There are now three AWS workflows:
`aws-app.yml` for the copilot, `aws-infra.yml` for infrastructure validation, and
`aws-payment-risk.yml` for the new service. Terraform still uses your local state file.

Start from your existing AWS folder:

```bash
cd /Users/prashanthhenry/fidelity-interview/finserv-ai-platform/aws/payment-risk
uname -m
sw_vers -productVersion
```

Use steps 2–7 for an Apple Silicon Mac (`arm64`) running macOS 14 or newer, or a
Linux x86_64 computer with Python 3.12. Intel Macs (`x86_64` on macOS), older Macs,
and other architectures should use the Linux Docker route in step 8. The pinned
PyTorch 2.15 macOS wheel requires Apple Silicon and macOS 14 or newer.

## 2. Install this component's dependencies

Use a separate environment inside `aws/payment-risk/`:

```bash
PYTHON="$(brew --prefix python@3.12)/bin/python3.12" bash scripts/setup.sh
source .venv/bin/activate
python --version
python -c "import tensorflow as tf, torch; print('TensorFlow:', tf.__version__); print('PyTorch:', torch.__version__)"
```

On Linux, use `PYTHON=python3.12 bash scripts/setup.sh` instead of the Homebrew command.

`setup.sh` selects `requirements-macos-arm64.txt` or `requirements-linux.txt` and
installs `requirements-dev.txt` as well. The runtime locks pin TensorFlow 2.21.0
and PyTorch 2.15.0. Linux explicitly selects the official PyTorch **CPU** build;
there is no CUDA/GPU requirement. The dev lock supplies scikit-learn metrics,
pytest, Ruff, Bandit, coverage and pip-audit. Downloads are much larger than for
the original copilot; allow several GB of free disk space.

The `.in` files contain chosen direct dependencies. The `.txt` files pin their
resolved dependencies. Do not add these frameworks to the copilot's existing
`aws/requirements.txt`.

## 3. Generate the payment dataset

```bash
python -m risk_ai.generate
```

`risk_ai/generate.py` writes 6,000 synthetic rows to `data/payments.csv` and a
dataset fingerprint to `data/payments.meta.json`. The fixed seed makes regeneration
repeatable. There are 1,000 positive labels in the supplied dataset.

| Input | Example | Meaning |
| --- | --- | --- |
| `amount_usd` | `5000` | Synthetic payment amount in USD |
| `transactions_10m` | `12` | Recent payment frequency |
| `account_age_days` | `2` | Age of the synthetic account |
| `country_mismatch` | `true` | Whether the example's country signal differs |
| `failed_attempts_1h` | `5` | Recent failed attempts |
| `hour` | `2` | Hour of day, 0–23 |

`risk_label` is the training answer: `0` means lower risk and `1` means review.
The generator combines these inputs with a deliberately learnable rule and noise.
It demonstrates the workflow, rather than discovering fraud from real transactions.

## 4. Train both models

```bash
python -m risk_ai.train
```

`risk_ai/train.py` performs these operations:

1. Validates input features and rejects duplicate payment IDs.
2. Makes a stratified 60/20/20 split: 3,600 training, 1,200 validation and 1,200 test rows.
3. Applies `log1p` to amount and account age to reduce their wide numeric ranges.
4. Fits feature means/scales using **training rows only**; both models reuse them.
5. Builds two networks with the same shape: 6 inputs, 16 hidden neurons, 8 hidden
   neurons, then 1 output. Hidden layers use ReLU. A sigmoid converts the output
   logit to a score between 0 and 1.
6. Trains for 50 epochs with batches of 128, binary cross-entropy loss and Adam
   learning rate 0.01. An epoch is one pass through the training rows.
7. Chooses each model's weights using its lowest validation loss. The test rows
   do not participate in optimization or weight selection.
8. Evaluates the chosen weights once on the test split. Both models must meet
   ROC-AUC >= 0.95, F1 >= 0.80 and recall >= 0.80 at threshold 0.5.
9. Saves both models and verifies that reloading preserves their predictions.
10. Publishes a versioned bundle only after the checks pass. A failed gate leaves
    the previous `current.json` pointer unchanged.

In TensorFlow, the learning step is:

```python
keras_model.train_on_batch(x[batch], y[batch, None])
```

Keras calculates predictions, loss and gradients, then updates weights internally.
In PyTorch those steps are explicit:

```python
optimizer.zero_grad(set_to_none=True)
logits = torch_model(torch.from_numpy(x[batch]))
loss = loss_function(logits, torch.from_numpy(y[batch, None]))
loss.backward()
optimizer.step()
```

`loss.backward()` calculates how weights contributed to the error;
`optimizer.step()` adjusts them. See `risk_ai/networks.py` for the model definitions
and `risk_ai/train.py` for the complete loop.

Preparation-run results on the supplied holdout:

| Engine | ROC-AUC | F1 | Recall |
| --- | ---: | ---: | ---: |
| TensorFlow | 0.98432 | 0.83854 | 0.805 |
| PyTorch | 0.98513 | 0.84184 | 0.825 |

Scores can vary slightly across framework builds and platforms. A failed gate
should trigger investigation; don't lower the threshold just to make CI green.
For real model development, use a larger independent benchmark, appropriate
entity/time splits, drift checks and a reviewed labeling process. Repeatedly
tuning against this small fixed test set would overfit the benchmark.

## 5. Understand the saved files

`artifacts/current.json` points to `artifacts/<bundle_version>/`:

| File inside the version folder | What it contains |
| --- | --- |
| `tensorflow.keras` | Keras architecture, learned weights and training configuration |
| `pytorch.pt` | PyTorch learned parameter tensors (`state_dict`) |
| `preprocessing.json` | Ordered features, transform version and train-only mean/scale |
| `manifest.json` | Framework versions, training settings, dataset SHA-256 and file hashes |
| `evaluation.json` | Test metrics, confusion matrices, gates and validation-loss history |
| `split-ids.json` | IDs assigned to each split for audit and leakage checks |

The PyTorch architecture is reconstructed from `networks.py`, then its saved
weights are loaded with `weights_only=True`. Keras loads the `.keras` model with
`safe_mode=True`. Only load artifacts you built and trust: hashes detect accidental
changes but are not a substitute for signed provenance or authorization.

The supplied archive includes a trained example bundle. CI regenerates and trains
its own. New training runs keep previous bundles; review disk usage and retain only
the versions you need. Restart the API to load a newly published bundle.

## 6. Test and start the API

```bash
python -m pytest -q
python -m uvicorn risk_ai.api:app --host 127.0.0.1 --port 8002 --no-access-log
```

Open [the new Swagger UI](http://127.0.0.1:8002/docs). Use `POST /risk/predict`:

```json
{
  "amount_usd": 5000,
  "transactions_10m": 12,
  "account_age_days": 2,
  "country_mismatch": true,
  "failed_attempts_1h": 5,
  "hour": 2
}
```

The default `engine=both` returns a score and `review`/`low_risk` label for each
model, plus the bundle version and `synthetic_only: true`. Try `engine=tensorflow`
or `engine=pytorch` to use one engine. Scores need not match exactly: these are
separately learned weights, not calls to one shared classifier.

`risk_ai/serving.py` verifies the artifact hashes, loads both models once at
startup, applies the saved preprocessing, and performs inference. It never trains
on API requests. Invalid features or engine names produce HTTP 422. The API will
fail startup if its models are missing or corrupt.

The original copilot can keep using host port 8000 or 8001. This service uses
host port 8002. Both are separate FastAPI applications.

## 7. Run the smoke and quality checks

In another terminal in this folder, activate its environment:

```bash
source .venv/bin/activate
python -m risk_ai.smoke --url http://127.0.0.1:8002
```

This tests readiness and runs both a lower-risk and review example through both
saved models. Expected summary: `"smoke": "passed"` with both engine names.

To run the full local quality sequence after stopping the API:

```bash
bash scripts/quality.sh
```

It lints, runs Bandit, audits runtime and training dependencies, regenerates data,
trains, enforces gates and runs tests with coverage. Evidence goes to `reports/`.
The audit maps PyTorch's official `+cpu` build suffix to the corresponding upstream
release because the advisory service doesn't recognize the local suffix. It fails
if any dependency is skipped. Trivy separately scans installed image packages.

## 8. Build and run with Docker — also the Intel Mac route

This component uses Docker's hardened **glibc** Python images, separately from the
copilot's Alpine image. Sign in to the registry using your Docker Hub account:

```bash
docker login dhi.io
docker build --platform linux/amd64 --pull -t payment-risk:ci .
```

The default `standalone` target installs dependencies and trains both models inside
Linux. You do not need native TensorFlow/PyTorch on an Intel Mac. On Apple Silicon,
`linux/amd64` uses emulation and can take longer. Docker must have enough memory
for the two frameworks; increase Docker Desktop's resource allocation if it is killed.

The runtime has a non-root UID, a model bundle and runtime packages. Training
dependencies stay in the separate trainer stage. A build-time import/load check
detects missing native libraries before the API image is produced. CI uses
`--target ci` to package the exact model bundle from its quality job without retraining.

The dependency stage now creates `/venv` with `--without-pip`. The builder's pip
installs into that environment using `python3 -m pip --python /venv install ...`.
The runtime copies this environment; it does not copy the builder's pip or its
vendored libraries. The trainer has a separate layer with development tools.
A build assertion checks that pip is absent from the inference environment.

This addresses the likely source of the reported older `msgpack 1.1.2`,
`setuptools 70.3.0` and `urllib3 2.7.0` copies. The application lockfile already pins
setuptools 84.2.1 and urllib3 2.8.0. An independent upgrade of application packages
does not update pip's internal vendored copies. The reported versions are
consistent with pip's bundled dependencies; the user's full package-path report
has not yet confirmed their exact locations. The rebuilt image must pass Trivy.
No vulnerability ignore or SBOM deletion is used by this change.

For the latest VEX integration, follow [VEX-UPDATE.md](VEX-UPDATE.md). Merge its
listed source/configuration files while retaining your own `.venv`, `data` and
`artifacts` folders. Rebuild from `aws/payment-risk/` and rescan:

```bash
docker build --platform linux/amd64 --target ci --pull --no-cache -t payment-risk:ci .
bash scripts/scan-image.sh payment-risk:ci
```

Pip is intentionally unavailable in the inference environment. Install changes
through a new image build; use `python` for model inspection and smoke checks.
If findings remain, inspect `PkgPath` and `PkgIdentifier` in the JSON report to
locate any additional copies in the base image or other bundled components.

Scan before starting a deployment:

```bash
bash scripts/scan-image.sh payment-risk:ci
bash ../scripts/scan-dast.sh payment-risk:ci
docker run --rm --name payment-risk-local --platform linux/amd64 \
  --read-only --tmpfs /tmp:rw,noexec,nosuid,size=256m \
  -p 127.0.0.1:8002:8000 payment-risk:ci
```

ZAP starts its own isolated test container, runs the active API scan and cleans up.
Find Trivy and ZAP reports under this component's `reports/security/` folder.
HIGH/CRITICAL image findings without an approved matching VEX assessment, secret
findings, scanner errors, unreviewed suppressions, and any nonzero DAST result block
CI/release. The payment-risk workflow uses its own checked scanner; the original
copilot continues using `aws/scripts/scan-image.sh`.

To smoke-test from another terminal without installing frameworks on the host:

```bash
docker exec payment-risk-local python -m risk_ai.smoke --url http://127.0.0.1:8000
```

The hardened runtime has no interactive shell. Use `docker exec ... python ...`
and `docker logs payment-risk-local` for these checks.

**Verification boundary:** Python training, API, dependency audits and tests were
run during preparation. The user subsequently verified training, API smoke, the
Linux/amd64 Docker build and reported exit code 0 from a manual VEX-aware scan.
The new checked scanner/workflow still require execution on a Docker host. The
current runtime is pinned to the reviewed base digest, and the vendor VEX document
is checksum-pinned in `security/vendor-vex/`. See [VEX-UPDATE.md](VEX-UPDATE.md). The hardened image requires registry authentication and
has not been built/scanned or DAST-tested here. The earlier standard Debian base
scan found 36 HIGH and 2 CRITICAL package findings, so it was not selected. The
hardened base and full application image must still pass your actual Trivy scan;
no zero-vulnerability claim is made for an unscanned image.

## 9. Connect GitHub Actions

The new workflow is `.github/workflows/aws-payment-risk.yml`. Commit the source,
lockfiles and synthetic dataset; `artifacts/` and `reports/` are ignored by Git.
CI generates them and uploads evidence using Actions artifacts.

The quality job trains/tests, builds the tested model pair, then runs Trivy and
DAST. A separate IaC job runs Checkov, tfsec and Trivy through the existing AWS
scanner script. A separate SonarQube Cloud project imports the coverage report.
Release requires all three jobs and runs only on `main` when explicitly enabled.

Add these GitHub settings before running the new workflow:

| Setting | Type | Value |
| --- | --- | --- |
| `DOCKERHUB_USERNAME` | Repository variable | Docker Hub username for hardened-base pulls |
| `DOCKERHUB_TOKEN` | Secret | Read-only Docker Hub token; never commit it |
| `SONAR_RISK_PROJECT_KEY` | Repository variable | Separate SonarQube Cloud project for this service |
| `SONAR_TOKEN` | Secret | Token authorized to analyze that project |
| `SONAR_ORGANIZATION`, `SONAR_HOST_URL` | Variables | Your existing SonarQube Cloud settings |

Fork pull requests have no access to these secrets; authenticated scans must run
in a trusted branch/context before release. Missing configuration causes a visible
failure; it does not silently disable scans.

## 10. Deploy to EKS after your AWS platform is ready

No cloud resources were deployed while preparing this addition. First complete
the existing [AWS setup](../SETUP.md) and its Terraform validation steps. This
component adds an ECR repository, not another Kubernetes cluster.

From `aws/`, use your existing local state:

```bash
terraform -chdir=infra init
terraform -chdir=infra validate
terraform -chdir=infra plan -out=payment-risk.tfplan
terraform -chdir=infra apply payment-risk.tfplan
terraform -chdir=infra output -raw ecr_risk_repository
```

Inspect the plan before apply. On an existing platform it should add the risk ECR
resources and update pipeline repository permissions. On a new platform it includes
all of the AWS resources and their costs. State remains `aws/infra/terraform.tfstate`.
Follow the existing state-backup procedure before infrastructure changes.

Using your local administrator credentials, bootstrap the namespace if it doesn't
already exist:

```bash
aws eks update-kubeconfig --region YOUR_REGION --name YOUR_CLUSTER
kubectl create namespace genai --dry-run=client -o yaml | kubectl apply -f -
```

Set `ECR_RISK_REPOSITORY` to the new Terraform output. Reuse `AWS_REGION`,
`EKS_CLUSTER`, `AWS_DEPLOY_ROLE_ARN`, `KUBECTL_VERSION` and the `aws-dev` GitHub
environment already configured for the copilot. The existing OIDC trust must allow
that environment. Ensure the EKS nodes are amd64 and have capacity for this new
workload: the chart requests 1 GiB memory and limits it to 2 GiB per pod.

After CI is green and AWS is configured, set repository variable
`DEPLOY_RISK_AWS=true`. The release job authenticates with OIDC, builds the tested
bundle into a uniquely tagged image, scans/DAST-tests it again, pushes to ECR, and
deploys `payment-risk` to the existing `genai` namespace. The Helm chart uses a
ClusterIP service, read-only container filesystem, no service-account token mount,
readiness/startup/liveness probes and a NetworkPolicy with no outbound access.
Both models execute locally in the pod; no Bedrock credentials are needed here.

`scripts/deploy.sh` uses Helm atomic rollout, then smoke-tests both engines via
port-forward. If that check fails, it rolls back the previous release or uninstalls
a failed first release. For manual access:

```bash
kubectl -n genai port-forward service/payment-risk 8002:8000
```

Then open `http://127.0.0.1:8002/docs`. This lab endpoint is not authenticated for
public use; keep it local/ClusterIP. Public exposure requires a configured identity
gateway, TLS and appropriate access controls.

## Official references

- [TensorFlow installation and platform support](https://www.tensorflow.org/install/pip)
- [PyTorch local installation](https://pytorch.org/get-started/locally/)
- [PyTorch 2.15 release](https://pytorch.org/blog/pytorch-2-15-release-blog/)
- [Keras model saving and loading](https://keras.io/guides/serialization_and_saving/)
- [PyTorch saving and loading](https://docs.pytorch.org/tutorials/beginner/basics/saveloadrun_tutorial.html)
- [Docker hardened Python build pattern](https://docs.docker.com/guides/python/)
- [Docker hardened image authentication](https://docs.docker.com/dhi/how-to/use/)
