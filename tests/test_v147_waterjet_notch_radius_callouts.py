from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_programmer as programmer
import shower_v4_features as v4


class WaterJetNotchRadiusCalloutTests(unittest.TestCase):
    @staticmethod
    def panel(text: str, process_text: str = "") -> SimpleNamespace:
        return SimpleNamespace(text=text, process_text=process_text, machine="WJ")

    def test_extracts_suffix_and_prefix_notch_radius_labels(self) -> None:
        panel = self.panel('3/8" Clear Tempered\n1/2 Radius', 'NOTCH R=5/8"')
        self.assertEqual(
            v4.extract_notch_radius_values_inches(panel, programmer),
            [0.5, 0.625],
        )

    def test_metric_waterjet_samples_keep_notch_and_exclude_clamps(self) -> None:
        panel = self.panel('3/8" Clear Tempered\n1/2 Radius\nNOTCH')
        samples = [
            (10.0, 10.0, 9.525),
            (20.0, 20.0, 12.7),
            (30.0, 30.0, 9.525),
        ]
        selected = v4.waterjet_notch_radius_samples(samples, panel, 1.0 / 25.4, programmer)
        self.assertEqual(selected, [(20.0, 20.0, 12.7)])

    def test_ambiguous_sketch_does_not_guess_from_fabrication_radii(self) -> None:
        panel = self.panel('3/8" Clear Tempered\nNOTCH')
        samples = [(10.0, 10.0, 9.525), (20.0, 20.0, 12.7)]
        self.assertEqual(
            v4.waterjet_notch_radius_samples(samples, panel, 1.0 / 25.4, programmer),
            [],
        )

    def test_glass_thickness_is_not_mistaken_for_radius(self) -> None:
        panel = self.panel('3/8" CLEAR TEMPERED INTERNAL RADIUS')
        self.assertEqual(v4.extract_notch_radius_values_inches(panel, programmer), [])

    def test_version_147_release_metadata(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertEqual(version["version"], "Version 1.47")
        self.assertEqual(version["version_number"], 147)
        self.assertEqual(version["marker"], "VERSION_1_47_WATERJET_NOTCH_RADIUS_CALLOUTS")
        source = (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8")
        self.assertIn(version["marker"], source)


if __name__ == "__main__":
    unittest.main()
