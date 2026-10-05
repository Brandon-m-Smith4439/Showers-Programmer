from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))
from shower_temp import workspace_temporary_directory


@unittest.skipUnless(sys.platform == "win32" and shutil.which("powershell"), "Windows repair")
class ManualRepairTests(unittest.TestCase):
    def invoke(self, target: Path, source: Path, *, fail_after_swap=False, fail_before_swap=False, prelude=""):
        def quote(value):
            return "'" + str(value).replace("'", "''") + "'"
        script = ROOT / "Repair Programmer.ps1"
        self.assertTrue(script.is_file(), "Standalone repair helper is missing")
        body = f". {quote(script)}; {prelude}; $script:calls=0; $validator={{param($folder,$report) $script:calls++; "
        if fail_after_swap:
            body += "if($script:calls -eq 2){throw 'Injected post-swap validation failure'}; "
        if fail_before_swap:
            body += "throw 'Injected staged validation failure'; "
        body += "}; "
        body += f"Install-ProgrammerRuntime -InstallDir {quote(target)} -PackageDir {quote(source)} -Validator $validator -Progress {{param($p,$m)}} | ConvertTo-Json -Compress"
        return subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", body], capture_output=True, text=True, timeout=40)

    def fixture(self, root):
        target, source = root / "existing", root / "replacement"
        for folder, data in ((target, b"old"), (source, b"new")):
            folder.mkdir()
            (folder / "Shower Programmer.exe").write_bytes(data)
            for name in ("_internal/_tcl_data/init.tcl", "_internal/_tk_data/tk.tcl", "_internal/pypdfium2_raw/pdfium.dll", "Assets/ShowersProgrammer.ico"):
                path = folder / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
        for name in ("Input/Orders/keep.pdf", "Input/Process List/batch.xls", "Output/processing_history.json", "Output/manual_overrides.json", "History/actions.json", "Recovery/keep.pdf", "shower_programmer_config.json", "shower_programmer_ui_settings.json"):
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"operator data must not change")
        return target, source

    def preserved(self, target):
        return {str(p.relative_to(target)): p.read_bytes() for p in target.rglob("*") if p.is_file() and p.parts[len(target.parts)] not in {"_internal", "Assets", "Rollback"} and p.name != "Shower Programmer.exe"}

    def test_repair_preserves_progress_and_retains_previous_runtime(self):
        with workspace_temporary_directory(prefix="repair") as raw:
            target, source = self.fixture(Path(raw))
            before = self.preserved(target)
            result = self.invoke(target, source)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(self.preserved(target), before)
            self.assertEqual((target / "Shower Programmer.exe").read_bytes(), b"new")
            backup = Path(json.loads(result.stdout)["backup"])
            self.assertEqual((backup / "Shower Programmer.exe").read_bytes(), b"old")
            self.assertTrue((source / "Shower Programmer.exe").is_file())

    def test_failed_post_swap_validation_restores_old_runtime_and_data(self):
        with workspace_temporary_directory(prefix="repair") as raw:
            target, source = self.fixture(Path(raw))
            before = self.preserved(target)
            result = self.invoke(target, source, fail_after_swap=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Injected post-swap", result.stderr)
            self.assertEqual((target / "Shower Programmer.exe").read_bytes(), b"old")
            self.assertEqual((target / "_internal/_tcl_data/init.tcl").read_bytes(), b"old")
            self.assertEqual(self.preserved(target), before)

    def test_incomplete_bundle_is_rejected_before_old_runtime_moves(self):
        with workspace_temporary_directory(prefix="repair") as raw:
            target, source = self.fixture(Path(raw))
            (source / "_internal/_tcl_data/init.tcl").unlink()
            result = self.invoke(target, source)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((target / "Shower Programmer.exe").read_bytes(), b"old")

    def test_same_source_and_destination_are_rejected(self):
        with workspace_temporary_directory(prefix="repair") as raw:
            target, _source = self.fixture(Path(raw))
            result = self.invoke(target, target)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((target / "Shower Programmer.exe").read_bytes(), b"old")

    def test_nested_package_layout_used_by_first_time_setup_is_accepted(self):
        with workspace_temporary_directory(prefix='repair') as raw:
            target, source = self.fixture(Path(raw))
            parent = source.with_name('extracted')
            parent.mkdir()
            source.rename(parent / 'Shower Programmer')
            before = self.preserved(target)
            result = self.invoke(target, parent)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual((target / 'Shower Programmer.exe').read_bytes(), b'new')
            self.assertEqual(self.preserved(target), before)

    def test_exe_paths_for_old_and_new_packages_are_accepted(self):
        with workspace_temporary_directory(prefix='repair') as raw:
            target, source = self.fixture(Path(raw))
            before = self.preserved(target)
            result = self.invoke(target / 'Shower Programmer.exe', source / 'Shower Programmer.exe')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(self.preserved(target), before)

    def test_missing_package_error_identifies_checked_location(self):
        with workspace_temporary_directory(prefix='repair') as raw:
            target, source = self.fixture(Path(raw))
            (source / 'Shower Programmer.exe').unlink()
            result = self.invoke(target, source)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(str(source), result.stderr)
            self.assertIn('NEW', result.stderr)
            self.assertEqual((target / 'Shower Programmer.exe').read_bytes(), b'old')

    def test_staged_validation_failure_never_moves_old_runtime(self):
        with workspace_temporary_directory(prefix="repair") as raw:
            target, source = self.fixture(Path(raw))
            before = self.preserved(target)
            result = self.invoke(target, source, fail_before_swap=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Injected staged", result.stderr)
            self.assertEqual((target / "Shower Programmer.exe").read_bytes(), b"old")
            self.assertEqual(self.preserved(target), before)

    def test_running_installation_is_refused_without_killing_it(self):
        with workspace_temporary_directory(prefix="repair") as raw:
            target, source = self.fixture(Path(raw))
            result = self.invoke(target, source, prelude="function Assert-ProgrammerClosed { throw 'Existing app still running' }")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Existing app still running", result.stderr)
            self.assertFalse((target / 'Rollback').exists())
            self.assertEqual((target / "Shower Programmer.exe").read_bytes(), b"old")

    def test_locked_existing_runtime_restores_already_moved_exe(self):
        with workspace_temporary_directory(prefix="repair") as raw:
            target, source = self.fixture(Path(raw))
            before = self.preserved(target)
            lock = str(target / '_internal/_tcl_data/init.tcl').replace("'", "''")
            result = self.invoke(target, source, prelude=f"$lock=[IO.File]::Open('{lock}','Open','Read','None')")
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((target / "Shower Programmer.exe").read_bytes(), b"old")
            self.assertEqual(self.preserved(target), before)


if __name__ == "__main__":
    unittest.main()
