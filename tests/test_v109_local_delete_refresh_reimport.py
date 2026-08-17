from __future__ import annotations

import inspect
import json
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


def make_order(aw_order: str = "236465") -> shower_batch.ProcessOrder:
    order = shower_batch.ProcessOrder(aw_order=aw_order, job_name="89183226 KINSDALE 132", customer="PULTE")
    order.items[1] = shower_batch.ProcessItem(1, width_text='15-31/32"', height_text='46-11/32"')
    return order


class Version109LocalDeleteRefreshReimportTests(unittest.TestCase):
    def test_delete_completion_refreshes_local_only_and_never_calls_scan_orders(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.apply_local_order_delete_result)
        self.assertIn("self.root.after(100, self.refresh_local_orders)", source)
        self.assertNotIn("self.root.after(100, self.scan_orders)", source)

    def test_local_refresh_worker_explicitly_skips_shared_network_paths(self) -> None:
        refresh_source = inspect.getsource(gui.ShowerProgrammerApp.refresh_local_orders)
        worker_source = inspect.getsource(gui.ShowerProgrammerApp.worker_scan_orders)
        self.assertIn("local_refresh_only=True", refresh_source)
        self.assertIn("if isolated_test_mode or local_refresh_only", worker_source)
        self.assertIn("LOCAL REFRESH: reading only local Input folders", worker_source)
        self.assertIn("LOCAL REFRESH: skipping production reconciliation", worker_source)

    def test_manual_scan_can_reactivate_single_deleted_order_when_shared_inputs_exist(self) -> None:
        with writable_test_directory() as temp:
            output = temp / "Output"
            local_orders = temp / "Input" / "Orders"
            local_orders.mkdir(parents=True)
            network_pdf = temp / "236465.pdf"
            network_dxf = temp / "236465_1.dxf"
            network_pdf.write_text("placeholder", encoding="utf-8")
            network_dxf.write_text("placeholder", encoding="utf-8")
            order = make_order()
            gui.ShowerProgrammerApp.mark_orders_deleted_for_output(
                [order],
                output,
                deletion_scope_by_aw={"236465": "order"},
            )

            with mock.patch.object(
                gui.ShowerProgrammerApp,
                "file_matches_missing_order_requirement",
                return_value=True,
            ), mock.patch.object(
                gui.programmer,
                "dxf_match_score",
                return_value=100.0,
            ):
                reactivated = gui.ShowerProgrammerApp.reactivate_deleted_orders_available_in_shared_input(
                    [{"path": temp / "Batch 9000.xlsx", "orders": [order]}],
                    {"order_files": [network_pdf, network_dxf]},
                    local_orders,
                    output,
                )

            self.assertEqual(reactivated, ["236465"])
            saved = gui.ShowerProgrammerApp.load_processing_history_for_output(output)
            entry = saved["orders"]["236465"]
            self.assertNotIn("deleted_at", entry)
            self.assertNotIn("deleted_process_signature", entry)
            self.assertNotIn("deleted_scope", entry)
            self.assertEqual(entry["reactivated_source"], "shared order input")

    def test_manual_scan_does_not_reactivate_current_signature_sent_order(self) -> None:
        with writable_test_directory() as temp:
            output = temp / "Output"
            local_orders = temp / "Input" / "Orders"
            local_orders.mkdir(parents=True)
            network_pdf = temp / "236465.pdf"
            network_dxf = temp / "236465_1.dxf"
            network_pdf.write_text("placeholder", encoding="utf-8")
            network_dxf.write_text("placeholder", encoding="utf-8")
            order = make_order()
            signature = gui.ShowerProgrammerApp.sent_process_signature(order)
            output.mkdir(parents=True, exist_ok=True)
            (output / "processing_history.json").write_text(
                json.dumps({
                    "orders": {
                        "236465": {
                            "sent_at": "2026-08-14 08:00:00",
                            "sent_process_signature": signature,
                            "deleted_at": "2026-08-14 08:30:00",
                            "deleted_process_signature": signature,
                            "deleted_scope": "order",
                        }
                    }
                }),
                encoding="utf-8",
            )

            with mock.patch.object(
                gui.ShowerProgrammerApp,
                "file_matches_missing_order_requirement",
                return_value=True,
            ), mock.patch.object(
                gui.programmer,
                "dxf_match_score",
                return_value=100.0,
            ):
                reactivated = gui.ShowerProgrammerApp.reactivate_deleted_orders_available_in_shared_input(
                    [{"path": temp / "Batch 9000.xlsx", "orders": [order]}],
                    {"order_files": [network_pdf, network_dxf]},
                    local_orders,
                    output,
                )

            self.assertEqual(reactivated, [])
            saved = gui.ShowerProgrammerApp.load_processing_history_for_output(output)
            self.assertIn("deleted_at", saved["orders"]["236465"])

    def test_manual_scan_reactivation_runs_before_completed_batch_retirement(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.worker_scan_orders)
        reactivate_at = source.index("reactivate_deleted_orders_available_in_shared_input")
        retire_at = source.index("completed_process_list_batches_from_history")
        self.assertLess(reactivate_at, retire_at)


if __name__ == "__main__":
    unittest.main()
