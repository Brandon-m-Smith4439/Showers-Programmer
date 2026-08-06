from __future__ import annotations

import json
import shutil
import sys
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

import shower_programmer as programmer


CONFIG = {
    "rules": {
        "mirror_keywords": ["MIRROR"],
        "denver_min_inches": 6.125,
        "waterjet_fit_limit_inches": 75,
        "door_keywords": ["DOOR", "HINGE", "PPH", "PULL", "HANDLE"],
        "hinge_label_keywords": ["GEN037", "V1E037", "AV1E037", "PPH"],
        "fabrication_keywords": ["HOLE", "CUTOUT", "NOTCH", "RADIUS"],
        "denver_fabrication_keywords": ["HOLE", "SLOT"],
        "waterjet_keywords": ["NOTCH", "RADIUS"],
        "weak_waterjet_keywords": ["IRREGULAR SHAPE"],
        "label_only_allow_keywords": ["RAKED EDGE"],
        "auto_dxf_fps_cut_min_segment_ratio": 0.12,
        "auto_dxf_fps_cut_min_coverage_ratio": 0.45,
    }
}


@contextmanager
def writable_test_directory():
    path = ROOT / "tmp" / "tests" / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def write_fps_transition_dxf(path: Path) -> None:
    pairs = [("0", "SECTION"), ("2", "ENTITIES")]
    lines = [
        ((0.0, 0.0), (28.0, 0.0)),
        ((28.0, 0.0), (27.75, 83.5)),
        ((27.75, 83.5), (0.0, 83.5)),
        ((0.0, 83.5), (0.0, 0.0)),
        ((27.9617769, 9.2499893), (27.75, 60.5)),
        ((27.75, 60.5), (27.75, 74.25)),
    ]
    for start, end in lines:
        pairs.extend(
            [
                ("0", "LINE"),
                ("10", f"{start[0]:g}"),
                ("20", f"{start[1]:g}"),
                ("11", f"{end[0]:g}"),
                ("21", f"{end[1]:g}"),
            ]
        )
    pairs.extend([("0", "ENDSEC"), ("0", "EOF")])
    path.write_text("\n".join(value for pair in pairs for value in pair) + "\n", encoding="ascii")


class KnownOrderRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = json.loads(
            (ROOT / "tests" / "known_order_regressions.json").read_text(encoding="utf-8")
        )["cases"]

    def test_known_order_library(self) -> None:
        for case in self.cases:
            with self.subTest(case=case["id"]):
                kind = case["kind"]
                if kind == "classification":
                    panel = programmer.Panel(
                        1,
                        1,
                        case["text"],
                        float(case["width"]),
                        float(case["height"]),
                        "",
                    )
                    programmer.classify_panel(panel, CONFIG, case["id"])
                    self.assertEqual(panel.machine, case["expected_machine"])
                    if "expected_label_only" in case:
                        self.assertEqual(panel.label_only, case["expected_label_only"])
                    if case.get("expected_reason"):
                        self.assertIn(case["expected_reason"], panel.reasons)
                elif kind == "pph_orientation":
                    panel = programmer.Panel(1, 1, case["text"], 30.0, 80.0, "DENVER 1")
                    panel.hinge_side = case["hinge_side"]
                    panel.hinges_up = False
                    panel.rotation_degrees = -90.0
                    programmer.enforce_pph_hinges_up(panel)
                    self.assertEqual(panel.hinges_up, case["expected_hinges_up"])
                    self.assertEqual(panel.rotation_degrees, case["expected_rotation"])
                    self.assertEqual(panel.indicator_corner, case["expected_indicator"])
                elif kind == "fps_short_transition":
                    with writable_test_directory() as temp:
                        source = temp / "source.dxf"
                        write_fps_transition_dxf(source)
                        panel = programmer.Panel(2, 2, "FP-S AGEN037 AGEN037", 28.0, 83.5, "DENVER 1")
                        panel.hinge_side = "right"
                        panel.hinges_up = False
                        panel.rotation_degrees = -90.0
                        panel.indicator_corner = "top_right"
                        panel.source_dxf = source
                        programmer.adjust_denver_door_hinge_side_from_dxf(panel, CONFIG)
                        programmer.apply_dxf_manual_review_warning(panel, CONFIG)
                        self.assertEqual(panel.hinges_up, case["expected_hinges_up"])
                        self.assertEqual(panel.rotation_degrees, case["expected_rotation"])
                        self.assertEqual(panel.indicator_corner, case["expected_indicator"])
                        self.assertEqual(
                            any("manual DXF review required" in warning for warning in panel.warnings),
                            case["expected_manual_review"],
                        )
                else:
                    self.fail(f"Unsupported regression kind: {kind}")


if __name__ == "__main__":
    unittest.main()
