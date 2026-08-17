from __future__ import annotations

import inspect
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


def order(aw_order: str) -> shower_batch.ProcessOrder:
    value = shower_batch.ProcessOrder(aw_order=aw_order, job_name="89183226 KINSDALE 132")
    value.items[1] = shower_batch.ProcessItem(1, width_text='15-31/32"', height_text='46-11/32"')
    return value


class Version108ArchiveBatchStatusDeleteRefreshTests(unittest.TestCase):
    def test_archive_batch_sent_summary_reports_single_date_range_and_partial(self) -> None:
        summarize = gui.ShowerProgrammerApp.archive_batch_sent_summary
        self.assertEqual(summarize([{"_sent_at": ""}]), "No")
        self.assertEqual(
            summarize([
                {"_sent_at": "2026-08-12 08:00:00"},
                {"_sent_at": "2026-08-12 14:00:00"},
            ]),
            "Sent 08/12/26",
        )
        self.assertEqual(
            summarize([
                {"_sent_at": "2026-08-10 08:00:00"},
                {"_sent_at": "2026-08-14 14:00:00"},
            ]),
            "Sent 08/10/26-08/14/26",
        )
        self.assertEqual(
            summarize([
                {"_sent_at": "2026-08-14 14:00:00"},
                {"_sent_at": ""},
            ]),
            "Partial 1/2 08/14/26",
        )

    def test_archive_batch_input_summary_reports_partial_state(self) -> None:
        summarize = gui.ShowerProgrammerApp.archive_batch_input_summary
        self.assertEqual(summarize([{"_active_copy": True}, {"_active_copy": True}]), "Yes")
        self.assertEqual(summarize([{"_active_copy": False}, {"_active_copy": False}]), "No")
        self.assertEqual(summarize([{"_active_copy": True}, {"_active_copy": False}]), "Partial 1/2")

    def test_individual_delete_receipt_is_not_reactivated_by_batch_reimport(self) -> None:
        with writable_test_directory() as temp:
            output = temp / "Output"
            batch_path = temp / "Batch 8000.xlsx"
            batch_path.write_bytes(b"placeholder")
            deleted_order = order("236465")
            gui.ShowerProgrammerApp.mark_orders_deleted_for_output(
                [deleted_order],
                output,
                deletion_scope_by_aw={"236465": "order"},
            )

            reactivated = gui.ShowerProgrammerApp.reactivate_reimported_process_list_orders(
                [{"path": batch_path, "orders": [deleted_order]}],
                [batch_path],
                output,
            )

            self.assertEqual(reactivated, [])
            saved = gui.ShowerProgrammerApp.load_processing_history_for_output(output)
            self.assertEqual(saved["orders"]["236465"]["deleted_scope"], "order")
            self.assertIn("deleted_at", saved["orders"]["236465"])

    def test_full_batch_delete_receipt_can_reactivate_after_batch_reimport(self) -> None:
        with writable_test_directory() as temp:
            output = temp / "Output"
            batch_path = temp / "Batch 8100.xlsx"
            batch_path.write_bytes(b"placeholder")
            first = order("236470")
            second = order("236471")
            gui.ShowerProgrammerApp.mark_orders_deleted_for_output(
                [first, second],
                output,
                deletion_scope_by_aw={"236470": "batch", "236471": "batch"},
            )

            reactivated = gui.ShowerProgrammerApp.reactivate_reimported_process_list_orders(
                [{"path": batch_path, "orders": [first, second]}],
                [batch_path],
                output,
            )

            self.assertEqual(set(reactivated), {"236470", "236471"})
            saved = gui.ShowerProgrammerApp.load_processing_history_for_output(output)
            self.assertNotIn("deleted_at", saved["orders"]["236470"])
            self.assertNotIn("deleted_scope", saved["orders"]["236470"])

    def test_successful_delete_schedules_local_only_refresh(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.apply_local_order_delete_result)
        self.assertIn('self.status_var.set("Order cleanup complete. Refreshing local Input folders only...")', source)
        self.assertIn("self.root.after(100, self.refresh_local_orders)", source)
        self.assertNotIn("self.root.after(100, self.scan_orders)", source)

    def test_kinsdale_numeric_difference_explains_why_generic_match_fails(self) -> None:
        process_order = order("236465")
        message = shower_batch.dimension_mismatch_message(
            process_order,
            Path("Glass Order PULTE_89183226 KINSDALE 132.pdf"),
            [(1, 15.75, 46.375)],
        )
        self.assertIn("NUMERIC DIFFERENCE", message)
        self.assertIn("width difference 0.2188 in", message)
        self.assertIn("height difference 0.0312 in", message)
        self.assertIn("normal tolerance 0.2000 in", message)
        self.assertIn("width exceeds tolerance by 0.0187 in", message)

    def test_archive_parent_rows_use_batch_sent_and_input_summaries(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.build_archive_settings_tab)
        self.assertIn("self.archive_batch_sent_summary(batch_entries)", source)
        self.assertIn("self.archive_batch_input_summary(batch_entries)", source)


if __name__ == "__main__":
    unittest.main()
