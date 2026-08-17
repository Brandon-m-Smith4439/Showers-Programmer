from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_batch
import shower_programmer_gui as gui


class _Var:
    def __init__(self, value: str) -> None:
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


class Version113DeleteScopeTypeSafetyTests(unittest.TestCase):
    def make_app(self, order: shower_batch.ProcessOrder):
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        app.is_busy = False
        app.status_var = _Var("")
        app.root = object()
        app.process_batches = {}
        app.order_batch_ids = {str(order.aw_order): ["input-only"]}
        app.run_managed_task = mock.Mock(return_value=True)
        app.show_structured_error = mock.Mock()
        return app

    def configure_paths(self, app, root: Path) -> None:
        order_dir = root / "Input" / "Orders"
        process_dir = root / "Input" / "Process List"
        output_dir = root / "Output"
        network_dir = root / "Network"
        for path in (order_dir, process_dir, output_dir, network_dir):
            path.mkdir(parents=True, exist_ok=True)
        app.folder_var = _Var(str(order_dir))
        app.process_list_var = _Var(str(process_dir))
        app.output_dir_var = _Var(str(output_dir))
        app.import_source_var = _Var(str(network_dir))

    def test_single_order_list_valued_batch_mapping_starts_delete(self) -> None:
        order = shower_batch.ProcessOrder("INPUT-113", "89620942 NUTHATCH", "Input file only")
        setattr(order, "process_list_missing", True)
        app = self.make_app(order)

        with tempfile.TemporaryDirectory() as temp_dir:
            self.configure_paths(app, Path(temp_dir))
            app.delete_order_inputs((order,), frozenset(), include_network=False)

        app.show_structured_error.assert_not_called()
        app.run_managed_task.assert_called_once()
        self.assertIn("Preparing local file cleanup", app.status_var.get())

    def test_batch_scope_checks_each_batch_id_in_order_mapping(self) -> None:
        order = shower_batch.ProcessOrder("236465", "89183226 KINSDALE 132", "PULTE")
        app = self.make_app(order)
        app.process_batches = {"batch-6151": {"orders": [order]}}
        app.order_batch_ids = {str(order.aw_order): ["older-revision", "batch-6151"]}
        captured: dict[str, str] = {}

        def capture_worker(*args, **kwargs):
            captured.update(kwargs.get("deletion_scope_by_aw") or {})
            return {}

        app.worker_prepare_local_order_delete = capture_worker

        def run_task(_name, worker, **_kwargs):
            worker(None)
            return True

        app.run_managed_task = mock.Mock(side_effect=run_task)

        with tempfile.TemporaryDirectory() as temp_dir:
            self.configure_paths(app, Path(temp_dir))
            app.delete_order_inputs((order,), frozenset({"batch-6151"}), include_network=False)

        app.show_structured_error.assert_not_called()
        self.assertEqual(captured.get("236465"), "batch")

    def test_order_scope_remains_order_when_no_mapped_batch_is_fully_selected(self) -> None:
        order = shower_batch.ProcessOrder("INPUT-113", "89620942 NUTHATCH", "Input file only")
        setattr(order, "process_list_missing", True)
        app = self.make_app(order)
        captured: dict[str, str] = {}

        def capture_worker(*args, **kwargs):
            captured.update(kwargs.get("deletion_scope_by_aw") or {})
            return {}

        app.worker_prepare_local_order_delete = capture_worker

        def run_task(_name, worker, **_kwargs):
            worker(None)
            return True

        app.run_managed_task = mock.Mock(side_effect=run_task)

        with tempfile.TemporaryDirectory() as temp_dir:
            self.configure_paths(app, Path(temp_dir))
            app.delete_order_inputs((order,), frozenset(), include_network=False)

        app.show_structured_error.assert_not_called()
        self.assertEqual(captured.get("INPUT-113"), "order")


if __name__ == "__main__":
    unittest.main()
