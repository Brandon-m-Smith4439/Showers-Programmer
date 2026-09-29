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


class SingleSurfaceWindowRecoveryTests(unittest.TestCase):
    def test_child_creation_keeps_one_tk_surface_without_win32_style_mutation(self) -> None:
        create = inspect.getsource(gui.ShowerProgrammerApp.create_hidden_toplevel)
        owner = inspect.getsource(gui.ShowerProgrammerApp.bind_native_window_owner)
        alpha = inspect.getsource(gui.ShowerProgrammerApp.set_native_window_alpha)
        self.assertIn("FlashFreeToplevel(owner, background=self.APP_BG)", create)
        self.assertIn("window.transient(owner_window)", owner)
        for forbidden in ("GWLP_HWNDPARENT", "SetWindowLongPtr", "WS_EX_LAYERED", "SetLayeredWindowAttributes"):
            self.assertNotIn(forbidden, owner + alpha)

    def test_hidden_stage_never_maps_or_reparents_window(self) -> None:
        stage = inspect.getsource(gui.ShowerProgrammerApp.stage_window_behind_owner)
        self.assertIn("window.withdraw()", stage)
        self.assertIn('window.attributes("-alpha", 0.0)', stage)
        self.assertNotIn("window.deiconify()", stage)
        self.assertNotIn("SetWindowPos", stage)
        self.assertNotIn("HWND_BOTTOM", stage)

    def test_final_present_maps_transparent_then_reveals_after_paint_turns(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.present_window_without_flash)
        mapping = source.split("def map_finished_surface() -> None:", 1)[1].split("def settle_pass", 1)[0]
        self.assertIn("self.release_first_map_guard(window)", mapping)
        self.assertIn("window.deiconify()", mapping)
        self.assertIn("self.maximize_window(window)", mapping)
        self.assertIn("mapped_paint_pass()", mapping)
        paint = source.split("def mapped_paint_pass", 1)[1].split("def map_finished_surface", 1)[0]
        self.assertIn("self.force_native_window_paint(window)", paint)
        visible = source.split("def finish_visible", 1)[1].split("def mapped_paint_pass", 1)[0]
        self.assertIn('window.attributes("-alpha", 1.0)', visible)

    def test_maximize_does_not_force_hidden_hwnd_visible_with_showwindow(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.maximize_window)
        self.assertIn('window.state("zoomed")', source)
        self.assertNotIn("ShowWindow", source)

    def test_settings_and_review_each_create_one_shared_toplevel_shell(self) -> None:
        settings = inspect.getsource(gui.ShowerProgrammerApp.open_settings)
        review = inspect.getsource(gui.ShowerProgrammerApp.open_order_review)
        self.assertEqual(settings.count("dialog = self.create_hidden_toplevel(self.root)"), 1)
        self.assertEqual(review.count("dialog = self.create_hidden_toplevel(self.root)"), 1)
        self.assertNotIn("tk.Toplevel(", settings)
        self.assertNotIn("tk.Toplevel(", review)

    def test_version_174_release_metadata(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 174)
        features = (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8")
        self.assertIn("VERSION_1_74_SINGLE_SURFACE_WINDOW_RECOVERY", features)
        flags = (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8")
        for flag in (
            "single_surface_tk_children",
            "tk_managed_transient_ownership",
            "no_direct_win32_reparent",
            "no_direct_layered_child_style",
            "hidden_mapped_paint_reveal",
            "version_1_74_single_surface_window_recovery",
        ):
            self.assertIn(flag, flags)


if __name__ == "__main__":
    unittest.main()
