from __future__ import annotations

import inspect
import io
import json
import sys
import unittest
from pathlib import Path

from pypdf import PdfReader
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_programmer as programmer
import shower_programmer_gui as gui


def sketch_reader(
    *,
    portrait: bool,
    short_labels: tuple[str, str],
    long_labels: tuple[str, str] = ("FP", "FP"),
    summary: str = "",
) -> PdfReader:
    stream = io.BytesIO()
    pdf = canvas.Canvas(stream, pagesize=(612, 792))
    if portrait:
        left, bottom, right, top = 180.0, 150.0, 420.0, 620.0
    else:
        left, bottom, right, top = 80.0, 260.0, 540.0, 500.0
    pdf.line(left, bottom, right, bottom)
    pdf.line(right, bottom, right, top)
    pdf.line(right, top, left, top)
    pdf.line(left, top, left, bottom)
    pdf.setFont("Helvetica", 10)
    if portrait:
        pdf.drawString((left + right) / 2, bottom + 14, short_labels[0])
        pdf.drawString((left + right) / 2, top - 22, short_labels[1])
        pdf.drawString(left + 10, (bottom + top) / 2, long_labels[0])
        pdf.drawString(right - 28, (bottom + top) / 2, long_labels[1])
    else:
        pdf.drawString(left + 10, (bottom + top) / 2, short_labels[0])
        pdf.drawString(right - 28, (bottom + top) / 2, short_labels[1])
        pdf.drawString((left + right) / 2, bottom + 14, long_labels[0])
        pdf.drawString((left + right) / 2, top - 22, long_labels[1])
    if summary:
        pdf.drawString(72, 700, summary)
    pdf.save()
    stream.seek(0)
    return PdfReader(stream)


class PolisherMaximumTests(unittest.TestCase):
    config = {"rules": {"polisher_max_edge_inches": 113}}

    def panel(self, *, portrait: bool, longest: float = 114.0, text: str = "") -> programmer.Panel:
        width, height = ((33.0, longest) if portrait else (longest, 33.0))
        return programmer.Panel(1, 0, text, width, height, "DENVER 2")

    def test_long_edge_fp_and_short_edge_se_is_allowed(self) -> None:
        reader = sketch_reader(portrait=True, short_labels=("SE", "SE"))
        panel = self.panel(portrait=True)

        programmer.validate_polisher_maximum(reader, panel, self.config)

        self.assertEqual(panel.warnings, [])

    def test_portrait_short_edge_fp_warns(self) -> None:
        reader = sketch_reader(portrait=True, short_labels=("FP", "SE"))
        panel = self.panel(portrait=True, longest=119.5)

        programmer.validate_polisher_maximum(reader, panel, self.config)

        self.assertEqual(len(panel.warnings), 1)
        self.assertIn("Polisher Maximums exceeded", panel.warnings[0])
        self.assertIn('119.5"', panel.warnings[0])

    def test_landscape_short_edge_fps_warns(self) -> None:
        reader = sketch_reader(portrait=False, short_labels=("FP-S", "SE"))
        panel = self.panel(portrait=False)

        programmer.validate_polisher_maximum(reader, panel, self.config)

        self.assertEqual(len(panel.warnings), 1)
        self.assertIn("FP-S", panel.warnings[0])

    def test_exactly_113_inches_does_not_warn(self) -> None:
        reader = sketch_reader(portrait=True, short_labels=("FP", "FP"))
        panel = self.panel(portrait=True, longest=113.0)

        programmer.validate_polisher_maximum(reader, panel, self.config)

        self.assertEqual(panel.warnings, [])

    def test_short_edge_summary_is_conservative_fallback(self) -> None:
        reader = sketch_reader(
            portrait=True,
            short_labels=("", ""),
            summary="Flat Polish 2 Long 2 Short As Shown",
        )
        panel = self.panel(portrait=True, text="Flat Polish 2 Long 2 Short As Shown")

        programmer.validate_polisher_maximum(reader, panel, self.config)

        self.assertEqual(len(panel.warnings), 1)

    def test_ambiguous_edgework_does_not_warn(self) -> None:
        reader = sketch_reader(portrait=True, short_labels=("", ""), long_labels=("FP", "FP"))
        panel = self.panel(portrait=True)

        programmer.validate_polisher_maximum(reader, panel, self.config)

        self.assertEqual(panel.warnings, [])


class WindowPresentationTests(unittest.TestCase):
    def test_main_window_reveals_without_hidden_paint_delay(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.force_main_window_maximized)

        self.assertIn('self.root.attributes("-alpha", 1.0)', source)
        self.assertNotIn("self.root.update()", source)
        self.assertNotIn("self.root.after(220", source)

    def test_shared_child_presenter_has_no_default_reveal_delay(self) -> None:
        source = inspect.getsource(gui.ShowerProgrammerApp.present_window_without_flash)

        self.assertIn('window.attributes("-alpha", 0.0)', source)
        self.assertIn('window.attributes("-alpha", 1.0)', source)
        self.assertIn("if maximize:", source)
        self.assertIn("delay_ms: int = 0", source)
        self.assertNotIn("window.update()", source)

    def test_major_workspaces_use_hidden_final_frame_presentation(self) -> None:
        send_source = inspect.getsource(gui.ShowerProgrammerApp.open_send_review_dialog)
        settings_source = inspect.getsource(gui.ShowerProgrammerApp.open_settings)
        notice_source = inspect.getsource(gui.ShowerProgrammerApp.show_themed_notice)

        self.assertIn("self.present_window_without_flash", send_source)
        self.assertIn("maximize=True", send_source)
        self.assertIn('dialog.attributes("-alpha", 0.0)', settings_source)
        self.assertIn("self.present_window_without_flash", settings_source)
        self.assertIn("self.create_hidden_toplevel(owner)", notice_source)

    def test_slow_workspaces_show_immediate_opening_feedback(self) -> None:
        review_source = inspect.getsource(gui.ShowerProgrammerApp.open_order_review)
        send_source = inspect.getsource(gui.ShowerProgrammerApp.send_all_to_shop)
        settings_source = inspect.getsource(gui.ShowerProgrammerApp.open_settings)

        self.assertIn('self.show_opening_window(', review_source)
        self.assertIn('"review_order"', review_source)
        self.assertIn('self.show_opening_window(', send_source)
        self.assertIn('"review_send"', send_source)
        self.assertIn('self.show_opening_window(', settings_source)
        self.assertIn('"settings"', settings_source)

    def test_version_160_release_marker_is_retained(self) -> None:
        version = json.loads((BACKEND / "version.json").read_text(encoding="utf-8"))
        marker = "VERSION_1_60_POLISHER_WARNING_WINDOW_PRESENTATION"

        self.assertGreaterEqual(version["version_number"], 160)
        self.assertIn(marker, (BACKEND / "shower_v4_features.py").read_text(encoding="utf-8"))
        self.assertIn(
            "version_1_60_polisher_warning_window_presentation",
            (BACKEND / "release_required_flags.txt").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
