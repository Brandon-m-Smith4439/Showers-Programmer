from __future__ import annotations

import json
import shutil
import sys
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

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


class ReimportedBatchReactivationTests(unittest.TestCase):
    @staticmethod
    def order(aw_order: str = "900001") -> shower_batch.ProcessOrder:
        order = shower_batch.ProcessOrder(aw_order, "12345678 REIMPORT TEST", "Customer")
        order.items[1] = shower_batch.ProcessItem(1, width_text='30"', height_text='80"')
        return order

    def test_reimported_batch_clears_only_matching_deleted_receipt(self) -> None:
        with writable_test_directory() as temp:
            output = temp / "Output"
            local_lists = temp / "Input" / "Process List"
            local_lists.mkdir(parents=True)
            batch_path = local_lists / "Batch 7000.xlsx"
            batch_path.write_bytes(b"placeholder")
            copied_source = local_lists / "Batch 7000.xls"
            copied_source.write_bytes(b"placeholder")
            order = self.order()
            signature = gui.ShowerProgrammerApp.sent_process_signature(order)
            history = {
                "orders": {
                    "900001": {
                        "deleted_at": "2026-08-13 09:00:00",
                        "deleted_process_signature": signature,
                    },
                    "900002": {
                        "deleted_at": "2026-08-13 09:01:00",
                        "deleted_process_signature": "other-signature",
                    },
                }
            }
            gui.ShowerProgrammerApp.save_processing_history_for_output(output, history)

            reactivated = gui.ShowerProgrammerApp.reactivate_reimported_process_list_orders(
                [{"path": batch_path, "orders": [order]}],
                [copied_source],
                output,
            )

            self.assertEqual(reactivated, ["900001"])
            saved = gui.ShowerProgrammerApp.load_processing_history_for_output(output)
            first = saved["orders"]["900001"]
            self.assertNotIn("deleted_at", first)
            self.assertNotIn("deleted_process_signature", first)
            self.assertEqual(first["reactivated_source"], batch_path.name)
            self.assertEqual(first["reactivated_from_deleted_at"], "2026-08-13 09:00:00")
            self.assertIn("reactivated_at", first)
            self.assertIn("deleted_at", saved["orders"]["900002"])

    def test_reimported_batch_preserves_sent_receipt(self) -> None:
        with writable_test_directory() as temp:
            output = temp / "Output"
            batch_path = temp / "Batch 7100.xlsx"
            batch_path.write_bytes(b"placeholder")
            order = self.order("900010")
            signature = gui.ShowerProgrammerApp.sent_process_signature(order)
            history = {
                "orders": {
                    "900010": {
                        "sent_at": "2026-08-13 08:00:00",
                        "sent_process_signature": signature,
                        "deleted_at": "2026-08-13 09:00:00",
                        "deleted_process_signature": signature,
                    }
                }
            }
            gui.ShowerProgrammerApp.save_processing_history_for_output(output, history)

            gui.ShowerProgrammerApp.reactivate_reimported_process_list_orders(
                [{"path": batch_path, "orders": [order]}],
                [batch_path],
                output,
            )

            saved = gui.ShowerProgrammerApp.load_processing_history_for_output(output)
            entry = saved["orders"]["900010"]
            self.assertEqual(entry["sent_at"], "2026-08-13 08:00:00")
            self.assertEqual(entry["sent_process_signature"], signature)
            self.assertNotIn("deleted_at", entry)
            self.assertTrue(gui.ShowerProgrammerApp.order_is_terminal_in_history(order, saved))

    def test_reactivated_deleted_batch_is_not_immediately_retired_again(self) -> None:
        with writable_test_directory() as temp:
            order_folder = temp / "Input" / "Orders"
            process_root = temp / "Input" / "Process List"
            output = temp / "Output"
            order_folder.mkdir(parents=True)
            process_root.mkdir(parents=True)
            batch_path = process_root / "Batch 7200.xlsx"
            batch_path.write_bytes(b"placeholder")
            order = self.order("900020")
            signature = gui.ShowerProgrammerApp.sent_process_signature(order)
            gui.ShowerProgrammerApp.save_processing_history_for_output(
                output,
                {
                    "orders": {
                        "900020": {
                            "deleted_at": "2026-08-13 09:00:00",
                            "deleted_process_signature": signature,
                        }
                    }
                },
            )
            batches = [{"id": "batch-7200", "path": batch_path, "orders": [order]}]

            before = gui.ShowerProgrammerApp.completed_process_list_batches_from_history(
                batches,
                order_folder,
                output,
            )
            self.assertEqual(len(before), 1)

            gui.ShowerProgrammerApp.reactivate_reimported_process_list_orders(
                batches,
                [batch_path],
                output,
            )
            after = gui.ShowerProgrammerApp.completed_process_list_batches_from_history(
                batches,
                order_folder,
                output,
            )
            self.assertEqual(after, [])

    def test_unrelated_copied_batch_does_not_clear_deleted_receipt(self) -> None:
        with writable_test_directory() as temp:
            output = temp / "Output"
            batch_path = temp / "Batch 7300.xlsx"
            copied_path = temp / "Batch 7400.xlsx"
            batch_path.write_bytes(b"placeholder")
            copied_path.write_bytes(b"placeholder")
            order = self.order("900030")
            signature = gui.ShowerProgrammerApp.sent_process_signature(order)
            gui.ShowerProgrammerApp.save_processing_history_for_output(
                output,
                {
                    "orders": {
                        "900030": {
                            "deleted_at": "2026-08-13 09:00:00",
                            "deleted_process_signature": signature,
                        }
                    }
                },
            )

            reactivated = gui.ShowerProgrammerApp.reactivate_reimported_process_list_orders(
                [{"path": batch_path, "orders": [order]}],
                [copied_path],
                output,
            )

            self.assertEqual(reactivated, [])
            saved = gui.ShowerProgrammerApp.load_processing_history_for_output(output)
            self.assertIn("deleted_at", saved["orders"]["900030"])


if __name__ == "__main__":
    unittest.main()
