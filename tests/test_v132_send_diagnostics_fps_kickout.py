from __future__ import annotations

import json
import shutil
import sys
import unittest
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_programmer as programmer
import shower_v4_features
from shower_programmer_gui import ShowerProgrammerApp


def write_kick_out_dxf(path: Path) -> None:
    lines = [
        ((0.0, 0.0), (28.0, 0.125)),
        ((28.0, 0.125), (28.125, 7.125)),
        ((28.125, 7.125), (28.0, 79.5)),
        ((28.0, 79.5), (0.0, 79.5)),
        ((0.0, 79.5), (0.0, 0.0)),
    ]
    pairs = [
        ("0", "SECTION"), ("2", "HEADER"), ("9", "$INSUNITS"), ("70", "1"),
        ("0", "ENDSEC"), ("0", "SECTION"), ("2", "ENTITIES"),
    ]
    for start, end in lines:
        pairs.extend(
            [
                ("0", "LINE"),
                ("10", f"{start[0]:g}"), ("20", f"{start[1]:g}"),
                ("11", f"{end[0]:g}"), ("21", f"{end[1]:g}"),
            ]
        )
    pairs.extend([("0", "ENDSEC"), ("0", "EOF")])
    path.write_text("\n".join(value for pair in pairs for value in pair) + "\n", encoding="ascii")


class DeferredRoot:
    def __init__(self) -> None:
        self.callbacks: list[object] = []

    def after_idle(self, callback: object) -> None:
        self.callbacks.append(callback)


class SendAppStub:
    def __init__(self, folder: Path) -> None:
        self.root = DeferredRoot()
        self.SHOP_SKETCHES_DIR = folder / "shop-sketches"
        self.SHOP_PROGRAMS_DIR = folder / "shop-programs"
        self.events: list[tuple[str, str]] = []
        self.run_kwargs: dict[str, object] = {}
        self.status_var = type("Status", (), {"set": lambda _self, _value: None})()
        self.send_review_status_var = None

    def record_send_pipeline_event(self, stage: str, message: str, **_kwargs: object) -> None:
        self.events.append((stage, message))

    def run_managed_task(self, _name: str, _worker: object, **kwargs: object) -> bool:
        self.run_kwargs = kwargs
        return True

    def show_structured_error(self, error: BaseException, *, title: str) -> None:  # pragma: no cover
        raise AssertionError(f"Unexpected {title}: {error}")


class SendDiagnosticsAndFpsKickOutTests(unittest.TestCase):
    def test_release_metadata_tracks_version_132(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 132)

    def test_fps_hinge_kick_out_overrides_configured_hinges_down(self) -> None:
        folder = ROOT / "tmp" / "tests" / uuid.uuid4().hex
        folder.mkdir(parents=True)
        try:
            source = folder / "kick-out.dxf"
            write_kick_out_dxf(source)
            panel = programmer.Panel(2, 2, "FP-S GEN037", 28.125, 79.5, "DENVER 1")
            panel.process_text = "DENVER 1"
            panel.hinge_side = "right"
            panel.hinges_up = False
            panel.rotation_degrees = -90.0
            panel.indicator_corner = "top_right"
            panel.source_dxf = source
            config = {
                "rules": {
                    "hinge_label_keywords": ["GEN037"],
                    "hinge_label_orientations": {"GEN037": "down"},
                    "auto_dxf_hinge_side_detection": True,
                    "auto_dxf_cut_in_min_offset": 0.03125,
                }
            }

            self.assertTrue(programmer.dxf_side_has_kick_out_transition(source, "right", config))
            programmer.adjust_denver_door_hinge_side_from_dxf(panel, config)
            programmer.enforce_configured_hinge_orientation(panel, config)

            self.assertTrue(panel.hinges_up)
            self.assertEqual(panel.rotation_degrees, 90.0)
            self.assertEqual(panel.indicator_corner, "bottom_left")
            self.assertTrue(any("FP-S kick-out transition" in reason for reason in panel.reasons))
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_kick_out_without_piece_hinge_evidence_keeps_existing_orientation(self) -> None:
        folder = ROOT / "tmp" / "tests" / uuid.uuid4().hex
        folder.mkdir(parents=True)
        try:
            source = folder / "panel-kick-out.dxf"
            write_kick_out_dxf(source)
            panel = programmer.Panel(1, 1, "FP-S DOOR REMAKE ONLY", 28.125, 79.5, "DENVER 1")
            panel.process_text = "DENVER 1"
            panel.hinge_side = "right"
            panel.hinges_up = False
            panel.rotation_degrees = -90.0
            panel.source_dxf = source
            config = {"rules": {"auto_dxf_hinge_side_detection": True}}

            self.assertTrue(programmer.dxf_side_has_kick_out_transition(source, "right", config))
            self.assertFalse(programmer.has_explicit_hinge_programming_evidence(panel, config))
            self.assertFalse(programmer.fps_hinge_side_has_cut_in(panel, "right", config))
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_core_send_handoff_runs_on_next_ui_turn(self) -> None:
        folder = ROOT / "tmp" / "tests" / uuid.uuid4().hex
        folder.mkdir(parents=True)
        app = SendAppStub(folder)
        core_calls: list[tuple[object, ...]] = []

        def original_start(*args: object, **kwargs: object) -> bool:
            core_calls.append(args + (kwargs,))
            return True

        try:
            started = shower_v4_features._start_send_outputs_worker(
                app,
                [],
                [],
                [],
                True,
                ["237716"],
                folder / "orders",
                folder / "process-lists",
                include_sketches=True,
                include_programs=True,
                gui=None,
                original_start=original_start,
            )
            self.assertTrue(started)
            on_done = app.run_kwargs["on_done"]
            self.assertTrue(callable(on_done))
            on_done([])
            self.assertEqual(core_calls, [])
            self.assertEqual(len(app.root.callbacks), 1)
            callback = app.root.callbacks.pop()
            self.assertTrue(callable(callback))
            callback()
            self.assertEqual(len(core_calls), 1)
            stages = [stage for stage, _message in app.events]
            self.assertIn("CORE_SEND_SCHEDULED", stages)
            self.assertIn("CORE_SEND_STARTED", stages)
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_send_pipeline_event_is_written_to_diagnostics(self) -> None:
        folder = ROOT / "tmp" / "tests" / uuid.uuid4().hex
        folder.mkdir(parents=True)
        try:
            app = object.__new__(ShowerProgrammerApp)
            app.runtime_root = folder
            app.is_busy = False
            app.task_manager = type("Manager", (), {"active": None})()
            app.action_identity_for_orders = lambda orders: ([str(value) for value in orders or []], [], [], [])

            entry = ShowerProgrammerApp.record_send_pipeline_event(
                app,
                "TEST_STAGE",
                "Diagnostic write test.",
                orders=["237716"],
            )

            self.assertIsNotNone(entry)
            path = folder / "Diagnostics" / "send_pipeline.jsonl"
            saved = json.loads(path.read_text(encoding="utf-8").strip())
            self.assertEqual(saved["stage"], "TEST_STAGE")
            self.assertEqual(saved["orders"], ["237716"])
            self.assertEqual(saved["version"], ShowerProgrammerApp.APP_VERSION)
        finally:
            shutil.rmtree(folder, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
