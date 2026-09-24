from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_batch
import shower_programmer as programmer


CONFIG = {
    "rules": {
        "denver_min_inches": 6.125,
        "waterjet_fp_min_count": 6,
        "door_keywords": ["DOOR", "HINGE", "PPH", "PULL", "HANDLE"],
        "hinge_label_keywords": ["GEN037", "V1E037", "AV1E037", "JRG037", "GEN180", "PPH"],
        "fabrication_keywords": ["HOLE", "CUTOUT", "NOTCH", "RADIUS"],
        "denver_fabrication_keywords": ["SCU", "SCU4", "SLOT", "MACRO", "HOLE"],
        "waterjet_keywords": ["CORNER NOTCH", "EDGE NOTCH", "NOTCH", "NOTCHED", "1/2 RADIUS", "RADIUS"],
        "weak_waterjet_keywords": ["IRREGULAR SHAPE"],
        "label_only_allow_keywords": ["RAKED EDGE"],
    }
}


def routed_panel(
    *,
    text: str,
    processing: list[str],
    machine_hints: list[str],
    width: float = 15.25,
    height: float = 45.25,
) -> programmer.Panel:
    panel = programmer.Panel(1, 1, text, width, height, "")
    programmer.classify_panel(panel, CONFIG, "900158")
    order = shower_batch.ProcessOrder("900158", "FABRICATION ROUTE TEST", "Customer")
    order.items[1] = shower_batch.ProcessItem(
        1,
        width_text=f'{width:g}"',
        height_text=f'{height:g}"',
        processing=processing,
        machine_hints=machine_hints,
    )
    shower_batch.apply_process_hints([panel], order, CONFIG)
    return panel


class FabricationGeometryRoutingTests(unittest.TestCase):
    def test_239169_p2_dimensioned_radius_notch_uses_waterjet(self) -> None:
        panel = routed_panel(
            text=(
                '3/8" Clear Tempered\n17-13/16" x 80"\n'
                "NOTCH AND ER REMAKES\n1/2 Radius\nFP"
            ),
            processing=["Flat Polish side(s) 1/2/3/4", "0 Notched Corners", "SCU4 Slot MACRO"],
            machine_hints=["Denver 2 (CNC)", "Denver 1 (CNC)", "Packing / Shipping"],
            width=17.8125,
            height=80.0,
        )

        self.assertEqual(panel.machine, "WJ")
        self.assertIn("piece-level dimensioned radius/notch geometry detected", panel.reasons)
        self.assertIn("WJ-only radius/notch fabrication overrides process-list Denver routing", panel.reasons)

    def test_239170_p1_fps_scu4_without_wj_geometry_uses_denver_two(self) -> None:
        panel = routed_panel(
            text='3/8" Clear Tempered\n15-1/4" x 45-1/4"\nPANEL REMAKE\nFP-S\nIrregular Shape',
            processing=["Shape Flat Polishing side(s) 1/3/4.", "SCU4 Slot MACRO", '3/8" Clear Tempered'],
            machine_hints=["Waterjet", "Tempering Furnace", "Packing / Shipping"],
        )

        self.assertEqual(panel.machine, "DENVER 2")
        self.assertIn("process list says WJ, but no WJ-only fabrication found", panel.reasons)

    def test_location_notch_word_does_not_count_as_piece_notch(self) -> None:
        text = '3/8" Clear Tempered\n42-7/8" x 42-5/8"\nNOTCH AND ER REMAKES\nFP\nFP\nFP'

        self.assertFalse(programmer.has_pdf_waterjet_evidence(text, CONFIG))
        panel = routed_panel(
            text=text,
            processing=["SCU4 Slot MACRO"],
            machine_hints=["Waterjet", "Packing / Shipping"],
            width=42.875,
            height=42.625,
        )
        self.assertEqual(panel.machine, "DENVER 2")

    def test_explicit_corner_notch_still_counts_as_waterjet_geometry(self) -> None:
        self.assertTrue(
            programmer.has_pdf_waterjet_evidence(
                '3/8" Clear Tempered\nCORNER NOTCH\nFP',
                CONFIG,
            )
        )

    def test_waterjet_scu4_with_dimensioned_radius_remains_waterjet(self) -> None:
        panel = routed_panel(
            text='3/8" Clear Tempered\n42" x 42"\nSCU4 Slot\n1/2 Radius',
            processing=["SCU4 Slot MACRO", "1/2 Radius"],
            machine_hints=["Waterjet", "Tempering Furnace"],
            width=42.0,
            height=42.0,
        )

        self.assertEqual(panel.machine, "WJ")

    def test_hinge_door_with_bad_waterjet_route_stays_denver_one(self) -> None:
        door = routed_panel(
            text='3/8" Clear Tempered\n28" x 79-1/2"\nPPH HINGE',
            processing=["PPH HINGE", "SCU4 Slot MACRO"],
            machine_hints=["Waterjet", "Packing / Shipping"],
            width=28.0,
            height=79.5,
        )

        self.assertEqual(door.machine, "DENVER 1")

    def test_version_158_release_marker_is_retained(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        marker = "VERSION_1_58_FABRICATION_GEOMETRY_ROUTING"

        self.assertGreaterEqual(version["version_number"], 158)
        self.assertIn(marker, (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8"))
        flags = (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8")
        self.assertIn("version_1_58_fabrication_geometry_routing", flags)


if __name__ == "__main__":
    unittest.main()
