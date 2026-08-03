from __future__ import annotations

import copy
import shutil
import sys
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

import shower_v4_features as v4


@contextmanager
def writable_test_directory():
    path = ROOT / "tmp" / "tests" / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


class ProcessItem:
    def __init__(self, item: int, *, width_text: str = "", height_text: str = "") -> None:
        self.item = item
        self.width_text = width_text
        self.height_text = height_text
        self.delivery_date = ""
        self.customer = ""
        self.processing: list[str] = []
        self.machine_hints: list[str] = []
        self.rows: list[int] = []


class ProcessOrder:
    def __init__(self, aw_order: str, job_name: str, customer: str = "") -> None:
        self.aw_order = aw_order
        self.job_name = job_name
        self.customer = customer
        self.items: dict[int, ProcessItem] = {}


class BatchStub:
    ProcessOrder = ProcessOrder
    ProcessItem = ProcessItem

    @staticmethod
    def clone_process_order(order: ProcessOrder) -> ProcessOrder:
        return copy.deepcopy(order)


class ProgrammerStub:
    @staticmethod
    def collect_dxf_internal_cut_radius_samples(path: Path):
        radius = float(path.read_text(encoding="utf-8"))
        return [(5.0, 5.0, radius)]

    @staticmethod
    def read_dxf_pairs(_path: Path):
        return [("9", "$INSUNITS"), ("70", "4")]


class PositionProgrammerStub:
    @staticmethod
    def estimate_panel_bbox(_reader, _page_index):
        return (0.0, 0.0, 100.0, 50.0)

    @staticmethod
    def text_origin_from_matrices(_cm, tm):
        return float(tm[4]), float(tm[5])


class FakePage:
    def __init__(self, points: list[tuple[float, float]]) -> None:
        self.points = points

    def extract_text(self, visitor_text=None):
        if visitor_text is not None:
            for x, y in self.points:
                visitor_text("SE", [1, 0, 0, 1, 0, 0], [1, 0, 0, 1, x, y], None, 10)
        return "SE " * len(self.points)


class FakeApp:
    def __init__(self, fail_names: set[str] | None = None) -> None:
        self._v4_send_conflict_actions: dict[str, str] = {}
        self._v4_send_summary = {"kept": [], "replaced": [], "failed": []}
        self.fail_names = fail_names or set()

    def copy_file_atomically(self, source: Path, target: Path) -> None:
        if source.name in self.fail_names:
            raise PermissionError("locked for test")
        target.write_bytes(source.read_bytes())


