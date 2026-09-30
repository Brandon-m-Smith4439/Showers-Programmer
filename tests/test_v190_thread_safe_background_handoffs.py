from __future__ import annotations

import ast
import json
import queue
import re
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_programmer_gui as gui


class _ExplodingVar:
    def get(self):
        raise AssertionError("background code touched a Tk variable")

    def set(self, _value):
        raise AssertionError("background code touched a Tk variable")


class _Manager:
    def __init__(self, active=None):
        self.active = active


class Version190ThreadSafeBackgroundHandoffsTests(unittest.TestCase):
    def test_ui_callback_handoff_uses_worker_queue(self) -> None:
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        app.worker_queue = queue.Queue()
        callback = lambda: None
        app.queue_ui_callback(callback)
        kind, payload = app.worker_queue.get_nowait()
        self.assertEqual(kind, "ui_callback")
        self.assertIs(payload, callback)

    def test_pending_terminal_handoff_counts_as_active_operation(self) -> None:
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        app.is_busy = False
        app.task_manager = _Manager(active=None)
        app._managed_task_pending_ids = {"task-190"}
        self.assertTrue(app.operation_active())
        app._managed_task_pending_ids.clear()
        self.assertFalse(app.operation_active())

    def test_background_thread_targets_do_not_call_tk_after_directly(self) -> None:
        source = (BACKEND / "shower_programmer_gui.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        app_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "ShowerProgrammerApp")
        offenders: list[str] = []
        for method in (node for node in app_class.body if isinstance(node, ast.FunctionDef)):
            local_functions = {node.name: node for node in method.body if isinstance(node, ast.FunctionDef)}
            thread_targets: list[str] = []
            for node in ast.walk(method):
                if not isinstance(node, ast.Call):
                    continue
                called = node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id if isinstance(node.func, ast.Name) else ""
                if called != "Thread":
                    continue
                for keyword in node.keywords:
                    if keyword.arg == "target" and isinstance(keyword.value, ast.Name):
                        thread_targets.append(keyword.value.id)
            for target_name in thread_targets:
                target = local_functions.get(target_name)
                if target is None:
                    continue
                for node in ast.walk(target):
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "after":
                        offenders.append(f"{method.name}->{target_name}:{node.lineno}")
        self.assertEqual(offenders, [])

    def test_worker_methods_do_not_read_or_write_tk_variables_directly(self) -> None:
        source = (BACKEND / "shower_programmer_gui.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        app_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "ShowerProgrammerApp")
        offenders: list[str] = []
        for method in (node for node in app_class.body if isinstance(node, ast.FunctionDef) and node.name.startswith("worker_")):
            for node in ast.walk(method):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                    continue
                owner = node.func.value
                if node.func.attr in {"get", "set"} and isinstance(owner, ast.Attribute) and isinstance(owner.value, ast.Name) and owner.value.id == "self" and owner.attr.endswith("_var"):
                    offenders.append(f"{method.name}:{node.lineno}:{owner.attr}.{node.func.attr}")
        self.assertEqual(offenders, [])

    def test_send_worker_requires_ui_thread_path_snapshots(self) -> None:
        source = (BACKEND / "shower_programmer_gui.py").read_text(encoding="utf-8")
        start = source.index("    def worker_send_outputs(")
        end = source.index("\n    def successfully_sent_orders", start)
        body = source[start:end]
        self.assertIn("Send worker requires an explicit output directory snapshot", body)
        self.assertIn("Send worker requires an explicit configuration snapshot path", body)
        self.assertNotIn("self.output_dir_var.get()", body)
        self.assertNotIn("self.editable_config_path()", body)

    def test_explicit_history_and_override_paths_never_touch_tk_variable(self) -> None:
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        app.output_dir_var = _ExplodingVar()
        app.order_by_aw = {}
        app._manual_overrides_session_output = None
        app._manual_overrides_session_data = None
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            (output_dir / "processing_history.json").write_text(json.dumps({"orders": {"239190": {"sent_at": "2026-09-30T10:00:00-04:00", "sketch_output_skipped": True}}}), encoding="utf-8")
            (output_dir / "manual_overrides.json").write_text(json.dumps({"item_overrides": {"239190": {"_order_checked": True}}}), encoding="utf-8")
            self.assertTrue(app.output_was_skipped_for_order("239190", "sketch", output_dir=output_dir))
            self.assertEqual(app.review_status_for_order_from_output("239190", output_dir), "Order checked")
            history_entry = app.history_for_order_from_output("239190", output_dir)
            self.assertTrue(app.sent_summary_for_order_from_history("239190", history_entry).startswith("Sent "))

    def test_batch_output_discovery_loads_history_once_per_call(self) -> None:
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        history = {"orders": {}}
        app.load_processing_history_for_output = mock.Mock(return_value=history)
        app.output_was_skipped_for_order = mock.Mock(return_value=False)
        app.find_order_sketch_path = mock.Mock(return_value=Path("missing.pdf"))
        app.output_dirs_for_order = mock.Mock(return_value=(Path("run"), Path("sketches"), Path("programs"), Path("reports")))
        aw_orders = [f"239{index:03d}" for index in range(120)]
        app.generated_sketch_paths_for_orders(aw_orders, Path("output"))
        self.assertEqual(app.load_processing_history_for_output.call_count, 1)
        app.load_processing_history_for_output.reset_mock()
        app.generated_dxf_paths_for_orders(aw_orders, Path("output"))
        self.assertEqual(app.load_processing_history_for_output.call_count, 1)

    def test_batch_history_writer_uses_explicit_output_snapshot(self) -> None:
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        app.output_dir_var = _ExplodingVar()
        result = SimpleNamespace(status="OK", aw_order="239190", delivery_date="09/30/2026", output_pdf=None, report_path=None, remake_items=None)
        run = SimpleNamespace(results=[result])
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            app.update_processing_history(run, output_dir, "2026-09-30 10:00:00", output_dir / "Runs" / "1", None, False, False)
            saved = json.loads((output_dir / "processing_history.json").read_text(encoding="utf-8"))
            self.assertIn("239190", saved["orders"])

    def test_network_worker_slots_refuse_unbounded_thread_creation(self) -> None:
        class NoSlots:
            def acquire(self, blocking=False):
                self.blocking = blocking
                return False
            def release(self):
                raise AssertionError("a slot that was never acquired must not be released")
        ran = []
        with mock.patch.object(gui.ShowerProgrammerApp, "_NETWORK_IO_THREAD_SLOTS", NoSlots()):
            started = gui.ShowerProgrammerApp.start_bounded_network_thread(lambda: ran.append(True), name="v190-capacity-test")
        self.assertFalse(started)
        self.assertEqual(ran, [])

    def test_network_timeout_helpers_use_bounded_worker_slots(self) -> None:
        source = (BACKEND / "shower_programmer_gui.py").read_text(encoding="utf-8")
        for method_name in ("index_import_source_folder_bounded", "matching_order_files_bounded", "existing_paths_bounded", "delete_import_paths_bounded"):
            start = source.index(f"    def {method_name}")
            end = source.find("\n    @", start + 8)
            body = source[start: end if end != -1 else len(source)]
            self.assertIn("start_bounded_network_thread", body, method_name)

    def test_retained_release_tests_do_not_pin_historical_current_version(self) -> None:
        pinned: list[str] = []
        pattern = re.compile(r'assertEqual\(version\["version_number"\],\s*(\d+)\)')
        for path in sorted((ROOT / "tests").glob("test_v*.py")):
            matches = pattern.findall(path.read_text(encoding="utf-8"))
            if matches:
                pinned.append(f"{path.name}: {', '.join(matches)}")
        self.assertEqual(pinned, [])

    def test_version_190_release_metadata_and_flags(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 190)
        features = (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8")
        self.assertIn("VERSION_1_90_THREAD_SAFE_BACKGROUND_HANDOFFS", features)
        flags = (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8")
        for flag in ("thread_safe_ui_callback_queue", "managed_task_terminal_handoff_guard", "background_history_path_isolation", "batch_history_single_read", "bounded_network_worker_slots", "version_1_90_thread_safe_background_handoffs"):
            self.assertIn(flag, flags)
        self_test = (BACKEND / "shower_programmer_gui.py").read_text(encoding="utf-8")
        for flag in ("thread_safe_ui_callback_queue", "managed_task_terminal_handoff_guard", "background_history_path_isolation", "batch_history_single_read", "bounded_network_worker_slots", "version_1_90_thread_safe_background_handoffs"):
            self.assertIn(f'"{flag}": True', self_test)


if __name__ == "__main__":
    unittest.main()
