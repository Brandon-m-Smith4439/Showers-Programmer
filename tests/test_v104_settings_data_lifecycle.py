from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_programmer_gui as gui


class Version104SettingsDataLifecycleTests(unittest.TestCase):
    def test_archives_have_tab_local_progress_cancel_retry_and_error_state(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.build_archive_settings_tab)
        self.assertIn("progress_card = ctk.CTkFrame", source)
        self.assertIn("archive_progress_bar = ModernProgressBar", source)
        self.assertIn('"Cancel"', source)
        self.assertIn('"Retry"', source)
        self.assertIn('"Archive load failed"', source)
        self.assertIn('state="error"', source)
        self.assertIn('state="cancelled"', source)

    def test_settings_close_does_not_orphan_archive_refresh_state(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.build_archive_settings_tab)
        cancel_start = source.index("        def cancel_archive_settings_work()")
        cancel_end = source.index('        setattr(dialog, "_archive_activate"', cancel_start)
        cancel_block = source[cancel_start:cancel_end]
        self.assertIn("refresh_needed[mode] = True", cancel_block)
        self.assertIn("archive_task_manager.cancel()", cancel_block)
        self.assertNotIn("after_cancel(archive_poll_after_id)", cancel_block)
        self.assertIn("refresh_inflight.discard(mode)", source)
        activate_start = source.index("        def activate_archive_tab()")
        activate_end = source.index("        def cancel_archive_settings_work()", activate_start)
        activate_block = source[activate_start:activate_end]
        self.assertLess(
            activate_block.index("if mode in refresh_inflight:"),
            activate_block.index("archive_cancelled_for_hide = False"),
        )

    def test_archive_errors_do_not_mark_failed_range_as_loaded(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.build_archive_settings_tab)
        error_start = source.index('                elif kind == "task_error":')
        error_end = source.index("            while True:", error_start)
        error_block = source[error_start:error_end]
        self.assertIn("refresh_needed[mode] = True", error_block)
        self.assertIn('set_archive_progress(', error_block)
        self.assertNotIn("archive_result_queue.put", error_block)

    def test_action_history_refreshes_every_time_tab_is_activated(self) -> None:
        settings_source = inspect.getsource(gui.ShowerProgrammerApp.open_settings)
        history_source = inspect.getsource(gui.ShowerProgrammerApp.build_action_history_settings_tab)
        self.assertIn('elif selected == "Action History":', settings_source)
        self.assertIn('getattr(dialog, "_action_history_activate", None)', settings_source)
        self.assertIn('setattr(dialog, "_action_history_activate", activate_action_history)', history_source)
        self.assertIn("parent.after_idle(refresh_history)", history_source)
        self.assertIn('count_var.set("Loading action history...")', history_source)

    def test_reopened_persistent_settings_reactivates_selected_tab(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.open_settings)
        reuse_start = source.index('        if existing is not None:')
        reuse_end = source.index("        dialog = ctk.CTkToplevel", reuse_start)
        reuse_block = source[reuse_start:reuse_end]
        self.assertIn('getattr(existing, "_settings_activate_selected", None)', reuse_block)
        self.assertIn("existing.after_idle(activate_selected)", reuse_block)


if __name__ == "__main__":
    unittest.main()
