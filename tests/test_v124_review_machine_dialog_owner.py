from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

import shower_programmer_gui


class FakeOwner:
    def __init__(self, x: int, y: int, width: int, height: int) -> None:
        self.x = x
        self.y = y
        self.width = width
        self.height = height

    def update_idletasks(self) -> None:
        return

    def winfo_rootx(self) -> int:
        return self.x

    def winfo_rooty(self) -> int:
        return self.y

    def winfo_width(self) -> int:
        return self.width

    def winfo_height(self) -> int:
        return self.height


class FakeChild:
    def __init__(self) -> None:
        self.geometry_value = ""
        self.transient_owner = None
        self.focused = False

    def geometry(self, value: str) -> None:
        self.geometry_value = value

    def after(self, _delay: int, callback) -> None:
        callback()

    def deiconify(self) -> None:
        return

    def transient(self, owner) -> None:
        self.transient_owner = owner

    def lift(self) -> None:
        return

    def focus_force(self) -> None:
        self.focused = True

    def attributes(self, *_args) -> None:
        return


class ReviewMachineDialogOwnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = shower_programmer_gui.ShowerProgrammerApp.__new__(
            shower_programmer_gui.ShowerProgrammerApp
        )
        self.main = FakeOwner(50, 40, 1200, 800)
        self.review = FakeOwner(2100, 120, 1600, 900)
        self.app.root = self.main

    def test_child_can_be_centered_on_review_window_instead_of_main_window(self) -> None:
        child = FakeChild()

        self.app.center_child_window(child, 500, 300, owner=self.review)

        self.assertEqual(child.geometry_value, "500x300+2650+420")

    def test_delayed_focus_preserves_review_window_as_transient_owner(self) -> None:
        child = FakeChild()

        self.app.bring_window_to_front(child, make_transient=True, owner=self.review)

        self.assertIs(child.transient_owner, self.review)
        self.assertTrue(child.focused)

    def test_change_machine_chooser_explicitly_uses_review_window_owner(self) -> None:
        source = (ROOT / "Backend" / "shower_programmer_gui.py").read_text(encoding="utf-8")

        self.assertIn("self.center_child_window(chooser, 500, 300, owner=dialog)", source)
        self.assertIn(
            "self.bring_window_to_front(chooser, make_transient=True, owner=dialog)",
            source,
        )


if __name__ == "__main__":
    unittest.main()
