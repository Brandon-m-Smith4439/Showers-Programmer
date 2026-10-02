from __future__ import annotations

import inspect
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_batch
import shower_programmer_gui as gui
from shower_temp import workspace_temporary_directory


class ArchiveRoundTripResponsivenessTests(unittest.TestCase):
    def test_restored_batch_registration_round_trips_by_active_process_key(self) -> None:
        app = object.__new__(gui.ShowerProgrammerApp)
        app.restored_archive_batch_returns = {}
        order = shower_batch.ProcessOrder("239337", "90000001 TEST", "CUSTOMER")
        entry = {
            "order": order,
            "archive_name": "Input Archive 2026-09-22",
            "order_archive_dir": Path("/archive/2026-09-22"),
        }
        active_process = Path("/input/process list/Batch 6200.xlsx")
        app.process_batches = {
            "batch-1": {
                "name": "Batch 6200.xlsx",
                "path": active_process,
                "orders": [order],
            }
        }
        app.order_batch_ids = {"239337": ["batch-1"]}

        app.register_restored_archive_batch("Batch 6200.xlsx", [active_process], [entry])

        restored = app.restored_archive_entries_for_batch("batch-1")
        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0]["order"].aw_order, "239337")
        self.assertEqual(app.restored_archive_batch_id_for_context(None, [order]), "batch-1")

        app.forget_restored_archive_batch("batch-1")
        self.assertEqual(app.restored_archive_entries_for_batch("batch-1"), [])


    def test_exact_batch_return_preserves_original_archive_and_removes_active_copies(self) -> None:
        with workspace_temporary_directory() as temp_text:
            temp = Path(temp_text)
            order_dir = temp / "Input" / "Orders"
            process_dir = temp / "Input" / "Process List"
            archive_dir = order_dir / "Archive 2026-09-22"
            process_archive_dir = process_dir / "Archive 2026-09-22"
            for directory in (order_dir, process_dir, archive_dir, process_archive_dir):
                directory.mkdir(parents=True, exist_ok=True)

            order = shower_batch.ProcessOrder("239337", "90000001 TEST", "CUSTOMER")
            archived_pdf = archive_dir / "239337.pdf"
            archived_dxf = archive_dir / "AW_239337_01.dxf"
            archived_process = process_archive_dir / "Batch 6200.xlsx"
            archived_pdf.write_bytes(b"pdf-source")
            archived_dxf.write_bytes(b"dxf-source")
            archived_process.write_bytes(b"process-source")
            (order_dir / archived_pdf.name).write_bytes(archived_pdf.read_bytes())
            (order_dir / archived_dxf.name).write_bytes(archived_dxf.read_bytes())
            (process_dir / archived_process.name).write_bytes(archived_process.read_bytes())

            entry = {
                "order": order,
                "archive_name": "Archive 2026-09-22",
                "order_archive_dir": archive_dir,
                "process_list_files": [archived_process],
            }
            returned, warnings = gui.ShowerProgrammerApp.return_archived_batch_to_archive(
                [entry], order_dir, process_dir
            )

            self.assertEqual(warnings, [])
            self.assertFalse((order_dir / archived_pdf.name).exists())
            self.assertFalse((order_dir / archived_dxf.name).exists())
            self.assertFalse((process_dir / archived_process.name).exists())
            self.assertEqual(archived_pdf.read_bytes(), b"pdf-source")
            self.assertEqual(archived_dxf.read_bytes(), b"dxf-source")
            self.assertEqual(archived_process.read_bytes(), b"process-source")
            self.assertTrue(returned)

    def test_context_menu_prefers_no_io_restored_batch_fast_path(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.open_orders_context_menu)
        restored_lookup = source.index("restored_archive_batch_id_for_context")
        history_lookup = source.index("archivable_batch_id_for_context")
        self.assertLess(restored_lookup, history_lookup)
        self.assertIn('"Return Restored Batch to Archive"', source)
        self.assertIn("self.return_restored_batch_inputs(selected_batch)", source)

    def test_restored_batch_return_runs_heavy_archive_work_in_managed_worker(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.return_restored_batch_inputs)
        worker_start = source.index("def worker(")
        managed_start = source.index("self.run_managed_task(")
        self.assertNotIn("return_archived_batch_to_archive(", source[:worker_start])
        self.assertIn("return_archived_batch_to_archive(", source[worker_start:managed_start])
        self.assertIn("task.check_cancelled()", source)
        self.assertIn('"Return Restored Batch"', source)
        self.assertIn("self.refresh_local_orders", source)

    def test_normal_sent_batch_archive_preflight_is_off_tk_thread(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.archive_sent_batch_inputs)
        worker_start = source.index("def worker(")
        before_worker = source[:worker_start]
        worker = source[worker_start:]
        self.assertNotIn("load_processing_history", before_worker)
        self.assertNotIn("completed_process_list_batches_for_orders", before_worker)
        self.assertNotIn("batch_is_ready_for_input_archive", before_worker)
        self.assertIn("load_processing_history_for_output", worker)
        self.assertIn("batch_is_ready_for_input_archive(batch, history)", worker)
        self.assertIn("completed_process_list_batches_for_orders(orders, history=history)", worker)
        self.assertIn("task.check_cancelled()", worker)

    def test_archive_restore_registers_exact_return_handoff_before_rescan(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.build_archive_settings_tab)
        register_index = source.index("self.register_restored_archive_batch(batch_name, process_files, entries)")
        scan_index = source.index("self.scan_orders()", register_index)
        self.assertLess(register_index, scan_index)

    def test_version_180_release_metadata(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 180)
        self.assertIn("VERSION_1_80_ARCHIVE_ROUNDTRIP_RESPONSIVENESS", (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8"))
        features = (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8")
        self.assertIn("VERSION_1_80_ARCHIVE_ROUNDTRIP_RESPONSIVENESS", features)
        flags = (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8")
        for flag in (
            "restored_batch_exact_archive_return",
            "archive_return_background_preflight",
            "restored_batch_context_fastpath",
            "version_1_80_archive_roundtrip_responsiveness",
        ):
            self.assertIn(flag, flags)


if __name__ == "__main__":
    unittest.main()
