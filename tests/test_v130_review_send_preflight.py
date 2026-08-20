from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_batch
import shower_v4_features
from shower_programmer_gui import ShowerProgrammerApp


class ReviewSendPreflightTests(unittest.TestCase):
    def test_review_send_route_starts_managed_preflight(self) -> None:
        order = shower_batch.ProcessOrder("237715", "90000001 MIRROR JOB", "Mirror")
        app = ShowerProgrammerApp.__new__(ShowerProgrammerApp)
        app.is_busy = False
        app.output_dir_var = SimpleNamespace(get=lambda: str(ROOT / "Output"))
        app.folder_var = SimpleNamespace(get=lambda: str(ROOT / "Input" / "Orders"))
        app.process_list_var = SimpleNamespace(get=lambda: str(ROOT / "Input" / "Process List"))
        app.order_by_aw = {"237715": order}
        app.focus_existing_page_window = mock.Mock(return_value=False)
        app.apply_import_source_dir = mock.Mock()
        app.selected_or_visible_aw_orders = mock.Mock(return_value=["237715"])
        app.run_managed_task = mock.Mock(return_value=True)
        app.progress = mock.Mock()

        app.send_outputs_to_shop(
            include_sketches=True,
            include_programs=True,
            archive_inputs=True,
            review_before_send=True,
        )

        app.run_managed_task.assert_called_once()
        args, kwargs = app.run_managed_task.call_args
        self.assertEqual(args[0], "Prepare Review / Send")
        self.assertEqual(kwargs["total"], 4)
        self.assertTrue(kwargs["cancellable"])
        self.assertIs(kwargs["on_done"].__func__, ShowerProgrammerApp.apply_review_send_preparation)

    def test_worker_resolves_only_requested_output_types(self) -> None:
        output = ROOT / "tests" / "_verification" / "v130-review-send"
        sketch = output / "Sketches" / "237715.pdf"
        dxf = output / "Programs" / "23771501.dxf"
        order = shower_batch.ProcessOrder("237715", "90000001 MIRROR JOB", "Mirror")
        app = ShowerProgrammerApp.__new__(ShowerProgrammerApp)
        app.generated_sketch_paths_for_orders = mock.Mock(return_value=[sketch])
        app.generated_dxf_paths_for_orders = mock.Mock(return_value=[dxf])
        task = mock.Mock()

        result = app.worker_prepare_review_send(
            output,
            True,
            True,
            True,
            ["237715"],
            [order],
            ROOT / "Input" / "Orders",
            ROOT / "Input" / "Process List",
            task_context=task,
        )

        self.assertEqual(result["sketch_paths"], [sketch])
        self.assertEqual(result["dxf_paths"], [dxf])
        self.assertEqual(result["missing"], [])
        self.assertEqual(task.progress.call_count, 4)
        task.check_cancelled.assert_called_once()

    def test_send_worker_starts_before_folder_or_route_validation(self) -> None:
        output = ROOT / "tests" / "_verification" / "v130-send-start"
        order = shower_batch.ProcessOrder("237715", "90000001 MIRROR JOB", "Mirror")
        app = ShowerProgrammerApp.__new__(ShowerProgrammerApp)
        app.output_dir_var = SimpleNamespace(get=lambda: str(output))
        app.editable_config_path = mock.Mock(return_value=ROOT / "Backend" / "shower_programmer_config.json")
        app.ensure_workflow_folders = mock.Mock(
            side_effect=AssertionError("folder validation must execute inside the worker")
        )
        app.run_managed_task = mock.Mock(return_value=True)
        app.record_action = mock.Mock()

        started = app.start_send_outputs_worker(
            [output / "Sketches" / "237715.pdf"],
            [output / "Programs" / "23771501.dxf"],
            [],
            True,
            [order],
            ROOT / "Input" / "Orders",
            ROOT / "Input" / "Process List",
            include_sketches=True,
            include_programs=True,
        )

        self.assertTrue(started)
        app.ensure_workflow_folders.assert_not_called()
        app.run_managed_task.assert_called_once()
        self.assertEqual(app.run_managed_task.call_args.args[0], "Send Output")
        app.record_action.assert_called_once()

    def test_production_conflict_check_has_a_hard_timeout(self) -> None:
        output = ROOT / "tests" / "_verification" / "v130-conflict-timeout"
        source = output / "source" / "237715.pdf"
        target_dir = output / "production"
        source.parent.mkdir(parents=True, exist_ok=True)
        target_dir.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b"source")
        (target_dir / source.name).write_bytes(b"target")

        with mock.patch.object(shower_v4_features, "files_are_identical", side_effect=lambda *_args: __import__("time").sleep(0.2)):
            with self.assertRaisesRegex(TimeoutError, "Production-file conflict check timed out"):
                shower_v4_features.find_send_conflicts(
                    [source],
                    [],
                    target_dir,
                    target_dir,
                    timeout_seconds=0.05,
                )

    def test_release_wrapper_defers_production_conflict_discovery(self) -> None:
        output = ROOT / "tests" / "_verification" / "v130-wrapper"
        app = SimpleNamespace(
            SHOP_SKETCHES_DIR=output / "shop-sketches",
            SHOP_PROGRAMS_DIR=output / "shop-programs",
            run_managed_task=mock.Mock(return_value=True),
        )
        original_start = mock.Mock(return_value=True)

        with mock.patch.object(
            shower_v4_features,
            "find_send_conflicts",
            side_effect=AssertionError("conflict discovery must not run on the button thread"),
        ):
            started = shower_v4_features._start_send_outputs_worker(
                app,
                [output / "237715.pdf"],
                [output / "23771501.dxf"],
                [],
                True,
                [shower_batch.ProcessOrder("237715", "90000001 MIRROR JOB", "Mirror")],
                ROOT / "Input" / "Orders",
                ROOT / "Input" / "Process List",
                include_sketches=True,
                include_programs=True,
                gui=SimpleNamespace(),
                original_start=original_start,
            )

        self.assertTrue(started)
        app.run_managed_task.assert_called_once()
        self.assertEqual(app.run_managed_task.call_args.args[0], "Prepare Send Output")
        original_start.assert_not_called()


if __name__ == "__main__":
    unittest.main()
