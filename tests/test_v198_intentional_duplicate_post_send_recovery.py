from __future__ import annotations

import copy
import json
import shutil
import sys
import tempfile
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_batch
import shower_programmer as programmer
import shower_programmer_gui as gui

JOB = "90479383 OCTOPLEX BLOCK 19 UNIT 135 4365"


@contextmanager
def writable_test_directory():
    path = ROOT / "tmp" / "tests" / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def write_sketch(path: Path, marker: str) -> None:
    document = canvas.Canvas(str(path))
    document.drawString(72, 720, JOB)
    document.drawString(72, 700, f"Source marker: {marker}")
    document.showPage()
    document.drawString(72, 720, '30" x 72"')
    document.drawString(72, 690, "Marks: P1")
    document.showPage()
    document.save()


def make_order(aw: str = "239591") -> shower_batch.ProcessOrder:
    order = shower_batch.ProcessOrder(aw_order=aw, job_name=JOB, customer="BFS East Greenville SC MW")
    order.items[1] = shower_batch.ProcessItem(item=1, width_text="30", height_text="72")
    return order


class _Tree:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, object]] = {}
        self.children: dict[str, list[str]] = {"": []}

    def add(self, row_id: str, parent: str = "", values=()) -> None:
        self.rows[row_id] = {"parent": parent, "values": tuple(values)}
        self.children.setdefault(parent, []).append(row_id)
        self.children.setdefault(row_id, [])

    def delete(self, row_id: str) -> None:
        parent = str(self.rows.get(row_id, {}).get("parent", ""))
        if row_id in self.children.get(parent, []):
            self.children[parent].remove(row_id)
        for child in list(self.children.get(row_id, [])):
            self.delete(child)
        self.children.pop(row_id, None)
        self.rows.pop(row_id, None)

    def item(self, row_id: str, **kwargs):
        row = self.rows[row_id]
        if kwargs:
            if "values" in kwargs:
                row["values"] = tuple(kwargs["values"])
            return None
        return {"values": row.get("values", ())}

    def get_children(self, parent: str = ""):
        return tuple(self.children.get(parent, []))


