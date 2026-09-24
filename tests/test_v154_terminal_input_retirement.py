from __future__ import annotations

import os
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_batch
import shower_programmer as programmer
import shower_programmer_gui as gui
import shower_state


class TerminalInputRetirementTests(unittest.TestCase):
    @staticmethod
    def process_row(order_item: str, job_name: str, machine: str) -> list[str]:
        row = [""] * 22
        row[2] = '42"'
        row[3] = '83"'
        row[6] = order_item
        row[7] = "Flat Polish side(s) 1/2/3/4"
        row[10] = "Customer"
        row[13] = job_name
        row[21] = machine
        return row

    def test_letter_suffix_before_revision_is_an_exact_job_identity(self) -> None:
        self.assertEqual(programmer.extract_job_number("90027720M.2 3107 COLVERFIELD"), "90027720M.2")
        self.assertTrue(programmer.text_contains_job_number("90027720M.2 panel", "90027720M.2"))
        self.assertFalse(programmer.text_contains_job_number("90027720M.3 panel", "90027720M.2"))

    def test_non_waterjet_mirror_rows_remain_available_for_retirement_guard(self) -> None:
        rows = [
            ['1/4" Mirror'],
            self.process_row("900001-1", "12345678M MIRROR JOB", "Packing / Shipping"),
        ]

        source_orders = shower_batch.load_process_orders_from_rows(rows)
        self.assertEqual([order.aw_order for order in source_orders], ["900001"])

        legacy_filtered = shower_batch.load_process_orders_from_rows(
            rows,
            include_non_waterjet_mirror=False,
        )
        self.assertEqual(legacy_filtered, [])

    def test_older_exact_production_sketch_requires_no_active_local_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temp_text:
            production = Path(temp_text)
            sketch = production / "900001.pdf"
            sketch.write_bytes(b"finished")
            os.utime(sketch, (100.0, 100.0))

            matches, _warnings, _checked, stale = gui.ShowerProgrammerApp.production_sketch_matches(
                production,
                {"900001"},
                {"900001": 200.0},
            )
            self.assertEqual(matches, {})
            self.assertEqual(stale, 1)

            matches, _warnings, _checked, stale = gui.ShowerProgrammerApp.production_sketch_matches(
                production,
                {"900001"},
                {"900001": 200.0},
                allow_older_aw_orders={"900001"},
            )
            self.assertEqual(matches, {"900001": [sketch]})
            self.assertEqual(stale, 0)

    def test_zero_programming_work_batch_retires_only_without_matching_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_text:
            temp = Path(temp_text)
            order_folder = temp / "Orders"
            process_folder = temp / "Process List"
            output = temp / "Output"
            order_folder.mkdir()
            process_folder.mkdir()
            source = process_folder / "Batch 7000.xls"
            source.write_bytes(b"process-list")
            source_order = shower_batch.ProcessOrder("900001", "12345678M MIRROR JOB", "Customer")
            source_order.items[1] = shower_batch.ProcessItem(1, machine_hints=["Packing / Shipping"])
            batch = {
                "id": "batch-7000",
                "path": source,
                "orders": [],
                "source_orders": [source_order],
                "zero_programming_work": True,
            }

            plans = gui.ShowerProgrammerApp.completed_process_list_batches_from_history(
                [batch], order_folder, output
            )
            self.assertEqual(len(plans), 1)

            (order_folder / "12345678M MIRROR JOB_1.dxf").write_bytes(b"dxf")
            plans = gui.ShowerProgrammerApp.completed_process_list_batches_from_history(
                [batch], order_folder, output
            )
            self.assertEqual(plans, [])

    def test_terminal_dxf_only_input_moves_to_dated_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_text:
            temp = Path(temp_text)
            order_folder = temp / "Orders"
            output = temp / "Output"
            order_folder.mkdir()
            source = order_folder / "90027720M.2 3107 COLVERFIELD_1.dxf"
            source.write_bytes(b"dxf")
            old = time.time() - 3600.0
            os.utime(source, (old, old))
            store = shower_state.StateStore.for_output(output)
            store.transition_order(
                "INPUT-TEST",
                shower_state.LifecycleState.DELETED_LOCAL,
                reason="test",
                job_name="Glass Order 90027720M.2 3107 COLVERFIELD",
            )

            archived, warnings = gui.ShowerProgrammerApp.archive_terminal_orphan_dxfs(
                order_folder,
                output,
                [],
            )

            self.assertEqual(warnings, [])
            self.assertEqual(len(archived), 1)
            self.assertFalse(source.exists())
            self.assertTrue(archived[0].exists())

    def test_active_job_prevents_terminal_orphan_sweep(self) -> None:
        with tempfile.TemporaryDirectory() as temp_text:
            temp = Path(temp_text)
            order_folder = temp / "Orders"
            output = temp / "Output"
            order_folder.mkdir()
            source = order_folder / "90027720M.2 3107 COLVERFIELD_1.dxf"
            source.write_bytes(b"dxf")
            old = time.time() - 3600.0
            os.utime(source, (old, old))
            store = shower_state.StateStore.for_output(output)
            store.transition_order(
                "INPUT-TEST",
                shower_state.LifecycleState.DELETED_LOCAL,
                reason="test",
                job_name="Glass Order 90027720M.2 3107 COLVERFIELD",
            )
            active = shower_batch.ProcessOrder("900999", "90027720M.2 3107 COLVERFIELD", "Customer")

            archived, warnings = gui.ShowerProgrammerApp.archive_terminal_orphan_dxfs(
                order_folder,
                output,
                [active],
            )

            self.assertEqual(warnings, [])
            self.assertEqual(archived, [])
            self.assertTrue(source.exists())

    def test_version_154_release_marker_is_retained(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        marker = "VERSION_1_54_TERMINAL_INPUT_RETIREMENT"

        self.assertGreaterEqual(version["version_number"], 154)
        self.assertIn(
            marker,
            (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
