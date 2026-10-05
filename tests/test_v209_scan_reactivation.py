from __future__ import annotations

import inspect
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
import shower_batch
import shower_programmer_gui as gui
from shower_temp import workspace_temporary_directory

App = gui.ShowerProgrammerApp


class ScanReactivationTests(unittest.TestCase):
    def fixture(self, root):
        local = root / 'Local/Orders'
        shared = root / 'Shared'
        output = root / 'Output'
        local.mkdir(parents=True)
        shared.mkdir()
        order = shower_batch.ProcessOrder('900001', '90499536M ARUNDEL', 'QA')
        order.items[1] = shower_batch.ProcessItem(1, width_text='80', height_text='28')
        App.mark_orders_deleted_for_output([order], output, deletion_scope_by_aw={'900001': 'order'})
        dxf = shared / '900001_1.dxf'
        dxf.write_bytes(b'fixture')
        return local, shared, output, order, dxf

    def test_filename_match_does_not_read_any_shared_pdf(self):
        with workspace_temporary_directory(prefix='scan-reactivate') as raw:
            local, shared, output, order, dxf = self.fixture(Path(raw))
            unrelated = shared / 'Glass Order 99999999 OTHER.pdf'
            matching = shared / 'Glass Order - 90499536M ARUNDEL.pdf'
            for pdf in (unrelated, matching):
                pdf.write_bytes(b'not opened')
            with mock.patch.object(gui.programmer, 'extract_first_page_text', return_value='') as read_pdf:
                result = App.reactivate_deleted_orders_available_in_shared_input(
                    [{'orders': [order]}], {'order_files': [unrelated, matching, dxf]}, local, output)
            self.assertEqual(result, [order.aw_order])
            read_pdf.assert_not_called()

    def test_unlabeled_pdf_is_inspected_only_after_local_staging(self):
        from reportlab.pdfgen import canvas
        with workspace_temporary_directory(prefix='scan-local-pdf') as raw:
            root = Path(raw)
            local, shared, output, order, dxf = self.fixture(root)
            pdf = shared / 'sketch.pdf'
            page = canvas.Canvas(str(pdf))
            page.drawString(72, 700, 'A&W Order: 900001 Job Nr: 90499536M ARUNDEL')
            page.save()
            original = gui.programmer.extract_first_page_text
            reads = []
            def read(candidate):
                reads.append(Path(candidate))
                return original(candidate)
            with mock.patch.object(gui.programmer, 'extract_first_page_text', side_effect=read):
                result = App.reactivate_deleted_orders_available_in_shared_input(
                    [{'orders': [order]}], {'order_files': [pdf, dxf]}, local, output)
            self.assertEqual(result, [order.aw_order])
            self.assertTrue(reads)
            self.assertTrue(all(shared not in p.parents for p in reads), reads)
            self.assertFalse(list(local.iterdir()))

    def test_failed_staging_keeps_deletion_receipt_and_reports_warning(self):
        with workspace_temporary_directory(prefix='scan-deferred') as raw:
            local, shared, output, order, dxf = self.fixture(Path(raw))
            pdf = shared / 'sketch.pdf'
            pdf.write_bytes(b'not opened')
            warnings = []
            def fail_copy(pairs, **kwargs):
                kwargs['errors'].append('Shared copy timed out; retry on next scan')
                return [(source, target, None) for source, target in pairs]
            with mock.patch.object(App, 'copy_network_file_pairs_bounded', side_effect=fail_copy), \
                 mock.patch.object(gui.programmer, 'extract_first_page_text') as read_pdf:
                result = App.reactivate_deleted_orders_available_in_shared_input(
                    [{'orders': [order]}], {'order_files': [pdf, dxf]}, local, output, warnings=warnings)
            self.assertEqual(result, [])
            self.assertTrue(warnings)
            self.assertIn('deleted_at', App.load_processing_history_for_output(output)['orders'][order.aw_order])
            read_pdf.assert_not_called()

    def test_sent_orders_skip_local_missing_input_inspection(self):
        order = shower_batch.ProcessOrder('900001', '90499536M ARUNDEL', 'QA')
        signature = App.sent_process_signature(order)
        history = {'orders': {order.aw_order: {'deleted_at': 'yesterday', 'deleted_process_signature': signature,
                                              'sent_at': 'yesterday', 'sent_process_signature': signature}}}
        with mock.patch.object(App, 'load_processing_history_for_output', return_value=history), \
             mock.patch.object(App, 'missing_order_input_requirements') as missing:
            self.assertEqual(App.reactivate_deleted_orders_available_in_shared_input(
                [{'orders': [order]}], {'files': [Path('shared/sketch.pdf')]}, Path('local'), Path('output')), [])
        missing.assert_not_called()

    def test_real_stall_timeout_keeps_receipt_and_does_not_read_stale_cache(self):
        with workspace_temporary_directory(prefix='scan-stall') as raw:
            local, shared, output, order, dxf = self.fixture(Path(raw))
            pdf = shared / 'sketch.pdf'
            pdf.write_bytes(b'not read')
            stale = App.local_network_pdf_cache_dir(local) / pdf.name
            stale.parent.mkdir(parents=True)
            stale.write_bytes(b'old copy must not be used')
            release = threading.Event()
            finished = threading.Event()
            def blocked_copy(*args):
                try:
                    release.wait(2)
                    return 'skip', None, None
                finally:
                    finished.set()
            warnings = []
            started = time.monotonic()
            try:
                with mock.patch.object(App, 'SCAN_NETWORK_COPY_STALL_SECONDS', .08), \
                     mock.patch.object(App, 'stage_network_copy_if_needed', side_effect=blocked_copy), \
                     mock.patch.object(gui.programmer, 'extract_first_page_text') as read_pdf:
                    result = App.reactivate_deleted_orders_available_in_shared_input(
                        [{'orders': [order]}], {'files': [pdf, dxf]}, local, output, warnings=warnings)
                self.assertEqual(result, [])
                self.assertLess(time.monotonic() - started, 1)
                self.assertTrue(any('without progress' in warning for warning in warnings), warnings)
                read_pdf.assert_not_called()
                self.assertIn('deleted_at', App.load_processing_history_for_output(output)['orders'][order.aw_order])
            finally:
                release.set()
                self.assertTrue(finished.wait(2))

    def test_cancel_keeps_history_unchanged(self):
        with workspace_temporary_directory(prefix='scan-cancel') as raw:
            local, shared, output, order, dxf = self.fixture(Path(raw))
            history_path = output / 'processing_history.json'
            before = history_path.read_bytes()
            def cancel():
                raise gui.shower_tasks.TaskCancelled('cancelled')
            with self.assertRaises(gui.shower_tasks.TaskCancelled):
                App.reactivate_deleted_orders_available_in_shared_input(
                    [{'orders': [order]}], {'files': [dxf]}, local, output, cancel_check=cancel)
            self.assertEqual(history_path.read_bytes(), before)

    def test_worker_reports_reactivation_stage_and_checks_cancellation(self):
        source = inspect.getsource(App.worker_scan_orders)
        start = source.index('scan_stage = "checking deleted shared orders"')
        check = source.index('self.reactivate_deleted_orders_available_in_shared_input', start)
        self.assertIn('queue_scan_progress', source[start:check])
        self.assertIn('cancel_check=check_cancelled', source[check:check+500])
        self.assertIn('"Deleted-order reactivation"', source)


if __name__ == '__main__':
    unittest.main()
