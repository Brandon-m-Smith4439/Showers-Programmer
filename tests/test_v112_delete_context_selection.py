from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_batch
import shower_programmer_gui as gui
from shower_temp import workspace_temporary_directory


class _Var:
    def __init__(self, value: str) -> None:
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


class _ExplodingTree:
    def selection(self):
        raise AssertionError("context-snapshot delete must not reread Treeview selection")


class _DeferredParent:
    def __init__(self) -> None:
        self.after_calls: list[tuple[int, object]] = []

    def after(self, delay_ms: int, callback):
        self.after_calls.append((delay_ms, callback))
        return "after-id"


class Version112DeleteContextSelectionTests(unittest.TestCase):
    def make_app(self, order: shower_batch.ProcessOrder):
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        app.is_busy = False
        app.status_var = _Var("")
        app.tree = _ExplodingTree()
        app.process_batches = {}
        app.order_batch_ids = {str(order.aw_order): ["input-only"]}
        app.run_managed_task = mock.Mock(return_value=True)
        app.show_structured_error = mock.Mock()
        app.root = object()
        return app

    def test_context_snapshot_delete_never_rereads_tree_selection(self) -> None:
        order = shower_batch.ProcessOrder("INPUT-112", "89620942 NUTHATCH", "Input file only")
        setattr(order, "process_list_missing", True)
        app = self.make_app(order)

        with workspace_temporary_directory() as temp_dir:
            root = Path(temp_dir)
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

            app.delete_order_inputs((order,), frozenset(), include_network=False)

        app.run_managed_task.assert_called_once()
        self.assertIn("Delete requested for 1 order", app.status_var.get())
        args, kwargs = app.run_managed_task.call_args
        self.assertEqual(args[0], "Prepare Order Cleanup")
        self.assertIn("selected order cleanup", kwargs["message"].lower())

    def test_context_action_runs_before_popup_destruction_is_deferred(self) -> None:
        parent = _DeferredParent()
        events: list[str] = []

        gui.ShowerProgrammerApp.dispatch_context_menu_action(
            parent,
            lambda: events.append("command"),
            lambda: events.append("hide"),
            lambda: events.append("destroy"),
        )

        self.assertEqual(events, ["hide", "command"])
        self.assertEqual(len(parent.after_calls), 1)
        delay_ms, callback = parent.after_calls[0]
        self.assertEqual(delay_ms, 20)
        callback()
        self.assertEqual(events, ["hide", "command", "destroy"])

    def test_context_action_exception_is_reported_instead_of_disappearing(self) -> None:
        parent = _DeferredParent()
        errors: list[BaseException] = []

        def fail() -> None:
            raise RuntimeError("simulated delete entry failure")

        gui.ShowerProgrammerApp.dispatch_context_menu_action(
            parent,
            fail,
            lambda: None,
            lambda: None,
            on_error=errors.append,
        )

        self.assertEqual(len(errors), 1)
        self.assertIn("simulated delete entry failure", str(errors[0]))

    def test_single_input_only_order_allows_local_and_network_delete(self) -> None:
        input_only = shower_batch.ProcessOrder("INPUT-112", "89620942 NUTHATCH", "Input file only")
        setattr(input_only, "process_list_missing", True)
        normal = shower_batch.ProcessOrder("236465", "89183226 KINSDALE 132", "PULTE")

        self.assertTrue(gui.ShowerProgrammerApp.orders_allow_network_input_delete([input_only]))
        self.assertFalse(gui.ShowerProgrammerApp.orders_allow_network_input_delete([normal]))
        self.assertFalse(gui.ShowerProgrammerApp.orders_allow_network_input_delete([input_only, normal]))

    def test_orders_context_menu_captures_delete_selection_before_popup_retirement(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.open_orders_context_menu)
        self.assertIn("selected_order_snapshot = tuple(selected_orders)", source)
        self.assertIn("selected_batch_snapshot = frozenset", source)
        self.assertIn("self.delete_order_inputs(", source)
        self.assertIn('network_action_text = "Delete Local + Network Input Files"', source)


if __name__ == "__main__":
    unittest.main()
