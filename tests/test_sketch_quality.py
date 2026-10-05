from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.annotations import Text
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject, NumberObject

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))
import shower_cache
import shower_sketch_quality as quality
from shower_temp import workspace_temporary_directory


def pdf(path, sizes, text="Job 89420398.4 P1 28 x 80 Clear Tempered"):
    writer = PdfWriter()
    for width, height in sizes:
        page = writer.add_blank_page(width * 72, height * 72)
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 10 10 Td ({text}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    writer.write(path)


class SketchQualityTests(unittest.TestCase):
    def tearDown(self):
        shower_cache.configure(None)

    def test_letter_legal_a4_landscape_and_larger_are_not_labels(self):
        with workspace_temporary_directory(prefix="paper") as raw:
            path = Path(raw) / "normal.pdf"
            pdf(path, [(8.5, 11), (14, 8.5), (8.27, 11.69), (11, 17)])
            self.assertFalse(quality.inspect_sketch(path).label_pages)

    def test_label_and_mixed_sizes_include_page_number_and_inches(self):
        with workspace_temporary_directory(prefix="paper") as raw:
            path = Path(raw) / "small.pdf"
            pdf(path, [(8.5, 11), (4, 6), (2, 4)])
            info = quality.inspect_sketch(path)
            self.assertEqual(info.label_pages, (2, 3))
            self.assertIn('4 x 6 in', info.warning)
            self.assertIn('Sketch paper size', info.warning)

    def test_user_unit_and_crop_are_respected(self):
        with workspace_temporary_directory(prefix="paper") as raw:
            path = Path(raw) / "units.pdf"
            writer = PdfWriter()
            page = writer.add_blank_page(306, 396)
            page[NameObject('/UserUnit')] = NumberObject(2)
            writer.write(path)
            self.assertFalse(quality.inspect_sketch(path).label_pages)

    def test_unreadable_and_blank_content_never_auto_replace(self):
        with workspace_temporary_directory(prefix="paper") as raw:
            root = Path(raw)
            good, bad = root / 'Glass Order 89420398.pdf', root / 'Glass Order 89420398 (1).pdf'
            pdf(good, [(8.5, 11)], '')
            pdf(bad, [(4, 6)], '')
            self.assertEqual(quality.replacement_pairs([bad, good]), [])
            bad.write_bytes(b'not a PDF')
            self.assertTrue(quality.inspect_sketch(bad).error)
            self.assertEqual(quality.replacement_pairs([bad, good]), [])

    def test_same_content_copy_variant_replaced_but_different_orders_not(self):
        with workspace_temporary_directory(prefix="paper") as raw:
            root = Path(raw)
            good, bad = root / 'Glass Order 89420398.4.pdf', root / 'Glass Order 89420398.4 (1).pdf'
            pdf(good, [(8.5, 11)])
            pdf(bad, [(4, 6)])
            self.assertEqual(quality.replacement_pairs([bad, good]), [(bad, good)])
            renamed = root / 'Glass Order 89420398.4_237009.pdf'
            bad.rename(renamed)
            other = root / 'Glass Order 89420398.4_237008.pdf'
            good.rename(other)
            self.assertEqual(quality.replacement_pairs([renamed, other]), [])

    def test_distinct_remake_suffix_or_content_or_multiple_good_copies_not_replaced(self):
        with workspace_temporary_directory(prefix="paper") as raw:
            root = Path(raw)
            bad, good = root / 'Glass Order 89420398.2R.pdf', root / 'Glass Order 89420398.2.2R.pdf'
            pdf(bad, [(4, 6)])
            pdf(good, [(8.5, 11)])
            self.assertEqual(quality.replacement_pairs([bad, good]), [])
            good.unlink()
            good = root / 'Glass Order 89420398.2R (1).pdf'
            pdf(good, [(8.5, 11)], 'Different glass order P2 33 x 80')
            self.assertEqual(quality.replacement_pairs([bad, good]), [])
            pdf(good, [(8.5, 11)])
            copy = root / 'Glass Order 89420398.2R (2).pdf'
            pdf(copy, [(8.5, 11)])
            self.assertEqual(quality.replacement_pairs([bad, good, copy]), [])

    def test_cached_dimensions_do_not_reopen_unchanged_pdf_and_invalidate_on_change(self):
        with workspace_temporary_directory(prefix="paper") as raw:
            root = Path(raw)
            shower_cache.configure(root / 'cache')
            path = root / 'order.pdf'
            pdf(path, [(4, 6)])
            self.assertTrue(quality.inspect_sketch(path).label_pages)
            with patch.object(quality, 'PdfReader', side_effect=AssertionError('must be cached')):
                self.assertTrue(quality.inspect_sketch(path).label_pages)
            pdf(path, [(8.5, 11)])
            self.assertFalse(quality.inspect_sketch(path).label_pages)

    def test_annotations_are_retained_even_when_all_order_text_matches(self):
        with workspace_temporary_directory(prefix='paper') as raw:
            root = Path(raw)
            good, bad = root / 'Glass Order 89420398.pdf', root / 'Glass Order 89420398 (1).pdf'
            pdf(good, [(8.5, 11)])
            pdf(bad, [(4, 6)])
            writer = PdfWriter(clone_from=bad)
            writer.add_annotation(0, Text(rect=(10, 10, 30, 30), text='Keep operator note'))
            writer.write(bad)
            self.assertEqual(quality.replacement_pairs([bad, good]), [])

    def test_glass_order_hyphen_replacement_preserves_all_reference_numbers(self):
        with workspace_temporary_directory(prefix='paper') as raw:
            root = Path(raw)
            bad = root / 'Glass Order 90485055 OCTOPLEX BLOCK 14 UNIT 33 43660582.pdf'
            good = root / 'Glass Order - 90485055 OCTOPLEX BLOCK 14 UNIT 33 43660582.pdf'
            pdf(bad, [(4, 6)])
            pdf(good, [(8.5, 11)])
            self.assertEqual(quality.replacement_pairs([bad, good]), [(bad, good)])
            other = good.with_name(good.name.replace('43660582', '43660583'))
            good.rename(other)
            self.assertEqual(quality.replacement_pairs([bad, other]), [])

    def test_label_reprint_layout_spaces_do_not_hide_normal_mirror_pdf(self):
        with workspace_temporary_directory(prefix='paper') as raw:
            root = Path(raw)
            bad = root / 'Glass Order 90499536M 2927 ARUNDEL.pdf'
            good = root / 'Glass Order - 90499536M 2927 ARUNDEL.pdf'
            pdf(bad, [(4.5, 5.5)], 'Job 90499536M 2927 ARUNDEL 6-3/8 r 1/42-1/4 24-3/425')
            pdf(good, [(8.5, 11)], 'Job 90499536M 2927 ARUNDEL 6-3/8 r 1/4 2-1/4 24-3/4 25')
            self.assertEqual(quality.replacement_pairs([bad, good]), [(bad, good)])
            pdf(good, [(8.5, 11)], 'Job 90499536M 2927 ARUNDEL 6-3/8 r 3/8 2-1/4 24-3/4 25')
            self.assertEqual(quality.replacement_pairs([bad, good]), [])


if __name__ == '__main__':
    unittest.main()
