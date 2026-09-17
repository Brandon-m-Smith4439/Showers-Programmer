from __future__ import annotations

import json
import os
import sys
import unittest
import uuid
from pathlib import Path
from unittest import mock

from pypdf import PdfWriter


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_batch
import shower_programmer_gui as gui


class ResilientImportHardwareRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = ROOT / "tmp" / "tests" / uuid.uuid4().hex
        self.temp.mkdir(parents=True)

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self.temp, ignore_errors=True)

    @staticmethod
    def write_pdf(path: Path) -> None:
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        with path.open("wb") as handle:
            writer.write(handle)

    @staticmethod
    def order(aw_order: str, job_name: str) -> shower_batch.ProcessOrder:
        return shower_batch.ProcessOrder(aw_order, job_name, "Customer")

    def test_atomic_copy_retries_transient_windows_sharing_lock(self) -> None:
        source = self.temp / "source.pdf"
        target = self.temp / "cache" / "target.pdf"
        source.write_bytes(b"pdf")
        original_replace = os.replace
        attempts = 0

        def transient_replace(partial, destination):
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise PermissionError(32, "being used by another process")
            return original_replace(partial, destination)

        with mock.patch.object(gui.os, "replace", side_effect=transient_replace), mock.patch.object(gui.time, "sleep"):
            gui.ShowerProgrammerApp.copy_file_atomically(source, target)

        self.assertEqual(attempts, 3)
        self.assertEqual(target.read_bytes(), b"pdf")

    def test_one_locked_file_does_not_stop_remaining_visible_imports(self) -> None:
        source_dir = self.temp / "shared"
        target_dir = self.temp / "local"
        source_dir.mkdir()
        locked = source_dir / "locked.pdf"
        available = source_dir / "available.pdf"
        locked.write_bytes(b"locked")
        available.write_bytes(b"available")
        original = gui.ShowerProgrammerApp.copy_file_if_needed.__func__

        def selective_copy(cls, source: Path, target: Path) -> bool:
            if source.name == "locked.pdf":
                raise PermissionError(32, "being used by another process")
            return original(cls, source, target)

        snapshot = {"source": str(source_dir), "order_files": [locked, available]}
        with mock.patch.object(gui.ShowerProgrammerApp, "copy_file_if_needed", classmethod(selective_copy)):
            summary = gui.ShowerProgrammerApp.copy_visible_import_order_files(target_dir, snapshot)

        self.assertTrue((target_dir / "available.pdf").is_file())
        self.assertFalse((target_dir / "locked.pdf").exists())
        self.assertEqual(len(summary["copy_warnings"]), 1)

    def test_stale_import_partial_is_removed_but_fresh_copy_is_preserved(self) -> None:
        cache = self.temp / ".Network PDF Cache"
        cache.mkdir()
        stale = cache / "copy-stale.part"
        fresh = cache / "copy-fresh.part"
        stale.write_bytes(b"stale")
        fresh.write_bytes(b"fresh")
        old_time = gui.time.time() - 600
        os.utime(stale, (old_time, old_time))

        removed = gui.ShowerProgrammerApp.cleanup_stale_import_partials(cache, older_than_seconds=300)

        self.assertEqual(removed, [stale])
        self.assertFalse(stale.exists())
        self.assertTrue(fresh.exists())

    def test_hardware_list_moves_to_order_named_destination(self) -> None:
        source_dir = self.temp / "shared"
        destination = self.temp / "Hardware Lists"
        source_dir.mkdir()
        hardware = source_dir / "Hardware List 89897793 227 STOREYBROOK.pdf"
        self.write_pdf(hardware)

        moved, warnings = gui.ShowerProgrammerApp.move_hardware_list_pdfs(
            source_dir,
            [self.order("237999", "89897793 227 STOREYBROOK")],
            [hardware],
            destination,
        )

        self.assertEqual(warnings, [])
        self.assertEqual(moved, [destination / "237999 Hardware.pdf"])
        self.assertTrue((destination / "237999 Hardware.pdf").is_file())
        self.assertFalse(hardware.exists())

    def test_ambiguous_duplicate_job_hardware_is_preserved(self) -> None:
        source_dir = self.temp / "shared"
        destination = self.temp / "Hardware Lists"
        source_dir.mkdir()
        hardware = source_dir / "Hardware List 89420398.4 2089 HOLBROOK.pdf"
        self.write_pdf(hardware)

        moved, warnings = gui.ShowerProgrammerApp.move_hardware_list_pdfs(
            source_dir,
            [
                self.order("237008", "89420398.4 2089 HOLBROOK"),
                self.order("237009", "89420398.4 2089 HOLBROOK"),
            ],
            [hardware],
            destination,
        )

        self.assertEqual(moved, [])
        self.assertTrue(hardware.is_file())
        self.assertEqual(len(warnings), 1)
        self.assertIn("matches multiple orders", warnings[0])

    def test_version_148_release_metadata(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertEqual(version["version"], "Version 1.48")
        self.assertEqual(version["version_number"], 148)
        self.assertEqual(version["marker"], "VERSION_1_48_RESILIENT_IMPORT_HARDWARE_ROUTING")
        source = (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8")
        self.assertIn(version["marker"], source)


if __name__ == "__main__":
    unittest.main()
