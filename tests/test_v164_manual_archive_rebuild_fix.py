from __future__ import annotations

import inspect
import json
import sys
import unittest
from types import SimpleNamespace
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_batch
import shower_programmer_gui as gui
from shower_temp import workspace_temporary_directory
import shower_v4_features


class ManualArchiveRebuildFixTests(unittest.TestCase):
    def test_order_archive_retires_manual_process_record(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.archive_sent_order_inputs)
        self.assertIn("output_dir = Path(self.output_dir_var.get()).resolve()", source)
        self.assertIn("self.archive_manual_process_orders_for_output", source)
        self.assertIn("manual_archives", source)

    def test_batch_archive_retires_manual_process_record(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.archive_sent_batch_inputs)
        self.assertIn("output_dir = Path(self.output_dir_var.get()).resolve()", source)
        self.assertIn("self.archive_manual_process_orders_for_output", source)
        self.assertIn("manual_archives", source)

    def test_manual_order_stays_retired_after_archive_action(self) -> None:
        with workspace_temporary_directory() as temp_text:
            temp = Path(temp_text)
            order_dir = temp / "Input" / "Orders"
            process_dir = temp / "Input" / "Process List"
            output_dir = temp / "Output"
            order_dir.mkdir(parents=True)
            process_dir.mkdir(parents=True)
            output_dir.mkdir(parents=True)

            order = shower_batch.ProcessOrder("239094", "90027720M.2 3107 CLOVERFIELD", "CUSTOMER")
            order.items[1] = shower_batch.ProcessItem(item=1, machine_hints=["WJ"])
            setattr(order, "manual_process_order", True)
            gui.ShowerProgrammerApp.save_manual_process_orders_for_output(output_dir, [order])

            app = object.__new__(gui.ShowerProgrammerApp)
            app.root = mock.Mock()
            app.operation_active = mock.Mock(return_value=False)
            app.load_processing_history_for_output = mock.Mock(return_value={"orders": {}})
            app.folder_var = mock.Mock(get=lambda: str(order_dir))
            app.process_list_var = mock.Mock(get=lambda: str(process_dir))
            app.output_dir_var = mock.Mock(get=lambda: str(output_dir))
            app.sent_orders_for_input_archive_context = mock.Mock(return_value=[order])
            app.archive_sent_input_files_for_orders = mock.Mock(return_value=([], []))
            app.refresh_local_orders = mock.Mock()
            app.show_themed_notice = mock.Mock()
            app.show_structured_error = mock.Mock()

            def run_task(_title, worker, **kwargs):
                payload = worker(SimpleNamespace(progress=lambda *_args, **_kwargs: None, check_cancelled=lambda: None))
                kwargs["on_done"](payload)

            app.run_managed_task = run_task

            with mock.patch.object(gui.messagebox, "askyesno", return_value=True):
                app.archive_sent_order_inputs([order])

            self.assertEqual(gui.ShowerProgrammerApp.load_manual_process_orders_for_output(output_dir), [])
            archive_path = gui.ShowerProgrammerApp.manual_process_archive_path(output_dir)
            self.assertTrue(archive_path.exists())
            archived_payload = json.loads(archive_path.read_text(encoding="utf-8"))
            archived = shower_batch.process_orders_from_cache(archived_payload["orders"] )
            self.assertEqual([item.aw_order for item in archived], ["239094"])

    def test_integrated_selftest_accepts_current_mirror_retention(self) -> None:
        source = (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8")
        self.assertIn('["900001", "900002"]', source)
        self.assertIn("Mirror - With Fabrication", source)
        self.assertIn("Mirror - Without Fabrication", source)
        self.assertIn("include_non_waterjet_mirror=False", source)
        self.assertNotIn("Mirror batches are not scoped to Waterjet-routed orders.", source)

    def test_version_164_release_marker_is_retained(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        marker = "VERSION_1_64_MANUAL_ARCHIVE_REBUILD_FIX"
        self.assertGreaterEqual(version["version_number"], 164)
        self.assertIn(marker, (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8"))
        flags = (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8")
        self.assertIn("manual_archive_retirement", flags)
        self.assertIn("mirror_selftest_current_scope", flags)
        self.assertIn("version_1_64_manual_archive_rebuild_fix", flags)


if __name__ == "__main__":
    unittest.main()
