from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

import shower_batch
import shower_programmer as programmer
from shower_temp import workspace_temporary_directory


JOB = "89589740M 146 WHITBY"
AW_ORDER = "237412"


def write_oos_mirror_dxf(path: Path) -> None:
    """Match the supplied 146 WHITBY geometry: 44-13/16 edge + 1/2 OOS."""
    pairs = [("0", "SECTION"), ("2", "ENTITIES")]
    for start, end in (
        ((0.0, 0.0), (0.5, 88.0)),
        ((0.0, 0.0), (44.8125, 0.0)),
        ((44.8125, 0.0), (45.3125, 88.0)),
        ((0.5, 88.0), (45.3125, 88.0)),
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


def mirror_order() -> shower_batch.ProcessOrder:
    order = shower_batch.ProcessOrder(AW_ORDER, JOB, "HUBERT WHITLOCK BUILDERS, INC")
    order.items[1] = shower_batch.ProcessItem(
        1,
        width_text='45" 5/16',
        height_text='88"',
        processing=["Flat Polish side(s) 1/2/3/4", "2'' Hole x 1"],
        machine_hints=["Waterjet"],
    )
    return order


class OutOfSquareDimensionMatchTests(unittest.TestCase):
    def test_supplied_mirror_order_reconciles_aw_overall_to_sketch_edge_size(self) -> None:
        with workspace_temporary_directory() as temp_name:
            folder = Path(temp_name)
            dxf = folder / f"{JOB}_1.dxf"
            write_oos_mirror_dxf(dxf)
            order = mirror_order()
            # The sketch's printed summary is 44-7/8 x 88-5/16, while the
            # drawing itself carries 44-13/16 edges and a 1/2 OOS callout.
            actual = [(1, 44.875, 88.3125)]

            self.assertFalse(shower_batch.process_dimensions_fit_values(order, actual))
            self.assertTrue(shower_batch.reconcile_out_of_square_dimension_match(order, actual, folder))
            note = order.dimension_match_notes[1]
            self.assertIn("DXF OOS geometry", note)
            self.assertIn("OOS shift 0.5 in", note)
            self.assertIn("edge 44.8125 x 88", note)

    def test_plain_wrong_size_does_not_get_oos_exception(self) -> None:
        with workspace_temporary_directory() as temp_name:
            folder = Path(temp_name)
            dxf = folder / f"{JOB}_1.dxf"
            # Rectangular 45-5/16 x 88 has no OOS shift, so it must not explain
            # a smaller sketch dimension.
            dxf.write_text(
                "0\nSECTION\n2\nENTITIES\n"
                "0\nLINE\n8\n0\n10\n0\n20\n0\n11\n45.3125\n21\n0\n"
                "0\nLINE\n8\n0\n10\n45.3125\n20\n0\n11\n45.3125\n21\n88\n"
                "0\nLINE\n8\n0\n10\n45.3125\n20\n88\n11\n0\n21\n88\n"
                "0\nLINE\n8\n0\n10\n0\n20\n88\n11\n0\n21\n0\n"
                "0\nENDSEC\n0\nEOF\n",
                encoding="ascii",
            )
            self.assertFalse(
                shower_batch.reconcile_out_of_square_dimension_match(
                    mirror_order(),
                    [(1, 44.875, 88.3125)],
                    folder,
                )
            )

    def test_oos_exception_rejects_unrelated_sketch_dimensions(self) -> None:
        with workspace_temporary_directory() as temp_name:
            folder = Path(temp_name)
            write_oos_mirror_dxf(folder / f"{JOB}_1.dxf")
            self.assertFalse(
                shower_batch.reconcile_out_of_square_dimension_match(
                    mirror_order(),
                    [(1, 40.0, 80.0)],
                    folder,
                )
            )

    def test_manual_dimension_override_bypasses_validation_but_is_recorded(self) -> None:
        order = mirror_order()
        actual = [(1, 40.0, 80.0)]
        config = {
            "dimension_match_overrides": {
                AW_ORDER: {"enabled": True, "job_name": JOB},
            }
        }
        shower_batch.validate_process_order_pdf_dimension_values(
            actual,
            order,
            Path("Glass Order example.pdf"),
            folder=Path("."),
            config=config,
        )
        self.assertTrue(order.manual_dimension_match_override_used)

    def test_manual_override_is_merged_separately_from_machine_overrides(self) -> None:
        base = {"item_overrides": {AW_ORDER: {"1": {"machine": "WJ"}}}}
        manual = {"dimension_match_overrides": {AW_ORDER: {"enabled": True}}}
        merged = programmer.merge_item_overrides(base, manual)
        self.assertTrue(merged["dimension_match_overrides"][AW_ORDER]["enabled"])
        self.assertEqual(merged["item_overrides"][AW_ORDER]["1"]["machine"], "WJ")

    def test_duplicate_job_dimension_selector_remains_strict(self) -> None:
        order = mirror_order()
        # Automatic OOS reconciliation is deliberately not part of the generic
        # dimension matcher used to choose between duplicate-Job PDFs.
        self.assertFalse(
            shower_batch.process_dimensions_fit_values(order, [(1, 44.875, 88.3125)])
        )


if __name__ == "__main__":
    unittest.main()
