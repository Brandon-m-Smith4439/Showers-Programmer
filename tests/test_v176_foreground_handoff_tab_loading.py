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


class ForegroundHandoffAndSettingsTabLoadingTests(unittest.TestCase):
    def test_review_keeps_main_cover_until_foreground_is_stable(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.open_order_review)
        self.assertIn("foreground_checks", source)
        self.assertIn("self.window_is_foreground(dialog)", source)
        self.assertIn('dialog.attributes("-topmost", True)', source)
        self.assertIn('dialog.attributes("-topmost", False)', source)
        handoff = source.split("def finish_review_foreground_handoff", 1)[1]
        self.assertIn("review_host_cover.destroy()", handoff)
        self.assertIn("foreground_checks[\"stable\"] >= 2", handoff)

    def test_manual_dxf_confirmation_uses_themed_staged_dialog(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.open_order_review)
        self.assertIn("self.ask_themed_confirmation(", source)
        self.assertIn('confirm_text="Mark Resolved"', source)
        helper = inspect.getsource(gui.ShowerProgrammerApp.ask_themed_confirmation)
        self.assertIn("self.create_hidden_toplevel(owner)", helper)
        self.assertIn("self.present_window_without_flash(", helper)
        self.assertIn("self.root.wait_variable(finished)", helper)

    def test_settings_unbuilt_tabs_get_loading_cover_before_construction(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.open_settings)
        self.assertIn("def build_tab_with_loading", source)
        self.assertIn('parent = tabview.tab(name)', source)
        self.assertIn('title=name', source)
        self.assertIn('detail=f"Loading {name}..."', source)
        self.assertIn("dialog.after(24, build_selected_tab)", source)
        self.assertIn("def finish_tab_loading_cover", source)
        self.assertIn('setattr(dialog, "_settings_select_tab", select_settings_tab)', source)

    def test_foreground_probe_compares_real_top_level_hwnd(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.window_is_foreground)
        self.assertIn("self.native_window_handle(window)", source)
        self.assertIn("GetForegroundWindow", source)

    def test_version_176_release_metadata(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 176)
        features = (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8")
        self.assertIn("VERSION_1_76_FOREGROUND_HANDOFF_TAB_LOADING", features)
        flags = (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8")
        for flag in (
            "review_foreground_cover_handoff",
            "themed_manual_dxf_confirmation",
            "settings_tab_loading_covers",
            "version_1_76_foreground_handoff_tab_loading",
        ):
            self.assertIn(flag, flags)


if __name__ == "__main__":
    unittest.main()
