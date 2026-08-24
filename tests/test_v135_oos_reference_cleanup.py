from __future__ import annotations

import json
import shutil
import sys
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_programmer as programmer
from shower_programmer_gui import ShowerProgrammerApp


@contextmanager
def writable_test_directory():
    path = ROOT / "tests" / "_verification" / f"v135-{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def write_line_dxf(
    path: Path,
    segments: list[tuple[tuple[float, float], tuple[float, float]]],
) -> None:
    pairs = [
        ("0", "SECTION"),
        ("2", "HEADER"),
        ("9", "$INSUNITS"),
        ("70", "1"),
        ("0", "ENDSEC"),
        ("0", "SECTION"),
        ("2", "ENTITIES"),
    ]
    for start, end in segments:
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


class OosReferenceAndCleanupTests(unittest.TestCase):
    def test_release_metadata_tracks_version_135(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 135)

    def test_reference_geometry_uses_square_axis_and_actual_endpoint(self) -> None:
        horizontal = ShowerProgrammerApp.dxf_oos_reference_geometry((0.0, 0.0), (60.0, 0.125))
        vertical = ShowerProgrammerApp.dxf_oos_reference_geometry((0.0, 0.0), (0.1875, 85.5))

        self.assertEqual(horizontal, ((0.0, 0.0), (60.0, 0.0), (60.0, 0.125)))
        self.assertEqual(vertical, ((0.0, 0.0), (0.0, 85.5), (0.1875, 85.5)))

    def test_three_oos_runs_on_one_edge_remain_automatic(self) -> None:
        segments = [
            ((0.0, 80.0), (20.0, 79.875)),
            ((20.0, 79.875), (40.0, 79.75)),
            ((40.0, 79.75), (60.0, 79.625)),
            ((60.0, 79.625), (60.0, 0.0)),
            ((60.0, 0.0), (0.0, 0.0)),
            ((0.0, 0.0), (0.0, 80.0)),
        ]

        details = programmer.dxf_complex_oos_review_from_segments(segments)

        self.assertFalse(details["requires_manual_review"])
        self.assertEqual(details["side_counts"].get("top"), 3)
        self.assertEqual(details["summary"], "")

    def test_two_oos_runs_remain_automatic(self) -> None:
        segments = [
            ((0.0, 80.0), (30.0, 79.875)),
            ((30.0, 79.875), (60.0, 79.75)),
            ((60.0, 79.75), (60.0, 0.0)),
            ((60.0, 0.0), (0.0, 0.0)),
            ((0.0, 0.0), (0.0, 80.0)),
        ]

        details = programmer.dxf_complex_oos_review_from_segments(segments)

        self.assertFalse(details["requires_manual_review"])
        self.assertEqual(details["side_counts"].get("top"), 2)

    def test_four_duplicate_oos_entities_require_manual_review(self) -> None:
        top = ((60.0, 85.375), (0.1875, 85.625))
        segments = [
            top,
            top,
            top,
            top,
            ((0.1875, 85.625), (0.0, 0.125)),
            ((0.0, 0.125), (60.0, 0.0)),
            ((60.0, 0.0), (60.0, 85.375)),
        ]

        details = programmer.dxf_complex_oos_review_from_segments(segments)

        self.assertTrue(details["requires_manual_review"])
        self.assertEqual(details["side_counts"].get("top"), 4)
        self.assertEqual(details["entity_count"], 6)
        self.assertIn("4 OOS runs on top edge", details["summary"])

    def test_four_multi_edge_oos_runs_remain_automatic(self) -> None:
        segments = [
            ((0.1875, 85.625), (60.0, 85.375)),
            ((60.0, 85.375), (60.25, 0.0)),
            ((60.25, 0.0), (0.0, 0.125)),
            ((0.0, 0.125), (0.1875, 85.625)),
        ]

        details = programmer.dxf_complex_oos_review_from_segments(segments)

        self.assertFalse(details["requires_manual_review"])
        self.assertEqual(len(details["highlighted_segments"]), 4)
        self.assertEqual(details["summary"], "")

    def test_complex_oos_warning_is_applied_to_panel(self) -> None:
        top = ((60.0, 85.375), (0.1875, 85.625))
        segments = [
            top,
            top,
            top,
            top,
            ((0.1875, 85.625), (0.0, 0.125)),
            ((0.0, 0.125), (60.0, 0.0)),
            ((60.0, 0.0), (60.0, 85.375)),
        ]
        with writable_test_directory() as temp:
            source = temp / "complex-oos.dxf"
            write_line_dxf(source, segments)
            panel = programmer.Panel(1, 1, "FP-S", 60.0, 85.625, "DENVER 2")
            panel.source_dxf = source

            programmer.apply_dxf_manual_review_warning(panel, {})

            self.assertTrue(any("4 OOS runs on top edge" in warning for warning in panel.warnings))
            self.assertTrue(any("manual DXF review required" in warning for warning in panel.warnings))

    def test_late_identical_local_copy_is_cleared_but_changed_copy_is_kept(self) -> None:
        with writable_test_directory() as temp:
            order_root = temp / "Orders"
            archive_root = order_root / "8.20.26"
            order_root.mkdir()
            archive_root.mkdir()
            same_source = order_root / "88524349 EMERSON GLEN 77_1__P1.dxf"
            same_archive = archive_root / same_source.name
            same_source.write_bytes(b"verified-sent-input")
            same_archive.write_bytes(b"verified-sent-input")
            changed_source = order_root / "Glass Order 88524349.pdf"
            changed_archive = archive_root / changed_source.name
            changed_source.write_bytes(b"new-revision")
            changed_archive.write_bytes(b"sent-revision")

            cleaned, warnings, remaining = ShowerProgrammerApp.reconcile_late_local_sent_inputs(
                order_root,
                {
                    same_source.name: same_archive,
                    changed_source.name: changed_archive,
                },
            )

            self.assertFalse(same_source.exists())
            self.assertIn(same_archive, cleaned)
            self.assertTrue(changed_source.exists())
            self.assertEqual(remaining, [changed_source])
            self.assertTrue(any("differs from the sent archive copy" in warning for warning in warnings))


if __name__ == "__main__":
    unittest.main()
