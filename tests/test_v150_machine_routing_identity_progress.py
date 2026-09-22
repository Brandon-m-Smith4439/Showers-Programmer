from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_batch
import shower_programmer as programmer
import shower_programmer_gui as gui


class FakePage:
    def __init__(self, text: str) -> None:
        self.text = text

    def extract_text(self) -> str:
        return self.text


class FakeReader:
    def __init__(self, texts: list[str]) -> None:
        self.pages = [FakePage(text) for text in texts]


class MachineRoutingIdentityProgressTests(unittest.TestCase):
    def test_ordinary_batch_does_not_inherit_waterjet_section(self) -> None:
        row = lambda order, processing, machine: [
            "", "", '28"', '77"', "", "", order, processing,
            "9/22/2026", "", "CUSTOMER", "", "", "JOB 1",
            "", "", "", "", "", "", "", machine,
        ]
        rows = [
            row("239023-2", "PPH HINGE", "Denver 1 (CNC)"),
            ["Waterjet (2200)"],
            row("239023-2", '3/8" Clear Tempered', "Packing / Shipping"),
        ]

        order = shower_batch.load_process_orders_from_rows(rows)[0]

        self.assertEqual(order.items[2].desired_machine(), "DENVER 1")
        self.assertNotIn("WJ", order.items[2].machine_hints)

    def test_gap_mapping_preserves_sketch_item_and_uses_aw_item_for_output(self) -> None:
        panel = programmer.Panel(3, 2, '28" x 77" FP', 28.0, 77.0, "DENVER 2")
        order = shower_batch.ProcessOrder("239018", "JOB 1")
        order.items[1] = shower_batch.ProcessItem(1)
        order.items[2] = shower_batch.ProcessItem(2)
        panels = [programmer.Panel(1, 1, '28" x 77" FP', 28.0, 77.0, "DENVER 2"), panel]

        remaps = shower_batch.remap_process_items_to_sketch_pages(panels, order)

        self.assertEqual(remaps, {2: 3})
        self.assertEqual(panel.item, 3)
        self.assertEqual(panel.source_item, 2)
        self.assertEqual(panel.aw_item, 2)
        self.assertEqual(programmer.panel_aw_item(panel), 2)

        job = programmer.Job(Path("input.pdf"), "239018", "JOB 1", panels, Path("out.pdf"), Path("report.txt"))
        with mock.patch.object(programmer, "validate_panel_constraints"), mock.patch.object(
            programmer, "find_source_dxf", return_value=None
        ):
            programmer.assign_dxf_paths(job, Path("."), Path("Programs"), {"rules": {}})
        self.assertEqual(panel.output_dxf, Path("Programs") / "23901802.dxf")

    def test_bottom_angle_uses_long_edge_not_short_cut_transition(self) -> None:
        panel = programmer.Panel(2, 2, "FP-S", 29.375, 80.0, "DENVER 2")
        panel.source_dxf = Path("piece.dxf")
        panel.rotation_degrees = -90.0
        segments = [
            ((28.9375, 0.0625), (29.375, 30.0625)),
            ((29.375, 30.0625), (29.375, 80.0)),
        ]
        config = {"rules": {"auto_dxf_angle_min_degrees": 0.02, "auto_dxf_angle_max_degrees": 1.0}}

        with mock.patch.object(programmer, "dxf_side_segments", return_value=segments):
            correction = programmer.dxf_bottom_angle_correction(panel, config)

        self.assertIsNotNone(correction)
        assert correction is not None
        self.assertAlmostEqual(correction[0], 0.0, places=6)
        self.assertAlmostEqual(correction[2], 49.9375, places=4)

    def test_no_machine_override_hides_indicator_and_skips_program(self) -> None:
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        data: dict[str, object] = {"item_overrides": {}}
        app.load_manual_overrides = mock.Mock(return_value=data)
        app.save_manual_overrides = mock.Mock()
        panel = programmer.Panel(1, 1, "P1", 28.0, 77.0, "DENVER 1")

        app.set_indicator_machine_override("239023", 1, "NO MACHINE", panel, {"rules": {}})

        override = data["item_overrides"]["239023"]["1"]  # type: ignore[index]
        self.assertEqual(override["machine"], "")
        self.assertTrue(override["skip_dxf"])
        self.assertTrue(override["hide_indicator"])

    def test_nonfabricated_mirror_page_receives_label_only_panel(self) -> None:
        order = shower_batch.ProcessOrder("239009", "MIRROR ORDER")
        order.items[2] = shower_batch.ProcessItem(2, processing=['1/4" Mirror'], machine_hints=["WJ"])
        fabricated = programmer.Panel(2, 2, '1/4" Mirror', 52.0, 118.0, "WJ", mirror_glass=True)
        reader = FakeReader(["Overview", '1/4" Mirror Clear Annealed\n52 x 118', '1/4" Mirror\nInternal Cutout'])

        panels = [fabricated]
        shower_batch.attach_mirror_label_only_pages(reader, panels, order, {"rules": {"mirror_keywords": ["MIRROR"]}})

        label_panel = next(panel for panel in panels if panel.page_index == 1)
        self.assertTrue(label_panel.mirror_label_only)
        self.assertTrue(label_panel.label_only)
        self.assertTrue(label_panel.skip_dxf)
        self.assertEqual(label_panel.item, 1)

    def test_version_150_release_marker_is_retained(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 150)
        self.assertIn(
            "VERSION_1_50_ROUTING_IDENTITY_RESPONSIVENESS",
            (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
