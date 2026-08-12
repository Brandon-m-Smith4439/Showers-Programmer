from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

import shower_programmer as programmer
import shower_programmer_gui as gui


class FakeCanvas:
    def __init__(self) -> None:
        self.created: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def create_text(self, *args: object, **kwargs: object) -> int:
        self.created.append(("text", args, kwargs))
        return len(self.created)

    def create_rectangle(self, *args: object, **kwargs: object) -> int:
        self.created.append(("rectangle", args, kwargs))
        return len(self.created)

    def addtag_withtag(self, _tag: str, _item_id: int) -> None:
        return None

    def tag_bind(self, _tag: str, _event: str, _callback: object) -> None:
        return None


class FakePage:
    class Box:
        width = 612
        height = 792

    mediabox = Box()


class FakeReader:
    pages = [FakePage()]


class ReviewStabilityPlacementTests(unittest.TestCase):
    def test_pending_text_position_does_not_treat_text_as_line_geometry(self) -> None:
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        canvas = FakeCanvas()
        obj = {
            "item": 1,
            "key": "label",
            "kind": "text",
            "lines": ["236583.1", "DENVER 2"],
            "x": 100.0,
            "y": 200.0,
            "font_size": 20.0,
            "rect": (60.0, 170.0, 140.0, 230.0),
        }
        state = {
            "objects": {},
            "positions": {(1, "label"): {"x": 112.0, "y": 208.0}},
            "start_drag": lambda _event, _key: None,
        }

        app.draw_editor_object(canvas, obj, 1.0, 0.0, 792.0, state, page_width=612.0)

        self.assertEqual(obj["lines"], ["236583.1", "DENVER 2"])
        self.assertEqual((obj["x"], obj["y"]), (112.0, 208.0))
        self.assertEqual(obj["rect"], (72.0, 178.0, 152.0, 238.0))
        self.assertEqual([entry[0] for entry in canvas.created], ["text", "text", "rectangle"])

    def test_diamon_fusion_stays_between_glass_and_top_measurement(self) -> None:
        panel = programmer.Panel(1, 0, "P1", 50.0, 46.0, "DENVER 2")
        piece_bbox = (120.0, 170.0, 490.0, 530.0)
        measurement_y = 588.0

        _x, _y, font_size, rect = programmer.choose_diamon_banner_position(
            612.0,
            792.0,
            {"diamon_fusion_min_font_size": 28, "diamon_fusion_edge_gap": 4},
            piece_bbox,
            (0.0, measurement_y, 612.0, measurement_y),
            "DIAMON FUSION",
            55.0,
            [],
            [],
            panel,
        )

        self.assertGreaterEqual(rect[1], piece_bbox[3])
        self.assertLessEqual(rect[3], measurement_y - 4.0)
        self.assertGreaterEqual(font_size, 18.0)

    def test_automatic_indicator_avoids_text_and_cutout(self) -> None:
        panel = programmer.Panel(
            1,
            0,
            "P1",
            60.0,
            80.0,
            "DENVER 2",
            indicator_corner="bottom_left",
        )
        piece_bbox = (100.0, 100.0, 500.0, 600.0)
        text_obstacles = [(128.0, 124.0, 158.0, 148.0)]
        cutout_obstacles = [(150.0, 128.0, 182.0, 176.0)]
        config = {
            "pdf": {
                "indicator_size": 18,
                "indicator_offset": 54,
                "avoid_corner_text_with_indicator": True,
                "corner_text_avoidance_max_shift": 36,
            }
        }

        with (
            mock.patch.object(programmer, "estimate_panel_outline_bbox", return_value=piece_bbox),
            mock.patch.object(programmer, "collect_page_text_obstacles", return_value=text_obstacles),
            mock.patch.object(programmer, "collect_indicator_cutout_obstacles", return_value=cutout_obstacles),
        ):
            programmer.apply_corner_text_indicator_avoidance(FakeReader(), [panel], config)

        geometry = programmer.indicator_marker_geometry(
            panel.machine,
            panel.indicator_corner,
            piece_bbox,
            612.0,
            792.0,
            config["pdf"],
            precise_edges=True,
            panel=panel,
        )
        self.assertIsNotNone(geometry)
        visible_rect = programmer.indicator_visible_rect(geometry or {})
        self.assertFalse(any(programmer.rects_overlap(visible_rect, rect) for rect in text_obstacles))
        self.assertFalse(any(programmer.rects_overlap(visible_rect, rect) for rect in cutout_obstacles))
        self.assertNotEqual((panel.indicator_nudge_x, panel.indicator_nudge_y), (0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
