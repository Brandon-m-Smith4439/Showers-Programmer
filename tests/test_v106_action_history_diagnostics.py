from __future__ import annotations

import inspect
import shutil
import sys
import threading
import unittest
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_programmer_gui as gui
import shower_tasks


@contextmanager
def writable_test_directory():
    path = ROOT / "tmp" / "tests" / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


class Version106ActionHistoryDiagnosticsTests(unittest.TestCase):
    def test_action_history_checkbox_uses_supported_ctk_checkbox_colors(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.build_action_history_settings_tab)
        checkbox_start = source.index("ctk.CTkCheckBox(")
        checkbox_end = source.index(").grid(row=0, column=4", checkbox_start)
        checkbox_source = source[checkbox_start:checkbox_end]
        self.assertIn("fg_color=self.ACCENT", checkbox_source)
        self.assertIn("checkmark_color=\"#ffffff\"", checkbox_source)
        self.assertNotIn("progress_color=", checkbox_source)

    def test_action_history_loader_report_exposes_files_invalid_lines_and_counts(self) -> None:
        app = object.__new__(gui.ShowerProgrammerApp)
        with writable_test_directory() as temp:
            app.runtime_root = temp
            app.action_history_lock = threading.RLock()
            current = app.action_history_path()
            current.parent.mkdir(parents=True, exist_ok=True)
            current.write_text(
                '{"id":"good","timestamp":"2026-08-14T07:00:00","action":"Scan Orders"}\n'
                'this is not json\n',
                encoding="utf-8",
            )

            report = app.load_action_history_date_range_report(
                datetime(2026, 8, 8),
                datetime(2026, 8, 14),
            )

            events = report["events"]
            diagnostics = "\n".join(report["diagnostics"])
            self.assertEqual([event["id"] for event in events], ["good"])
            self.assertEqual(report["invalid_lines"], 1)
            self.assertEqual(report["matching_records"], 1)
            self.assertIn("History folder:", diagnostics)
            self.assertIn("WARNING:", diagnostics)
            self.assertIn("Action History file load completed successfully.", diagnostics)

    def test_action_history_tab_has_visible_progress_retry_and_diagnostic_output(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.build_action_history_settings_tab)
        self.assertIn("history_progress_bar = ModernProgressBar", source)
        self.assertIn("history_diagnostics = ctk.CTkTextbox", source)
        self.assertIn('"Retry Load"', source)
        self.assertIn('"Open History Folder"', source)
        self.assertIn('"Copy Diagnostics"', source)
        self.assertIn("load_action_history_date_range_report", source)
        self.assertIn("RENDER ERROR:", source)
        self.assertIn("LOAD ERROR:", source)

    def test_settings_tab_construction_errors_are_shown_inside_the_tab(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.open_settings)
        self.assertIn("Settings tab stopped while constructing its controls", source)
        self.assertIn("could not finish opening", source)
        self.assertIn("Settings Tab Build Failure", source)

    def test_background_task_error_event_contains_traceback(self) -> None:
        events: list[tuple[str, dict[str, object]]] = []
        finished = threading.Event()

        def callback(kind: str, payload: dict[str, object]) -> None:
            events.append((kind, payload))
            if kind == "task_error":
                finished.set()

        manager = shower_tasks.BackgroundTaskManager(callback)

        def worker(_task: shower_tasks.TaskContext) -> None:
            raise RuntimeError("history diagnostic failure")

        manager.start("History Diagnostic", worker, message="Starting", total=1)
        self.assertTrue(finished.wait(2.0))
        error_payload = next(payload for kind, payload in events if kind == "task_error")
        self.assertIn("RuntimeError: history diagnostic failure", str(error_payload.get("traceback", "")))


if __name__ == "__main__":
    unittest.main()
