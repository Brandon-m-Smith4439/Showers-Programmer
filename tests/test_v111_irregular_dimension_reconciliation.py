from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_batch
from shower_temp import workspace_temporary_directory


JOB = "89183226 KINSDALE 132"
AW_ORDER = "236465"


def write_kinsdale_outline(path: Path) -> None:
    """Synthetic outline matching the supplied 236465 source-DXF corners."""
    pairs = [("0", "SECTION"), ("2", "ENTITIES")]
    for start, end in (
        ((0.125, 46.25), (0.0, 0.125)),
        ((0.0, 0.125), (15.75, 0.0)),
        ((15.75, 0.0), (15.625, 46.375)),
        ((15.625, 46.375), (0.125, 46.25)),
    ):
        pairs.extend(
            [
                ("0", "LINE"), ("8", "0"),
                ("10", f"{start[0]:g}"), ("20", f"{start[1]:g}"),
                ("11", f"{end[0]:g}"), ("21", f"{end[1]:g}"),
            ]
        )
    pairs.extend([("0", "ENDSEC"), ("0", "EOF")])
    path.write_text("\n".join(value for pair in pairs for value in pair) + "\n", encoding="ascii")


def kinsdale_order() -> shower_batch.ProcessOrder:
    order = shower_batch.ProcessOrder(AW_ORDER, JOB, "PULTE GROUP")
    order.items[1] = shower_batch.ProcessItem(
        1,
        width_text='15"31/32',
        height_text='46"11/32',
        processing=["Flat Polish side(s) 1/2/3/4", "SCU4 Slot MACRO"],
        machine_hints=["Waterjet"],
    )
    return order


class Version111IrregularDimensionReconciliationTests(unittest.TestCase):
    def test_supplied_kinsdale_geometry_reconciles_when_sketch_matches_dxf_envelope(self) -> None:
        with workspace_temporary_directory() as temp_name:
            folder = Path(temp_name)
            write_kinsdale_outline(folder / f"{JOB}_1__P1.dxf")
            order = kinsdale_order()
            actual = [(2, 15.75, 46.375)]

            self.assertFalse(shower_batch.process_dimensions_fit_values(order, actual))
            self.assertTrue(shower_batch.reconcile_out_of_square_dimension_match(order, actual, folder))
            note = order.dimension_match_notes[1]
            self.assertIn("sketch matches the source DXF envelope", note)
            self.assertIn("OOS shift 0.125 in", note)
            self.assertIn("A+W/DXF delta 0.21875 x 0.03125 in", note)

    def test_sketch_must_match_source_dxf_envelope_for_process_variance_path(self) -> None:
        with workspace_temporary_directory() as temp_name:
            folder = Path(temp_name)
            write_kinsdale_outline(folder / f"{JOB}_1__P1.dxf")
            self.assertFalse(
                shower_batch.reconcile_out_of_square_dimension_match(
                    kinsdale_order(),
                    [(2, 15.50, 46.00)],
                    folder,
                )
            )

    def test_process_dimensions_cannot_drift_beyond_quarter_inch(self) -> None:
        with workspace_temporary_directory() as temp_name:
            folder = Path(temp_name)
            write_kinsdale_outline(folder / f"{JOB}_1__P1.dxf")
            order = kinsdale_order()
            order.items[1].width_text = '16"1/16'
            self.assertFalse(
                shower_batch.reconcile_out_of_square_dimension_match(
                    order,
                    [(2, 15.75, 46.375)],
                    folder,
                )
            )

    def test_rectangular_dxf_still_cannot_explain_dimension_mismatch(self) -> None:
        with workspace_temporary_directory() as temp_name:
            folder = Path(temp_name)
            path = folder / f"{JOB}_1__P1.dxf"
            pairs = [("0", "SECTION"), ("2", "ENTITIES")]
            for start, end in (
                ((0.0, 0.0), (15.75, 0.0)),
                ((15.75, 0.0), (15.75, 46.375)),
                ((15.75, 46.375), (0.0, 46.375)),
                ((0.0, 46.375), (0.0, 0.0)),
            ):
                pairs.extend(
                    [
                        ("0", "LINE"), ("8", "0"),
                        ("10", f"{start[0]:g}"), ("20", f"{start[1]:g}"),
                        ("11", f"{end[0]:g}"), ("21", f"{end[1]:g}"),
                    ]
                )
            pairs.extend([("0", "ENDSEC"), ("0", "EOF")])
            path.write_text("\n".join(value for pair in pairs for value in pair) + "\n", encoding="ascii")
            self.assertFalse(
                shower_batch.reconcile_out_of_square_dimension_match(
                    kinsdale_order(),
                    [(2, 15.75, 46.375)],
                    folder,
                )
            )


if __name__ == "__main__":
    unittest.main()
