from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
import shower_programmer_gui as gui
import shower_scan_index
from shower_temp import workspace_temporary_directory
from test_sketch_quality import pdf


class SketchQualityGuiTests(unittest.TestCase):
    def test_only_bad_local_copy_is_recoverable_and_good_becomes_unique_source(self):
        with workspace_temporary_directory(prefix='paper-ui') as raw:
            root = Path(raw)
            folder = root / 'Orders'
            folder.mkdir()
            good, bad = folder / 'Glass Order 89420398.4.pdf', folder / 'Glass Order 89420398.4 (1).pdf'
            pdf(good, [(8.5, 11)])
            pdf(bad, [(4, 6)])
            before = good.read_bytes()
            removed, warnings = gui.ShowerProgrammerApp.replace_label_sketch_copies(folder, root / 'Recovery', [good, bad])
            self.assertEqual(removed, [bad])
            self.assertFalse(warnings)
            self.assertFalse(bad.exists())
            self.assertEqual(good.read_bytes(), before)
            self.assertEqual(len(list((root / 'Recovery').rglob('*.pdf'))), 1)
            self.assertEqual(gui.programmer.find_pdf(folder, '89420398.4 JOB'), good)

    def test_failed_quarantine_keeps_files_and_returns_warning(self):
        with workspace_temporary_directory(prefix='paper-ui') as raw:
            root = Path(raw)
            good, bad = root / 'Glass Order 89420398.4.pdf', root / 'Glass Order 89420398.4 (1).pdf'
            pdf(good, [(8.5, 11)])
            pdf(bad, [(4, 6)])
            with patch.object(gui.ShowerProgrammerApp, 'quarantine_paths', side_effect=PermissionError('locked')):
                removed, warnings = gui.ShowerProgrammerApp.replace_label_sketch_copies(root, root / 'Recovery', [good, bad])
            self.assertEqual(removed, [])
            self.assertTrue(warnings)
            self.assertTrue(good.exists() and bad.exists())

    def test_warning_attaches_to_selected_source_and_row_color_survives_checked(self):
        with workspace_temporary_directory(prefix='paper-ui') as raw:
            path = Path(raw) / 'Glass Order 89420398.4.pdf'
            pdf(path, [(4, 6)])
            order = gui.shower_batch.ProcessOrder(aw_order='237008', job_name='89420398.4 JOB', customer='', items={})
            result = gui.shower_batch.BatchJobResult(aw_order=order.aw_order, job_name=order.job_name, customer='', items='P1', status='READY', input_pdf=path)
            warning = gui.shower_sketch_quality.inspect_sketch(path).warning
            by_aw = gui.ShowerProgrammerApp.attach_sketch_paper_warnings([result], [order], {path: warning}, shower_scan_index.OrderInputIndex([path]))
            self.assertEqual(by_aw, {order.aw_order: warning})
            self.assertEqual(result.status, 'ISSUES')
            self.assertEqual(result.issues, [warning])
            app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
            app.sketch_paper_warnings = by_aw
            values = [''] * len(app.ORDER_TREE_COLUMNS)
            for key, value in [('order', '237008'), ('status', 'OK'), ('review', 'Checked')]:
                values[app.ORDER_TREE_INDEX[key]] = value
            self.assertEqual(app.order_tree_tags_for_values(values), ('SKETCH_SIZE',))


if __name__ == '__main__':
    unittest.main()
