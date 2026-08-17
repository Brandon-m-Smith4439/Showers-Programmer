from __future__ import annotations

import shutil
import sys
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

import shower_batch
import shower_programmer_gui as gui
import shower_state


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


def archive_entry(root: Path, aw_order: str, job_name: str, batch_file: Path) -> dict[str, object]:
    order = shower_batch.ProcessOrder(aw_order, job_name, "TEST CUSTOMER")
    order.items[1] = shower_batch.ProcessItem(1, width_text='30"', height_text='80"')
    source = root / f"{job_name}_1.dxf"
    source.write_text("0\nEOF\n", encoding="ascii")
    return {
        "archive_name": "08.13.26",
        "batch_name": batch_file.name,
        "batch_key": "test-batch-key",
        "order": order,
        "order_files": [source],
        "process_list_files": [batch_file],
        "order_archive_dir": root,
    }


class Version099VisualBatchArchiveTests(unittest.TestCase):
    def test_archive_action_entries_support_order_and_batch_rows(self) -> None:
        with writable_test_directory() as temp:
            batch = temp / "Batch 9000.xlsx"
            batch.write_bytes(b"batch")
            first = archive_entry(temp, "900001", "10000001 TEST A", batch)
            second = archive_entry(temp, "900002", "10000002 TEST B", batch)

            self.assertEqual(gui.ShowerProgrammerApp.archive_action_entries(first), [first])
            self.assertEqual(
                gui.ShowerProgrammerApp.archive_action_entries({"kind": "batch", "children": [first, second]}),
                [first, second],
            )

    def test_batch_restore_copies_all_order_files_and_original_process_list(self) -> None:
        with writable_test_directory() as temp:
            archive = temp / "archive"
            active_orders = temp / "Input" / "Orders"
            active_process = temp / "Input" / "Process List"
            archive.mkdir()
            batch = archive / "Batch 9000.xlsx"
            batch.write_bytes(b"original batch process list")
            first = archive_entry(archive, "900001", "10000001 TEST A", batch)
            second = archive_entry(archive, "900002", "10000002 TEST B", batch)

            restored, process_files, warnings = gui.ShowerProgrammerApp.copy_archived_batch_for_testing(
                [first, second],
                active_orders,
                active_process,
            )

            self.assertEqual(warnings, [])
            self.assertEqual({path.name for path in restored}, {"10000001 TEST A_1.dxf", "10000002 TEST B_1.dxf"})
            self.assertEqual([path.name for path in process_files], [batch.name])
            self.assertEqual((active_process / batch.name).read_bytes(), batch.read_bytes())
            self.assertTrue(batch.exists(), "Restoring a batch must never remove the dated archive process list.")

    def test_batch_test_mode_uses_one_isolated_workspace_and_marks_all_orders_testing(self) -> None:
        with writable_test_directory() as temp:
            archive = temp / "archive"
            archive.mkdir()
            batch = archive / "Batch 9000.xlsx"
            batch.write_bytes(b"batch")
            entries = [
                archive_entry(archive, "900001", "10000001 TEST A", batch),
                archive_entry(archive, "900002", "10000002 TEST B", batch),
            ]
            app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
            app.runtime_root = temp
            app.folder_var = SimpleVar(str(temp / "production" / "Input" / "Orders"))
            app.process_list_var = SimpleVar(str(temp / "production" / "Input" / "Process List"))
            app.output_dir_var = SimpleVar(str(temp / "production" / "Output"))
            app.status_var = SimpleVar("")
            app.test_mode_workspace = None
            app._production_paths_before_test = None

            workspace, warnings = app.enter_test_mode_batch(
                entries,
                batch_name=batch.name,
                archive_name="08.13.26",
            )

            self.assertEqual(warnings, [])
            self.assertTrue(workspace.is_dir())
            self.assertEqual(Path(app.folder_var.get()), workspace / "Input" / "Orders")
            self.assertEqual(Path(app.process_list_var.get()), workspace / "Input" / "Process List")
            self.assertEqual(Path(app.output_dir_var.get()), workspace / "Output")
            store = shower_state.StateStore.for_output(workspace / "Output")
            self.assertEqual(store.order_state("900001")["lifecycle_state"], shower_state.LifecycleState.TESTING)
            self.assertEqual(store.order_state("900002")["lifecycle_state"], shower_state.LifecycleState.TESTING)
            self.assertIn("2 order(s)", app.status_var.get())

    def test_network_input_quick_access_is_available_from_main_and_settings(self) -> None:
        source = (ROOT / "Backend" / "shower_programmer_gui.py").read_text(encoding="utf-8")
        self.assertIn('"Network Input"', source)
        self.assertIn("def open_network_input_folder", source)
        self.assertIn('"Open Network Input"', source)
        self.assertIn('"network_folder"', source)

    def test_visual_polish_raises_table_density_and_archive_batch_actions(self) -> None:
        source = (ROOT / "Backend" / "shower_programmer_gui.py").read_text(encoding="utf-8")
        self.assertIn("rowheight=38", source)
        self.assertIn('text="Batch Test Mode"', source)
        self.assertIn('text="Restore Batch"', source)
        self.assertIn('text="Return Batch"', source)
        self.assertIn("copy_archived_batch_for_testing", source)
        self.assertIn('"Restore Archived Batch"', source)
        self.assertIn('"Prepare Batch Test Mode"', source)
        self.assertIn('"Return Archived Batch"', source)
        self.assertIn("task_context=task", source)


if __name__ == "__main__":
    unittest.main()
