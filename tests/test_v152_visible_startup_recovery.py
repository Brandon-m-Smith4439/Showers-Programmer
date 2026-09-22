from __future__ import annotations

import inspect
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_programmer_gui as gui


class VisibleStartupRecoveryTests(unittest.TestCase):
    def test_main_window_uses_transparency_without_withdrawal(self) -> None:
        main_source = inspect.getsource(gui.main)
        presentation_source = inspect.getsource(gui.ShowerProgrammerApp.force_main_window_maximized)

        self.assertIn('root.attributes("-alpha", 0.0)', main_source)
        startup = main_source.split("guard = SingleInstanceGuard()", 1)[0]
        self.assertNotIn("root.withdraw()", startup)
        self.assertIn('self.root.attributes("-alpha", 1.0)', presentation_source)

    def test_version_152_release_marker_is_retained(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 152)
        self.assertIn(
            "VERSION_1_52_VISIBLE_STARTUP_RECOVERY",
            (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
