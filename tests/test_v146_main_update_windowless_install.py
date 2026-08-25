from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from shower_programmer_gui import ShowerProgrammerApp


class MainUpdateWindowlessInstallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = (BACKEND / "shower_programmer_gui.py").read_text(encoding="utf-8")

    def test_check_for_updates_is_on_main_overview_and_not_preferences(self) -> None:
        main_start = self.source.index("    def build_ui(self) -> None:")
        main_end = self.source.index("    def make_sidebar_button", main_start)
        main_ui = self.source[main_start:main_end]
        self.assertIn('"Check for Updates", "refresh", self.check_for_updates', main_ui)

        preferences_start = self.source.index("    def build_preferences_settings_tab(")
        preferences_end = self.source.index("    def build_folder_settings_tab(", preferences_start)
        preferences = self.source[preferences_start:preferences_end]
        self.assertNotIn('"Check for Updates"', preferences)

    def test_update_script_launch_is_windowless_and_has_no_hidden_failure_pause(self) -> None:
        fake_process = object()
        with mock.patch("shower_programmer_gui.subprocess.Popen", return_value=fake_process) as popen:
            launched = ShowerProgrammerApp.launch_update_script_hidden(Path("C:/SPU/session/apply_update.cmd"))

        self.assertIs(launched, fake_process)
        kwargs = popen.call_args.kwargs
        self.assertIs(kwargs["stdin"], subprocess.DEVNULL)
        self.assertIs(kwargs["stdout"], subprocess.DEVNULL)
        self.assertIs(kwargs["stderr"], subprocess.DEVNULL)
        if os.name == "nt":
            self.assertEqual(kwargs["creationflags"], 0x08000000)

        stage_start = self.source.index("    def stage_app_bundle_replacement(")
        stage_end = self.source.index("    @staticmethod\n    def download_file", stage_start)
        stage_source = self.source[stage_start:stage_end]
        self.assertNotIn("color 1F", stage_source)
        self.assertNotIn('"    pause\\n"', stage_source)
        self.assertNotIn("\npause\n", stage_source)

    def test_powershell_update_fallback_is_hidden_and_noninteractive(self) -> None:
        for method_name in ("download_text_with_powershell", "download_file_with_powershell"):
            start = self.source.index(f"    def {method_name}(")
            end = self.source.index("\n    def ", start + 10)
            method_source = self.source[start:end]
            self.assertIn('"-NonInteractive"', method_source)
            self.assertIn('"-WindowStyle"', method_source)
            self.assertIn('"Hidden"', method_source)
            self.assertIn("hidden_windows_subprocess_options()", method_source)

    def test_version_146_release_marker_is_retained(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 146)
        feature_source = (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8")
        self.assertIn("VERSION_1_46_MAIN_UPDATE_WINDOWLESS_INSTALL", feature_source)


if __name__ == "__main__":
    unittest.main()
