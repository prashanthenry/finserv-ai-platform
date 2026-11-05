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


def main():
    root = Path(__file__).resolve().parents[1]
    lockfiles = {
        name: root / name
        for name in (
            "requirements-linux.txt",
            "requirements-macos-arm64.txt",
            "requirements-dev.txt",
        )
    }
    reports = {
        name: root / name
        for name in (
            "reports/dependencies.json",
            "reports/dependencies-training.json",
        )
    }
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--requirements", choices=tuple(lockfiles), default="requirements-linux.txt",
    )
    parser.add_argument(
        "--report", choices=tuple(reports), default="reports/dependencies.json",
    )
    args = parser.parse_args()

    try:
        requirements = lockfiles[args.requirements].resolve(strict=True)
        report = reports[args.report].resolve()
        reports_root = (root / "reports").resolve()
        if requirements.parent != root or not requirements.is_file():
            parser.error("Requirements must be a regular lockfile inside the project")
        for candidate in (report, report.with_suffix(".requirements.txt")):
            path = candidate.resolve()
            if not path.is_relative_to(reports_root):
                parser.error("Audit output must stay inside the reports directory")
            if path.exists() and not path.is_file():
                parser.error("Audit output must reference a regular file")
    except (OSError, RuntimeError) as error:
        parser.error(f"Invalid audit path: {error}")

    audit(requirements, report)


if __name__ == "__main__":
    main()
