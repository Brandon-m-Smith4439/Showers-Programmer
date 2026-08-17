from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


class Version101SettingsLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = (BACKEND / "shower_programmer_gui.py").read_text(encoding="utf-8")
        cls.open_settings = cls.source[
            cls.source.index("    def open_settings(") : cls.source.index("    @staticmethod\n    def archive_date_from_name", cls.source.index("    def open_settings("))
        ]
        cls.archive_tab = cls.source[
            cls.source.index("    def build_archive_settings_tab(") : cls.source.index("    def build_recovery_settings_tab(", cls.source.index("    def build_archive_settings_tab("))
        ]
        cls.archive_start = cls.archive_tab[
            cls.archive_tab.index("        def start_load(") : cls.archive_tab.index("        def apply_date_filter()", cls.archive_tab.index("        def start_load("))
        ]

    def test_settings_close_has_explicit_safe_window_lifecycle(self) -> None:
        self.assertIn('dialog.protocol("WM_DELETE_WINDOW", close_settings)', self.open_settings)
        self.assertIn('dialog.bind("<Escape>", close_settings)', self.open_settings)
        self.assertIn("dialog.withdraw()", self.open_settings)
        self.assertIn("self.root.after_idle(restore_main_focus)", self.open_settings)
        self.assertIn("grabber = dialog.grab_current()", self.open_settings)
        self.assertIn("grabber.grab_release()", self.open_settings)

    def test_opening_preferences_does_not_automatically_load_archives(self) -> None:
        self.assertIn('if selected == "Archives":', self.open_settings)
        self.assertIn('elif selected == "Action History":', self.open_settings)
        self.assertIn("dialog.after_idle(activate_selected_tab)", self.open_settings)
        self.assertNotIn("dialog.after(100, refresh)", self.archive_tab)
        self.assertIn('value="Archives are ready. Open this tab to load the most recent seven days."', self.archive_tab)

    def test_archive_browser_uses_settings_owned_task_manager(self) -> None:
        self.assertIn("archive_task_manager = shower_tasks.BackgroundTaskManager", self.archive_tab)
        self.assertIn("snapshot = archive_task_manager.start(", self.archive_start)
        self.assertNotIn("self.run_managed_task(", self.archive_start)
        self.assertIn('setattr(dialog, "_archive_cancel", cancel_archive_settings_work)', self.archive_tab)
        self.assertIn("archive_task_manager.cancel()", self.archive_tab)

    def test_settings_archive_worker_never_updates_tk_from_worker_thread(self) -> None:
        self.assertIn("archive_task_events.put((kind, payload))", self.archive_tab)
        worker = self.archive_start[
            self.archive_start.index("            def worker(") : self.archive_start.index("            try:\n                snapshot = archive_task_manager.start")
        ]
        self.assertNotIn("archive_status_var.set", worker)
        self.assertNotIn("dialog.after", worker)
        self.assertNotIn("messagebox.", worker)


if __name__ == "__main__":
    unittest.main()