class Version198IntentionalDuplicateAndPostSendTests(unittest.TestCase):
    def build_authorized_config(self, folder: Path, order: shower_batch.ProcessOrder, selected: Path, candidates: list[Path]):
        collision = programmer.classify_pdf_duplicate_collision(candidates)
        self.assertIsNotNone(collision)
        assert collision is not None
        return {
            "pdf_order_mappings": {
                str(order.aw_order): {
                    "filename": selected.name,
                    "job_number": programmer.extract_job_number(order.job_name) or "",
                }
            },
            "duplicate_order_authorizations": {
                str(order.aw_order): {
                    "authorized": True,
                    "filename": selected.name,
                    "job_number": programmer.extract_job_number(order.job_name) or "",
                    "collision_kind": collision.kind,
                    "collision_fingerprint": programmer.duplicate_collision_fingerprint(collision),
                    "note": "Customer confirmed intentional replacement/duplicate",
                }
            },
        }

    def test_explicit_intentional_duplicate_authorization_allows_selected_pdf_but_keeps_red_flag_issue(self) -> None:
        with writable_test_directory() as folder:
            first = folder / "Glass Order 90479383 OCTOPLEX BLOCK 19 UNIT 135 43658876.pdf"
            second = folder / "Glass Order 90479383 OCTOPLEX BLOCK 19 UNIT 135 43659060.pdf"
            write_sketch(first, "original")
            write_sketch(second, "resent")
            order = make_order()
            config = self.build_authorized_config(folder, order, second, [first, second])

            resolved = shower_batch.preview_process_order_pdf(folder, order, [first, second], config=config)
            self.assertEqual(resolved, second.resolve())

            results = shower_batch.preview_orders([order], folder, config=config)
            self.assertEqual(results[0].status, "ISSUES")
            self.assertTrue(any("INTENTIONAL DUPLICATE AUTHORIZED" in issue for issue in results[0].issues))

    def test_stale_duplicate_authorization_fails_closed_when_candidate_changes(self) -> None:
        with writable_test_directory() as folder:
            first = folder / "Glass Order 90479383 OCTOPLEX BLOCK 19 UNIT 135 43658876.pdf"
            second = folder / "Glass Order 90479383 OCTOPLEX BLOCK 19 UNIT 135 43659060.pdf"
            write_sketch(first, "original")
            write_sketch(second, "resent")
            order = make_order()
            config = self.build_authorized_config(folder, order, second, [first, second])

            # Replacing an acknowledged source invalidates its file signature/fingerprint.
            second.write_bytes(second.read_bytes() + b"changed")
            self.assertIsNone(
                shower_batch.mapped_process_order_pdf(folder, order, config, candidate_pdfs=[first, second])
            )
            with self.assertRaises(programmer.AmbiguousPdfError):
                shower_batch.preview_process_order_pdf(folder, order, [first, second], config=config)

    def test_normal_source_mapping_still_cannot_bypass_duplicate_guard(self) -> None:
        with writable_test_directory() as folder:
            first = folder / "Glass Order 90479383 SAMPLE.pdf"
            second = folder / "Glass Order 90479383 SAMPLE (1).pdf"
            write_sketch(first, "original")
            write_sketch(second, "duplicate")
            order = make_order()
            config = {
                "pdf_order_mappings": {
                    str(order.aw_order): {"filename": second.name, "job_number": "90479383"}
                }
            }
            self.assertIsNone(
                shower_batch.mapped_process_order_pdf(folder, order, config, candidate_pdfs=[first, second])
            )

    def test_post_send_reconciliation_removes_only_sent_orders_and_preserves_failed_rows(self) -> None:
        sent = make_order("239591")
        failed = make_order("239592")
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        app.tree = _Tree()
        app.tree.add("batch")
        app.tree.add("sent-row", "batch", values=("OK",) * len(gui.ShowerProgrammerApp.ORDER_TREE_COLUMNS))
        app.tree.add("failed-row", "batch", values=("FAILED",) * len(gui.ShowerProgrammerApp.ORDER_TREE_COLUMNS))
        app.tree_rows = {"239591": "sent-row", "239592": "failed-row"}
        app.tree_row_orders = {"sent-row": sent, "failed-row": failed}
        app.tree_row_batches = {"batch": "batch-1"}
        app.batch_tree_rows = {"batch-1": "batch"}
        app.process_batches = {
            "batch-1": {
                "id": "batch-1",
                "name": "Batch 8671.xls",
                "orders": [sent, failed],
                "mirror_category_by_order": {},
                "mirror_categories": {},
            }
        }
        app.order_batch_ids = {"239591": ["batch-1"], "239592": ["batch-1"]}
        app.orders = [sent, failed]
        app.order_by_aw = {"239591": sent, "239592": failed}
        app.order_result_sources = {"239591": object(), "239592": object()}
        app.pending_import_duplicate_groups = {"239591": [], "239592": []}
        app.update_summary_strip = mock.Mock()
        app.apply_order_tree_sort = mock.Mock()
        app.clear_review_context_cache = mock.Mock()
        app.start_review_cache_warmup = mock.Mock()
        app.batch_tree_label = mock.Mock(return_value="Batch 8671.xls")
        app.batch_tree_summary = mock.Mock(return_value="1 order")
        app.reflow_mirror_sections_for_batch = mock.Mock()

        gui.ShowerProgrammerApp.reconcile_active_orders_after_send(app, [sent])

        self.assertNotIn("239591", app.order_by_aw)
        self.assertIn("239592", app.order_by_aw)
        self.assertEqual([order.aw_order for order in app.orders], ["239592"])
        self.assertNotIn("sent-row", app.tree.rows)
        self.assertIn("failed-row", app.tree.rows)
        self.assertEqual([order.aw_order for order in app.process_batches["batch-1"]["orders"]], ["239592"])
        app.start_review_cache_warmup.assert_called_once_with([failed])

    def test_send_completion_uses_in_memory_reconciliation_not_post_send_scan(self) -> None:
        source = Path(BACKEND / "shower_programmer_gui.py").read_text(encoding="utf-8")
        send_done = source.split('elif kind == "send_done":', 1)[1].split('elif kind == "send_error":', 1)[0]
        self.assertIn("self.reconcile_active_orders_after_send", send_done)
        self.assertNotIn("self.schedule_post_send_local_refresh()", send_done)
        self.assertNotIn("self.refresh_local_orders", send_done)
        self.assertNotIn("self.scan_orders", send_done)

    def test_duplicate_override_ui_is_explicit_and_red_warning_survives_checked_state(self) -> None:
        source = Path(BACKEND / "shower_programmer_gui.py").read_text(encoding="utf-8")
        self.assertIn("DUPLICATE PRODUCTION WARNING", source)
        self.assertIn("if not verified_var.get():", source)
        self.assertIn('confirm_text="Allow Duplicate"', source)
        self.assertIn('"DUPLICATE_OVERRIDE"', source)
        self.assertIn('confirm_text="Send Duplicate Anyway"', source)

    def test_version_198_release_metadata_and_flags(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 198)
        if version["version_number"] == 198:
            self.assertEqual(version["marker"], "VERSION_1_98_INTENTIONAL_DUPLICATE_POST_SEND_RECOVERY")
        features = (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8")
        self.assertIn("VERSION_1_98_INTENTIONAL_DUPLICATE_POST_SEND_RECOVERY", features)
        flags = (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8")
        for flag in (
            "intentional_duplicate_authorization",
            "duplicate_authorization_fingerprint",
            "red_duplicate_send_confirmation",
            "post_send_in_memory_reconciliation",
            "failed_order_pool_preservation",
            "version_1_98_intentional_duplicate_post_send_recovery",
        ):
            self.assertIn(flag, flags)


if __name__ == "__main__":
    unittest.main()
