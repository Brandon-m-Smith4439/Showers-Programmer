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


class FullSurfacePresentationTests(unittest.TestCase):
    def test_main_root_uses_native_tk_shell(self) -> None:
        source = inspect.getsource(gui.main)
        self.assertIn("root = tk.Tk()", source)
        self.assertNotIn("root = ctk.CTk()", source)
        self.assertIn("ShowerProgrammerApp.install_first_map_guard(root)", source)
        self.assertIn("root.withdraw()", source)

    def test_packaged_build_has_pre_interpreter_splash(self) -> None:
        rebuild = (ROOT / "Rebuild Shower Programmer EXE.bat").read_text(encoding="utf-8")
        self.assertIn('--splash "%CD%\\Assets\\ShowersProgrammerSplash.png"', rebuild)
        self.assertTrue((ROOT / "Assets" / "ShowersProgrammerSplash.png").is_file())
        source = inspect.getsource(gui.close_packager_splash)
        self.assertIn("import pyi_splash", source)
        self.assertIn("pyi_splash.close()", source)
        main = inspect.getsource(gui.main)
        self.assertLess(main.index("startup_shield = StartupShield("), main.index("close_packager_splash()"))

    def test_startup_cover_waits_through_stable_paint_barrier(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.finish_startup_presentation)
        self.assertIn("signatures:", source)
        self.assertIn("pass_index >= 5", source)
        self.assertIn("self.root.after(22", source)
        self.assertLess(source.index('self.root.attributes("-alpha", 1.0)'), source.index("shield.destroy()"))

    def test_all_child_windows_finish_hidden_layout_before_first_map(self) -> None:
        create = inspect.getsource(gui.ShowerProgrammerApp.create_hidden_toplevel)
        self.assertNotIn("GWLP_HWNDPARENT", create)
        stage = inspect.getsource(gui.ShowerProgrammerApp.stage_window_behind_owner)
        self.assertIn("window.withdraw()", stage)
        self.assertIn('window.attributes("-alpha", 0.0)', stage)
        self.assertNotIn("HWND_BOTTOM", stage)
        self.assertNotIn("window.deiconify()", stage)
        present = inspect.getsource(gui.ShowerProgrammerApp.present_window_without_flash)
        self.assertIn("self.stage_window_behind_owner(window, transient_owner)", present)
        self.assertIn("self.release_first_map_guard(window)", present)
        self.assertIn("settle_pass", present)


    def test_slow_review_feedback_is_inline_not_another_toplevel(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.show_workspace_loading_shield)
        self.assertIn("WindowLoadingCover(", source)
        self.assertNotIn("StartupShield(", source)
        self.assertNotIn("create_hidden_toplevel", source)

    def test_review_covers_main_before_any_review_window_construction(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.open_order_review)
        host_cover = source.index("review_host_cover = WindowLoadingCover(")
        dialog = source.index("dialog = self.create_hidden_toplevel(self.root)", host_cover)
        first_ctk = source.index("header = ctk.CTkFrame(review_content", dialog)
        present = source.index("self.present_window_without_flash(", first_ctk)
        self.assertLess(host_cover, dialog)
        self.assertLess(dialog, first_ctk)
        self.assertLess(first_ctk, present)
        presentation = source.split("def present_review_window() -> None:", 1)[1]
        self.assertIn("on_presented=review_is_in_front", presentation)
        self.assertIn("pass_index >= 4", presentation)
        self.assertIn("review_host_cover.destroy()", presentation)

    def test_application_has_no_direct_customtkinter_toplevel_creation(self) -> None:
        source = (BACKEND / "shower_programmer_gui.py").read_text(encoding="utf-8")
        self.assertNotIn("ctk.CTkToplevel(", source)

    def test_version_169_release_metadata(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 169)
        self.assertIn("VERSION_1_69_FULL_SURFACE_PRESENTATION", (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8"))
        flags = (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8")
        for flag in (
            "staged_native_first_paint",
            "inline_workspace_loading_veil",
            "stable_startup_reveal_barrier",
            "native_tk_root_shell",
            "packager_startup_splash",
            "version_1_69_full_surface_presentation",
        ):
            self.assertIn(flag, flags)


if __name__ == "__main__":
    unittest.main()
