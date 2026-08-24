from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_programmer as programmer
import shower_programmer_gui as gui


class _Var:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


class _Widget:
    def __init__(self) -> None:
        self.visible = False

    def grid(self, *args, **kwargs) -> None:
        self.visible = True

    def grid_remove(self) -> None:
        self.visible = False


class _Root:
    def __init__(self) -> None:
        self.titles: list[str] = []
        self.events: list[str] = []

    def title(self, value: str) -> None:
        self.titles.append(value)

    def quit(self) -> None:
        self.events.append("quit")

    def destroy(self) -> None:
        self.events.append("destroy")


class Version114TestModeVisibilityDxfDisplayTests(unittest.TestCase):
    def test_dxf_reference_degrees_remain_bounded_for_operator_display(self) -> None:
        self.assertEqual(gui.ShowerProgrammerApp.format_degrees(89.850011), "89.850011")
        self.assertEqual(gui.ShowerProgrammerApp.format_degrees(-90.154436), "-90.154436")
        self.assertEqual(gui.ShowerProgrammerApp.format_degrees(90.0), "90")
        self.assertEqual(programmer.format_display_decimal(-90.154436), "-90.15")

    def test_test_mode_visual_state_is_prominent_and_reversible(self) -> None:
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        app.root = _Root()
        app.test_mode_workspace = Path(r"C:\Test Workspace\20260814-TEST")
        app.test_mode_orders = [object(), object()]
        app.test_mode_banner_var = _Var()
        app.test_mode_banner = _Widget()
        app.exit_test_mode_button = _Widget()

        app.update_test_mode_visual_state()

        self.assertTrue(app.test_mode_banner.visible)
        self.assertTrue(app.exit_test_mode_button.visible)
        self.assertIn("TEST MODE", app.root.titles[-1])
        self.assertIn("PRODUCTION SEND DISABLED", app.test_mode_banner_var.get())
        self.assertIn("2 archived order(s)", app.test_mode_banner_var.get())

        app.test_mode_workspace = None
        app.test_mode_orders = []
        app.update_test_mode_visual_state()

        self.assertFalse(app.test_mode_banner.visible)
        self.assertFalse(app.exit_test_mode_button.visible)
        self.assertEqual(app.root.titles[-1], f"Shower Programmer {app.APP_VERSION}")

    def test_close_time_exit_restores_production_without_rescan(self) -> None:
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        app.root = _Root()
        app.test_mode_workspace = Path("test-workspace")
        app.test_mode_orders = []
        app._production_paths_before_test = ("prod-orders", "prod-process", "prod-output")
        app.folder_var = _Var("test-orders")
        app.process_list_var = _Var("test-process")
        app.output_dir_var = _Var("test-output")
        app.status_var = _Var()
        app.update_test_mode_visual_state = mock.Mock()
        app.record_action = mock.Mock()
        app.scan_orders = mock.Mock()

        with mock.patch.object(gui.shower_cache, "configure"), mock.patch.object(
            gui.shower_state.StateStore, "for_output", return_value=object()
        ):
            app.exit_test_mode(rescan=False, closing=True)

        self.assertIsNone(app.test_mode_workspace)
        self.assertEqual(app.folder_var.get(), "prod-orders")
        self.assertEqual(app.process_list_var.get(), "prod-process")
        self.assertEqual(app.output_dir_var.get(), "prod-output")
        app.scan_orders.assert_not_called()
        self.assertIn("before closing", app.status_var.get())

    def test_application_close_exits_test_mode_before_quit(self) -> None:
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        app.root = _Root()
        app.is_busy = False
        app.test_mode_workspace = Path("test-workspace")
        app.save_ui_settings = mock.Mock(side_effect=lambda: app.root.events.append("save"))
        app.managed_page_window = mock.Mock(return_value=None)

        def exit_mode(*, rescan: bool = True, closing: bool = False) -> None:
            self.assertFalse(rescan)
            self.assertTrue(closing)
            app.root.events.append("exit-test")
            app.test_mode_workspace = None

        app.exit_test_mode = mock.Mock(side_effect=exit_mode)
        app.on_close()

        self.assertEqual(app.root.events[:4], ["exit-test", "save", "quit", "destroy"])
        app.exit_test_mode.assert_called_once_with(rescan=False, closing=True)


if __name__ == "__main__":
    unittest.main()
