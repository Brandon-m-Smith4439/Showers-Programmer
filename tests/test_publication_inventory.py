"""Keep fresh-install sources visible while excluding workstation state."""
from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("git"), "Git required for repository ignore checks")
class PublicationInventoryTests(unittest.TestCase):
    def test_rebuild_prefers_setup_environment(self):
        build = (ROOT / "Rebuild Shower Programmer EXE.bat").read_text(encoding="utf-8")
        local = 'if exist "%~dp0.venv\\Scripts\\python.exe"'
        fallback = 'else if exist "%CODEX_PYTHON%"'
        self.assertLess(build.index(local), build.index(fallback))
        self.assertIn('set "PYTHON_EXE=%~dp0.venv\\Scripts\\python.exe"', build)

    def ignored(self, path: str) -> bool:
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", "--quiet", path],
            cwd=ROOT, capture_output=True, text=True, timeout=10,
        )
        self.assertIn(result.returncode, (0, 1), result.stderr)
        return result.returncode == 0

    def test_workstation_data_is_ignored(self):
        paths = (
            "Input/Orders/example.pdf", "Input/Process List/example.xls",
            "Output/Runs/example.dxf", "Shower Programmer/Input/Orders/example.pdf",
            "Shower Programmer/Output/processing_history.json",
            "Diagnostics/example.zip", "History/example.json", "Recovery/example.pdf",
            "_verification/example.txt", "build/example.exe", "tmp/example.txt",
            "Test Workspace/example.pdf", "Rollback/PreviousRuntime/example.exe",
            "Backend/Configuration Backups/config.json", ".Network PDF Cache/copy.part",
            ".__sp_new_fixture/example.exe", ".__sp_old_fixture/example.exe",
            ".venv/Scripts/python.exe", ".shower_update.json", "manual_overrides.json",
            "processing_history.json", "shower_programmer.sqlite3-wal",
            "Shower Programmer.lnk", "setup.log", ".env", ".env.local",
            "tests/known_orders/customer-order.pdf", "tests/known_orders/production.xls",
        )
        for path in paths:
            with self.subTest(path=path):
                self.assertTrue(self.ignored(path), path)

    def test_install_and_update_sources_are_publishable(self):
        paths = (
            "First-Time Setup.bat", "First-Time Setup.ps1", "requirements.txt",
            "Create-ShowerProgrammerShortcut.ps1", "GUI.bat",
            "Rebuild Shower Programmer EXE.bat", "Backend/shower_programmer_v4.py",
            "Backend/shower_programmer_config.json", "Backend/version.json",
            "Backend/release_required_flags.txt", "Backend/build_update_package.py",
            "Assets/ShowersProgrammer.ico", "Assets/ShowersProgrammer.png",
            "Assets/ShowersProgrammerSplash.png", "README.md", "CHANGELOG.md",
            "tests/test_v203_first_time_setup_recovery.py",
            "tests/known_orders/README.md", "tests/known_orders/manifest.json",
            "tests/known_orders/kinsdale_oos_001.json", "tests/known_orders/legacy_process_list_sample.xls",
            "release/Shower-Programmer-Windows.zip", "release/Shower-Programmer-Windows.json",
        )
        for path in paths:
            with self.subTest(path=path):
                self.assertTrue((ROOT / path).is_file(), path)
                self.assertFalse(self.ignored(path), path)
        self.assertFalse(self.ignored(".env.example"))
        self.assertTrue(self.ignored("release/stale-build.zip"))


if __name__ == "__main__":
    unittest.main()
