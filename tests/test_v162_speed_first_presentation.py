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

    def test_review_shell_builds_under_cover_before_native_presentation(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.open_order_review)
        host = source.index("review_host_cover = WindowLoadingCover(")
        cover = source.index("review_cover = WindowLoadingCover(", host)
        first_ctk = source.index("header = ctk.CTkFrame(review_content", cover)
        present = source.index("self.present_window_without_flash(", first_ctk)
        self.assertLess(host, cover)
        self.assertLess(cover, first_ctk)
        self.assertLess(first_ctk, present)

        presentation = source.split("def present_review_window() -> None:", 1)[1]
        self.assertIn("redraw()", presentation)
        self.assertIn("reveal_after_stable_paint", presentation)
        self.assertIn("dialog.update_idletasks()", presentation)
        self.assertLess(presentation.index("redraw()"), presentation.index("review_cover.destroy()"))
        self.assertNotIn("dialog.update()", presentation)


    def test_review_reentry_uses_background_context_handoff_without_fixed_delay(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.open_order_review)

        self.assertIn("self.request_order_review_context(process_order, folder, output_dir)", source)
        self.assertIn("prepared_context", source)
        self.assertNotIn("self.root.after(\n                60,", source)

    def test_version_162_release_marker_is_retained(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        marker = "VERSION_1_62_SPEED_FIRST_PRESENTATION"

        self.assertGreaterEqual(version["version_number"], 162)
        self.assertIn(marker, (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8"))
        self.assertIn(
            "version_1_62_speed_first_presentation",
            (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
