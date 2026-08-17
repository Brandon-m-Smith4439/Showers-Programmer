from __future__ import annotations

import inspect
import shutil
import sys
import threading
import unittest
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_programmer_gui as gui


@contextmanager
def writable_test_directory():
    path = ROOT / "tmp" / "tests" / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


class Version105HistoryArchiveSettingsPolishTests(unittest.TestCase):
    def test_action_history_date_range_reads_only_intersecting_month_files(self) -> None:
        app = object.__new__(gui.ShowerProgrammerApp)
        with writable_test_directory() as temp:
            app.runtime_root = temp
            app.action_history_lock = threading.RLock()
            recent = {
                "id": "recent",
                "timestamp": "2026-08-13T09:00:00",
                "action": "Scan Orders",
                "status": "SUCCESS",
                "message": "Recent",
            }
            august = {
                "id": "august",
                "timestamp": "2026-08-08T09:00:00",
                "action": "Delete Local Inputs",
                "status": "SUCCESS",
                "message": "August",
            }
            july = {
                "id": "july",
                "timestamp": "2026-07-20T09:00:00",
                "action": "Send Output",
                "status": "SUCCESS",
                "message": "July",
            }
            app.write_action_history_file(app.action_history_path(), [recent])
            archive_dir = app.action_history_archive_dir()
            app.write_action_history_file(archive_dir / "actions-2026-08.jsonl", [august])
            app.write_action_history_file(archive_dir / "actions-2026-07.jsonl", [july])

            events = app.load_action_history_date_range(
                datetime(2026, 8, 7),
                datetime(2026, 8, 13),
            )

            self.assertEqual([event["id"] for event in events], ["recent", "august"])

    def test_action_history_archive_path_range_is_month_scoped(self) -> None:
        paths = gui.ShowerProgrammerApp.action_history_archive_paths_for_range(
            Path("History") / "Archive",
            datetime(2026, 7, 29),
            datetime(2026, 8, 3),
        )
        self.assertEqual([path.name for path in paths], ["actions-2026-07.jsonl", "actions-2026-08.jsonl"])

    def test_settings_action_history_is_seven_day_date_windowed_and_background_loaded(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.build_action_history_settings_tab)
        self.assertIn('initial_from = today - timedelta(days=6)', source)
        self.assertIn('text="History dates"', source)
        self.assertIn('"Apply Range"', source)
        self.assertIn('"Last 7 Days"', source)
        self.assertIn("load_action_history_date_range", source)
        self.assertIn("BackgroundTaskManager", source)
        self.assertIn("render_history", source)
        self.assertNotIn('values=["Last 7 Days", "Archive", "All"]', source)

    def test_archive_tab_has_one_date_action_strip_and_clean_archive_actions(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.build_archive_settings_tab)
        self.assertIn('"Load 7 More Days"', source)
        self.assertNotIn('"Refresh Range"', source)
        self.assertIn("mode_menu = ctk.CTkSegmentedButton", source)
        self.assertIn('text="Open Test Mode"', source)
        self.assertIn('"Archive Sent Inputs"', source)

    def test_settings_is_maximized_on_first_open_and_reopen(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.open_settings)
        self.assertIn("existing.after_idle(lambda window=existing: self.maximize_window(window))", source)
        self.assertIn("dialog.after_idle(lambda: self.maximize_window(dialog))", source)


if __name__ == "__main__":
    unittest.main()
