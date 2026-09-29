from __future__ import annotations

import inspect
import json
import sys
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_batch
import shower_programmer_gui as gui
from shower_temp import workspace_temporary_directory


class FakeTop:
    def __init__(self, name: str) -> None:
        self.name = name
        self.focused = None
        self.grabbed = None
        self._state = "normal"

    def winfo_toplevel(self):
        return self

    def winfo_exists(self):
        return True

    def state(self):
        return self._state

    def focus_displayof(self):
        return self.focused

    def grab_current(self):
        return self.grabbed


class FakeWidget:
    def __init__(self, top: FakeTop) -> None:
        self.top = top

    def winfo_toplevel(self):
        return self.top


class PopupOwnershipAndArchiveTestTests(unittest.TestCase):
    @staticmethod
    def make_order(aw_order: str) -> shower_batch.ProcessOrder:
        order = shower_batch.ProcessOrder(aw_order, f"902{aw_order} TEST JOB", "Customer")
        order.items[1] = shower_batch.ProcessItem(
            item=1,
            width_text="24",
            height_text="72",
            delivery_date="9/25/2026",
            customer="Customer",
            processing=["DENVER 2"],
            machine_hints=["DENVER 2"],
        )
        return order

    def test_root_owned_popup_resolves_to_focused_settings_page(self) -> None:
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        root = FakeTop("root")
        settings = FakeTop("settings")
        root.focused = FakeWidget(settings)
        app.root = root
        app._last_active_page_window = settings
        self.assertIs(app.resolve_popup_owner(root), settings)

    def test_nested_popup_keeps_explicit_review_owner(self) -> None:
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        root = FakeTop("root")
        review = FakeTop("review")
        root.focused = FakeWidget(FakeTop("settings"))
        app.root = root
        self.assertIs(app.resolve_popup_owner(review), review)

    def test_messagebox_and_structured_errors_use_hierarchical_owner(self) -> None:
        messagebox_source = inspect.getsource(gui._ProgramMessageBox._show)
        error_source = inspect.getsource(gui.ShowerProgrammerApp.show_structured_error)
        presenter_source = inspect.getsource(gui.ShowerProgrammerApp.present_window_without_flash)
        page_front_source = inspect.getsource(gui.ShowerProgrammerApp.bring_page_window_to_front)
        self.assertIn("resolve_popup_owner", messagebox_source)
        self.assertIn("error_owner = self.resolve_popup_owner(self.root)", error_source)
        self.assertIn("_shower_logical_owner", presenter_source)
        self.assertIn("_shower_logical_owner", page_front_source)
        self.assertIn("page_owner", page_front_source)

    def test_batch_test_mode_finds_order_files_from_earlier_dated_archive_without_process_revision(self) -> None:
        with workspace_temporary_directory() as raw:
            temp = Path(raw)
            order_archive_root = temp / "Orders"
            older = order_archive_root / "09.22.26"
            newest = order_archive_root / "09.25.26"
            older.mkdir(parents=True)
            newest.mkdir(parents=True)

            order = self.make_order("239337")
            pdf = older / "Glass Order 239337.pdf"
            dxf = older / "239337_P1.dxf"
            pdf.write_bytes(b"archived pdf")
            dxf.write_bytes(b"archived dxf")

            entry = {
                "archive_name": "09.25.26",
                "archive_date": datetime(2026, 9, 25),
                "batch_name": "Batch 9937.xlsx",
                "batch_key": "latest-process-only",
                "order": order,
                "order_archive_dir": newest,
                "process_list_files": [],
                "order_files": [],
            }

            prepared = gui.ShowerProgrammerApp.prepare_archived_batch_test_mode(
                [entry],
                batch_name="Batch 9937.xlsx",
                archive_name="09.25.26",
                runtime_root=temp / "Runtime",
            )
            restored = {Path(path).name for path in prepared["restored"]}
            self.assertEqual(restored, {pdf.name, dxf.name})
            self.assertEqual(
                gui.ShowerProgrammerApp.archived_batch_test_missing_sources(
                    prepared["entries"],
                    Path(prepared["order_dir"]),
                ),
                [],
            )
            manifest = json.loads(Path(prepared["provenance_manifest"]).read_text(encoding="utf-8"))
            source_archives = {
                row.get("source_archive")
                for order_row in manifest["orders"]
                for row in order_row.get("files", [])
            }
            self.assertIn("09.22.26", source_archives)

    def test_version_171_release_metadata(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 171)
        self.assertIn(
            "VERSION_1_71_POPUP_OWNERSHIP_ARCHIVE_TEST",
            (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8"),
        )
        flags = (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8")
        for flag in (
            "hierarchical_popup_ownership",
            "dated_archive_test_mode_fallback",
            "version_1_71_popup_ownership_archive_test",
        ):
            self.assertIn(flag, flags)


if __name__ == "__main__":
    unittest.main()
