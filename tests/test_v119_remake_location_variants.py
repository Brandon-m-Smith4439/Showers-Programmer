from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import shower_batch


class FakePage:
    def __init__(self, text: str) -> None:
        self.text = text

    def extract_text(self) -> str:
        return self.text


class FakeReader:
    def __init__(self, *pages: str) -> None:
        self.pages = [FakePage(text) for text in pages]


class Version119RemakeLocationVariantTests(unittest.TestCase):
    def test_location_value_accepts_supported_remake_forms(self) -> None:
        for value in ("REMAK", "REMAKE", "REMAKES", "REMAKED", "REMAKING", "REMAKER"):
            with self.subTest(value=value):
                self.assertTrue(shower_batch.location_value_indicates_remake(value))

    def test_forward_location_field_accepts_supported_remake_forms(self) -> None:
        for value in ("REMAK", "REMAKE", "REMAKES", "REMAKED", "REMAKING", "REMAKER"):
            with self.subTest(value=value):
                reader = FakeReader(f"Project #: TEST\nLocation: {value}\nMarks: P1")
                self.assertTrue(shower_batch.pdf_location_indicates_remake(reader))

    def test_reverse_extracted_location_accepts_supported_remake_forms(self) -> None:
        for value in ("REMAK", "REMAKE", "REMAKES", "REMAKED", "REMAKING", "REMAKER"):
            with self.subTest(value=value):
                reader = FakeReader(f"Project #: TEST\n{value}Location:\nPrinted On: 8/17/2026")
                self.assertIn(value, [item.upper() for item in shower_batch.pdf_location_values(reader)])
                self.assertTrue(shower_batch.pdf_location_indicates_remake(reader))

    def test_location_variant_can_be_part_of_a_longer_location_value(self) -> None:
        self.assertTrue(shower_batch.location_value_indicates_remake("REMAKES - MASTER LEFT"))
        self.assertTrue(shower_batch.location_value_indicates_remake("REMAK #2"))

    def test_unrelated_remake_text_and_normal_locations_do_not_trigger(self) -> None:
        readers = (
            FakeReader("Project #: TEST\nLocation: MASTER LEFT\nNote: REMAKES hardware only"),
            FakeReader("Project #: TEST\nMASTER LEFTLocation:\nCustomer note: REMAKED due to damage"),
            FakeReader("Project Name: REMAKE HOUSE\nLocation: MASTER RIGHT\nMarks: P1"),
        )
        for reader in readers:
            with self.subTest(text=reader.pages[0].text):
                self.assertFalse(shower_batch.pdf_location_indicates_remake(reader))


if __name__ == "__main__":
    unittest.main()
