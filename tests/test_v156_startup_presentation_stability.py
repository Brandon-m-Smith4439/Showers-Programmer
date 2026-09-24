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


class StartupPresentationStabilityTests(unittest.TestCase):
    def test_main_window_prioritizes_immediate_presentation(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.force_main_window_maximized)
        startup_path = source.split("if self._main_window_present_job is not None:", 1)[1]

        self.assertEqual(startup_path.count("self.maximize_window(self.root)"), 1)
        self.assertIn('self.root.attributes("-alpha", 1.0)', startup_path)
        self.assertNotIn("self.root.after(220", startup_path)
        self.assertNotIn("self.root.after(60", startup_path)
        self.assertNotIn("self.root.update()", startup_path)

    def test_small_desktop_uses_tight_fixed_sidebar_layout(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.build_ui)

        self.assertIn('mode = "tight" if height < 800', source)
        self.assertIn('workflow_height = 29 if mode == "tight"', source)
        self.assertIn('tool_height = 26 if mode == "tight"', source)
        self.assertIn('options_card.pack_configure', source)
        self.assertIn('send_card.grid_configure', source)
        self.assertNotIn("CTkScrollableFrame", source)

    def test_version_156_release_marker_is_retained(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        marker = "VERSION_1_56_STARTUP_PRESENTATION_STABILITY"

        self.assertGreaterEqual(version["version_number"], 156)
        self.assertIn(
            marker,
            (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
