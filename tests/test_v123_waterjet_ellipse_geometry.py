from __future__ import annotations

import math
import shutil
import sys
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

import shower_batch
import shower_programmer as programmer


CONFIG = {
    "rules": {
        "denver_min_inches": 6.125,
        "waterjet_fit_limit_inches": 75,
        "door_keywords": ["DOOR", "HINGE", "PPH", "PULL", "HANDLE"],
        "hinge_label_keywords": ["GEN037", "V1E037", "AV1E037", "PPH"],
        "fabrication_keywords": ["HOLE", "CUTOUT", "NOTCH", "RADIUS"],
        "denver_fabrication_keywords": ["HOLE", "SLOT"],
        "waterjet_keywords": ["NOTCH", "RADIUS"],
        "weak_waterjet_keywords": ["IRREGULAR SHAPE"],
        "label_only_allow_keywords": ["RAKED EDGE"],
    },
    "dxf": {
        "waterjet_output_scale": 25.4,
        "waterjet_insunits": 4,
        "waterjet_measurement": 1,
    },
}


@contextmanager
def writable_test_directory():
    path = ROOT / "tmp" / "tests" / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def write_ellipse_notch_dxf(path: Path) -> None:
    pairs = [("0", "SECTION"), ("2", "HEADER"), ("0", "ENDSEC"), ("0", "SECTION"), ("2", "ENTITIES")]
    for start, end in (
        ((0.0, 0.0), (33.0, 0.0)),
        ((33.0, 0.0), (33.0, 78.375)),
        ((33.0, 78.375), (0.0, 78.375)),
        ((0.0, 78.375), (0.0, 0.0)),
    ):
        pairs.extend(
            [
                ("0", "LINE"),
                ("10", str(start[0])),
                ("20", str(start[1])),
                ("11", str(end[0])),
                ("21", str(end[1])),
            ]
        )
    pairs.extend(
        [
            ("0", "ELLIPSE"),
            ("10", "15.1279965753425"),
            ("20", "35.625"),
            ("11", "0"),
            ("21", "0.50000293206121"),
            ("40", "0.999994158744812"),
            ("41", "-3.13816798936152"),
            ("42", "-1.5707963267949"),
            ("0", "ENDSEC"),
            ("0", "EOF"),
        ]
    )
    path.write_text("\n".join(value for pair in pairs for value in pair) + "\n", encoding="ascii")


def first_entity_values(path: Path, wanted_type: str) -> dict[str, float]:
    pairs = programmer.read_dxf_pairs(path)
    in_entities = False
    active = False
    values: dict[str, float] = {}
    for code_raw, value_raw in pairs:
        code = code_raw.strip()
        value = value_raw.strip()
        if code == "2" and value.upper() == "ENTITIES":
            in_entities = True
            continue
        if not in_entities:
            continue
        if code == "0":
            if active:
                return values
            active = value.upper() == wanted_type
            continue
        if active and code in {"10", "20", "11", "21", "40", "41", "42"}:
            values[code] = float(value)
    return values


class WaterjetEllipseGeometryTests(unittest.TestCase):
    def test_prefix_half_inch_radius_overrides_conflicting_denver_route(self) -> None:
        panel = programmer.Panel(
            2,
            2,
            '3/8" Clear Tempered\n33" x 78-3/8"\nr 1/2\nFP',
            33.0,
            78.375,
            "",
        )
        programmer.classify_panel(panel, CONFIG, "900123")
        order = shower_batch.ProcessOrder("900123", "SANITIZED ELLIPSE NOTCH")
        order.items[2] = shower_batch.ProcessItem(
            2,
            width_text='33"',
            height_text='78"3/8',
            processing=["0 Notched Corners", "U-Notch Macro"],
            machine_hints=["Denver 2 (CNC)", "Denver 1 (CNC)"],
        )

        shower_batch.apply_process_hints([panel], order, CONFIG)

        self.assertTrue(programmer.has_radius_text("r 1/2"))
        self.assertFalse(programmer.has_radius_text("r 5/16"))
        self.assertEqual(panel.machine, "WJ")
        self.assertIn("WJ-only radius/notch fabrication overrides process-list Denver routing", panel.reasons)

    def test_u_notch_without_radius_keeps_existing_denver_rule(self) -> None:
        panel = programmer.Panel(1, 1, '3/8" Clear Tempered\n42" x 41-3/8"\nFP', 42.0, 41.375, "DENVER 2")
        order = shower_batch.ProcessOrder("900124", "SANITIZED STANDARD U NOTCH")
        order.items[1] = shower_batch.ProcessItem(
            1,
            width_text='42"',
            height_text='41"3/8',
            processing=["U-Notch Macro", '0\'\' 3/4 Hole x 1'],
            machine_hints=["Waterjet", "Denver 1 (CNC)"],
        )

        shower_batch.apply_process_hints([panel], order, CONFIG)

        self.assertEqual(panel.machine, "DENVER 2")

    def test_rotated_metric_ellipse_keeps_major_axis_as_vector(self) -> None:
        with writable_test_directory() as temp:
            source = temp / "ellipse_notch_source.dxf"
            output = temp / "ellipse_notch_wj.dxf"
            write_ellipse_notch_dxf(source)

            programmer.transform_dxf(
                source,
                output,
                rotation_degrees=90.0,
                force=True,
                scale=25.4,
                insunits="4",
                measurement="1",
            )

            ellipse = first_entity_values(output, "ELLIPSE")
            major_axis_length = math.hypot(ellipse["11"], ellipse["21"])
            self.assertAlmostEqual(major_axis_length, 0.50000293206121 * 25.4, places=6)
            self.assertAlmostEqual(ellipse["10"], (78.375 - 35.625) * 25.4, places=6)
            self.assertAlmostEqual(ellipse["20"], 15.1279965753425 * 25.4, places=6)
            self.assertAlmostEqual(ellipse["40"], 0.999994158744812, places=12)
            self.assertAlmostEqual(ellipse["41"], -3.13816798936152, places=12)
            self.assertAlmostEqual(ellipse["42"], -1.5707963267949, places=12)
            self.assertLess(major_axis_length, 20.0)


if __name__ == "__main__":
    unittest.main()
