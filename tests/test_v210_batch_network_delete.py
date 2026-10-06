from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
import shower_batch
import shower_programmer_gui as gui
from shower_temp import workspace_temporary_directory

App = gui.ShowerProgrammerApp


class BatchNetworkDeleteTests(unittest.TestCase):
    def order(self, aw='900001', job='90499536M MIRROR QA'):
        order = shower_batch.ProcessOrder(aw, job, 'QA')
        order.items[1] = shower_batch.ProcessItem(1, width_text='24', height_text='36', processing=['FP'])
        return order

    def test_batch_mirror_without_fabrication_allows_network_delete(self):
        order = self.order()
        self.assertTrue(App.orders_allow_network_input_delete([order]))
        self.assertTrue(App.batch_allows_network_input_delete({'orders': [order]}))
        self.assertFalse(App.orders_allow_network_input_delete([]))
        self.assertFalse(App.batch_allows_network_input_delete({'orders': [None]}))

    def test_no_fab_mirror_cleanup_moves_only_confirmed_local_and_network_inputs(self):
        with workspace_temporary_directory(prefix='mirror-cleanup') as raw:
            base = Path(raw)
            local, shared, lists, output = [base / name for name in ('Orders','Shared','Lists','Output')]
            for folder in (local, shared, lists, output):
                folder.mkdir()
            order = self.order()
            name = 'Glass Order - 90499536M MIRROR QA.pdf'
            selected = local / name
            selected.write_bytes(b'fixture')
            (shared / name).write_bytes(b'fixture')
            unrelated = shared / 'Glass Order - 99999999 KEEP.pdf'
            unrelated.write_bytes(b'keep')
            list_path = lists / 'Batch QA.xls'
            list_path.write_bytes(b'keep incomplete batch')
            app = object.__new__(App)
            app.queue_scan_progress = mock.Mock()
            app.quarantine_root = lambda: base / 'Recovery'
            app.completed_process_list_batches_for_orders = mock.Mock(return_value=[])
            data = app.worker_prepare_local_order_delete([order], local, lists, output, shared, True)
            self.assertEqual(data['network_files'], [shared / name])
            result = app.worker_delete_local_order_inputs(data)
            self.assertEqual(result['successfully_deleted_orders'], [order])
            self.assertFalse(selected.exists())
            self.assertFalse((shared / name).exists())
            self.assertTrue(unrelated.exists())
            self.assertTrue(list_path.exists())
            self.assertTrue(list((base / 'Recovery').rglob('*.pdf')))

    def test_colliding_unselected_order_stops_before_removing_any_files(self):
        with workspace_temporary_directory(prefix='delete-collision') as raw:
            base = Path(raw)
            local = base / 'Orders'
            local.mkdir()
            pdf = local / 'Glass Order - 90499536M MIRROR QA.pdf'
            pdf.write_bytes(b'fixture')
            app = object.__new__(App)
            app.queue_scan_progress = mock.Mock()
            with self.assertRaisesRegex(RuntimeError, 'unselected order'):
                app.worker_prepare_local_order_delete(
                    [self.order()], local, base / 'Lists', base / 'Output', base / 'Shared', True,
                    other_orders=[self.order('900002')])
            self.assertTrue(pdf.exists())

    def test_network_failure_keeps_local_inputs_and_has_no_deleted_receipt(self):
        with workspace_temporary_directory(prefix='delete-network-fail') as raw:
            base = Path(raw)
            local = base / 'Orders'
            local.mkdir()
            pdf = local / 'Glass Order - 90499536M MIRROR QA.pdf'
            pdf.write_bytes(b'fixture')
            app = object.__new__(App)
            app.queue_scan_progress = mock.Mock()
            with mock.patch.object(app, 'delete_import_paths_bounded', return_value=([], ['Locked'], False)), \
                 mock.patch.object(app, 'quarantine_paths') as quarantine, \
                 mock.patch.object(app, 'mark_orders_deleted_for_output') as receipt:
                result = app.worker_delete_local_order_inputs({
                    'orders': [self.order()], 'files': [pdf], 'network_files': [base / 'Shared' / pdf.name],
                    'local_order_folder': local, 'process_list_root': base / 'Lists',
                    'output_dir': base / 'Output', 'include_network': True})
            self.assertTrue(result['incomplete'])
            self.assertTrue(pdf.exists())
            quarantine.assert_not_called()
            receipt.assert_not_called()


if __name__ == '__main__':
    unittest.main()
