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


class ProfessionalWindowPresentationTests(unittest.TestCase):
    def test_startup_uses_native_loading_shield_before_app_construction(self) -> None:
        source = inspect.getsource(gui.main)
        self.assertIn("ShowerProgrammerApp.startup_palette()", source)
        self.assertIn("ShowerProgrammerApp.install_first_map_guard(root)", source)
        self.assertIn("root.withdraw()", source)
        self.assertIn("startup_shield = StartupShield(", source)
        self.assertIn("root.after(18, construct_application)", source)
        self.assertLess(source.index("startup_shield = StartupShield("), source.index("ShowerProgrammerApp(root)"))
        shield_prefix = source[:source.index("startup_shield = StartupShield(")]
        self.assertNotIn("ShowerProgrammerApp.maximize_window(root)", shield_prefix)

    def test_startup_shield_is_native_and_spinner_based(self) -> None:
        source = inspect.getsource(gui.StartupShield)
        self.assertIn("tk.Toplevel(root, background=background)", source)
        self.assertIn("overrideredirect(True)", source)
        self.assertIn('attributes("-topmost", True)', source)
        self.assertIn("create_arc(", source)
        self.assertIn("self.window.after(55, self._animate)", source)

    def test_main_reveal_waits_for_hidden_geometry_settle(self) -> None:
        force_source = inspect.getsource(gui.ShowerProgrammerApp.force_main_window_maximized)
        finish_source = inspect.getsource(gui.ShowerProgrammerApp.finish_startup_presentation)
        self.assertIn('_shower_startup_shield_active', force_source)
        self.assertIn("self.root.update_idletasks()", finish_source)
        self.assertLess(finish_source.index("self.root.update_idletasks()"), finish_source.index('self.root.attributes("-alpha", 1.0)'))
        self.assertIn("def stable_pass(pass_index: int = 0)", finish_source)
        self.assertIn("pass_index >= 5", finish_source)

    def test_review_window_uses_maximized_layout_without_early_native_map(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.open_order_review)
        start = source.index("dialog = self.create_hidden_toplevel(self.root)")
        prime = source.index("self.prime_hidden_maximized_geometry(dialog, self.root)", start)
        layout = source.index("dialog.grid_columnconfigure(0, weight=1)", prime)
        presentation = source.index("self.present_window_without_flash(", layout)
        self.assertLess(start, prime)
        self.assertLess(prime, layout)
        self.assertLess(layout, presentation)
        self.assertNotIn("self.maximize_window(dialog)", source[start:presentation])
        self.assertNotIn("self.position_child_window(dialog, 1180, 820)", source)

    def test_review_reveal_exposes_only_settled_frame(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.open_order_review)
        self.assertIn("review_cover = WindowLoadingCover(", source)
        self.assertLess(source.index("review_cover = WindowLoadingCover("), source.index("header = ctk.CTkFrame(review_content"))
        presentation = source.split("def present_review_window() -> None:", 1)[1]
        self.assertIn("dialog.update_idletasks()", presentation)
        self.assertIn("redraw()", presentation)
        self.assertLess(presentation.index("redraw()"), presentation.index("review_cover.destroy()"))
        self.assertNotIn("dialog.deiconify()", presentation)
        self.assertNotIn("dialog.focus_force()", presentation)
        self.assertIn("reveal_after_stable_paint", presentation)
        self.assertIn("on_presented=review_is_in_front", presentation)

    def test_slow_review_uses_full_workspace_loading_shield(self) -> None:
        feedback_source = inspect.getsource(gui.ShowerProgrammerApp.schedule_review_opening_feedback)
        shield_source = inspect.getsource(gui.ShowerProgrammerApp.show_workspace_loading_shield)
        self.assertIn("self.show_workspace_loading_shield(", feedback_source)
        self.assertIn("WindowLoadingCover(", shield_source)
        self.assertNotIn("StartupShield(", shield_source)
        self.assertIn("background=self.APP_BG", shield_source)
        self.assertIn("accent=self.ACCENT", shield_source)

    def test_version_165_release_marker_is_retained(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        marker = "VERSION_1_65_PROFESSIONAL_WINDOW_PRESENTATION"
        self.assertGreaterEqual(version["version_number"], 165)
        self.assertIn(marker, (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8"))
        flags = (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8")
        self.assertIn("startup_loading_shield", flags)
        self.assertIn("premaximized_review_shell", flags)
        self.assertIn("single_frame_review_reveal", flags)
        self.assertIn("version_1_65_professional_window_presentation", flags)


if __name__ == "__main__":
    unittest.main()
