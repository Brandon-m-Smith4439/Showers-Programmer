from __future__ import annotations

import shutil
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_batch
import shower_programmer as programmer
import shower_programmer_gui as gui
from shower_temp import workspace_temporary_directory


class FakePage:
    def __init__(self, text: str) -> None:
        self.text = text

    def extract_text(self) -> str:
        return self.text


class FakeReader:
    def __init__(self, *pages: str) -> None:
        self.pages = [FakePage(text) for text in pages]


def sample_order() -> shower_batch.ProcessOrder:
    order = shower_batch.ProcessOrder("240001", "89366422.2 700 POLE BRANCH", "TEST")
    order.items[1] = shower_batch.ProcessItem(1, width_text='30"', height_text='80"')
    return order


class Version118SentCleanupRemakeAutoTests(unittest.TestCase):
    def test_reverse_extracted_location_remake_is_detected_without_false_normal_location(self) -> None:
        remake_reader = FakeReader(
            "89366422.2 700 POLE BRANCHProject Name:\n"
            "Project #: TEST\n"
            "REMAKELocation:\n"
            "8/17/2026Printed On:\n"
            "Delivery Date: 8/20/2026"
        )
        normal_reader = FakeReader(
            "89183226 KINSDALE 132Project Name:\n"
            "Project #: PULTE\n"
            "MASTER LEFTLocation:\n"
            "7/22/2026Printed On:\n"
            "Delivery Date: 7/28/2026"
        )
        self.assertIn("REMAKE", [value.upper() for value in shower_batch.pdf_location_values(remake_reader)])
        self.assertTrue(shower_batch.pdf_location_indicates_remake(remake_reader))
        self.assertFalse(shower_batch.pdf_location_indicates_remake(normal_reader))

    def test_prepare_job_auto_routes_location_remake_without_manual_remake_map(self) -> None:
        process_order = sample_order()
        reader = FakeReader("Project #: TEST\nREMAKELocation:\nPrinted On: 8/17/2026")
        panel = programmer.Panel(1, 1, "P1", 30.0, 80.0, "DENVER 1")

        with (
            mock.patch.object(shower_batch, "open_process_order_pdf", return_value=(Path("remake.pdf"), reader)),
            mock.patch.object(programmer, "analyze_panels", return_value=[panel]),
            mock.patch.object(shower_batch, "match_process_items_to_sketch_pages", return_value={}),
            mock.patch.object(shower_batch, "attach_unlabeled_process_pages"),
            mock.patch.object(shower_batch, "attach_unmarked_process_pages"),
            mock.patch.object(shower_batch, "reconcile_process_list_item_gaps"),
            mock.patch.object(shower_batch, "reconcile_missing_items_from_extra_sketch_pages"),
            mock.patch.object(shower_batch, "apply_process_hints"),
            mock.patch.object(shower_batch, "apply_process_list_scope"),
            mock.patch.object(programmer, "refine_panel_orientations"),
            mock.patch.object(programmer, "apply_override"),
            mock.patch.object(programmer, "assign_dxf_paths"),
            mock.patch.object(programmer, "apply_corner_text_indicator_avoidance"),
            mock.patch.object(shower_batch, "collect_issues", return_value=[]),
        ):
            job, _reader, _issues = shower_batch.prepare_job(
                Path("Input/Orders"),
                Path("Output/Sketches"),
                Path("Output/Programs"),
                Path("Output/Reports"),
                {},
                process_order,
                remake_items=None,
            )

        self.assertEqual(job.remake_items, {1})
        self.assertTrue(panel.remake)
        self.assertIn("REMAKE auto-detected from PDF Location", panel.reasons)

    def test_send_archive_second_sweep_catches_file_arriving_before_process_list_retirement(self) -> None:
        with workspace_temporary_directory() as raw_temp:
            temp = Path(raw_temp)
            order_dir = temp / "Input" / "Orders"
            process_dir = temp / "Input" / "Process List"
            order_dir.mkdir(parents=True)
            process_dir.mkdir(parents=True)
            process_file = process_dir / "Batch 6400.xlsx"
            process_file.write_bytes(b"process list")
            late_pdf = order_dir / "89366422.2 700 POLE BRANCH.pdf"
            order = sample_order()

            class LateArrivalApp(gui.ShowerProgrammerApp):
                root_scan_count = 0

                @classmethod
                def matching_order_files(
                    cls,
                    folder: Path,
                    orders: list[shower_batch.ProcessOrder],
                    *,
                    root_only: bool,
                    inspect_pdf_text: bool,
                    candidate_files: list[Path] | None = None,
                ) -> list[Path]:
                    if candidate_files is None and folder == order_dir:
                        cls.root_scan_count += 1
                        if cls.root_scan_count == 1:
                            # Simulate a delayed local copy completing immediately
                            # after the first sent-input inventory was taken.
                            late_pdf.write_bytes(b"late local input")
                            return []
                    return super().matching_order_files(
                        folder,
                        orders,
                        root_only=root_only,
                        inspect_pdf_text=inspect_pdf_text,
                        candidate_files=candidate_files,
                    )

            app = object.__new__(LateArrivalApp)
            archived, warnings = app.archive_sent_input_files_for_orders(
                [order],
                order_dir,
                process_dir,
                include_process_lists=False,
                completed_process_batches=[
                    {"files": [process_file], "orders": [order], "batch_ids": ["batch-6400"]}
                ],
            )

            self.assertFalse(late_pdf.exists())
            self.assertFalse(process_file.exists())
            self.assertTrue(any(path.name == late_pdf.name for path in archived))
            self.assertTrue(any(path.name == process_file.name for path in archived))
            self.assertTrue(any("arrived during sent-input cleanup" in warning for warning in warnings))

    def test_second_sweep_reuses_initial_match_without_full_post_move_rescan(self) -> None:
        with workspace_temporary_directory() as raw_temp:
            temp = Path(raw_temp)
            order_dir = temp / "Input" / "Orders"
            process_dir = temp / "Input" / "Process List"
            order_dir.mkdir(parents=True)
            process_dir.mkdir(parents=True)
            source_pdf = order_dir / "89366422.2 700 POLE BRANCH.pdf"
            source_pdf.write_bytes(b"sent input")
            order = sample_order()

            class CountingArchiveApp(gui.ShowerProgrammerApp):
                match_calls = 0

                @classmethod
                def matching_order_files(
                    cls,
                    folder: Path,
                    orders: list[shower_batch.ProcessOrder],
                    *,
                    root_only: bool,
                    inspect_pdf_text: bool,
                    candidate_files: list[Path] | None = None,
                ) -> list[Path]:
                    cls.match_calls += 1
                    if candidate_files is not None:
                        return list(candidate_files)
                    return [source_pdf] if source_pdf.exists() else []

            app = object.__new__(CountingArchiveApp)
            archived, _warnings = app.archive_sent_input_files_for_orders(
                [order],
                order_dir,
                process_dir,
                include_process_lists=False,
            )

            self.assertEqual(CountingArchiveApp.match_calls, 2)
            self.assertFalse(source_pdf.exists())
            self.assertTrue(any(path.name == source_pdf.name for path in archived))

    def test_completed_process_list_is_kept_if_sent_input_still_cannot_be_archived(self) -> None:
        with workspace_temporary_directory() as raw_temp:
            temp = Path(raw_temp)
            order_dir = temp / "Input" / "Orders"
            process_dir = temp / "Input" / "Process List"
            order_dir.mkdir(parents=True)
            process_dir.mkdir(parents=True)
            process_file = process_dir / "Batch 6401.xlsx"
            process_file.write_bytes(b"process list")
            source_pdf = order_dir / "89366422.2 700 POLE BRANCH.pdf"
            source_pdf.write_bytes(b"locked input")
            order = sample_order()

            class LockedInputApp(gui.ShowerProgrammerApp):
                @staticmethod
                def move_file_to_folder(source: Path, target_dir: Path) -> Path:
                    if source.suffix.lower() == ".pdf":
                        raise OSError("simulated file lock")
                    return gui.ShowerProgrammerApp.move_file_to_folder(source, target_dir)

            app = object.__new__(LockedInputApp)
            _archived, warnings = app.archive_sent_input_files_for_orders(
                [order],
                order_dir,
                process_dir,
                include_process_lists=False,
                completed_process_batches=[
                    {"files": [process_file], "orders": [order], "batch_ids": ["batch-6401"]}
                ],
            )

            self.assertTrue(source_pdf.exists())
            self.assertTrue(process_file.exists(), "Never retire a completed process list while its sent input remains local.")
            self.assertTrue(any("Kept the completed process list active" in warning for warning in warnings))


if __name__ == "__main__":
    unittest.main()
