from __future__ import annotations

import json
import unittest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND = PROJECT_ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from shower_programmer_gui import ShowerProgrammerApp
from shower_temp import workspace_temporary_directory


class _Manager:
    def __init__(self, active=None):
        self.active = active


class _Status:
    def __init__(self):
        self.value = ""

    def set(self, value):
        self.value = str(value)


class Version189FullSystemReliabilityAuditTests(unittest.TestCase):
    def test_soft_managed_task_counts_as_operation_active(self):
        app = ShowerProgrammerApp.__new__(ShowerProgrammerApp)
        app.is_busy = False
        app.task_manager = _Manager(active=object())
        self.assertTrue(app.operation_active())
        app.task_manager.active = None
        self.assertFalse(app.operation_active())
        app.is_busy = True
        self.assertTrue(app.operation_active())

    def test_terminal_queue_dispatch_failure_releases_busy_ui_and_writes_diagnostic(self):
        app = ShowerProgrammerApp.__new__(ShowerProgrammerApp)
        app.status_var = _Status()
        released = []
        app.finish_background_activity = lambda: released.append(True)
        with workspace_temporary_directory() as tmp:
            root = Path(tmp)
            app.internal_output_dir = lambda: root
            try:
                raise RuntimeError("synthetic queue handoff failure")
            except RuntimeError as exc:
                app.handle_worker_queue_dispatch_failure("scan_done", exc)
            self.assertEqual(released, [True])
            self.assertIn("Recovered from an internal scan_done", app.status_var.value)
            log_path = root / app.DIAGNOSTICS_FOLDER_NAME / "worker_queue_errors.log"
            self.assertTrue(log_path.is_file())
            text = log_path.read_text(encoding="utf-8")
            self.assertIn("scan_done", text)
            self.assertIn("synthetic queue handoff failure", text)

    def test_nonterminal_queue_dispatch_failure_does_not_unlock_active_worker(self):
        app = ShowerProgrammerApp.__new__(ShowerProgrammerApp)
        app.status_var = _Status()
        released = []
        app.finish_background_activity = lambda: released.append(True)
        with workspace_temporary_directory() as tmp:
            app.internal_output_dir = lambda: Path(tmp)
            try:
                raise ValueError("progress paint failed")
            except ValueError as exc:
                app.handle_worker_queue_dispatch_failure("task_progress", exc)
        self.assertEqual(released, [])

    def test_queue_pump_has_general_dispatch_recovery_and_rearm_guard(self):
        source = (PROJECT_ROOT / "Backend" / "shower_programmer_gui.py").read_text(encoding="utf-8")
        start = source.index("    def drain_worker_queue(self) -> None:")
        end = source.index("    @staticmethod\n    def scan_status_message", start)
        body = source[start:end]
        self.assertIn("except Exception as exc:", body)
        self.assertIn("handle_worker_queue_dispatch_failure(current_kind, exc)", body)
        self.assertIn("except (tk.TclError, RuntimeError):", body)

    def test_production_guards_include_soft_managed_tasks(self):
        source = (PROJECT_ROOT / "Backend" / "shower_programmer_gui.py").read_text(encoding="utf-8")
        for method_name in (
            "on_close",
            "toggle_color_mode",
            "scan_orders",
            "refresh_local_orders",
            "import_edi_orders",
            "validate_selected_orders",
            "run_orders",
            "check_for_updates",
            "send_all_to_shop",
            "send_outputs_to_shop",
        ):
            start = source.index(f"    def {method_name}")
            next_def = source.find("\n    def ", start + 8)
            body = source[start: next_def if next_def != -1 else len(source)]
            self.assertIn("operation_active()", body, method_name)

    def test_integrated_self_test_reports_all_version_189_required_flags(self):
        source = (PROJECT_ROOT / "Backend" / "shower_programmer_gui.py").read_text(encoding="utf-8")
        start = source.index("def run_packaged_self_test(report_path: Path)")
        end = source.index("\ndef main() -> None:", start)
        body = source[start:end]
        for flag in (
            "worker_queue_dispatch_recovery",
            "terminal_queue_ui_unlock",
            "soft_managed_task_operation_guard",
            "queue_pump_rearm_guard",
            "version_1_89_full_system_reliability_audit",
        ):
            self.assertIn(f'"{flag}": True', body, flag)

    def test_version_189_release_metadata_and_flag(self):
        version = json.loads((PROJECT_ROOT / "Backend" / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 189)
        features = (PROJECT_ROOT / "Backend" / "shower_v4_features.py").read_text(encoding="utf-8")
        self.assertIn("VERSION_1_89_FULL_SYSTEM_RELIABILITY_AUDIT", features)
        flags = (PROJECT_ROOT / "Backend" / "release_required_flags.txt").read_text(encoding="utf-8")
        self.assertIn("version_1_89_full_system_reliability_audit", flags)


if __name__ == "__main__":
    unittest.main()
