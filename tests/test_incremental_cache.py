from __future__ import annotations

import json
import os
import shutil
import sys
import threading
import time
import unittest
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
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
            name_groups = snapshot["duplicate_name_groups"]
            self.assertEqual(len(name_groups), 4)
            self.assertEqual(snapshot["duplicate_groups"], [])
            groups = shower_programmer_gui.ShowerProgrammerApp.import_duplicate_groups(
                snapshot["order_files"]
            )
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

    def test_unlabeled_network_pdf_is_staged_before_text_inspection(self) -> None:
        with writable_test_directory() as temp:
            source = temp / "Showers Programmer Input"
            target = temp / "Input" / "Orders"
            source.mkdir()
            target.mkdir(parents=True)
            network_pdf = source / "Unlabeled sketch.pdf"
            network_pdf.write_bytes(b"network placeholder")
            order = shower_batch.ProcessOrder("900001", "89124424 WATER LN 123", "Customer")
            requirements = {"900001": {"pdf": True, "dxf_items": []}}
            inspected: list[Path] = []

            def local_pdf_text(path: Path) -> str:
                inspected.append(Path(path))
                return "A&W Order 900001 Job Nr 89124424 WATER LN 123"

            original_source = shower_programmer_gui.ShowerProgrammerApp.EDI_IMPORT_ORDERS_DIR
            try:
                shower_programmer_gui.ShowerProgrammerApp.EDI_IMPORT_ORDERS_DIR = source
                snapshot = shower_programmer_gui.ShowerProgrammerApp.index_import_source_folder(source)
                with mock.patch.object(programmer, "extract_first_page_text", side_effect=local_pdf_text):
                    summary = shower_programmer_gui.ShowerProgrammerApp.copy_edi_orders_for_process_orders(
                        target,
                        [order],
                        import_snapshot=snapshot,
                        missing_requirements=requirements,
                    )
            finally:
                shower_programmer_gui.ShowerProgrammerApp.EDI_IMPORT_ORDERS_DIR = original_source

            self.assertTrue((target / network_pdf.name).exists())
            self.assertEqual(summary["staged_pdf_count"], 1)
            self.assertTrue(inspected)
            self.assertTrue(all(path.parent != source for path in inspected))

    def test_dxf_side_measurements_convert_mm_geometry_to_fractional_inches(self) -> None:
        segments = [
            ((0.0, 0.0), (2540.0, 0.0)),
            ((2540.0, 0.0), (2540.0, 1066.8)),
            ((2540.0, 1066.8), (0.0, 1066.8)),
            ((0.0, 1066.8), (0.0, 0.0)),
        ]
        measurements = shower_programmer_gui.ShowerProgrammerApp.dxf_cardinal_side_measurements(
            segments,
            1.0 / 25.4,
        )
        self.assertEqual(
            {side: shower_programmer_gui.ShowerProgrammerApp.format_inches(value) for side, value in measurements.items()},
            {"top": '100"', "bottom": '100"', "left": '42"', "right": '42"'},
        )

    def test_hinge_detection_settings_preserve_config_and_normalize_codes(self) -> None:
        with writable_test_directory() as temp:
            path = temp / "shower_programmer_config.json"
            path.write_text(
                '{"rules":{"denver_min_inches":6.125,"hinge_label_keywords":["GEN037"]},"item_overrides":{}}',
                encoding="utf-8",
            )

            codes = shower_programmer_gui.ShowerProgrammerApp.save_hinge_detection_codes(
                path,
                "gen037\nJRG037\nGEN180\ngen037",
                {"GEN037": "down", "JRG037": "up", "GEN180": "down"},
            )
            saved = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(codes, ["GEN037", "JRG037", "GEN180"])
            self.assertEqual(saved["rules"]["hinge_label_keywords"], codes)
            self.assertEqual(
                saved["rules"]["hinge_label_orientations"],
                {"GEN037": "down", "JRG037": "up", "GEN180": "down"},
            )
            self.assertEqual(saved["rules"]["denver_min_inches"], 6.125)
            self.assertEqual(saved["item_overrides"], {})

    def test_hinge_detection_guarded_add_and_remove(self) -> None:
        app = shower_programmer_gui.ShowerProgrammerApp
        added = app.add_hinge_detection_code(["GEN037"], " new037 ")

        self.assertEqual(added, ["GEN037", "NEW037"])
        self.assertEqual(
            app.remove_hinge_detection_code(added, "NEW037"),
            ["GEN037"],
        )
        with self.assertRaisesRegex(ValueError, "already"):
            app.add_hinge_detection_code(added, "GEN037")
        self.assertEqual(app.remove_hinge_detection_code(["GEN037", "PPH"], "PPH"), ["GEN037"])

    def test_hinge_code_matching_tolerates_letter_o_and_zero_and_uses_orientation(self) -> None:
        config = {
            "rules": {
                "hinge_label_keywords": ["COL037", "PPH"],
                "hinge_label_orientations": {"COL037": "down", "PPH": "up"},
            }
        }
        panel = programmer.Panel(1, 2, "AC0L037", 34.125, 95.1875, "DENVER 1")
        panel.hinge_side = "right"
        panel.hinges_up = True

        self.assertTrue(programmer.has_hinge_label_text("Template A: C0L037", config))
        self.assertEqual(programmer.matched_hinge_label_codes("AC0L037", config), ["COL037"])
        programmer.enforce_configured_hinge_orientation(panel, config)

        self.assertFalse(panel.hinges_up)
        self.assertEqual(panel.rotation_degrees, -90)
        self.assertEqual(panel.indicator_corner, "top_right")

    def test_input_only_pdf_becomes_visible_issue_row(self) -> None:
        with writable_test_directory() as temp:
            pdf = temp / "Glass Order Example.pdf"
            pdf.write_bytes(b"pdf")
            with (
                mock.patch.object(shower_programmer_gui.ShowerProgrammerApp, "file_matches_process_orders", return_value=False),
                mock.patch.object(programmer, "extract_aw_order_from_pdf", return_value="237999"),
                mock.patch.object(programmer, "extract_job_from_pdf", return_value="90000000.1 EXAMPLE"),
            ):
                orders, results = shower_programmer_gui.ShowerProgrammerApp.input_only_orders_from_pdfs([pdf], [])

            self.assertEqual([order.aw_order for order in orders], ["237999"])
            self.assertTrue(shower_programmer_gui.ShowerProgrammerApp.is_input_only_order(orders[0]))
            self.assertEqual(results[0].status, "ISSUES")
            self.assertIn("No matching order", results[0].issues[0])

    def test_sketch_refresh_returns_to_editable_overlay_state(self) -> None:
        class Reader:
            pages = [object(), object(), object()]

        source = Path("editable-source.pdf")
        state = {
            "embedded_sketch_preview": True,
            "sketch_preview_path": Path("saved-output.pdf"),
            "show_sketch_marks": True,
        }

        shower_programmer_gui.ShowerProgrammerApp.configure_editable_sketch_preview_state(
            state,
            Reader(),
            source,
        )

        self.assertFalse(state["embedded_sketch_preview"])
        self.assertEqual(state["sketch_preview_path"], source)
        self.assertEqual(state["pdf_page_count"], 3)
        self.assertTrue(shower_programmer_gui.ShowerProgrammerApp.should_draw_sketch_overlays(state))

    def test_manual_wj_machine_change_rewrites_program_in_millimeters(self) -> None:
        with writable_test_directory() as temp:
            source = temp / "source.dxf"
            output = temp / "output.dxf"
            pairs = [
                ("0", "SECTION"),
                ("2", "HEADER"),
                ("9", "$INSUNITS"),
                ("70", "1"),
                ("9", "$MEASUREMENT"),
                ("70", "0"),
                ("0", "ENDSEC"),
                ("0", "SECTION"),
                ("2", "ENTITIES"),
                ("0", "LINE"),
                ("10", "0"),
                ("20", "0"),
                ("11", "10"),
                ("21", "20"),
                ("0", "ENDSEC"),
                ("0", "EOF"),
            ]
            source.write_text(
                "\n".join(value for pair in pairs for value in pair) + "\n",
                encoding="ascii",
            )
            panel = programmer.Panel(1, 0, "", 10.0, 20.0, "WJ")
            panel.source_dxf = source
            panel.output_dxf = output
            panel.rotation_degrees = 0
            config = {
                "dxf": {
                    "waterjet_output_scale": 25.4,
                    "waterjet_insunits": 4,
                    "waterjet_measurement": 1,
                    "default_output_scale": 1,
                    "default_insunits": 1,
                    "default_measurement": 0,
                }
            }

            written = shower_programmer_gui.ShowerProgrammerApp.write_machine_changed_dxfs(
                [panel],
                [1],
                config,
            )
            output_pairs = programmer.read_dxf_pairs(output)
            header_values: dict[str, str] = {}
            for index, pair in enumerate(output_pairs):
                if pair[0].strip() != "9" or pair[1].strip().upper() not in {"$INSUNITS", "$MEASUREMENT"}:
                    continue
                for code, value in output_pairs[index + 1:index + 8]:
                    if code.strip() == "9":
                        break
                    if code.strip() == "70":
                        header_values[pair[1].strip().upper()] = value.strip()
                        break
            coordinates = [
                float(value)
                for code, value in output_pairs
                if code.strip() in {"10", "11", "20", "21"}
            ]

            self.assertEqual(written, [output])
            self.assertEqual(header_values["$INSUNITS"], "4")
            self.assertEqual(header_values["$MEASUREMENT"], "1")
            self.assertAlmostEqual(max(coordinates), 508.0, places=6)

    def test_mirror_non_waterjet_rows_do_not_block_local_process_list_archive(self) -> None:
        with writable_test_directory() as temp:
            order_root = temp / "Orders"
            process_root = temp / "Process List"
            order_root.mkdir()
            process_root.mkdir()
            process_list = process_root / "Batch 7300.xls"
            process_list.write_text("mirror batch", encoding="utf-8")

            def process_row(order_item: str, job_name: str, machine: str) -> list[str]:
                row = [""] * 22
                row[2] = '42"'
                row[3] = '83"'
                row[6] = order_item
                row[7] = "Flat Polish"
                row[10] = "Customer"
                row[13] = job_name
                row[21] = machine
                return row

            orders = shower_batch.load_process_orders_from_rows(
                [
                    ['1/4" Mirror'],
                    process_row("900001-1", "12345678 MIRROR JOB", "Waterjet"),
                    process_row("900002-1", "12345679 PACKING ONLY", "Packing / Shipping"),
                ]
            )
            self.assertEqual([order.aw_order for order in orders], ["900001"])
            order_dxf = order_root / "12345678 MIRROR JOB_1.dxf"
            order_dxf.write_text("DXF", encoding="utf-8")

            class MirrorArchiveApp(shower_programmer_gui.ShowerProgrammerApp):
                def load_processing_history(self):
                    return {"orders": {}}

            app = object.__new__(MirrorArchiveApp)
            app.process_batches = {
                "batch-7300": {
                    "id": "batch-7300",
                    "path": process_list,
                    "name": process_list.name,
                    "orders": orders,
                    "all_orders": orders,
                }
            }
            plans = app.completed_process_list_batches_for_orders(orders)
            archived, warnings = app.archive_sent_input_files_for_orders(
                orders,
                order_root,
                process_root,
                include_process_lists=False,
                completed_process_batches=plans,
            )

            self.assertEqual(len(plans), 1)
            self.assertFalse(process_list.exists())
            self.assertTrue(any(path.name == process_list.name for path in archived))
            self.assertEqual(warnings, [])

    def test_preview_annotation_rectangles_detect_collisions(self) -> None:
        overlaps = shower_programmer_gui.ShowerProgrammerApp.preview_rects_overlap
        self.assertTrue(overlaps((10, 10, 40, 30), (30, 20, 60, 40)))
        self.assertFalse(overlaps((10, 10, 20, 20), (24, 10, 34, 20)))

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

    def test_validated_network_cleanup_deletes_files_concurrently(self) -> None:
        with writable_test_directory() as temp:
            paths = []
            for index in range(4):
                path = temp / f"validated-{index}.pdf"
                path.write_text(str(index), encoding="utf-8")
                paths.append(path)
            lock = threading.Lock()
            active = 0
            max_active = 0

            class ConcurrentCleanupApp(shower_programmer_gui.ShowerProgrammerApp):
                @staticmethod
                def unlink_import_path(path: Path) -> None:
                    nonlocal active, max_active
                    with lock:
                        active += 1
                        max_active = max(max_active, active)
                    try:
                        time.sleep(0.04)
                        path.unlink()
                    finally:
                        with lock:
                            active -= 1

            deleted, warnings, timed_out = ConcurrentCleanupApp.delete_import_paths_bounded(
                paths,
                timeout_seconds=1.0,
            )

            self.assertEqual({path.name for path in deleted}, {path.name for path in paths})
            self.assertEqual(warnings, [])
            self.assertEqual(timed_out, [])
            self.assertGreater(max_active, 1)

    def test_cleanup_timeout_keeps_process_list_and_reports_fallback(self) -> None:
        with writable_test_directory() as temp:
            source = temp / "Showers Programmer Input"
            local = temp / "Process List"
            source.mkdir()
            local.mkdir()
            order_dxf = source / "12345678 SLOW JOB_1.dxf"
            network_list = source / "Batch 7100.xlsx"
            local_list = local / "Batch 7100.xlsx"
            order_dxf.write_text("DXF", encoding="utf-8")
            network_list.write_text("network", encoding="utf-8")
            local_list.write_text("local", encoding="utf-8")
            order = shower_batch.ProcessOrder("900071", "12345678 SLOW JOB", "Customer")
            order.items[1] = shower_batch.ProcessItem(1)
            plan = {"name": "Batch 7100", "files": [local_list], "orders": [order]}

            class SlowCleanupApp(shower_programmer_gui.ShowerProgrammerApp):
                EDI_IMPORT_ORDERS_DIR = source

                @staticmethod
                def unlink_import_path(path: Path) -> None:
                    if path.suffix.lower() == ".dxf":
                        time.sleep(0.15)
                    path.unlink(missing_ok=True)

            deleted, warnings = SlowCleanupApp.clear_import_staging_folder(
                [order],
                completed_process_batches=[plan],
                delete_timeout_seconds=0.02,
            )

            self.assertNotIn(network_list, deleted)
            self.assertTrue(network_list.exists())
            self.assertTrue(any("timed out" in warning.lower() for warning in warnings))
            self.assertTrue(any("kept completed process lists" in warning.lower() for warning in warnings))
            time.sleep(0.18)

    def test_network_folder_index_timeout_returns_safe_failure(self) -> None:
        with writable_test_directory() as temp:
            source = temp / "Showers Programmer Input"
            source.mkdir()

            class SlowIndexApp(shower_programmer_gui.ShowerProgrammerApp):
                @classmethod
                def index_import_source_folder(cls, source_dir: Path | None = None) -> dict[str, object]:
                    time.sleep(0.15)
                    return {"source_missing": False, "files": []}

            started = time.perf_counter()
            snapshot = SlowIndexApp.index_import_source_folder_bounded(source, timeout_seconds=0.02)
            elapsed = time.perf_counter() - started

            self.assertTrue(snapshot["source_missing"])
            self.assertTrue(snapshot["cleanup_timed_out"])
            self.assertIn("timed out", str(snapshot["source_error"]).lower())
            self.assertLess(elapsed, 0.1)
            time.sleep(0.16)

    def test_validated_archive_names_avoid_shared_pdf_content_scan(self) -> None:
        with writable_test_directory() as temp:
            source = temp / "Showers Programmer Input"
            source.mkdir()
            matching_pdf = source / "Glass Order TRUE HOMES_88643652 EDGEWATER 1007.pdf"
            matching_dxf = source / "88643652 EDGEWATER 1007_1__P1.dxf"
            unrelated_pdf = source / "customer_export_without_order_in_filename.pdf"
            matching_pdf.write_text("matching", encoding="utf-8")
            matching_dxf.write_text("matching", encoding="utf-8")
            unrelated_pdf.write_text("unrelated", encoding="utf-8")
            order = shower_batch.ProcessOrder("237239", "88643652 EDGEWATER 1007", "TRUE HOMES")
            order.items[1] = shower_batch.ProcessItem(1)

            class ValidatedCleanupApp(shower_programmer_gui.ShowerProgrammerApp):
                EDI_IMPORT_ORDERS_DIR = source

                @classmethod
                def matching_order_files_bounded(cls, *args, **kwargs):
                    raise AssertionError("Validated filenames should avoid shared PDF content matching.")

            deleted, warnings = ValidatedCleanupApp.clear_import_staging_folder(
                [order],
                source_files=[matching_pdf, matching_dxf, unrelated_pdf],
                validated_order_sources_by_aw={
                    "237239": {matching_pdf.name, matching_dxf.name},
                },
            )

            self.assertEqual({path.name for path in deleted}, {matching_pdf.name, matching_dxf.name})
            self.assertEqual(warnings, [])
            self.assertTrue(unrelated_pdf.exists())

    def test_explicit_archive_handoff_never_scans_unrelated_shared_pdfs(self) -> None:
        with writable_test_directory() as temp:
            source = temp / "Showers Programmer Input"
            source.mkdir()
            unrelated_pdf = source / "customer_export_without_order_in_filename.pdf"
            unrelated_pdf.write_text("unrelated", encoding="utf-8")
            order = shower_batch.ProcessOrder("237239", "88643652 EDGEWATER 1007", "TRUE HOMES")

            class ReconciledCleanupApp(shower_programmer_gui.ShowerProgrammerApp):
                EDI_IMPORT_ORDERS_DIR = source

                @classmethod
                def matching_order_files_bounded(cls, *args, **kwargs):
                    raise AssertionError("An explicit local handoff must not inspect shared PDF content.")

            deleted, warnings = ReconciledCleanupApp.clear_import_staging_folder(
                [order],
                source_files=[unrelated_pdf],
                validated_order_sources_by_aw={},
            )

            self.assertEqual(deleted, [])
            self.assertEqual(warnings, [])
            self.assertTrue(unrelated_pdf.exists())

    def test_cleanup_keeps_shared_file_needed_by_unsent_duplicate_job(self) -> None:
        with writable_test_directory() as temp:
            source = temp / "Showers Programmer Input"
            source.mkdir()
            shared_pdf = source / "Glass Order BUILDER_89494499 130 DEERBROOK.pdf"
            shared_dxf = source / "89494499 130 DEERBROOK_1__P1.dxf"
            shared_pdf.write_text("shared", encoding="utf-8")
            shared_dxf.write_text("shared", encoding="utf-8")
            sent_order = shower_batch.ProcessOrder("237178", "89494499 130 DEERBROOK", "BUILDER")
            sent_order.items[1] = shower_batch.ProcessItem(1)
            unsent_order = shower_batch.ProcessOrder("237179", "89494499 130 DEERBROOK", "BUILDER")
            unsent_order.items[1] = shower_batch.ProcessItem(1)

            class ProtectedCleanupApp(shower_programmer_gui.ShowerProgrammerApp):
                EDI_IMPORT_ORDERS_DIR = source

            deleted, warnings = ProtectedCleanupApp.clear_import_staging_folder(
                [sent_order],
                source_files=[shared_pdf, shared_dxf],
                validated_order_sources_by_aw={
                    "237178": {shared_pdf.name, shared_dxf.name},
                },
                protected_orders=[unsent_order],
            )

            self.assertEqual(deleted, [])
            self.assertEqual(warnings, [])
            self.assertTrue(shared_pdf.exists())
            self.assertTrue(shared_dxf.exists())

    def test_missing_shared_source_during_copy_does_not_abort_scan(self) -> None:
        with writable_test_directory() as temp:
            missing = temp / "already_removed.pdf"
            target = temp / "Orders" / missing.name

            results = list(
                shower_programmer_gui.ShowerProgrammerApp.copy_file_pairs_concurrently(
                    [(missing, target)]
                )
            )

            self.assertEqual(results, [(missing, target, False)])
            self.assertFalse(target.exists())

    def test_completed_batch_reuses_prior_dated_archive_names(self) -> None:
        with writable_test_directory() as temp:
            order_root = temp / "Orders"
            process_root = temp / "Process List"
            order_root.mkdir()
            process_root.mkdir()
            archive_root = order_root / shower_programmer_gui.ShowerProgrammerApp.dated_archive_folder_name()
            archive_root.mkdir()

            prior_order = shower_batch.ProcessOrder("237239", "88643652 EDGEWATER 1007", "TRUE HOMES")
            prior_order.items[1] = shower_batch.ProcessItem(1)
            current_order = shower_batch.ProcessOrder("237240", "88651438 ENCORE 75", "DAVID WEEKLEY")
            current_order.items[1] = shower_batch.ProcessItem(1)
            prior_pdf = archive_root / "Glass Order TRUE HOMES_88643652 EDGEWATER 1007.pdf"
            prior_dxf = archive_root / "88643652 EDGEWATER 1007_1__P1.dxf"
            current_pdf = order_root / "Glass Order DAVID WEEKLEY_88651438 ENCORE 75.pdf"
            current_dxf = order_root / "88651438 ENCORE 75_1__P1.dxf"
            process_list = process_root / "Batch 7200.xlsx"
            for path in (prior_pdf, prior_dxf, current_pdf, current_dxf, process_list):
                path.write_text(path.name, encoding="utf-8")
            plan = {
                "name": "Batch 7200",
                "files": [process_list],
                "orders": [prior_order, current_order],
            }

            app = object.__new__(shower_programmer_gui.ShowerProgrammerApp)
            archived, warnings = app.archive_sent_input_files_for_orders(
                [current_order],
                order_root,
                process_root,
                include_process_lists=False,
                completed_process_batches=[plan],
            )

            self.assertEqual(warnings, [])
            self.assertEqual(len(archived), 3)
            self.assertEqual(
                app._last_archived_order_sources_by_aw["237239"],
                {prior_pdf.name, prior_dxf.name},
            )
            self.assertEqual(
                app._last_archived_order_sources_by_aw["237240"],
                {current_pdf.name, current_dxf.name},
            )

            source = temp / "Showers Programmer Input"
            source.mkdir()
            shared_current_pdf = source / current_pdf.name
            shared_current_dxf = source / current_dxf.name
            unrelated_pdf = source / "customer_export_without_order_in_filename.pdf"
            for path in (shared_current_pdf, shared_current_dxf, unrelated_pdf):
                path.write_text(path.name, encoding="utf-8")

            class CompletedBatchCleanupApp(shower_programmer_gui.ShowerProgrammerApp):
                EDI_IMPORT_ORDERS_DIR = source

                @classmethod
                def matching_order_files_bounded(cls, *args, **kwargs):
                    raise AssertionError("Completed archive evidence should avoid shared PDF matching.")

            deleted, cleanup_warnings = CompletedBatchCleanupApp.clear_import_staging_folder(
                [current_order],
                completed_process_batches=[plan],
                source_files=[shared_current_pdf, shared_current_dxf, unrelated_pdf],
                validated_order_sources_by_aw=app._last_archived_order_sources_by_aw,
            )

            self.assertEqual(
                {path.name for path in deleted},
                {shared_current_pdf.name, shared_current_dxf.name},
            )
            self.assertEqual(cleanup_warnings, [])
            self.assertTrue(unrelated_pdf.exists())

    def test_local_archive_reuses_initial_match_without_post_move_rescan(self) -> None:
        with writable_test_directory() as temp:
            order_root = temp / "Orders"
            process_root = temp / "Process List"
            order_root.mkdir()
            process_root.mkdir()
            order_pdf = order_root / "Glass Order TRUE HOMES_88643652 EDGEWATER 1007.pdf"
            order_dxf = order_root / "88643652 EDGEWATER 1007_1__P1.dxf"
            unrelated = order_root / "99999999 OTHER JOB_1.dxf"
            process_list = process_root / "Batch 7200.xlsx"
            for path in (order_pdf, order_dxf, unrelated, process_list):
                path.write_text(path.name, encoding="utf-8")
            order = shower_batch.ProcessOrder("237239", "88643652 EDGEWATER 1007", "TRUE HOMES")
            order.items[1] = shower_batch.ProcessItem(1)
            plan = {"name": "Batch 7200", "files": [process_list], "orders": [order]}

            class CountingArchiveApp(shower_programmer_gui.ShowerProgrammerApp):
                match_calls = 0

                @classmethod
                def matching_order_files(cls, *args, **kwargs):
                    cls.match_calls += 1
                    return super().matching_order_files(*args, **kwargs)

            app = object.__new__(CountingArchiveApp)
            archived, warnings = app.archive_sent_input_files_for_orders(
                [order],
                order_root,
                process_root,
                include_process_lists=False,
                completed_process_batches=[plan],
            )

            self.assertEqual(warnings, [])
            self.assertEqual(CountingArchiveApp.match_calls, 2)
            self.assertEqual(
                app._last_archived_order_sources_by_aw["237239"],
                {order_pdf.name, order_dxf.name},
            )
            self.assertEqual(len(archived), 3)
            self.assertTrue(unrelated.exists())
            self.assertFalse(process_list.exists())

    def test_action_history_partitions_records_after_seven_days(self) -> None:
        now = datetime(2026, 8, 10, 12, 0, 0)
        recent = {"id": "recent", "timestamp": (now - timedelta(days=2)).isoformat()}
        boundary = {"id": "boundary", "timestamp": (now - timedelta(days=7)).isoformat()}
        old = {"id": "old", "timestamp": (now - timedelta(days=8)).isoformat()}

        current, archived = shower_programmer_gui.ShowerProgrammerApp.partition_action_history_events(
            [recent, boundary, old],
            now=now,
        )

        self.assertEqual([event["id"] for event in current], ["recent", "boundary"])
        self.assertEqual([event["id"] for event in archived], ["old"])

    def test_action_history_archives_old_records_and_searches_job_fields(self) -> None:
        with writable_test_directory() as temp:
            app = object.__new__(shower_programmer_gui.ShowerProgrammerApp)
            app.runtime_root = temp
            app.action_history_lock = threading.RLock()
            app.order_by_aw = {}
            recent = {
                "id": "recent",
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "action": "Validate Selected",
                "status": "SUCCESS",
                "orders": ["237009"],
                "job_numbers": ["89420398.4"],
                "job_names": ["2089 HOLBROOK"],
                "customers": ["SAUSSY BURBANK HOMES"],
                "message": "Validation complete",
                "details": "Generated DXF verified",
            }
            old_stamp = datetime.now() - timedelta(days=9)
            old = {
                "id": "old",
                "timestamp": old_stamp.isoformat(timespec="seconds"),
                "action": "Scan Orders",
                "status": "SUCCESS",
                "orders": ["236472"],
                "job_numbers": ["88000000"],
                "job_names": ["OLD JOB"],
                "message": "Scan complete",
                "details": "Archived test",
            }
            app.write_action_history_file(app.action_history_path(), [old, recent])

            self.assertEqual(app.archive_old_action_history(), 1)
            current = app.load_action_history_events("Last 7 Days")
            archived = app.load_action_history_events("Archive")

            self.assertEqual([event["id"] for event in current], ["recent"])
            self.assertEqual([event["id"] for event in archived], ["old"])
            self.assertTrue(app.action_history_matches(recent, "237009 holbrook dxf"))
            self.assertTrue(app.action_history_matches(recent, "89420398.4 validation"))
            self.assertTrue(app.action_history_matches(recent, "saussy burbank"))
            self.assertFalse(app.action_history_matches(recent, "236472"))

    def test_order_sort_values_use_dates_and_natural_numbers(self) -> None:
        app = shower_programmer_gui.ShowerProgrammerApp
        self.assertLess(app.order_sort_value("P2", "items"), app.order_sort_value("P10", "items"))
        self.assertLess(
            app.order_sort_value("08/09/2026", "delivery"),
            app.order_sort_value("08/10/2026", "delivery"),
        )
        self.assertLess(app.order_sort_value("ISSUES", "status"), app.order_sort_value("READY", "status"))


if __name__ == "__main__":
    unittest.main()
