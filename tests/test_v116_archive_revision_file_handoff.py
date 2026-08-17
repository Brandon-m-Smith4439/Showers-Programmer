from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_batch
import shower_programmer_gui as gui


def make_order(aw: str) -> shower_batch.ProcessOrder:
    order = shower_batch.ProcessOrder(aw, f"JOB {aw}", "Customer")
    order.items[1] = shower_batch.ProcessItem(
        item=1,
        width_text="24",
        height_text="72",
        delivery_date="8/17/2026",
        customer="Customer",
        processing=["DENVER 2"],
        machine_hints=["DENVER 2"],
    )
    return order


def make_revision_entry(
    archive_dir: Path,
    process_file: Path,
    stamp: datetime,
    revision: int,
    order: shower_batch.ProcessOrder,
    order_files: list[Path] | None = None,
) -> dict[str, object]:
    return {
        "archive_name": stamp.strftime("%m.%d.%y"),
        "archive_date": stamp,
        "batch_name": process_file.name,
        "batch_key": f"rev-{revision}",
        "process_list_files": [process_file],
        "order_archive_dir": archive_dir,
        "order_files": list(order_files or []),
        "order": order,
    }


class Version116ArchiveRevisionFileHandoffTests(unittest.TestCase):
    def test_consolidated_children_keep_all_revision_order_directories(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            temp = Path(raw)
            base = datetime(2026, 8, 17)
            entries: list[dict[str, object]] = []
            for revision in range(5):
                archive_dir = temp / f"orders-{revision}"
                archive_dir.mkdir()
                process = temp / f"process-{revision}" / "Batch 6338.xlsx"
                process.parent.mkdir()
                process.write_bytes(b"process")
                stamp = base - timedelta(days=4 - revision)
                entries.append(
                    make_revision_entry(
                        archive_dir,
                        process,
                        stamp,
                        revision,
                        make_order("633801"),
                    )
                )

            groups = gui.ShowerProgrammerApp.consolidate_archive_batch_entries(entries)
            self.assertEqual(len(groups), 1)
            child = groups[0]["children"][0]
            self.assertEqual(child["_archive_batch_revision_count"], 5)
            self.assertEqual(len(child["_archive_order_revision_sources"]), 5)
            self.assertEqual(len(child["_archive_batch_revision_order_dirs"]), 5)

    def test_test_mode_falls_back_to_older_revision_folders_for_pdf_and_dxf(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            temp = Path(raw)
            base = datetime(2026, 8, 17)
            entries: list[dict[str, object]] = []
            orders = [make_order("633801"), make_order("633802"), make_order("633803")]
            revision_dirs: list[Path] = []

            for revision in range(5):
                archive_dir = temp / f"archive-{revision}"
                archive_dir.mkdir()
                revision_dirs.append(archive_dir)
                process = archive_dir / "Batch 6338.xlsx"
                process.write_bytes(b"process")
                stamp = base - timedelta(days=4 - revision)
                for order in orders:
                    entries.append(
                        make_revision_entry(
                            archive_dir,
                            process,
                            stamp,
                            revision,
                            make_order(order.aw_order),
                        )
                    )

            # The newest revision contains only the process list. The actual source
            # files live in older archive dates, which is the production failure this
            # release must recover from.
            source_locations = {
                "633801": revision_dirs[0],
                "633802": revision_dirs[1],
                "633803": revision_dirs[2],
            }
            for aw_order, archive_dir in source_locations.items():
                (archive_dir / f"Glass Order {aw_order}.pdf").write_bytes(b"pdf")
                (archive_dir / f"{aw_order}_P1.dxf").write_bytes(b"dxf")

            groups = gui.ShowerProgrammerApp.consolidate_archive_batch_entries(entries)
            children = groups[0]["children"]
            order_dir = temp / "test" / "Input" / "Orders"
            process_dir = temp / "test" / "Input" / "Process List"
            restored, process_files, warnings = gui.ShowerProgrammerApp.copy_archived_batch_for_testing(
                children,
                order_dir,
                process_dir,
            )

            self.assertEqual(len(process_files), 1)
            self.assertEqual(process_files[0].suffix.lower(), ".xlsx")
            self.assertEqual(len(restored), 6)
            self.assertEqual(
                sorted(path.name for path in restored),
                sorted(
                    [
                        "Glass Order 633801.pdf",
                        "633801_P1.dxf",
                        "Glass Order 633802.pdf",
                        "633802_P1.dxf",
                        "Glass Order 633803.pdf",
                        "633803_P1.dxf",
                    ]
                ),
            )
            self.assertEqual(warnings, [])
            self.assertEqual(gui.ShowerProgrammerApp.archived_batch_test_missing_sources(children, order_dir), [])

    def test_prepare_test_mode_refuses_process_list_only_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            temp = Path(raw)
            archive_dir = temp / "archive"
            archive_dir.mkdir()
            process = archive_dir / "Batch 6338.xlsx"
            process.write_bytes(b"process")
            stamp = datetime(2026, 8, 17)
            entries = [
                make_revision_entry(archive_dir, process, stamp, 1, make_order("633801")),
                make_revision_entry(archive_dir, process, stamp, 1, make_order("633802")),
                make_revision_entry(archive_dir, process, stamp, 1, make_order("633803")),
            ]

            with self.assertRaisesRegex(RuntimeError, "required PDF/DXF source files"):
                gui.ShowerProgrammerApp.prepare_archived_batch_test_mode(
                    entries,
                    batch_name="Batch 6338.xlsx",
                    archive_name="08.17.26",
                    runtime_root=temp / "runtime",
                )


if __name__ == "__main__":
    unittest.main()
