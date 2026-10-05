from __future__ import annotations

import inspect
from types import SimpleNamespace
from unittest import TestCase, mock

import test_v188_manual_program_send_responsiveness as fixtures
import shower_programmer_gui as gui


class ReviewInteractionsTests(TestCase):
    def test_copy_actions_capture_right_clicked_order_not_first_selected(self):
        app, order, captured = fixtures.ManualProgramSendResponsivenessTests().make_context_app(('row-other', 'row-188'))
        app.tree_row_orders['row-other'] = gui.shower_batch.ProcessOrder('999999', 'OTHER', 'OTHER CUSTOMER')
        order.customer = 'TARGET CUSTOMER'
        app.tree.identify_column = mock.Mock(return_value='#3')
        app.tree.set = mock.Mock(return_value=order.job_name)
        app.copy_order_value_to_clipboard = mock.Mock()
        gui.ShowerProgrammerApp.open_orders_context_menu(app, SimpleNamespace(x=100, y=5, x_root=100, y_root=120))
        actions = {action.get('text'): action for action in captured['actions']}
        actions['Copy to Clipboard']['command']()
        app.copy_order_value_to_clipboard.assert_called_once_with(order.job_name)
        app.tree.set.assert_called_once_with('row-188', '#3')

    def test_clipboard_keeps_full_value_and_uses_no_nested_update(self):
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        app.root = mock.Mock()
        app.status_var = mock.Mock()
        app.copy_order_value_to_clipboard('89420398.2.2R EXACT CUSTOMER', 'Job name')
        app.root.clipboard_clear.assert_called_once_with()
        app.root.clipboard_append.assert_called_once_with('89420398.2.2R EXACT CUSTOMER')
        app.root.update.assert_not_called()

    def test_copy_cell_uses_clicked_column_without_truncating_value(self):
        app, _order, captured = fixtures.ManualProgramSendResponsivenessTests().make_context_app()
        app.tree.identify_column = mock.Mock(return_value='#7')
        app.tree.set = mock.Mock(return_value='FULL UNTRUNCATED CELL VALUE')
        app.copy_order_value_to_clipboard = mock.Mock()
        app.open_orders_context_menu(SimpleNamespace(x=450, y=5, x_root=100, y_root=120))
        next(action for action in captured['actions'] if action.get('text') == 'Copy to Clipboard')['command']()
        app.tree.set.assert_called_once_with('row-188', '#7')
        app.copy_order_value_to_clipboard.assert_called_once_with('FULL UNTRUNCATED CELL VALUE')

    def test_click_observer_runs_before_consuming_handlers_and_cleans_own_tags(self):
        class Widget:
            def __init__(self, name, children=()):
                self.tags = (name, 'class', 'all')
                self.children = children

            def bindtags(self, tags=None):
                if tags is not None:
                    self.tags = tags
                return self.tags

            def winfo_children(self):
                return self.children

        outside = Widget('outside')
        popup = Widget('popup')
        root = Widget('root', (outside, popup))
        root.bind_class = mock.Mock(return_value='callback')
        root.unbind_class = mock.Mock()
        root.deletecommand = mock.Mock()
        app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
        app.root = root
        app.active_themed_context_popup = popup
        app.install_context_outside_click_observer(popup)
        self.assertTrue(outside.tags[0].startswith('ShowerContextClick'))
        self.assertEqual(popup.tags, ('popup', 'class', 'all'))
        app.clear_context_outside_click_observer(popup)
        self.assertEqual(outside.tags, ('outside', 'class', 'all'))
        root.deletecommand.assert_called_once_with('callback')
        self.assertIsNone(app._context_click_observer)

    def test_editor_focus_is_attached_to_presentation_not_timer(self):
        source = inspect.getsource(gui.ShowerProgrammerApp.ask_themed_text)
        self.assertIn('_shower_preferred_focus_widget', source)
        self.assertIn('on_presented=', source)
        self.assertNotIn('prompt.after(100, text_box.focus_set)', source)

    def test_menu_destroy_cleanup_ignores_descendant_events(self):
        source = inspect.getsource(gui.ShowerProgrammerApp.show_themed_context_menu)
        self.assertIn('_event.widget is not popup', source)
        self.assertIn('install_context_outside_click_observer', source)
