from __future__ import annotations

import inspect
import json
import queue
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_programmer_gui as gui


class StartupUpdateNotificationTests(unittest.TestCase):
    def test_packaged_startup_schedules_quiet_update_check(self) -> None:
        init_source = inspect.getsource(gui.ShowerProgrammerApp.__init__)
        self.assertIn("self.root.after(2600, self.start_startup_update_check)", init_source)
        source = inspect.getsource(gui.ShowerProgrammerApp.start_startup_update_check)
        self.assertIn('not getattr(sys, "frozen", False)', source)
        self.assertIn('args=(repo, "", False, True)', source)
        self.assertIn('name="shower-startup-update-check"', source)

    def test_startup_worker_is_silent_for_progress_and_errors(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.worker_check_for_updates)
        self.assertIn("if not startup_notify_only:", source)
        self.assertIn("self.queue_update_progress(percent, stage, detail)", source)
        error_block = source.split("except Exception as exc:", 1)[1]
        self.assertIn("if startup_notify_only:", error_block)
        self.assertIn("return", error_block)

    def test_startup_results_hide_no_update_and_information_dialogs(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.drain_worker_queue)
        no_update = source.split('elif kind == "update_no_updates":', 1)[1].split('elif kind == "update_available":', 1)[0]
        self.assertIn('if bool(data.get("startup_notify_only", False)):', no_update)
        self.assertIn("continue", no_update)
        information = source.split('elif kind == "update_information":', 1)[1].split('elif kind == "update_install_done":', 1)[0]
        self.assertIn('if bool(data.get("startup_notify_only", False)):', information)
        self.assertIn("continue", information)

    def test_available_startup_update_defers_while_production_is_busy(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.drain_worker_queue)
        available = source.split('elif kind == "update_available":', 1)[1].split('elif kind == "update_information":', 1)[0]
        self.assertIn('startup_notify_only = bool(data.get("startup_notify_only", False))', available)
        self.assertIn('active_modal = self.root.grab_current()', available)
        self.assertTrue(
            'startup_notify_only and (self.is_busy or active_modal is not None)' in available
            or 'startup_notify_only and (self.operation_active() or active_modal is not None)' in available
        )
        self.assertIn('self.root.after(1200', available)
        self.assertIn('self.begin_update_install(data)', available)

    def test_manual_check_keeps_visible_progress_workflow(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.check_for_updates)
        self.assertIn('self.startup_update_check_started = True', source)
        self.assertIn('self.start_background_activity("Connecting to GitHub...", maximum=100)', source)
        self.assertIn("self.open_update_progress_window()", source)
        self.assertIn("args=(repo, str(git or \"\"), use_git)", source)

    def test_version_187_release_metadata_and_flags(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 187)
        features = (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8")
        self.assertIn("VERSION_1_87_STARTUP_UPDATE_NOTIFICATION", features)
        flags = (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8")
        for flag in (
            "packaged_startup_update_notification",
            "silent_startup_update_check",
            "startup_update_network_failure_suppression",
            "startup_update_busy_defer",
            "version_1_87_startup_update_notification",
        ):
            self.assertIn(flag, flags)


if __name__ == "__main__":
    unittest.main()
