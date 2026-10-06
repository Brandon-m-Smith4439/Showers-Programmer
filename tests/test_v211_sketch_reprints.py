from __future__ import annotations

import sys
import unittest
from pathlib import Path

from pypdf import PdfWriter
from pypdf.annotations import Text
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))
import shower_cache
import shower_sketch_quality as quality
import shower_programmer as programmer
from shower_temp import workspace_temporary_directory


def reprint(path, *, label=False, measurement="28 x 80", curve=15):
    writer = PdfWriter()
    header = "GLASS ORDER Project Name: 90509379 RCM69 43667950 "
    pages = [header + "10/5/2026Printed On:", "Delivery Date: 10/9/2026 1 Panel"] if label else [header + "10/6/2026Printed On: Delivery Date: 10/9/2026 1 Panel"]
    pages.append(f'Marks: P1 3/8 Clear Tempered {measurement} FP BUG')
    for index, text in enumerate(pages):
        page = writer.add_blank_page(324 if label else 612, 396 if label else 792)
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
        data = f'BT /F1 12 Tf 10 10 Td ({text} Page {index + 1} of {len(pages)} BFS Operations LLC) Tj ET\n'
        if index == len(pages) - 1:
            data += ('0.5 0 0 0.5 20 30 cm\n' if label else '')
            data += f'10 10 m 200 10 l 200 300 l 10 300 l 10 100 l 10 {curve} 30 {curve} 30 10 c S\n'
        stream = DecodedStreamObject()
        stream.set_data(data.encode('ascii'))
        page[NameObject('/Contents')] = writer._add_object(stream)
    writer.write(path)


class SketchReprintTests(unittest.TestCase):
    def tearDown(self):
        shower_cache.configure(None)

    def files(self, root):
        return root / 'Glass Order 90509379 RCM69 43667950.pdf', root / 'Glass Order - 90509379 RCM69 43667950.pdf'

    def test_print_date_and_overview_repagination_allow_verified_replacement(self):
        with workspace_temporary_directory(prefix='reprint') as raw:
            bad, good = self.files(Path(raw))
            reprint(bad, label=True)
            reprint(good)
            self.assertEqual(quality.replacement_pairs([bad, good]), [(bad, good)])

    def test_changed_glass_measurement_is_not_ignored_as_print_metadata(self):
        with workspace_temporary_directory(prefix='reprint') as raw:
            bad, good = self.files(Path(raw))
            reprint(bad, label=True)
            reprint(good, measurement='30 x 80')
            self.assertEqual(quality.replacement_pairs([bad, good]), [])

    def test_changed_drawing_with_identical_piece_text_is_not_a_reprint(self):
        with workspace_temporary_directory(prefix='reprint') as raw:
            bad, good = self.files(Path(raw))
            reprint(bad, label=True)
            reprint(good, curve=25)
            self.assertEqual(quality.replacement_pairs([bad, good]), [])

    def test_annotated_label_is_kept_even_for_verified_reprint(self):
        with workspace_temporary_directory(prefix='reprint') as raw:
            bad, good = self.files(Path(raw))
            reprint(bad, label=True)
            reprint(good)
            writer = PdfWriter(clone_from=bad)
            writer.add_annotation(0, Text(rect=(10, 10, 30, 30), text='Operator note'))
            writer.write(bad)
            self.assertEqual(quality.replacement_pairs([bad, good]), [])

    def test_multiple_normal_replacements_remain_ambiguous(self):
        with workspace_temporary_directory(prefix='reprint') as raw:
            bad, good = self.files(Path(raw))
            other = good.with_name(good.stem + ' (1).pdf')
            reprint(bad, label=True)
            reprint(good)
            reprint(other)
            self.assertEqual(quality.replacement_pairs([bad, good, other]), [])

    def test_pdf_selection_prefers_verified_normal_reprint_without_deleting_label(self):
        with workspace_temporary_directory(prefix='reprint') as raw:
            root = Path(raw)
            bad, good = self.files(root)
            reprint(bad, label=True)
            reprint(good)
            selected = programmer.find_pdf(root, '90509379 RCM69 43667950', '239684')
            self.assertEqual(selected, good)
            self.assertTrue(bad.exists())

    def test_selection_does_not_prefer_normal_paper_with_different_piece_contents(self):
        with workspace_temporary_directory(prefix='reprint') as raw:
            root = Path(raw)
            bad, good = self.files(root)
            reprint(bad, label=True)
            reprint(good, measurement='30 x 80')
            with self.assertRaises(programmer.AmbiguousPdfError):
                programmer.find_pdf(root, '90509379 RCM69 43667950', '239684')


if __name__ == '__main__':
    unittest.main()
