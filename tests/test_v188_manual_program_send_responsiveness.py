from __future__ import annotations

import inspect
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_batch
import shower_programmer_gui as gui


class _Var:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


class _ContextTree:
    def __init__(self, row_id: str, selection: tuple[str, ...] = ()) -> None:
        self.row_id = row_id
        self._selection = list(selection)
        self.focused = ""

    def identify_row(self, _y: int) -> str:
        return self.row_id

    def selection(self) -> tuple[str, ...]:
        return tuple(self._selection)

    def selection_set(self, *row_ids: str) -> None:
        self._selection = list(row_ids)

    def focus(self, row_id: str) -> None:
        self.focused = row_id


class _DeferredRoot:
    def __init__(self) -> None:
        self.after_calls: list[tuple[int, object]] = []

    def after(self, delay_ms: int, callback):
        self.after_calls.append((delay_ms, callback))
        return f"after-{len(self.after_calls)}"


class ManualProgramSendResponsivenessTests(unittest.TestCase):
    def make_context_app(self, selection: tuple[str, ...] = ()):
        order = shower_batch.ProcessOrder("INPUT-188", "90433005 MANUAL", "Input file only")
        setattr(order, "process_list_missing", True)
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        app.tree = _ContextTree("row-188", selection)
        app.tree_row_orders = {"row-188": order}
        app.tree_row_batches = {}
        app.order_by_aw = {str(order.aw_order): order}
        app.process_batches = {}
        app.order_batch_ids = {}
        app.status_var = _Var()
        app.close_active_themed_context_menu = mock.Mock()
        app.dimension_match_override_enabled = mock.Mock(return_value=False)
        app.restored_archive_batch_id_for_context = mock.Mock(return_value=None)
        app.archivable_batch_id_for_context = mock.Mock(return_value=None)
        app.sent_orders_for_input_archive_context = mock.Mock(return_value=[])
        app.open_manual_program_dialog = mock.Mock()
        app.open_programming_evidence = mock.Mock()
        app.create_diagnostic_package_for_order = mock.Mock()
        app.set_selected_dimension_match_override = mock.Mock()
        captured: dict[str, object] = {}

        def capture(_parent, _x, _y, _title, _subtitle, actions):
            captured["actions"] = actions

        app.show_themed_context_menu = capture
        app.root = object()
        return app, order, captured

    def test_right_click_selects_fresh_context_row_and_exposes_manual_programming(self) -> None:
        app, order, captured = self.make_context_app()
        event = SimpleNamespace(y=5, x_root=100, y_root=120)

        result = gui.ShowerProgrammerApp.open_orders_context_menu(app, event)

        self.assertEqual(result, "break")
        self.assertEqual(app.tree.selection(), ("row-188",))
        self.assertEqual(app.tree.focused, "row-188")
        actions = captured.get("actions", [])
        labels = [str(action.get("text", "")) for action in actions]
        self.assertIn("Program Manually", labels)
        manual_action = next(action for action in actions if action.get("text") == "Program Manually")
        manual_action["command"]()
        app.open_manual_program_dialog.assert_called_once_with(order)

    def test_right_click_preserves_existing_multi_selection_when_row_is_already_selected(self) -> None:
        app, _order, _captured = self.make_context_app(("row-188", "row-other"))
        app.tree_row_orders["row-other"] = shower_batch.ProcessOrder("239999", "OTHER")
        event = SimpleNamespace(y=5, x_root=100, y_root=120)

        gui.ShowerProgrammerApp.open_orders_context_menu(app, event)

        self.assertEqual(app.tree.selection(), ("row-188", "row-other"))

    def test_manual_programming_synthetic_batch_is_not_a_completed_process_list(self) -> None:
        order = shower_batch.ProcessOrder("239188", "90433005 MANUAL")
        setattr(order, "manual_process_order", True)
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        app.process_batches = {
            "manual-programming": {
                "id": "manual-programming",
                "path": None,
                "name": "Manual Programming",
                "orders": [order],
                "manual": True,
            }
        }

        plans = gui.ShowerProgrammerApp.completed_process_list_batches_for_orders(
            app,
            [order],
            history={"orders": {}},
        )

        self.assertEqual(plans, [])

    def test_real_process_list_batch_still_produces_completion_plan(self) -> None:
        order = shower_batch.ProcessOrder("239188", "90433005 NORMAL")
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "Batch 6188.xls"
            source.write_bytes(b"test")
            app.process_batches = {
                "real": {
                    "id": "real",
                    "path": source,
                    "name": source.name,
                    "orders": [order],
                }
            }
            plans = gui.ShowerProgrammerApp.completed_process_list_batches_for_orders(
                app,
                [order],
                history={"orders": {}},
            )

        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["stem"], "Batch 6188")
        self.assertIn(source, plans[0]["files"])

    def test_post_send_refresh_waits_for_send_task_then_uses_soft_local_refresh(self) -> None:
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        app.root = _DeferredRoot()
        app.status_var = _Var()
        app.task_manager = SimpleNamespace(active=object())
        app.refresh_local_orders = mock.Mock()

        gui.ShowerProgrammerApp.schedule_post_send_local_refresh(app)
        self.assertEqual(app.root.after_calls[0][0], 100)

        first_callback = app.root.after_calls.pop(0)[1]
        first_callback()
        app.refresh_local_orders.assert_not_called()
        self.assertEqual(app.root.after_calls[0][0], 75)

        app.task_manager.active = None
        retry_callback = app.root.after_calls.pop(0)[1]
        retry_callback()

        app.refresh_local_orders.assert_called_once_with(lock_controls=False)
        self.assertIn("Refreshing local Orders", app.status_var.get())

    def test_send_completion_no_longer_launches_full_network_scan(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.drain_worker_queue)
        send_done = source.split('elif kind == "send_done":', 1)[1].split('elif kind == "send_error":', 1)[0]
        self.assertIn("self.schedule_post_send_local_refresh()", send_done)
        self.assertNotIn("self.scan_orders", send_done)

    def test_version_188_release_metadata_and_flags(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 188)
        self.assertGreaterEqual(int(version["version_number"]), 188)
        features = (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8")
        self.assertIn("VERSION_1_88_MANUAL_PROGRAM_SEND_RESPONSIVENESS", features)
        flags = (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8")
        for flag in (
            "right_click_context_row_selection",
            "manual_batch_process_list_isolation",
            "nonblocking_post_send_local_refresh",
            "version_1_88_manual_program_send_responsiveness",
        ):
            self.assertIn(flag, flags)


if __name__ == "__main__":
    unittest.main()
