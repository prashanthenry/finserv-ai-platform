"""Audit all pinned packages, mapping the official torch CPU build to its release."""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


def audit(requirements: Path, report: Path):
    report.parent.mkdir(parents=True, exist_ok=True)
    pins = []
    for line in requirements.read_text().splitlines():
        line = line.partition("#")[0].strip()
        if not line or line.startswith("--"):
            continue
        if not re.fullmatch(r"[\w.-]+==[\w.+-]+", line):
            raise ValueError("Audit input must be a fully pinned lockfile")
        # PyPI's advisory API doesn't recognize local '+cpu' version suffixes.
        # Audit the same upstream release; image scanning also checks installed packages.
        pins.append(re.sub(r"^(torch==[0-9.]+)\+cpu$", r"\1", line))
    audit_input = report.with_suffix(".requirements.txt")
    audit_input.write_text("\n".join(pins) + "\n")
    result = subprocess.run([
        sys.executable, "-m", "pip_audit", "--disable-pip", "--no-deps",
        "-r", str(audit_input), "-f", "json", "-o", str(report),
    ], check=False)
    if result.returncode:
        raise SystemExit(result.returncode)
    dependencies = json.loads(report.read_text())["dependencies"]
    skipped = [item["name"] for item in dependencies if item.get("skip_reason")]
    if len(dependencies) != len(pins) or skipped:
        raise ValueError(f"Incomplete audit; skipped packages: {skipped}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--requirements", type=Path, default=Path("requirements-linux.txt"))
    parser.add_argument("--report", type=Path, default=Path("reports/dependencies.json"))
    args = parser.parse_args()
    audit(args.requirements, args.report)
