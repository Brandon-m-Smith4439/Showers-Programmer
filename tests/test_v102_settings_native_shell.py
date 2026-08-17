from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_programmer_gui as gui


class _FakeWindow:
    def __init__(self) -> None:
        self.alive = True
        self.withdrawn = False
        self.children = [object(), object()]
        self._shower_settings_retired = False

    def withdraw(self) -> None:
        self.withdrawn = True

    def grab_current(self):
        return None

    def attributes(self, *_args):
        return None

    def winfo_exists(self) -> int:
        return int(self.alive)

    def winfo_children(self):
        return list(self.children)


class Version102SettingsNativeShellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = (BACKEND / "shower_programmer_gui.py").read_text(encoding="utf-8")
        start = cls.source.index("    def retire_settings_window(")
        end = cls.source.index("    @staticmethod\n    def archive_date_from_name", start)
        cls.settings_block = cls.source[start:end]

    def test_damaged_settings_shell_is_retired_without_recursive_destroy(self) -> None:
        window = _FakeWindow()
        app = SimpleNamespace(
            managed_page_windows={"settings": window},
            settings_tabview=None,
        )

        gui.ShowerProgrammerApp.retire_settings_window(app, window)

        self.assertTrue(window.withdrawn)
        self.assertTrue(window._shower_settings_retired)
        self.assertNotIn("settings", app.managed_page_windows)

    def test_settings_window_reuse_rejects_retired_or_blank_shells(self) -> None:
        window = _FakeWindow()
        app = SimpleNamespace()

        self.assertTrue(gui.ShowerProgrammerApp.settings_window_reusable(app, window))

        window._shower_settings_retired = True
        self.assertFalse(gui.ShowerProgrammerApp.settings_window_reusable(app, window))

        window._shower_settings_retired = False
        window.children.clear()
        self.assertFalse(gui.ShowerProgrammerApp.settings_window_reusable(app, window))

    def test_settings_close_withdraws_instead_of_destroying_widget_tree(self) -> None:
        close_start = self.settings_block.index("        def close_settings(")
        close_end = self.settings_block.index('        dialog.bind("<Destroy>"', close_start)
        close_block = self.settings_block[close_start:close_end]
        self.assertIn("dialog.withdraw()", close_block)
        self.assertNotIn("dialog.destroy()", close_block)
        self.assertNotIn("destroy_toplevel_safely", close_block)

    def test_open_settings_retires_a_damaged_shell_without_recursive_destroy(self) -> None:
        self.assertIn("not self.settings_window_reusable(existing)", self.settings_block)
        self.assertIn("self.retire_settings_window(existing)", self.settings_block)
        self.assertIn("existing = None", self.settings_block)


if __name__ == "__main__":
    unittest.main()
