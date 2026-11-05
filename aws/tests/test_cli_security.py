import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from risk_ai import audit, generate


class CliSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "project"
        (self.root / "risk_ai").mkdir(parents=True)
        (self.root / "data").mkdir()
        (self.root / "reports").mkdir()
        self.outside = Path(self.temp.name) / "outside"
        self.outside.mkdir()
        for name in ("requirements-linux.txt", "requirements-macos-arm64.txt", "requirements-dev.txt"):
            (self.root / name).write_text("torch==2.15.0+cpu\n")
        for target, name, value in (
            (generate, "ROOT", self.root),
            (audit, "__file__", str(self.root / "risk_ai/audit.py")),
        ):
            p = patch.object(target, name, value)
            p.start()
            self.addCleanup(p.stop)

    def invoke(self, module, args):
        with patch.object(sys, "argv", [module.__name__, *args]), contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            module.main()

    def rejected(self, module, args):
        with self.assertRaises(SystemExit) as error:
            self.invoke(module, args)
        self.assertEqual(error.exception.code, 2)

    def test_generator_accepts_default_and_in_directory_output(self):
        with patch.object(generate, "generate", return_value={}) as call:
            self.invoke(generate, [])
            call.assert_called_once_with(self.root / "data/payments.csv")
        with patch.object(generate, "generate", return_value={}) as call:
            self.invoke(generate, ["--output", str(self.root / "data/custom.csv")])
            call.assert_called_once_with(self.root / "data/custom.csv")

    def test_generator_rejects_outside_sibling_prefix_and_parent_traversal(self):
        bad_paths = [self.outside / "payments.csv", self.root / "data-other/payments.csv", self.root / "data/../escape.csv"]
        with patch.object(generate, "generate") as call:
            for path in bad_paths:
                self.rejected(generate, ["--output", str(path)])
            call.assert_not_called()
        self.assertFalse((self.root / "escape.csv").exists())

    def test_generator_rejects_output_and_metadata_symlinks(self):
        (self.root / "data/link.csv").symlink_to(self.outside / "file.csv")
        (self.root / "data/normal.meta.json").symlink_to(self.outside / "metadata.json")
        with patch.object(generate, "generate") as call:
            for name in ("link.csv", "normal.csv"):
                self.rejected(generate, ["--output", str(self.root / "data" / name)])
            call.assert_not_called()

    def test_generator_rejects_non_csv_and_directory_output(self):
        (self.root / "data/directory.csv").mkdir()
        with patch.object(generate, "generate") as call:
            for name in ("wrong.json", "directory.csv"):
                self.rejected(generate, ["--output", str(self.root / "data" / name)])
            call.assert_not_called()

    def test_audit_accepts_all_existing_pipeline_combinations(self):
        commands = [([], "requirements-linux.txt", "dependencies.json"),
                    (["--requirements", "requirements-macos-arm64.txt"], "requirements-macos-arm64.txt", "dependencies.json"),
                    (["--requirements", "requirements-dev.txt", "--report", "reports/dependencies-training.json"], "requirements-dev.txt", "dependencies-training.json")]
        with patch.object(audit, "audit") as call:
            for args, lock, report in commands:
                self.invoke(audit, args)
                call.assert_called_with(self.root / lock, self.root / "reports" / report)

    def test_audit_rejects_arbitrary_paths_and_option_shaped_inputs(self):
        with patch.object(audit, "audit") as call:
            for args in (["--requirements", "/etc/passwd"], ["--requirements=--help"], ["--report", "../../outside.json"]):
                self.rejected(audit, args)
            call.assert_not_called()

    def test_audit_rejects_symlinked_lockfile_report_and_sidecar(self):
        lock = self.root / "requirements-linux.txt"
        lock.unlink()
        outside_lock = self.outside / "lock.txt"
        outside_lock.write_text("torch==2.15.0+cpu\n")
        lock.symlink_to(outside_lock)
        with patch.object(audit, "audit") as call:
            self.rejected(audit, [])
            lock.unlink()
            lock.write_text("torch==2.15.0+cpu\n")
            for name in ("dependencies.json", "dependencies.requirements.txt"):
                link = self.root / "reports" / name
                link.symlink_to(self.outside / name)
                self.rejected(audit, [])
                link.unlink()
            call.assert_not_called()

    def test_audit_still_normalizes_cpu_pins_and_rejects_skipped_dependencies(self):
        lock = self.root / "requirements-linux.txt"
        report = self.root / "reports/dependencies.json"

        def fake_audit(command, check):
            self.assertFalse(check)
            self.assertIn("--disable-pip", command)
            self.assertEqual(report.with_suffix(".requirements.txt").read_text(), "torch==2.15.0\n")
            report.write_text(json.dumps({"dependencies": [{"name": "torch", "skip_reason": "unavailable"}]}))
            return SimpleNamespace(returncode=0)

        with patch.object(audit.subprocess, "run", fake_audit):
            with self.assertRaisesRegex(ValueError, "Incomplete audit"):
                audit.audit(lock, report)


if __name__ == "__main__":
    unittest.main()
