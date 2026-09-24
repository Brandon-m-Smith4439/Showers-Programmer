from __future__ import annotations

import inspect
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_batch
import shower_programmer as programmer
import shower_programmer_gui as gui


class ActiveInputTraversalTests(unittest.TestCase):
    def test_active_files_include_nested_work_but_prune_dated_archives(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            active = root / "active.pdf"
            nested = root / "Incoming" / "nested.pdf"
            archived = root / "9.23.2026" / "archived.pdf"
            active.write_bytes(b"active")
            nested.parent.mkdir()
            nested.write_bytes(b"nested")
            archived.parent.mkdir()
            archived.write_bytes(b"archived")

            found = set(programmer.iter_active_input_files(root, ".pdf"))

            self.assertEqual(found, {active, nested})

    def test_pdf_and_dxf_lookup_use_archive_pruned_iterator(self) -> None:
        pdf_source = inspect.getsource(programmer.find_pdf)
        dxf_source = inspect.getsource(programmer.find_source_dxf)
        preview_source = inspect.getsource(shower_batch.preview_orders)

        self.assertIn("iter_active_input_files", pdf_source)
        self.assertIn("iter_active_input_files", dxf_source)
        self.assertIn("iter_active_input_files", preview_source)
        self.assertNotIn(".rglob(", pdf_source)
        self.assertNotIn(".rglob(", dxf_source)


class OpeningPerformanceTests(unittest.TestCase):
    def test_opening_feedback_uses_owner_centering(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.show_opening_window)

        self.assertIn("self.center_child_window(window, 420, 150)", source)
        self.assertNotIn("self.position_child_window(window, 420, 150)", source)

    def test_openpyxl_is_loaded_only_when_workbook_features_are_used(self) -> None:
        batch_source = (BACKEND / "shower_batch.py").read_text(encoding="utf-8")
        gui_source = (BACKEND / "shower_programmer_gui.py").read_text(encoding="utf-8")

        self.assertNotIn("\nfrom openpyxl import load_workbook\n", batch_source[:2000])
        self.assertNotIn("\nfrom openpyxl import Workbook\n", gui_source[:5000])
        self.assertIn("def load_process_orders_from_workbook", batch_source)
        self.assertIn("    from openpyxl import load_workbook", batch_source)
        self.assertGreaterEqual(gui_source.count("        from openpyxl import Workbook"), 2)

    def test_version_161_release_marker_is_retained(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        marker = "VERSION_1_61_CENTERED_FAST_OPENING"

        self.assertGreaterEqual(version["version_number"], 161)
        self.assertIn(marker, (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8"))
        self.assertIn(
            "version_1_61_centered_fast_opening",
            (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
