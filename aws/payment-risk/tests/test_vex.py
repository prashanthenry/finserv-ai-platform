import copy
import json
import shutil
import sys
from pathlib import Path

import pytest

from risk_ai import vex

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def evidence():
    raw = json.loads((FIXTURES / "vex-raw.json").read_text())
    assessed = json.loads((FIXTURES / "vex-applied.json").read_text())
    policy, allowed = vex.validate_policy()
    return raw, assessed, policy, allowed


def test_native_trivy_fixture_reconciles_all_findings(evidence):
    result = vex.review_reports(*evidence)
    assert result["status"] == "passed"
    assert result["raw_findings"] == result["suppressed_findings"] == 11
    assert result["active_findings"] == 0
    assert all(d["approved"] for d in result["decisions"])


@pytest.mark.parametrize("mutation", ["unknown_cve", "wrong_version", "affected_status", "wrong_source"])
def test_unreviewed_suppression_is_blocked(evidence, mutation):
    raw, assessed, policy, allowed = evidence
    entry = assessed["Results"][0]["ExperimentalModifiedFindings"][0]
    if mutation == "unknown_cve":
        entry["Finding"]["VulnerabilityID"] = "CVE-2099-99999"
    elif mutation == "wrong_version":
        entry["Finding"]["InstalledVersion"] = "0.0"
    elif mutation == "affected_status":
        entry["Status"] = "affected"
    else:
        entry["Source"] = "unreviewed.json"
    assert vex.review_reports(raw, assessed, policy, allowed)["status"] == "blocked"


def test_missing_findings_cannot_disappear_silently(evidence):
    raw, assessed, policy, allowed = evidence
    assessed["Results"][0]["ExperimentalModifiedFindings"].pop()
    assert "Raw and assessed findings do not reconcile" in vex.review_reports(raw, assessed, policy, allowed)["errors"]


def test_active_high_findings_and_secrets_block_release(evidence):
    raw, assessed, policy, allowed = evidence
    original = raw["Results"][0]["Vulnerabilities"][0]
    assessed["Results"][0]["Vulnerabilities"] = [copy.deepcopy(original)]
    assessed["Results"][0]["ExperimentalModifiedFindings"] = [
        item for item in assessed["Results"][0]["ExperimentalModifiedFindings"]
        if vex.finding_key(item["Finding"]) != vex.finding_key(original)
    ]
    raw["Results"][0]["Secrets"] = [{"Severity": "HIGH"}]
    summary = vex.review_reports(raw, assessed, policy, allowed)
    assert summary["status"] == "blocked"
    assert "HIGH/CRITICAL vulnerabilities remain" in summary["errors"]
    assert "Secret findings remain" in summary["errors"]


def test_vex_tampering_is_blocked(tmp_path):
    original = vex.POLICY.parent
    for name in ("review.json", "dhi-python-vex.json"):
        shutil.copyfile(original / name, tmp_path / name)
    with (tmp_path / "dhi-python-vex.json").open("a") as handle:
        handle.write(" ")
    with pytest.raises(ValueError, match="checksum mismatch"):
        vex.validate_policy(tmp_path / "review.json")


def test_base_layer_or_platform_mismatch_is_blocked():
    base = {"Os": "linux", "Architecture": "amd64", "RootFS": {"Layers": ["sha256:base"]}}
    app = copy.deepcopy(base)
    app["RootFS"]["Layers"].append("sha256:app")
    vex.check_layers(app, base)
    app["RootFS"]["Layers"][0] = "sha256:other"
    with pytest.raises(ValueError, match="exact reviewed base"):
        vex.check_layers(app, base)
    app["Architecture"] = "arm64"
    with pytest.raises(ValueError, match="linux/amd64"):
        vex.check_layers(app, base)


def test_scan_report_must_match_inspected_image(evidence):
    with pytest.raises(ValueError, match="inspected application image"):
        vex.review_reports(*evidence, image_id="sha256:unrelated")


def test_missing_language_analysis_cannot_report_clean(evidence):
    raw, assessed, policy, allowed = evidence
    for report in (raw, assessed):
        report.setdefault("Metadata", {})["ImageID"] = "sha256:test"
    with pytest.raises(ValueError, match="both Debian and Python"):
        vex.review_reports(raw, assessed, policy, allowed, image_id="sha256:test")


def test_cli_writes_decision_and_blocks_scanner_error(evidence, tmp_path, monkeypatch):
    raw, assessed, _, _ = evidence
    image_id = "sha256:test-app"
    for name, report in (("trivy-image-raw.json", raw), ("trivy-image-vex.json", assessed)):
        report.setdefault("Metadata", {})["ImageID"] = image_id
        report["Results"].append({"Type": "python-pkg", "Target": "Python unit-test placeholder"})
        (tmp_path / name).write_text(json.dumps(report))
    base = {"Os": "linux", "Architecture": "amd64", "RootFS": {"Layers": ["sha256:base"]}}
    app = copy.deepcopy(base)
    app["Id"] = image_id
    for name, record in (("vex-base-inspect.json", base), ("vex-app-inspect.json", app)):
        (tmp_path / name).write_text(json.dumps([record]))
    monkeypatch.setattr(sys, "argv", ["vex", "gate", "--reports", str(tmp_path), "--scan-exit", "2"])
    with pytest.raises(SystemExit) as error:
        vex.main()
    assert error.value.code == 1
    assert json.loads((tmp_path / "trivy-vex-decision.json").read_text())["status"] == "blocked"
    monkeypatch.setattr(sys, "argv", ["vex", "gate", "--reports", str(tmp_path)])
    vex.main()
    assert json.loads((tmp_path / "trivy-vex-decision.json").read_text())["status"] == "passed"
