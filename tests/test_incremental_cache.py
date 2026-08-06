from __future__ import annotations

import os
import shutil
import sys
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

import shower_batch
import shower_cache
import shower_programmer as programmer
import shower_programmer_gui
from openpyxl import Workbook


@contextmanager
def writable_test_directory():
    path = ROOT / "tmp" / "tests" / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shower_cache.configure(None)
        shutil.rmtree(path, ignore_errors=True)


class IncrementalCacheTests(unittest.TestCase):
    def test_pdf_piece_dimensions_are_extracted_once_for_unchanged_sketch(self) -> None:
        with writable_test_directory() as temp:
            source = temp / "Glass Order 900001.pdf"
            source.write_bytes(b"stable pdf placeholder")
            shower_cache.configure(temp / "cache")
            dimensions = [(1, 42.0, 83.0)]
            with (
                mock.patch.object(shower_batch, "PdfReader", return_value=object()) as reader,
                mock.patch.object(
                    shower_batch,
                    "pdf_piece_dimensions",
                    return_value=dimensions,
                ) as extractor,
            ):
                first = shower_batch.cached_pdf_piece_dimensions(source)
                second = shower_batch.cached_pdf_piece_dimensions(source)
            self.assertEqual(first, dimensions)
            self.assertEqual(second, dimensions)
            reader.assert_called_once_with(str(source))
            extractor.assert_called_once()

    def test_preview_orders_enumerates_local_pdfs_once_for_entire_scan(self) -> None:
        with writable_test_directory() as temp:
            pdf = temp / "Glass Order 900001.pdf"
            pdf.write_bytes(b"preview placeholder")
            orders = [
                shower_batch.ProcessOrder("900001", "12345678 TEST A", "Customer"),
                shower_batch.ProcessOrder("900002", "12345679 TEST B", "Customer"),
            ]
            original_rglob = Path.rglob
            calls: list[tuple[Path, str]] = []

            def counted_rglob(path: Path, pattern: str):
                calls.append((path, pattern))
                return original_rglob(path, pattern)

            with (
                mock.patch.object(Path, "rglob", counted_rglob),
                mock.patch.object(
                    shower_batch,
                    "preview_process_order_pdf",
                    return_value=pdf,
                ),
            ):
                previews = shower_batch.preview_orders(orders, temp)
            self.assertEqual(len(previews), 2)
            self.assertEqual(calls, [(temp, "*.pdf")])

    def test_local_pdf_filename_matches_before_any_pdf_is_opened(self) -> None:
        with writable_test_directory() as temp:
            (temp / "A unrelated.pdf").write_bytes(b"not a real pdf")
            (temp / "Glass Order 900001.pdf").write_bytes(b"not a real pdf")
            order = shower_batch.ProcessOrder("900001", "12345678 TEST", "Customer")
            order.items[1] = shower_batch.ProcessItem(1)
            with mock.patch.object(
                programmer,
                "extract_first_page_text",
                side_effect=AssertionError("filename matches must be exhausted first"),
            ):
                requirements = shower_programmer_gui.ShowerProgrammerApp.missing_order_input_requirements(
                    temp,
                    [order],
                )
            self.assertFalse(requirements["900001"]["pdf"])

    def test_duplicate_file_hashes_are_reused_on_repeat_shared_scan(self) -> None:
        with writable_test_directory() as temp:
            source = temp / "Showers Programmer Input"
            source.mkdir()
            canonical = source / "Glass Order 900001.pdf"
            duplicate = source / "Glass Order 900001_1.pdf"
            canonical.write_bytes(b"identical content")
            duplicate.write_bytes(b"identical content")
            shower_cache.configure(temp / "cache")
            with mock.patch.object(
                shower_cache,
                "file_sha256",
                wraps=shower_cache.file_sha256,
            ) as hasher:
                first = shower_programmer_gui.ShowerProgrammerApp.import_duplicate_groups(
                    [canonical, duplicate]
                )
                second = shower_programmer_gui.ShowerProgrammerApp.import_duplicate_groups(
                    [canonical, duplicate]
                )
            self.assertEqual(len(first), 1)
            self.assertEqual(len(second), 1)
            self.assertEqual(hasher.call_count, 2)

    def test_legacy_xls_conversion_uses_hidden_powershell(self) -> None:
        command = shower_batch.hidden_powershell_command(
            "Write-Output test",
            bypass_execution_policy=True,
        )
        self.assertIn("-NonInteractive", command)
        self.assertEqual(command[command.index("-WindowStyle") + 1], "Hidden")
        self.assertEqual(command[command.index("-ExecutionPolicy") + 1], "Bypass")
        self.assertEqual(command[-2:], ["-Command", "Write-Output test"])
        options = shower_batch.hidden_windows_subprocess_options()
        if os.name == "nt":
            self.assertTrue(
                int(options.get("creationflags", 0))
                & int(getattr(shower_batch.subprocess, "CREATE_NO_WINDOW", 0x08000000))
            )

    def test_file_cache_reuses_unchanged_content_after_timestamp_change(self) -> None:
        with writable_test_directory() as temp:
            source = temp / "source.txt"
            source.write_text("same content", encoding="utf-8")
            shower_cache.configure(temp / "cache")
            shower_cache.reset_stats()
            shower_cache.store("test", source, {"value": 7})
            self.assertEqual(shower_cache.load("test", source), {"value": 7})
            stat = source.stat()
            os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
            self.assertEqual(shower_cache.load("test", source), {"value": 7})
            stats = shower_cache.stats()
            self.assertEqual(stats["hits"], 1)
            self.assertEqual(stats["hash_hits"], 1)

    def test_process_order_cache_round_trip_preserves_evidence(self) -> None:
        order = shower_batch.ProcessOrder("900001", "12345678 TEST", "Customer")
        item = shower_batch.ProcessItem(
            2,
            width_text='42"',
            height_text='83"',
            delivery_date="08/03/2026",
            customer="Customer",
            processing=["1/4 Mirror Annealed"],
            machine_hints=["WJ"],
            rows=[17],
        )
        order.items[2] = item
        restored = shower_batch.process_orders_from_cache(shower_batch.process_orders_to_cache([order]))
        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0].items[2].processing, ["1/4 Mirror Annealed"])
        self.assertEqual(restored[0].items[2].machine_hints, ["WJ"])
        self.assertEqual(restored[0].items[2].rows, [17])

    def test_xlsx_process_list_is_parsed_once_then_reused(self) -> None:
        with writable_test_directory() as temp:
            workbook_path = temp / "process.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            row = [""] * 22
            row[2] = '42"'
            row[3] = '83"'
            row[6] = "900001-1"
            row[13] = "12345678 TEST"
            row[21] = "DENVER 1"
            sheet.append(row)
            workbook.save(workbook_path)
            workbook.close()
            shower_cache.configure(temp / "cache")
            progress: list[str] = []
            first = shower_batch.load_process_orders_from_file(
                workbook_path,
                lambda stage, _path, _detail: progress.append(stage),
            )
            second = shower_batch.load_process_orders_from_file(
                workbook_path,
                lambda stage, _path, _detail: progress.append(stage),
            )
            self.assertEqual([order.aw_order for order in first], ["900001"])
            self.assertEqual([order.aw_order for order in second], ["900001"])
            self.assertIn("loaded", progress)
            self.assertIn("cached", progress)

    def test_persisted_dxf_geometry_restores_hashable_coordinate_tuples(self) -> None:
        with writable_test_directory() as temp:
            source = temp / "preview.dxf"
            source.write_text(
                "0\nSECTION\n2\nENTITIES\n"
                "0\nLINE\n10\n0\n20\n0\n11\n30\n21\n0.125\n"
                "0\nLINE\n10\n30\n20\n0.125\n11\n30\n21\n80\n"
                "0\nLINE\n10\n30\n20\n80\n11\n0\n21\n80\n"
                "0\nLINE\n10\n0\n20\n80\n11\n0\n21\n0\n"
                "0\nENDSEC\n0\nEOF\n",
                encoding="ascii",
            )
            shower_cache.configure(temp / "cache")
            app = shower_programmer_gui.ShowerProgrammerApp.__new__(
                shower_programmer_gui.ShowerProgrammerApp
            )
            first = app.order_review_dxf_preview_data(source, {})
            second = app.order_review_dxf_preview_data(source, {})
            self.assertEqual(first["segments"], second["segments"])
            self.assertIsInstance(second["segments"][0][0], tuple)
            highlighted = app.out_of_square_preview_segments(second["segments"], 80.0)
            self.assertTrue(highlighted)

    def test_shared_folder_is_indexed_once_and_copy_suffix_duplicates_are_grouped(self) -> None:
        with writable_test_directory() as temp:
            source = temp / "Showers Programmer Input"
            source.mkdir()
            names = [
                "Batch 7000.xlsx",
                "89124424 WATER LN 123_1.dxf",
                "89124424 WATER LN 123_1_1.dxf",
                "89124424 WATER LN 123_2.dxf",
                "89124424 WATER LN 123_2_1.dxf",
                "Glass Order 900001.pdf",
                "Glass Order 900001_1.pdf",
                "Glass Order 900002.pdf",
                "Glass Order 900002_1.pdf",
            ]
            for name in names:
                content_name = {
                    "89124424 WATER LN 123_1_1.dxf": "89124424 WATER LN 123_1.dxf",
                    "89124424 WATER LN 123_2_1.dxf": "89124424 WATER LN 123_2.dxf",
                    "Glass Order 900001_1.pdf": "Glass Order 900001.pdf",
                }.get(name, name)
                (source / name).write_text(content_name, encoding="utf-8")
            snapshot = shower_programmer_gui.ShowerProgrammerApp.index_import_source_folder(source)
            self.assertEqual(snapshot["entry_count"], len(names))
            groups = snapshot["duplicate_groups"]
            self.assertEqual(len(groups), 3)
            duplicate_names = {
                path.name
                for group in groups
                for path in group["duplicates"]
            }
            self.assertEqual(
                duplicate_names,
                {
                    "89124424 WATER LN 123_1_1.dxf",
                    "89124424 WATER LN 123_2_1.dxf",
                    "Glass Order 900001_1.pdf",
                },
            )
            self.assertNotIn(
                "Glass Order 900002_1.pdf",
                duplicate_names,
                "A copy-suffixed file with different content is a separate order, not a duplicate.",
            )
            original_source = shower_programmer_gui.ShowerProgrammerApp.EDI_IMPORT_ORDERS_DIR
            try:
                shower_programmer_gui.ShowerProgrammerApp.EDI_IMPORT_ORDERS_DIR = source
                selected = source / "89124424 WATER LN 123_1_1.dxf"
                deleted, warnings = shower_programmer_gui.ShowerProgrammerApp.remove_import_duplicate_files(
                    [selected]
                )
            finally:
                shower_programmer_gui.ShowerProgrammerApp.EDI_IMPORT_ORDERS_DIR = original_source
            self.assertEqual(deleted, [selected])
            self.assertEqual(warnings, [])
            self.assertFalse(selected.exists())
            self.assertTrue((source / "89124424 WATER LN 123_1.dxf").exists())

    def test_unchanged_process_list_is_not_recopied_after_source_timestamp_refresh(self) -> None:
        with writable_test_directory() as temp:
            source = temp / "Showers Programmer Input"
            target = temp / "Process List"
            source.mkdir()
            target.mkdir()
            source_file = source / "Batch 7000.xlsx"
            target_file = target / source_file.name
            source_file.write_bytes(b"same process list")
            target_file.write_bytes(b"same process list")
            source_time = target_file.stat().st_mtime_ns + 10_000_000
            os.utime(source_file, ns=(source_time, source_time))
            original_source = shower_programmer_gui.ShowerProgrammerApp.EDI_IMPORT_ORDERS_DIR
            try:
                shower_programmer_gui.ShowerProgrammerApp.EDI_IMPORT_ORDERS_DIR = source
                snapshot = shower_programmer_gui.ShowerProgrammerApp.index_import_source_folder(source)
                summary = shower_programmer_gui.ShowerProgrammerApp.copy_process_lists_from_import_folder(
                    target,
                    import_snapshot=snapshot,
                )
            finally:
                shower_programmer_gui.ShowerProgrammerApp.EDI_IMPORT_ORDERS_DIR = original_source
            self.assertEqual(summary["copied"], [])
            self.assertEqual(summary["skipped"], 1)
            self.assertEqual(target_file.stat().st_mtime_ns, source_file.stat().st_mtime_ns)

    def test_missing_pdf_is_recovered_even_when_the_order_dxf_is_already_local(self) -> None:
        with writable_test_directory() as temp:
            source = temp / "Showers Programmer Input"
            target = temp / "Orders"
            source.mkdir()
            target.mkdir()
            dxf_name = "89124424 WATER LN 123_1.dxf"
            second_dxf_name = "89124424 WATER LN 123_2.dxf"
            pdf_name = "89124424 WATER LN 123.pdf"
            (source / dxf_name).write_text("0\nEOF\n", encoding="ascii")
            (source / second_dxf_name).write_text("0\nEOF\n", encoding="ascii")
            (source / pdf_name).write_text("network pdf placeholder", encoding="utf-8")
            (target / dxf_name).write_text("0\nEOF\n", encoding="ascii")
            order = shower_batch.ProcessOrder("900001", "89124424 WATER LN 123", "Customer")
            order.items[1] = shower_batch.ProcessItem(1)
            order.items[2] = shower_batch.ProcessItem(2)
            requirements = shower_programmer_gui.ShowerProgrammerApp.missing_order_input_requirements(
                target,
                [order],
            )
            self.assertTrue(requirements["900001"]["pdf"])
            self.assertEqual(requirements["900001"]["dxf_items"], [2])
            original_source = shower_programmer_gui.ShowerProgrammerApp.EDI_IMPORT_ORDERS_DIR
            try:
                shower_programmer_gui.ShowerProgrammerApp.EDI_IMPORT_ORDERS_DIR = source
                snapshot = shower_programmer_gui.ShowerProgrammerApp.index_import_source_folder(source)
                summary = shower_programmer_gui.ShowerProgrammerApp.copy_edi_orders_for_process_orders(
                    target,
                    [order],
                    import_snapshot=snapshot,
                    missing_requirements=requirements,
                )
            finally:
                shower_programmer_gui.ShowerProgrammerApp.EDI_IMPORT_ORDERS_DIR = original_source
            self.assertTrue((target / pdf_name).exists())
            self.assertTrue((target / second_dxf_name).exists())
            self.assertEqual(
                {path.name for path in summary["copied"]},
                {pdf_name, second_dxf_name},
            )
            self.assertEqual(summary["considered"], 2)

    def test_completed_converted_batch_deletes_matching_network_xls(self) -> None:
        with writable_test_directory() as temp:
            source = temp / "Showers Programmer Input"
            local = temp / "Process List"
            source.mkdir()
            local.mkdir()
            network_xls = source / "Batch 7000.xls"
            local_xlsx = local / "Batch 7000.xlsx"
            network_xls.write_bytes(b"legacy process list")
            local_xlsx.write_bytes(b"converted process list")
            order = shower_batch.ProcessOrder("900001", "12345678 MIRROR JOB", "Customer")
            order.items[1] = shower_batch.ProcessItem(1, machine_hints=["Waterjet"])
            plan = {"name": "Batch 7000", "files": [local_xlsx], "orders": [order]}
            original_source = shower_programmer_gui.ShowerProgrammerApp.EDI_IMPORT_ORDERS_DIR
            try:
                shower_programmer_gui.ShowerProgrammerApp.EDI_IMPORT_ORDERS_DIR = source
                deleted, warnings = shower_programmer_gui.ShowerProgrammerApp.clear_import_staging_folder(
                    [],
                    include_process_lists=False,
                    completed_process_batches=[plan],
                    source_files=[network_xls],
                )
            finally:
                shower_programmer_gui.ShowerProgrammerApp.EDI_IMPORT_ORDERS_DIR = original_source

            self.assertEqual(deleted, [network_xls])
            self.assertEqual(warnings, [])
            self.assertFalse(network_xls.exists())


if __name__ == "__main__":
    unittest.main()
