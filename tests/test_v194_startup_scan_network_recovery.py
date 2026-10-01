from __future__ import annotations

import json
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_programmer_gui as gui
import shower_tasks


class _Root:
    def __init__(self) -> None:
        self.after_calls: list[tuple[int, object]] = []

    def after(self, delay: int, callback):
        self.after_calls.append((int(delay), callback))
        return "after-id"


class Version194StartupScanNetworkRecoveryTests(unittest.TestCase):
    def test_startup_scan_is_soft_and_explicitly_marked_startup(self) -> None:
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        app.root = _Root()
        app.scan_orders = mock.Mock()
        app._startup_recovery_check_finished = True
        app._startup_recovery_prompt_active = False
        app._startup_initial_scan_started = False
        app._startup_initial_scan_deferred_for_recovery = False

        self.assertTrue(app.schedule_startup_initial_scan(delay_ms=1))
        self.assertEqual(len(app.root.after_calls), 1)
        _delay, callback = app.root.after_calls[0]
        callback()
        app.scan_orders.assert_called_once_with(startup=True)

        source = (BACKEND / "shower_programmer_gui.py").read_text(encoding="utf-8")
        self.assertIn("lock_controls=not startup", source)
        self.assertIn("mark_busy=not startup", source)

    def test_shared_input_index_honors_cancel_while_network_worker_is_pending(self) -> None:
        calls = 0

        def cancel_check() -> None:
            nonlocal calls
            calls += 1
            if calls >= 2:
                raise shower_tasks.TaskCancelled("stop")

        with mock.patch.object(gui.ShowerProgrammerApp, "start_bounded_network_thread", return_value=True):
            started = time.monotonic()
            with self.assertRaises(shower_tasks.TaskCancelled):
                gui.ShowerProgrammerApp.index_import_source_folder_bounded(
                    Path(r"I:\unresponsive"),
                    timeout_seconds=5.0,
                    cancel_check=cancel_check,
                )
            elapsed = time.monotonic() - started

        self.assertLess(elapsed, 1.0)
        self.assertGreaterEqual(calls, 2)

    def test_prepare_import_snapshot_uses_bounded_index_and_reports_timeout(self) -> None:
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        app.EDI_IMPORT_ORDERS_DIR = Path(r"I:\shared")
        timeout_snapshot = {
            "source": str(app.EDI_IMPORT_ORDERS_DIR),
            "source_missing": True,
            "source_error": "Network folder check timed out after 10 seconds",
            "cleanup_timed_out": True,
            "files": [],
        }
        app.index_import_source_folder_bounded = mock.Mock(return_value=timeout_snapshot)

        snapshot, _removed, warnings = app.prepare_import_source_snapshot()

        self.assertTrue(snapshot["cleanup_timed_out"])
        self.assertTrue(warnings)
        app.index_import_source_folder_bounded.assert_called_once()

    def test_production_sketch_probe_returns_without_waiting_for_unresolved_paths(self) -> None:
        production = Path(r"I:\Sketches")
        candidate = {"123456", "123457"}
        found = production / "123456.pdf"
        unresolved = production / "123457.pdf"

        with mock.patch.object(
            gui.ShowerProgrammerApp,
            "network_path_mtimes_bounded",
            return_value=({found: 1000.0}, [unresolved]),
        ):
            matches, warnings, checked, stale = gui.ShowerProgrammerApp.production_sketch_matches(
                production,
                candidate,
                {"123456": 900.0, "123457": 900.0},
            )

        self.assertEqual(matches, {"123456": [found]})
        self.assertEqual(checked, 2)
        self.assertEqual(stale, 0)
        self.assertTrue(any("timeout" in warning.casefold() for warning in warnings))

    def test_network_copy_timeout_never_commits_live_target(self) -> None:
        source = ROOT / "tmp" / "never-read.pdf"
        target = ROOT / "tmp" / "never-written.pdf"
        target.unlink(missing_ok=True)
        warnings: list[str] = []

        with mock.patch.object(gui.ShowerProgrammerApp, "start_bounded_network_thread", return_value=True):
            result = gui.ShowerProgrammerApp.copy_network_file_pairs_bounded(
                [(source, target)],
                stall_timeout_seconds=0.05,
                errors=warnings,
            )

        self.assertEqual(result, [(source, target, None)])
        self.assertFalse(target.exists())
        self.assertTrue(any("retry" in warning.casefold() for warning in warnings))

    def test_version_194_release_metadata_and_flags(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 194)
        self.assertEqual(version["marker"], "VERSION_1_94_STARTUP_SCAN_NETWORK_RECOVERY")
        features = (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8")
        self.assertIn("VERSION_1_94_STARTUP_SCAN_NETWORK_RECOVERY", features)
        flags = (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8")
        for flag in (
            "cancellable_network_scan_index",
            "bounded_production_sketch_probe",
            "bounded_network_import_copy",
            "nonblocking_startup_scan_controls",
            "version_1_94_startup_scan_network_recovery",
        ):
            self.assertIn(flag, flags)


if __name__ == "__main__":
    unittest.main()
