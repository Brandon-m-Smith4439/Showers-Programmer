from __future__ import annotations

import inspect
import os
import subprocess
import sys
import unittest
import time
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
import shower_batch
import shower_programmer as programmer
import shower_programmer_gui as gui
from shower_temp import workspace_temporary_directory


class LifecycleArchiveTests(unittest.TestCase):
    def order(self, number='900001'):
        order = shower_batch.ProcessOrder(number, '90499536M 2927 ARUNDEL', 'QA')
        order.items[1] = shower_batch.ProcessItem(item=1, width_text='80', height_text='28', processing=['WJ'])
        return order

    def test_archived_sent_inputs_not_reimported_from_incomplete_batch(self):
        with workspace_temporary_directory(prefix='retired-input') as raw:
            root = Path(raw)
            source = root / 'Shared' / 'Glass Order 90499536M 2927 ARUNDEL.pdf'
            archived = root / 'Orders' / '10.5.26' / source.name
            source.parent.mkdir()
            archived.parent.mkdir(parents=True)
            source.write_bytes(b'sent sketch')
            import shutil
            shutil.copy2(source, archived)
            order = self.order()
            history = {'orders': {order.aw_order: {'sent_at': '2026-10-05',
                        'sent_process_signature': gui.ShowerProgrammerApp.sent_process_signature(order)}}}
            gui.ShowerProgrammerApp.save_processing_history_for_output(root / 'Output', history)
            gui.ShowerProgrammerApp.record_retired_inputs_for_output([order], root / 'Output', [archived],
                                                                     {order.aw_order: [source.name]})
            snapshot = {'source': str(source.parent), 'files': [source], 'order_files': [source]}
            filtered, retired = gui.ShowerProgrammerApp.filter_retired_import_snapshot(snapshot, [order], root / 'Output')
            self.assertEqual(filtered['order_files'], [])
            self.assertEqual(retired, {order.aw_order})
            filtered, _retired = gui.ShowerProgrammerApp.filter_retired_import_snapshot(snapshot, [], root / 'Output')
            self.assertEqual(filtered['order_files'], [])
            # Changed input and changed process-list signatures remain eligible.
            source.write_bytes(b'changed source revision')
            filtered, retired = gui.ShowerProgrammerApp.filter_retired_import_snapshot(snapshot, [order], root / 'Output')
            self.assertEqual(filtered['order_files'], [source])
            self.assertFalse(retired)
            source.write_bytes(archived.read_bytes())
            os.utime(source, ns=(archived.stat().st_atime_ns, archived.stat().st_mtime_ns))
            order.items[1].width_text = '81'
            filtered, retired = gui.ShowerProgrammerApp.filter_retired_import_snapshot(snapshot, [order], root / 'Output')
            self.assertEqual(filtered['order_files'], [source])
            self.assertFalse(retired)

    def test_other_visible_modal_prevents_parent_focus_retry(self):
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        app.root = mock.Mock()
        modal = SimpleNamespace(winfo_toplevel=lambda: modal, _w='.!dialog')
        app.root.grab_current.return_value = modal
        root = SimpleNamespace(_w='.', winfo_toplevel=lambda: root)
        self.assertTrue(app.another_modal_owns_input(root))
        self.assertFalse(app.another_modal_owns_input(modal))
        nested = SimpleNamespace(_w='.!dialog.!nested', winfo_toplevel=lambda: nested)
        self.assertFalse(app.another_modal_owns_input(nested))

    def test_unprocessed_review_accepts_cache_generation_zero(self):
        source = inspect.getsource(gui.ShowerProgrammerApp.drain_worker_queue)
        self.assertNotIn('int(data.get("generation", -1) or -1)', source)

    def test_copy_menu_has_one_action_for_pointer_cell(self):
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        order = self.order()
        app.root = mock.Mock()
        app.tree = mock.Mock()
        app.tree.identify_row.return_value = 'row'
        app.tree.selection.return_value = ('row',)
        app.tree.identify_column.return_value = '#3'
        app.tree.set.return_value = order.job_name
        app.tree_row_batches = {}
        app.process_batches = {}
        app.order_for_tree_row = mock.Mock(return_value=order)
        app.selected_orders = mock.Mock(return_value=[order])
        for name in ('is_input_only_order', 'orders_allow_network_input_delete', 'selected_orders_are_all_checked',
                     'dimension_match_override_enabled'):
            setattr(app, name, mock.Mock(return_value=False))
        for name in ('pdf_order_mapping', 'duplicate_order_authorization', 'restored_archive_batch_id_for_context',
                     'archivable_batch_id_for_context'):
            setattr(app, name, mock.Mock(return_value=None))
        app.sent_orders_for_input_archive_context = mock.Mock(return_value=[])
        app.show_themed_context_menu = mock.Mock()
        app.copy_order_value_to_clipboard = mock.Mock()
        app.open_orders_context_menu(SimpleNamespace(x=40, y=100, x_root=40, y_root=100))
        actions = app.show_themed_context_menu.call_args.args[-1]
        copying = [action for action in actions if action.get('icon') == 'copy']
        self.assertEqual(len(copying), 1)
        copying[0]['command']()
        app.copy_order_value_to_clipboard.assert_called_once_with(order.job_name)

    def test_canvas_text_rotates_with_sketch_page(self):
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        canvas = mock.Mock()
        obj = {'key': 'label', 'kind': 'text', 'item': 1, 'font_size': 21,
               'x': 200, 'y': 300, 'lines': ['900001.1', 'WJ'], 'rect': (170, 260, 230, 340)}
        app.draw_editor_object(canvas, obj, 1, 8, 792, {'objects': {}, 'start_drag': mock.Mock()},
                               page_width=612, rotation_degrees=90)
        self.assertTrue(canvas.create_text.called)
        self.assertTrue(all(call.kwargs.get('angle') == 270 for call in canvas.create_text.call_args_list))

    def test_manual_quarter_turn_is_not_reset_for_landscape_wj_mirror(self):
        panel = programmer.Panel(1, 1, 'Mirror NOTCH', 80, 28, 'WJ', mirror_glass=True,
                                 source_dxf=Path('source.dxf'), rotation_degrees=90,
                                 indicator_corner='bottom_left', manual_rotation_override=True)
        with mock.patch.object(programmer, 'wj_needs_quarter_turn_for_horizontal_output', return_value=False):
            programmer.adjust_wj_rotation_for_indicator(panel, {})
        self.assertEqual(panel.rotation_degrees, 90)

    def test_setup_requires_packaged_exe_instead_of_pythonw_shortcut(self):
        setup = (ROOT / 'First-Time Setup.ps1').read_text()
        self.assertIn('Ensure-FirstTimeExecutable', setup)
        self.assertNotIn("$Target = Join-Path $Venv 'Scripts\\pythonw.exe'", setup)

    def test_explicit_rotate_wins_over_existing_manual_wj_corner(self):
        panel = programmer.Panel(1, 0, 'Mirror NOTCH', 80, 28, 'WJ', mirror_glass=True,
                                 source_dxf=Path('source.dxf'), rotation_degrees=0)
        config = {'item_overrides': {'900001': {'1': {'manual_indicator_corner': True,
                  'indicator_corner': 'bottom_left', 'manual_dxf_rotation': True, 'rotation_degrees': 90}}}}
        with mock.patch.object(programmer, 'wj_needs_quarter_turn_for_horizontal_output', return_value=False), \
             mock.patch.object(programmer, 'panel_is_landscape', return_value=True):
            programmer.apply_override(panel, config, '900001')
            programmer.adjust_indicator_for_source_dxf(panel, config)
        self.assertEqual(panel.rotation_degrees, 90)

    def test_close_is_idempotent_and_cancels_active_task(self):
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        app.root = mock.Mock()
        app.operation_active = mock.Mock(return_value=False)
        app.save_ui_settings = mock.Mock()
        app.cancel_review_opening_feedback = mock.Mock()
        app.task_manager = mock.Mock()
        app.review_context_prefetcher = mock.Mock()
        app.cache_maintenance = mock.Mock()
        app.managed_page_window = mock.Mock(return_value=None)
        app.on_close()
        app.on_close()
        app.task_manager.cancel.assert_called_once()
        app.root.destroy.assert_called_once()

    def test_exit_does_not_wait_forever_on_executor_threads(self):
        with mock.patch.object(gui.multiprocessing, 'active_children', return_value=[]), \
             mock.patch.object(gui.threading, 'enumerate', return_value=[mock.Mock(daemon=False,
                              is_alive=mock.Mock(return_value=True))]), \
             mock.patch.object(gui.os, '_exit') as exit_process:
            gui.finish_application_process_shutdown()
        exit_process.assert_called_once_with(0)

    def test_real_process_exits_with_blocked_executor_and_owned_child(self):
        snippet = (
            "import sys,time,multiprocessing; from concurrent.futures import ThreadPoolExecutor; "
            "sys.path.insert(0,sys.argv[1]); import shower_programmer_gui as gui; "
            "child=multiprocessing.get_context('spawn').Process(target=time.sleep,args=(60,)); child.start(); "
            "pool=ThreadPoolExecutor(1); pool.submit(time.sleep,60); "
            "print('Closing isolated test process',flush=True); gui.finish_application_process_shutdown()"
        )
        started = time.monotonic()
        result = subprocess.run([sys.executable, '-c', snippet, str(ROOT / 'Backend')],
                                capture_output=True, text=True, timeout=8)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Closing isolated test process', result.stdout)
        self.assertLess(time.monotonic()-started, 6)


if __name__ == '__main__':
    unittest.main()
