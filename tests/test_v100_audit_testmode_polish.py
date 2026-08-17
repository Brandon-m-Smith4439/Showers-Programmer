from __future__ import annotations

import queue
import shutil
import sys
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_batch
import shower_programmer_gui as gui


@contextmanager
def writable_test_directory():
    path = ROOT / "tmp" / "tests" / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


class SimpleVar:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = str(value)


def process_order(aw_order: str = "910001") -> shower_batch.ProcessOrder:
    order = shower_batch.ProcessOrder(aw_order, "10000001 TEST JOB", "TEST CUSTOMER")
    order.items[1] = shower_batch.ProcessItem(1, width_text='30"', height_text='80"')
    return order


class Version100AuditTestModePolishTests(unittest.TestCase):
    def test_scan_orders_passes_isolated_test_mode_to_worker_and_skips_network_setup(self) -> None:
        with writable_test_directory() as temp:
            app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
            app.is_busy = False
            app.test_mode_workspace = temp / "Test Workspace"
            app.test_mode_orders = [process_order()]
            app.folder_var = SimpleVar(str(temp / "Input" / "Orders"))
            app.process_list_var = SimpleVar(str(temp / "Input" / "Process List"))
            app.output_dir_var = SimpleVar(str(temp / "Output"))
            app.status_var = SimpleVar("")
            app.apply_import_source_dir = mock.Mock(side_effect=AssertionError("network setup must not run in Test Mode"))
            app.record_action = mock.Mock()
            app.worker_scan_orders = mock.Mock()
            captured: dict[str, object] = {}

            def run_managed_task(name, worker, **kwargs):
                captured["name"] = name
                captured["worker"] = worker
                captured["kwargs"] = kwargs
                return True

            app.run_managed_task = run_managed_task
            app.scan_orders()

            self.assertEqual(captured["name"], "Scan Orders")
            captured["worker"](mock.Mock())
            self.assertTrue(app.worker_scan_orders.call_args.kwargs["isolated_test_mode"])
            app.apply_import_source_dir.assert_not_called()
            self.assertIn("isolated Test Mode", captured["kwargs"]["message"])

    def test_worker_isolated_test_mode_does_not_touch_shared_or_production_sources(self) -> None:
        with writable_test_directory() as temp:
            folder = temp / "Input" / "Orders"
            process_dir = temp / "Input" / "Process List"
            output = temp / "Output"
            folder.mkdir(parents=True)
            process_dir.mkdir(parents=True)
            output.mkdir(parents=True)
            process_file = process_dir / "Batch 9100.xlsx"
            process_file.write_bytes(b"placeholder")
            order = process_order()
            batch = {"id": "batch", "path": process_file, "name": process_file.name, "orders": [order]}

            app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
            app.worker_queue = queue.Queue()
            app.queue_scan_progress = mock.Mock()
            app.config_with_manual_overrides = mock.Mock(return_value={})
            app.record_performance = mock.Mock()
            app.load_process_list_batches = mock.Mock(return_value=[batch])
            app.reactivate_reimported_process_list_orders = mock.Mock(side_effect=AssertionError("reactivation is production-only"))
            app.reconcile_orders_sent_from_production = mock.Mock(side_effect=AssertionError("production reconciliation is disabled"))
            app.prepare_import_source_snapshot = mock.Mock(side_effect=AssertionError("shared input must not be indexed"))
            app.copy_process_lists_from_import_folder = mock.Mock(side_effect=AssertionError("shared process lists must not be copied"))
            app.completed_process_list_batches_from_history = mock.Mock(side_effect=AssertionError("test scan must not retire production batches"))
            app.copy_edi_orders_for_process_orders = mock.Mock(side_effect=AssertionError("shared order files must not be copied"))
            app.copy_visible_import_order_files = mock.Mock(side_effect=AssertionError("shared visible files must not be copied"))
            app.clear_import_staging_folder = mock.Mock(side_effect=AssertionError("shared input cleanup must not run"))
            app.missing_order_input_requirements = mock.Mock(return_value={})
            app.filter_batches_to_local_inputs = mock.Mock(return_value=([batch], [order], 0))
            app.import_duplicate_groups = mock.Mock(return_value=[])
            app.duplicate_groups_by_order = mock.Mock(return_value={})
            app.input_only_orders_from_pdfs = mock.Mock(return_value=([], []))
            app.is_hardware_list_pdf = mock.Mock(return_value=False)

            with mock.patch.object(shower_batch, "process_list_files", return_value=[process_file]), mock.patch.object(
                shower_batch, "preview_orders", return_value=[]
            ):
                app.worker_scan_orders(folder, process_dir, output, isolated_test_mode=True)

            kind, payload = app.worker_queue.get_nowait()
            self.assertEqual(kind, "scan_done")
            self.assertTrue(payload["isolated_test_mode"])
            self.assertEqual(payload["orders"], [order])
            app.prepare_import_source_snapshot.assert_not_called()
            app.reconcile_orders_sent_from_production.assert_not_called()
            app.clear_import_staging_folder.assert_not_called()

    def test_batch_archive_actions_use_full_batch_even_when_visible_children_are_filtered(self) -> None:
        first = {"order": process_order("910001")}
        second = {"order": process_order("910002")}
        target = {
            "kind": "batch",
            "children": [first],
            "action_children": [first, second],
        }
        self.assertEqual(gui.ShowerProgrammerApp.archive_action_entries(target), [first, second])

    def test_action_history_filters_action_result_and_order_scope(self) -> None:
        event = {
            "action": "Delete Local Inputs",
            "status": "SUCCESS",
            "orders": ["910001"],
        }
        self.assertTrue(gui.ShowerProgrammerApp.action_history_filter_matches(event))
        self.assertTrue(
            gui.ShowerProgrammerApp.action_history_filter_matches(
                event,
                action_filter="Delete Local Inputs",
                status_filter="SUCCESS",
                orders_only=True,
            )
        )
        self.assertFalse(
            gui.ShowerProgrammerApp.action_history_filter_matches(
                event,
                action_filter="Send Output",
            )
        )
        self.assertFalse(
            gui.ShowerProgrammerApp.action_history_filter_matches(
                {"action": "Scan Orders", "status": "SUCCESS", "orders": []},
                orders_only=True,
            )
        )
        options = gui.ShowerProgrammerApp.action_history_action_options(
            [event, {"action": "Send Output"}, {"action": "Delete Local Inputs"}]
        )
        self.assertEqual(options, ["All Actions", "Delete Local Inputs", "Send Output"])

    def test_successful_local_delete_is_written_to_action_history(self) -> None:
        order = process_order()
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        app.tree_rows = {}
        app.tree_row_orders = {}
        app.tree_row_batches = {}
        app.batch_tree_rows = {}
        app.process_batches = {}
        app.order_batch_ids = {}
        app.order_by_aw = {order.aw_order: order}
        app.orders = [order]
        app.update_summary_strip = mock.Mock()
        app.status_var = SimpleVar("")
        app.root = None
        app.record_action = mock.Mock()
        payload = {
            "orders": [order],
            "successfully_deleted_orders": [order],
            "deleted": [Path("order.pdf")],
            "deleted_network": [],
            "deleted_process_lists": [],
            "completed_batches": [],
            "warnings": [],
            "include_network": False,
        }
        with mock.patch.object(gui.messagebox, "showinfo"):
            app.apply_local_order_delete_result(payload)
        app.record_action.assert_called_once()
        self.assertEqual(app.record_action.call_args.args[0], "Delete Local Inputs")
        self.assertEqual(app.record_action.call_args.kwargs["orders"], [order])

    def test_visual_header_borders_and_preferences_network_button_are_present(self) -> None:
        source = (BACKEND / "shower_programmer_gui.py").read_text(encoding="utf-8")
        self.assertIn('relief="raised"', source)
        self.assertIn('borderwidth=1', source)
        preferences = source[source.index("def build_preferences_settings_tab"):source.index("def build_folder_settings_tab")]
        self.assertIn('("Open Network Input", "network_folder", self.open_network_input_folder)', preferences)
        self.assertIn('action_filter_var = tk.StringVar(value="All Actions")', source)
        self.assertIn('status_filter_var = tk.StringVar(value="All Results")', source)


if __name__ == "__main__":
    unittest.main()
