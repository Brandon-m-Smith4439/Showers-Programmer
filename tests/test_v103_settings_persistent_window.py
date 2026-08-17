from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


class Version103SettingsPersistentWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = (BACKEND / "shower_programmer_gui.py").read_text(encoding="utf-8")
        start = cls.source.index("    def open_settings(")
        end = cls.source.index("    @staticmethod\n    def archive_date_from_name", start)
        cls.open_settings = cls.source[start:end]

    def test_normal_settings_close_never_runs_recursive_destroy(self) -> None:
        close_start = self.open_settings.index("        def close_settings(")
        close_end = self.open_settings.index('        dialog.bind("<Destroy>"', close_start)
        close_block = self.open_settings[close_start:close_end]
        self.assertIn("dialog.withdraw()", close_block)
        self.assertNotIn(".destroy()", close_block)
        self.assertIn('setattr(dialog, "_shower_settings_hidden", True)', close_block)

    def test_hidden_settings_window_is_reused_with_widgets_intact(self) -> None:
        reuse_start = self.open_settings.index('        existing = self.managed_page_window("settings")')
        reuse_end = self.open_settings.index("        dialog = ctk.CTkToplevel", reuse_start)
        reuse_block = self.open_settings[reuse_start:reuse_end]
        self.assertIn("self.settings_window_reusable(existing)", reuse_block)
        self.assertIn('setattr(existing, "_shower_settings_hidden", False)', reuse_block)
        self.assertIn("self.bring_page_window_to_front(existing)", reuse_block)

    def test_nonselected_settings_tabs_build_lazily(self) -> None:
        self.assertIn("tab_builders = {", self.open_settings)
        self.assertIn("built_tabs: set[str] = set()", self.open_settings)
        self.assertIn("def ensure_tab_built(tab_name: str)", self.open_settings)
        self.assertIn("ensure_tab_built(initial_tab)", self.open_settings)
        self.assertIn("ensure_tab_built(selected)", self.open_settings)
        pre_initial = self.open_settings[: self.open_settings.index("ensure_tab_built(initial_tab)")]
        self.assertNotIn('self.build_action_history_settings_tab(tabview.tab("Action History"))\n', pre_initial)

    def test_application_shutdown_quits_mainloop_before_destroy(self) -> None:
        start = self.source.index("    def on_close(self)")
        end = self.source.index("    def activity_elapsed_seconds", start)
        block = self.source[start:end]
        self.assertIn("self.root.quit()", block)
        self.assertIn("self.root.destroy()", block)
        self.assertLess(block.index("self.root.quit()"), block.index("self.root.destroy()"))


if __name__ == "__main__":
    unittest.main()
