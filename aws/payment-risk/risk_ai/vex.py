"""Validate reviewed vendor data and retain a bounded, auditable image-scan gate."""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "security/vendor-vex/review.json"


def product_ids(products):
    for product in products:
        yield unquote(product.get("@id", "")).split("?")[0]
        yield from product_ids(product.get("subcomponents", []))


def validate_policy(path=POLICY):
    policy = json.loads(path.read_text())
    if policy.get("platform") != "linux/amd64":
        raise ValueError("This review covers linux/amd64 only")
    reference = policy["runtime_base"]
    if not re.fullmatch(r"dhi\.io/python@sha256:[0-9a-f]{64}", reference):
        raise ValueError("Expected an immutable DHI Python base reference")
    content = (path.parent / policy["vex_file"]).read_bytes()
    if hashlib.sha256(content).hexdigest() != policy["vex_sha256"]:
        raise ValueError("Reviewed VEX checksum mismatch")
    document = json.loads(content)
    if document.get("author") != policy["vendor_author"]:
        raise ValueError("Unexpected VEX author")
    digest = reference.split("sha256:")[1]
    allowed = {}
    for cve, decision in policy["decisions"].items():
        allowed[cve] = set()
        for statement in document["statements"]:
            if statement.get("vulnerability", {}).get("name") != cve:
                continue
            products = statement.get("products", [])
            scoped = [p for p in products if p.get("hashes", {}).get("sha-256") == digest]
            if not scoped:
                continue
            if statement.get("status") != "not_affected" or decision["status"] != "not_affected":
                raise ValueError(f"Unresolved vendor status for {cve}")
            if statement.get("justification") not in decision["justifications"]:
                raise ValueError(f"Unreviewed justification for {cve}")
            allowed[cve].update(p for p in product_ids(scoped) if p.startswith("pkg:deb/") and "@" in p)
        if not allowed[cve]:
            raise ValueError(f"No versioned packages bound to the reviewed base for {cve}")
    return policy, allowed


def check_layers(application, base):
    for image in (application, base):
        if image.get("Os") != "linux" or image.get("Architecture") != "amd64":
            raise ValueError("This VEX review covers linux/amd64 only")
    base_layers = base.get("RootFS", {}).get("Layers", [])
    app_layers = application.get("RootFS", {}).get("Layers", [])
    if not base_layers or app_layers[:len(base_layers)] != base_layers:
        raise ValueError("Application layers do not inherit the exact reviewed base")


def finding_key(finding):
    return (finding["VulnerabilityID"], finding["PkgName"], finding["InstalledVersion"])


def review_reports(raw, filtered, policy, allowed, image_id=None):
    for report in (raw, filtered):
        if not report.get("Results"):
            raise ValueError("Missing scan results")
        if image_id and report.get("Metadata", {}).get("ImageID") != image_id:
            raise ValueError("Scan report does not match the inspected application image")
        if image_id and not {"debian", "python-pkg"}.issubset({r.get("Type") for r in report["Results"]}):
            raise ValueError("Expected both Debian and Python package analysis")
    original = {finding_key(v) for r in raw["Results"] for v in r.get("Vulnerabilities", [])}
    active = {finding_key(v) for r in filtered["Results"] for v in r.get("Vulnerabilities", [])}
    decisions = []
    errors = []
    for result in filtered["Results"]:
        for modification in result.get("ExperimentalModifiedFindings", []):
            if modification.get("Type") != "vulnerability":
                errors.append("Unexpected non-vulnerability suppression")
                continue
            finding = modification["Finding"]
            cve, package, version = finding_key(finding)
            purl = f"pkg:deb/debian/{package}@{version}"
            approved = policy["decisions"].get(cve, {})
            valid = (result.get("Type") == "debian" and modification.get("Status") == "not_affected"
                     and modification.get("Statement") in approved.get("justifications", [])
                     and Path(modification.get("Source", "")).name == policy["vex_file"]
                     and purl in allowed.get(cve, set()))
            if not valid:
                errors.append(f"Unreviewed suppression: {cve} {package} {version}")
            decisions.append({"cve": cve, "package": package, "version": version,
                              "status": modification.get("Status"), "justification": modification.get("Statement"),
                              "source": modification.get("Source"), "approved": valid})
    suppressed = {(d["cve"], d["package"], d["version"]) for d in decisions}
    if original != active | suppressed or active & suppressed:
        errors.append("Raw and assessed findings do not reconcile")
    if active:
        errors.append("HIGH/CRITICAL vulnerabilities remain")
    raw_secrets = sum(len(r.get("Secrets", [])) for r in raw["Results"])
    assessed_secrets = sum(len(r.get("Secrets", [])) for r in filtered["Results"])
    if raw_secrets or assessed_secrets:
        errors.append("Secret findings remain")
    return {"status": "blocked" if errors else "passed", "runtime_base": policy["runtime_base"],
            "vex_sha256": policy["vex_sha256"],
            "raw_findings": len(original), "active_findings": len(active), "suppressed_findings": len(suppressed),
            "secret_findings": max(raw_secrets, assessed_secrets), "decisions": decisions, "errors": errors}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["base", "layers", "gate"])
    parser.add_argument("--reports", type=Path, default=ROOT / "reports/security")
    parser.add_argument("--scan-exit", type=int, default=0)
    args = parser.parse_args()
    policy, allowed = validate_policy()
    if args.command == "base":
        print(policy["runtime_base"])
        return
    def read(name):
        return json.loads((args.reports / name).read_text())

    application, base = read("vex-app-inspect.json")[0], read("vex-base-inspect.json")[0]
    check_layers(application, base)
    if args.command == "layers":
        print("Reviewed base layers match the application image.")
        return
    summary = review_reports(read("trivy-image-raw.json"), read("trivy-image-vex.json"),
                             policy, allowed, application["Id"])
    if args.scan_exit:
        summary["errors"].append(f"Trivy returned {args.scan_exit}")
        summary["status"] = "blocked"
    (args.reports / "trivy-vex-decision.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "decisions"}))
    if summary["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError) as error:
        print(f"VEX gate blocked: {error}", file=sys.stderr)
        raise SystemExit(1) from error