class CurrentFeatureTests(unittest.TestCase):
    def panel(self, **kwargs):
        defaults = {
            "width": 30.0,
            "height": 80.0,
            "machine": "",
            "text": "",
            "process_text": "",
            "warnings": [],
            "skip_dxf": False,
            "page_index": 1,
            "source_dxf": None,
        }
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_long_glass_requires_two_short_end_se_marks(self):
        panel = self.panel(width=117.0, height=23.0, text='117" x 23" FP FP FP FP')
        self.assertFalse(v4.validate_long_glass_se(panel, {}))
        self.assertTrue(any(w.startswith(v4.SE_WARNING_PREFIX) for w in panel.warnings))
        panel.text += " SE SE"
        self.assertTrue(v4.validate_long_glass_se(panel, {}))
        self.assertFalse(any(w.startswith(v4.SE_WARNING_PREFIX) for w in panel.warnings))

    def test_long_glass_position_mapping_requires_both_ends(self):
        panel = self.panel(width=117.0, height=23.0, text='117" x 23" SE SE')
        good_reader = SimpleNamespace(pages=[None, FakePage([(4.0, 25.0), (96.0, 25.0)])])
        self.assertTrue(v4.validate_long_glass_se(panel, {}, reader=good_reader, programmer=PositionProgrammerStub))
        bad_reader = SimpleNamespace(pages=[None, FakePage([(4.0, 25.0), (8.0, 25.0)])])
        self.assertFalse(v4.validate_long_glass_se(panel, {}, reader=bad_reader, programmer=PositionProgrammerStub))

    def test_waterjet_envelope_flags_both_dimensions_over_75(self):
        panel = self.panel(width=76.0, height=76.0, machine="WJ")
        self.assertFalse(v4.validate_waterjet_envelope(panel, {"rules": {"waterjet_fit_limit_inches": 75}}))
        self.assertTrue(panel.skip_dxf)
        self.assertTrue(any(w.startswith(v4.WJ_OVERSIZE_WARNING_PREFIX) for w in panel.warnings))
        narrow = self.panel(width=117.0, height=23.0, machine="WJ")
        self.assertTrue(v4.validate_waterjet_envelope(narrow, {"rules": {"waterjet_fit_limit_inches": 75}}))

    def test_glass_thickness_parser_ignores_radius_note(self):
        panel = self.panel(text='3/8" CLEAR TEMPERED\n1/4" INTERNAL RADIUS')
        self.assertAlmostEqual(v4.extract_glass_thickness_inches(panel), 0.375)

    def test_metric_dxf_radius_is_compared_in_inches(self):
        with writable_test_directory() as temp:
            path = temp / "metric_radius.dxf"
            path.write_text("6.35", encoding="utf-8")  # 1/4 inch in mm
            panel = self.panel(machine="WJ", text='3/8" CLEAR TEMPERED INTERNAL RADIUS', source_dxf=path)
            self.assertFalse(v4.validate_waterjet_internal_radius(panel, {}, ProgrammerStub))
            self.assertTrue(any(w.startswith(v4.WJ_RADIUS_WARNING_PREFIX) for w in panel.warnings))
            path.write_text("9.525", encoding="utf-8")  # 3/8 inch in mm
            self.assertTrue(v4.validate_waterjet_internal_radius(panel, {}, ProgrammerStub))
            self.assertFalse(any(w.startswith(v4.WJ_RADIUS_WARNING_PREFIX) for w in panel.warnings))

    def test_split_batches_merge_items_for_same_aw_order(self):
        first = ProcessOrder("900001", "12345678 TEST", "Customer")
        first.items[1] = ProcessItem(1, width_text='30"', height_text='80"')
        second = ProcessOrder("900001", "12345678 TEST", "Customer")
        second.items[2] = ProcessItem(2, width_text='24"', height_text='80"')
        merged = v4.unique_orders_from_batches([{"orders": [first]}, {"orders": [second]}], BatchStub)
        self.assertEqual(len(merged), 1)
        self.assertEqual(set(merged[0].items), {1, 2})

    def test_conflict_detection_distinguishes_identical_and_changed(self):
        with writable_test_directory() as root:
            source = root / "source"
            sketches = root / "sketches"
            programs = root / "programs"
            source.mkdir(); sketches.mkdir(); programs.mkdir()
            identical = source / "900001.pdf"
            changed = source / "90000101.dxf"
            identical.write_text("same", encoding="utf-8")
            changed.write_text("new", encoding="utf-8")
            (sketches / identical.name).write_text("same", encoding="utf-8")
            (programs / changed.name).write_text("old", encoding="utf-8")
            conflicts = v4.find_send_conflicts([identical], [changed], sketches, programs)
            self.assertEqual(len(conflicts), 2)
            self.assertEqual([item.identical for item in conflicts], [True, False])

    def test_keep_replace_and_per_file_failure_continue(self):
        with writable_test_directory() as root:
            source_dir = root / "source"
            target_dir = root / "target"
            source_dir.mkdir(); target_dir.mkdir()
            keep_source = source_dir / "keep.pdf"
            replace_source = source_dir / "replace.dxf"
            fail_source = source_dir / "fail.dxf"
            final_source = source_dir / "final.dxf"
            for path, content in ((keep_source, "new keep"), (replace_source, "new replace"), (fail_source, "fail"), (final_source, "final")):
                path.write_text(content, encoding="utf-8")
            keep_target = target_dir / keep_source.name
            replace_target = target_dir / replace_source.name
            keep_target.write_text("old keep", encoding="utf-8")
            replace_target.write_text("old replace", encoding="utf-8")
            app = FakeApp({"fail.dxf"})
            app._v4_send_conflict_actions = {
                str(keep_target.resolve()).casefold(): "keep",
                str(replace_target.resolve()).casefold(): "replace",
            }
            copied = v4._copy_outputs_with_policy(app, [keep_source, replace_source, fail_source, final_source], target_dir)
            self.assertEqual(keep_target.read_text(encoding="utf-8"), "old keep")
            self.assertEqual(replace_target.read_text(encoding="utf-8"), "new replace")
            self.assertTrue((target_dir / final_source.name).exists())
            self.assertFalse((target_dir / fail_source.name).exists())
            self.assertEqual(len(copied), 3)
            self.assertEqual(len(app._v4_send_summary["failed"]), 1)

    def test_radius_callout_points_and_severity(self):
        callouts = v4.radius_callouts(
            [(5.0, 5.0, 0.25), (15.0, 8.0, 0.375)],
            min_x=0,
            max_x=20,
            min_y=0,
            max_y=10,
            scale=20,
            margin=34,
            header_height=132,
            inches_per_unit=1,
            thickness_inches=0.375,
            pph=False,
        )
        self.assertEqual(len(callouts), 2)
        self.assertEqual(callouts[0].severity, "danger")
        self.assertNotEqual(callouts[0].center_x, callouts[0].label_x)
        pph = v4.radius_callouts(
            [(5.0, 9.0, 5.0 / 16.0)],
            min_x=0,
            max_x=20,
            min_y=0,
            max_y=10,
            scale=20,
            margin=34,
            header_height=132,
            inches_per_unit=1,
            thickness_inches=None,
            pph=True,
        )
        self.assertEqual(pph[0].severity, "ok")

    def test_radius_leader_starts_after_text_and_stops_at_ring(self):
        start_x, start_y, end_x, end_y = v4.leader_line_endpoints(
            (40.0, 40.0, 80.0, 60.0),
            (60.0, 50.0),
            (140.0, 50.0),
            12.0,
            label_gap=10.0,
        )
        self.assertGreaterEqual(start_x, 90.0)
        self.assertEqual(start_y, 50.0)
        self.assertLess(end_x, 140.0)
        self.assertEqual(end_y, 50.0)

    def test_radius_label_placement_avoids_oos_text(self):
        callout = v4.RadiusCallout(
            center_x=120.0,
            center_y=100.0,
            label_x=72.0,
            label_y=72.0,
            ring_radius=12.0,
            label='R 5/16"',
            severity="ok",
        )
        occupied = [(44.0, 60.0, 100.0, 84.0)]
        placed, rects = v4.place_radius_callout_labels(
            [callout],
            occupied=occupied,
            bounds=(10.0, 20.0, 260.0, 220.0),
        )
        self.assertEqual(len(placed), 1)
        self.assertFalse(v4._rects_overlap(v4._expand_rect(rects[0], 5.0), v4._expand_rect(occupied[0], 8.0)))

    def test_display_panel_suppresses_old_radius_header_triggers(self):
        panel = self.panel(machine="WJ", text="PPH hinge", process_text="PPH")
        preview = v4._panel_without_radius_header(panel)
        self.assertNotEqual(preview.machine, "WJ")
        self.assertNotIn("PPH", preview.text.upper())
        self.assertNotIn("PPH", preview.process_text.upper())
        self.assertEqual(panel.machine, "WJ")


if __name__ == "__main__":
    unittest.main()
