import hashlib
import json
import shutil

import numpy as np
import pytest
from fastapi.testclient import TestClient

from risk_ai.api import create_app
from risk_ai.audit import audit
from risk_ai.evaluation import enforce_gate
from risk_ai.features import ROOT, normalize, transform
from risk_ai.generate import generate
from risk_ai.serving import RiskService
from risk_ai.smoke import HIGH, LOW
from risk_ai.train import prepare


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app(ROOT / "artifacts")) as test_client:
        yield test_client


def test_generation_is_reproducible_and_synthetic(tmp_path):
    first, second = tmp_path / "a.csv", tmp_path / "b.csv"
    metadata = generate(first, count=100)
    generate(second, count=100)
    assert first.read_bytes() == second.read_bytes()
    assert metadata["synthetic"] is True
    assert metadata["sha256"] == hashlib.sha256(first.read_bytes()).hexdigest()


def test_split_has_no_overlap_and_scaling_fits_training_only():
    x, _, splits, preprocessing, ids = prepare(ROOT / "data/payments.csv")
    train, validation, test = splits
    assert not set(train) & set(validation)
    assert not set(train) & set(test)
    assert not set(validation) & set(test)
    assert len(set(train) | set(validation) | set(test)) == len(ids)
    np.testing.assert_allclose(x[train].mean(axis=0), np.zeros(6), atol=1e-5)
    assert not np.allclose(x[test].mean(axis=0), np.zeros(6), atol=1e-5)
    assert preprocessing["features"][0] == "amount_usd"


@pytest.mark.parametrize("payment,label", [(LOW, "low_risk"), (HIGH, "review")])
def test_saved_models_run_real_inference(client, payment, label):
    response = client.post("/risk/predict", json=payment)
    assert response.status_code == 200
    result = response.json()
    assert result["bundle_version"] == client.get("/readyz").json()["bundle_version"]
    assert result["synthetic_only"] is True
    assert set(result["predictions"]) == {"tensorflow", "pytorch"}
    for prediction in result["predictions"].values():
        assert prediction["label"] == label
        assert 0 <= prediction["score"] <= 1


@pytest.mark.parametrize("engine", ["tensorflow", "pytorch"])
def test_select_one_framework(client, engine):
    result = client.post(f"/risk/predict?engine={engine}", json=HIGH).json()
    assert list(result["predictions"]) == [engine]


@pytest.mark.parametrize("patch", [{"amount_usd": -1}, {"hour": 24}, {"unknown": 1}, {"failed_attempts_1h": 0.5}])
def test_invalid_inputs_are_rejected(client, patch):
    assert client.post("/risk/predict", json=LOW | patch).status_code == 422


def test_unknown_engine_is_rejected(client):
    assert client.post("/risk/predict?engine=unknown", json=LOW).status_code == 422


@pytest.mark.parametrize("bad_metric", [0.1, float("nan")])
def test_gate_rejects_bad_or_nonfinite_models(bad_metric):
    with pytest.raises(ValueError, match="MODEL GATE FAILED"):
        enforce_gate({"roc_auc": bad_metric, "f1": 0.9, "recall": 0.9})


def test_artifact_tampering_blocks_model_load(tmp_path):
    shutil.copytree(ROOT / "artifacts", tmp_path / "artifacts")
    artifact_dir = tmp_path / "artifacts"
    version = json.loads((artifact_dir / "current.json").read_text())["bundle_version"]
    (artifact_dir / version / "pytorch.pt").write_bytes(b"not the trained model")
    with pytest.raises(ValueError, match="integrity check failed"):
        RiskService(artifact_dir)


def test_bad_feature_contract_is_rejected():
    with pytest.raises(ValueError, match="feature contract"):
        normalize(np.ones((1, 6)), {"features": [], "transform": "unknown"})


def test_log_transform_does_not_mutate_input():
    raw = np.array([[100, 2, 300, 0, 1, 12]], dtype=np.float32)
    original = raw.copy()
    result = transform(raw)
    np.testing.assert_array_equal(raw, original)
    assert result[0, 0] == pytest.approx(np.log1p(100))


def test_health_and_security_headers(client):
    response = client.get("/healthz")
    assert response.json() == {"status": "ok"}
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "tensorflow" in client.get("/version").json()
    assert 'risk_model_loaded{engine="pytorch"} 1' in client.get("/metrics").text


def test_saved_evidence_passes_fixed_holdout_gates():
    version = json.loads((ROOT / "artifacts/current.json").read_text())["bundle_version"]
    report = json.loads((ROOT / "artifacts" / version / "evaluation.json").read_text())
    assert report["split_sizes"] == {"train": 3600, "validation": 1200, "test": 1200}
    for engine in ("tensorflow", "pytorch"):
        enforce_gate(report[engine])
        assert sum(map(sum, report[engine]["confusion_matrix"])) == 1200


def test_audit_maps_cpu_build_and_rejects_skipped_packages(tmp_path, monkeypatch):
    from types import SimpleNamespace

    requirements = tmp_path / "requirements.txt"
    requirements.write_text("--extra-index-url https://download.pytorch.org/whl/cpu\ntorch==2.15.0+cpu\n")
    report = tmp_path / "audit.json"

    def simulated_audit(command, check):
        assert "--disable-pip" in command and "--no-deps" in command
        assert report.with_suffix(".requirements.txt").read_text() == "torch==2.15.0\n"
        report.write_text(json.dumps({"dependencies": [{"name": "torch", "skip_reason": "unavailable"}]}))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("risk_ai.audit.subprocess.run", simulated_audit)
    with pytest.raises(ValueError, match="Incomplete audit"):
        audit(requirements, report)


def test_audit_requires_pinned_versions(tmp_path):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("torch>=2\n")
    with pytest.raises(ValueError, match="fully pinned"):
        audit(requirements, tmp_path / "report.json")
