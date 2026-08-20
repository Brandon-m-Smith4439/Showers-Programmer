from __future__ import annotations

import sys
import unittest
import uuid
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_batch
from shower_programmer_gui import ShowerProgrammerApp


class ExactOrderCleanupTests(unittest.TestCase):
    def test_prepare_worker_hands_validated_local_names_to_network_lookup(self) -> None:
        base = ROOT / "tests" / "_verification" / f"v130-worker-handoff-{uuid.uuid4().hex[:8]}"
        local = base / "local"
        shared = base / "shared"
        process_lists = base / "process"
        output = base / "output"
        for path in (local, shared, process_lists, output):
            path.mkdir(parents=True)
        local_pdf = local / "Glass Order 90000000 WORKER JOB.pdf"
        local_pdf.write_bytes(b"local")
        network_pdf = shared / local_pdf.name
        network_pdf.write_bytes(b"network")
        order = shower_batch.ProcessOrder("INPUT-WORKER", "90000000 WORKER JOB", "Input file only")
        setattr(order, "process_list_missing", True)
        setattr(order, "source_pdf", local_pdf)

        app = ShowerProgrammerApp.__new__(ShowerProgrammerApp)
        app.queue_scan_progress = lambda *_args, **_kwargs: None
        with mock.patch.object(app, "matching_order_files", return_value=[local_pdf]), mock.patch.object(
            app,
            "network_input_files_for_orders",
            return_value=[network_pdf],
        ) as network_lookup:
            result = app.worker_prepare_local_order_delete(
                [order],
                local,
                process_lists,
                output,
                shared,
                True,
            )

        network_lookup.assert_called_once_with(shared, [order], known_local_files=[local_pdf])
        self.assertEqual(result["files"], [local_pdf])
        self.assertEqual(result["network_files"], [network_pdf])

    def test_known_local_handoff_skips_network_scan_and_pdf_correlation(self) -> None:
        base = ROOT / "tests" / "_verification" / f"v130-order-cleanup-{uuid.uuid4().hex[:8]}"
        local = base / "local"
        shared = base / "shared"
        local.mkdir(parents=True)
        shared.mkdir(parents=True)

        names = [
            "Glass Order 90000001 SAMPLE JOB.pdf",
            "90000001 SAMPLE JOB_1.dxf",
        ]
        local_files = []
        for name in names:
            local_path = local / name
            network_path = shared / name
            local_path.write_bytes(name.encode("ascii"))
            network_path.write_bytes(name.encode("ascii"))
            local_files.append(local_path)
        unrelated = shared / "Glass Order 99999999 KEEP ME.pdf"
        unrelated.write_bytes(b"unrelated")

        order = shower_batch.ProcessOrder(
            "INPUT-V130",
            "90000001 SAMPLE JOB",
            "Input file only",
        )
        setattr(order, "process_list_missing", True)
        setattr(order, "source_pdf", local_files[0])

        with mock.patch.object(
            ShowerProgrammerApp,
            "index_import_source_folder_bounded",
            side_effect=AssertionError("exact cleanup must not enumerate the shared folder"),
        ), mock.patch.object(
            ShowerProgrammerApp,
            "matching_order_files_bounded",
            side_effect=AssertionError("exact cleanup must not reopen network PDFs"),
        ):
            matched = ShowerProgrammerApp.network_input_files_for_orders(
                shared,
                [order],
                known_local_files=local_files,
            )

        self.assertEqual({path.name for path in matched}, set(names))
        self.assertTrue(unrelated.exists())

    def test_source_pdf_name_is_enough_when_local_match_list_is_empty(self) -> None:
        base = ROOT / "tests" / "_verification" / f"v130-source-pdf-{uuid.uuid4().hex[:8]}"
        local = base / "local"
        shared = base / "shared"
        local.mkdir(parents=True)
        shared.mkdir(parents=True)
        source_pdf = local / "Glass Order 90000002 SECOND JOB.pdf"
        source_pdf.write_bytes(b"local")
        network_pdf = shared / source_pdf.name
        network_pdf.write_bytes(b"network")

        order = shower_batch.ProcessOrder("INPUT-V130-B", "90000002 SECOND JOB", "Input file only")
        setattr(order, "process_list_missing", True)
        setattr(order, "source_pdf", source_pdf)

        with mock.patch.object(
            ShowerProgrammerApp,
            "index_import_source_folder_bounded",
            side_effect=AssertionError("source PDF should provide the exact network name"),
        ):
            matched = ShowerProgrammerApp.network_input_files_for_orders(shared, [order])

        self.assertEqual(matched, [network_pdf])


if __name__ == "__main__":
    unittest.main()
