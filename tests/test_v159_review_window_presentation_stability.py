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


class ReviewWindowPresentationStabilityTests(unittest.TestCase):
    def test_review_window_presents_shell_before_preview_render(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.open_order_review)
        presentation = source.split("def present_review_window() -> None:", 1)[1]

        self.assertIn('dialog.state("zoomed")', presentation)
        self.assertIn('dialog.attributes("-alpha", 1.0)', presentation)
        self.assertIn('state["review_geometry_settled"] = True', presentation)
        self.assertIn("dialog.after(75, redraw)", presentation)
        self.assertNotIn("dialog.after(220", presentation)
        self.assertNotIn("dialog.after(90", presentation)
        self.assertNotIn("dialog.update_idletasks()", presentation)
        self.assertNotIn("dialog.update()", presentation)

    def test_temporary_canvas_sizes_do_not_trigger_visible_redraws(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.open_order_review)

        self.assertIn('"review_geometry_settled": False', source)
        self.assertIn('"review_window_presented": False', source)
        self.assertIn('if not bool(state.get("review_geometry_settled")):', source)
        self.assertIn('canvas_sizes[canvas_name] = size', source)

    def test_version_159_release_marker_is_current(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        marker = "VERSION_1_59_REVIEW_WINDOW_PRESENTATION_STABILITY"

        self.assertGreaterEqual(version["version_number"], 159)
        self.assertIn(marker, (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8"))
        self.assertIn(
            "version_1_59_review_window_presentation_stability",
            (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
