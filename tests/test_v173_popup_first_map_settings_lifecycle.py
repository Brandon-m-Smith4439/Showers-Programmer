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


class PopupFirstMapSettingsLifecycleTests(unittest.TestCase):
    def test_opening_feedback_never_creates_temporary_native_window(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.show_opening_window)
        self.assertIn("show_workspace_loading_shield", source)
        self.assertNotIn("create_hidden_toplevel", source)
        self.assertNotIn("tk.Toplevel", source)

    def test_major_page_presentation_does_not_resolve_root_to_temporary_popup(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.present_window_without_flash)
        self.assertIn("if make_transient and transient_owner is self.root", source)
        self.assertIn("if make_transient and transient_owner is self.root", source)

    def test_hidden_child_avoids_direct_win32_layered_style_mutation(self) -> None:
        hidden_source = inspect.getsource(gui.ShowerProgrammerApp.create_hidden_toplevel)
        native_hidden_source = inspect.getsource(gui.ShowerProgrammerApp.create_hidden_native_toplevel)
        alpha_source = inspect.getsource(gui.ShowerProgrammerApp.set_native_window_alpha)
        self.assertIn("FlashFreeToplevel(owner, background=self.APP_BG)", hidden_source)
        self.assertIn("window.withdraw()", native_hidden_source)
        self.assertNotIn("WS_EX_LAYERED", alpha_source)
        self.assertNotIn("SetLayeredWindowAttributes", alpha_source)


    def test_presenter_forces_mapped_paint_before_tk_opaque_reveal(self) -> None:
        stage_source = inspect.getsource(gui.ShowerProgrammerApp.stage_window_behind_owner)
        present_source = inspect.getsource(gui.ShowerProgrammerApp.present_window_without_flash)
        self.assertNotIn("window.deiconify()", stage_source)
        self.assertIn("self.force_native_window_paint(window)", present_source)
        self.assertIn('window.attributes("-alpha", 1.0)', present_source)
        self.assertNotIn("SetLayeredWindowAttributes", present_source)


    def test_custom_messagebox_defers_modal_grab_until_presented(self) -> None:
        source = inspect.getsource(gui._ProgramMessageBox._show)
        self.assertIn('setattr(dialog, "_shower_grab_on_present", True)', source)
        tail = source[source.index("if app is not None and hasattr(app, \"present_window_without_flash\")"):]
        self.assertNotIn("dialog.grab_set()", tail)

    def test_version_173_release_metadata(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 173)
        features = (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8")
        self.assertIn("VERSION_1_73_POPUP_FIRST_MAP_SETTINGS_LIFECYCLE", features)
        flags = (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8")
        for flag in (
            "native_pre_map_alpha",
            "native_hidden_first_paint",
            "inline_workspace_opening_feedback",
            "stable_major_page_ownership",
            "deferred_popup_modal_grab",
            "version_1_73_popup_first_map_settings_lifecycle",
        ):
            self.assertIn(flag, flags)



if __name__ == "__main__":
    unittest.main()
