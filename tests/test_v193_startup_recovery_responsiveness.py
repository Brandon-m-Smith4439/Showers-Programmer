from __future__ import annotations

import json
import sys
import unittest
import uuid
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_programmer_gui as gui
import shower_reliability


class _Root:
    def __init__(self) -> None:
        self.after_calls: list[tuple[int, object]] = []

    def after(self, delay: int, callback):
        self.after_calls.append((int(delay), callback))
        return "after-id"


class Version193StartupRecoveryResponsivenessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = ROOT / "tmp" / "tests" / uuid.uuid4().hex
        self.temp.mkdir(parents=True)

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self.temp, ignore_errors=True)

    def test_startup_scan_waits_until_recovery_check_finishes(self) -> None:
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        app.root = _Root()
        app.scan_orders = mock.Mock()
        app._startup_recovery_check_finished = False
        app._startup_recovery_prompt_active = False
        app._startup_initial_scan_started = False
        app._startup_initial_scan_deferred_for_recovery = False

        self.assertFalse(app.schedule_startup_initial_scan())
        self.assertEqual(app.root.after_calls, [])

        app._startup_recovery_check_finished = True
        self.assertTrue(app.schedule_startup_initial_scan())
        self.assertEqual(len(app.root.after_calls), 1)
        self.assertEqual(app.root.after_calls[0][0], 120)

    def test_open_recovery_defers_initial_scan(self) -> None:
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        app.runtime_root = self.temp
        app.root = mock.Mock()
        app.output_dir_var = mock.Mock(get=lambda: str(self.temp / "Output"))
        app.action_history_dir = lambda: self.temp / "History"
        app.record_action = mock.Mock()
        app.open_settings = mock.Mock()
        app.schedule_startup_initial_scan = mock.Mock(return_value=True)
        app._startup_recovery_check_finished = False
        app._startup_recovery_prompt_active = False
        app._startup_initial_scan_started = False
        app._startup_initial_scan_deferred_for_recovery = False
        warning = {
            "type": "send",
            "severity": "WARN",
            "title": "Interrupted Send transaction",
            "detail": "send-old stopped at NEEDS_ATTENTION for 123456.",
            "path": str(self.temp / "Output" / "Transactions" / "Send" / "send-old.json"),
        }

        with mock.patch.object(gui.messagebox, "_show", return_value="recovery"):
            app.apply_startup_recovery_results([warning])

        self.assertTrue(app._startup_recovery_check_finished)
        self.assertTrue(app._startup_initial_scan_deferred_for_recovery)
        app.open_settings.assert_called_once_with("Recovery")
        app.schedule_startup_initial_scan.assert_not_called()

    def test_later_releases_initial_scan(self) -> None:
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        app.runtime_root = self.temp
        app.root = mock.Mock()
        app.output_dir_var = mock.Mock(get=lambda: str(self.temp / "Output"))
        app.action_history_dir = lambda: self.temp / "History"
        app.record_action = mock.Mock()
        app.open_settings = mock.Mock()
        app.schedule_startup_initial_scan = mock.Mock(return_value=True)
        app._startup_recovery_check_finished = False
        app._startup_recovery_prompt_active = False
        app._startup_initial_scan_started = False
        app._startup_initial_scan_deferred_for_recovery = False
        warning = {
            "type": "send",
            "severity": "WARN",
            "title": "Interrupted Send transaction",
            "detail": "send-old stopped at NEEDS_ATTENTION for 123456.",
            "path": "journal.json",
        }

        with mock.patch.object(gui.messagebox, "_show", return_value="later"):
            app.apply_startup_recovery_results([warning])

        app.schedule_startup_initial_scan.assert_called_once()
        app.open_settings.assert_not_called()

    def test_recovery_acknowledgement_is_written_beside_history_and_send_journals(self) -> None:
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        output = self.temp / "Output"
        app.output_dir_var = mock.Mock(get=lambda: str(output))
        app.action_history_dir = lambda: self.temp / "History"
        state = {
            "active_fingerprint": "abc123",
            "acknowledged_fingerprint": "abc123",
            "history": [],
        }

        app.save_startup_recovery_notice_state(state)

        history_path = self.temp / "History" / app.STARTUP_RECOVERY_STATE_FILE_NAME
        output_path = output / "Transactions" / "Recovery" / app.STARTUP_RECOVERY_STATE_FILE_NAME
        self.assertTrue(history_path.is_file())
        self.assertTrue(output_path.is_file())
        self.assertEqual(json.loads(history_path.read_text(encoding="utf-8"))["active_fingerprint"], "abc123")
        self.assertEqual(json.loads(output_path.read_text(encoding="utf-8"))["active_fingerprint"], "abc123")

    def test_reviewed_send_journal_resolution_does_not_touch_production_file(self) -> None:
        output = self.temp / "Output"
        output.mkdir(parents=True)
        production = self.temp / "production.dxf"
        production.write_bytes(b"keep-me")
        journal = shower_reliability.SendJournal(output)
        transaction_id = journal.begin(
            aw_orders=["237938"],
            output_sources=[production],
            archive_inputs=True,
        )
        journal.update(
            transaction_id,
            shower_reliability.SendStage.NEEDS_ATTENTION,
            "Post-send integrity needs attention.",
            integrity_ok=False,
        )

        journal.resolve_after_operator_review(transaction_id)

        self.assertEqual(journal.incomplete(), [])
        self.assertEqual(production.read_bytes(), b"keep-me")
        payload = journal.read(transaction_id)
        self.assertEqual(payload["stage"], shower_reliability.SendStage.FAILED_RESOLVED)
        self.assertTrue(payload["operator_reviewed"])

    def test_reconcile_scan_guard_is_present(self) -> None:
        source = (BACKEND / "shower_programmer_gui.py").read_text(encoding="utf-8")
        self.assertIn("if reconciled:\n                self.scan_orders()", source)
        self.assertNotIn("reconciled += 1\n            self.scan_orders()", source)
        self.assertIn("Mark Reviewed", source)

    def test_version_193_release_metadata_and_flags(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 193)
        features = (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8")
        self.assertIn("VERSION_1_93_STARTUP_RECOVERY_RESPONSIVENESS", features)
        flags = (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8")
        for flag in (
            "startup_recovery_scan_gate",
            "durable_recovery_acknowledgement",
            "reviewed_send_journal_resolution",
            "recovery_reconcile_scan_guard",
            "version_1_93_startup_recovery_responsiveness",
        ):
            self.assertIn(flag, flags)


if __name__ == "__main__":
    unittest.main()
