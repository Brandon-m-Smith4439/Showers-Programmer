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


class SpeedFirstPresentationTests(unittest.TestCase):
    def test_main_window_has_no_intentional_settle_timer(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.force_main_window_maximized)

        self.assertNotIn("after(220", source)
        self.assertNotIn("after(60", source)
        self.assertNotIn(".update()", source)
        self.assertIn('self.root.attributes("-alpha", 1.0)', source)

    def test_review_shell_opens_before_deferred_preview_redraw(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.open_order_review)
        presentation = source.split("def present_review_window() -> None:", 1)[1]

        self.assertIn('dialog.attributes("-alpha", 1.0)', presentation)
        self.assertIn("dialog.after(75, redraw)", presentation)
        self.assertNotIn("dialog.after(220", presentation)
        self.assertNotIn("dialog.after(90", presentation)
        self.assertNotIn("dialog.update_idletasks()", presentation)

    def test_review_reentry_uses_idle_queue_instead_of_fixed_delay(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.open_order_review)

        self.assertIn("self.root.after_idle(", source)
        self.assertNotIn("self.root.after(\n                60,", source)

    def test_version_162_release_marker_is_current(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        marker = "VERSION_1_62_SPEED_FIRST_PRESENTATION"

        self.assertEqual(version["version_number"], 162)
        self.assertEqual(version["marker"], marker)
        self.assertIn(marker, (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8"))
        self.assertIn(
            "version_1_62_speed_first_presentation",
            (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
