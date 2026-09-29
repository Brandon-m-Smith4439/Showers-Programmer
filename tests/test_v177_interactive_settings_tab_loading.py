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


class InteractiveSettingsTabLoadingTests(unittest.TestCase):
    def test_settings_loading_cover_is_scoped_to_tab_content(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.open_settings)
        self.assertIn("parent = tabview.tab(name)", source)
        self.assertIn("tab_loading_covers: dict[str, WindowLoadingCover]", source)
        self.assertNotIn('WindowLoadingCover(\n                dialog,\n                background=self.APP_BG,\n                accent=self.ACCENT,\n                text_color=self.TEXT,\n                muted_color=self.MUTED,\n                title=f"Settings - {name}"', source)

    def test_tab_switch_can_defer_unstarted_build(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.open_settings)
        self.assertIn("if selected != name:", source)
        self.assertIn("tab_build_in_progress.discard(name)", source)
        self.assertIn("dialog.after(24, build_selected_tab)", source)
        self.assertIn("The segmented tab selector stays outside each tab-local loading", source)

    def test_async_tabs_keep_independent_cover_until_ready(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.open_settings)
        self.assertIn('async_initial_tabs = {"System Health", "Archives", "Action History"}', source)
        self.assertIn('setattr(dialog, "_settings_mark_tab_ready", mark_settings_tab_ready)', source)
        self.assertIn("if name not in async_initial_tabs:", source)
        archive = inspect.getsource(gui.ShowerProgrammerApp.build_archive_settings_tab)
        history = inspect.getsource(gui.ShowerProgrammerApp.build_action_history_settings_tab)
        health = inspect.getsource(gui.ShowerProgrammerApp.build_system_health_settings_tab)
        self.assertIn('mark_ready("Archives")', archive)
        self.assertIn('mark_ready("Action History")', history)
        self.assertIn('mark_ready("System Health")', health)

    def test_version_177_release_metadata(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 177)
        features = (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8")
        self.assertIn("VERSION_1_77_INTERACTIVE_SETTINGS_TAB_LOADING", features)
        flags = (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8")
        for flag in (
            "settings_content_local_loading",
            "settings_loading_tab_switching",
            "settings_async_tab_cover_lifecycle",
            "version_1_77_interactive_settings_tab_loading",
        ):
            self.assertIn(flag, flags)


if __name__ == "__main__":
    unittest.main()
