from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
import shower_programmer as programmer
import shower_programmer_gui as gui
import shower_v4_features as v4
from shower_temp import workspace_temporary_directory


class WaterjetSizeBypassTests(unittest.TestCase):
    config = {'rules': {'waterjet_fit_limit_inches': 75}}

    def panel(self, **kwargs):
        values = dict(item=1, page_index=1, text='Mirror', width=118.1875,
                      height=75.9375, machine='WJ')
        values.update(kwargs)
        return programmer.Panel(**values)

    def approval(self, panel):
        return {'signature': programmer.waterjet_size_signature(panel, self.config),
                'approved_at': '2026-10-05T12:00:00-04:00'}

    def test_oversize_source_is_available_but_cannot_be_written(self):
        panel = self.panel()
        programmer.validate_panel_constraints(panel, self.config)
        job = programmer.Job(Path('job.pdf'), '900001', 'TEST', [panel],
                             Path('sketch.pdf'), Path('report.json'))
        source = Path('source.dxf')
        with mock.patch.object(programmer, 'find_source_dxf', return_value=source) as lookup, \
             mock.patch.object(programmer, 'adjust_indicator_for_source_dxf'), \
             mock.patch.object(programmer, 'apply_dxf_angle_correction'), \
             mock.patch.object(programmer, 'apply_dxf_manual_review_warning'):
            programmer.assign_dxf_paths(job, Path('Input'), Path('Programs'), self.config)
        lookup.assert_called_once()
        self.assertEqual(panel.source_dxf, source)
        self.assertTrue(panel.skip_dxf)
        self.assertIsNone(panel.output_dxf)

    def test_bypass_survives_both_validators_without_clearing_other_warnings(self):
        panel = self.panel(warnings=['Internal radius requires review.'])
        programmer.validate_panel_constraints(panel, self.config)
        panel.waterjet_size_bypass = self.approval(panel)
        programmer.validate_panel_constraints(panel, self.config)
        self.assertTrue(v4.validate_waterjet_envelope(panel, self.config))
        self.assertFalse(panel.skip_dxf)
        self.assertFalse(panel.waterjet_size_blocked)
        self.assertIn('Internal radius requires review.', panel.warnings)
        self.assertTrue(any('bypass approved' in w.lower() for w in panel.warnings))
        self.assertEqual(sum(w.startswith(('WJ size limit:', 'Oversize WJ:'))
                             for w in panel.warnings), 1)

    def test_bypass_is_bound_to_dimensions_and_limit(self):
        panel = self.panel()
        panel.waterjet_size_bypass = self.approval(panel)
        for changes, config in [({'width': 120}, self.config),
                                ({}, {'rules': {'waterjet_fit_limit_inches': 74}})]:
            changed = copy.deepcopy(panel)
            for name, value in changes.items():
                setattr(changed, name, value)
            programmer.validate_panel_constraints(changed, config)
            self.assertTrue(changed.skip_dxf)
        panel.width, panel.height = panel.height, panel.width
        programmer.validate_panel_constraints(panel, self.config)
        self.assertFalse(panel.skip_dxf)

    def test_other_skip_reasons_are_not_bypassed(self):
        panel = self.panel(skip_dxf=True)
        panel.waterjet_size_bypass = self.approval(panel)
        programmer.validate_panel_constraints(panel, self.config)
        v4.validate_waterjet_envelope(panel, self.config)
        self.assertTrue(panel.skip_dxf)
        for excluded in (self.panel(remake_excluded=True), self.panel(label_only=True)):
            programmer.validate_panel_constraints(excluded, self.config)
            job = programmer.Job(Path('job.pdf'), '900001', 'TEST', [excluded],
                                 Path('sketch.pdf'), Path('report.json'))
            with mock.patch.object(programmer, 'find_source_dxf') as lookup:
                programmer.assign_dxf_paths(job, Path('Input'), Path('Programs'), self.config)
            lookup.assert_not_called()

    def test_process_list_reclassifying_oversize_mirror_as_no_fabrication_keeps_its_skip(self):
        panel = self.panel(mirror_glass=True)
        programmer.validate_panel_constraints(panel, self.config)
        panel.machine = ''
        panel.label_only = True
        panel.skip_dxf = True
        programmer.validate_panel_constraints(panel, self.config)
        self.assertTrue(panel.skip_dxf)
        self.assertFalse(panel.waterjet_size_blocked)

    def test_override_is_per_order_and_piece_and_explicit_skip_is_preserved(self):
        panel = self.panel()
        config = copy.deepcopy(self.config)
        config['item_overrides'] = {'900001': {'1': {'waterjet_size_bypass': self.approval(panel)}}}
        programmer.apply_override(panel, config, '900001')
        programmer.validate_panel_constraints(panel, config)
        self.assertFalse(panel.skip_dxf)
        for other, order in [(self.panel(item=2), '900001'), (self.panel(), '900002')]:
            programmer.apply_override(other, config, order)
            programmer.validate_panel_constraints(other, config)
            self.assertTrue(other.skip_dxf)
        config['item_overrides']['900001']['1']['skip_dxf'] = True
        programmer.apply_override(panel, config, '900001')
        programmer.validate_panel_constraints(panel, config)
        self.assertTrue(panel.skip_dxf)

    def test_release_validator_supports_plain_panels_and_clears_only_its_block(self):
        panel = SimpleNamespace(machine='WJ', width=76, height=76, warnings=[], skip_dxf=False)
        self.assertFalse(v4.validate_waterjet_envelope(panel, self.config))
        panel.width = 74
        self.assertTrue(v4.validate_waterjet_envelope(panel, self.config))
        self.assertFalse(panel.skip_dxf)

    def test_gui_approval_persists_and_invalidates_check_without_losing_edits(self):
        with workspace_temporary_directory(prefix='wj-bypass') as raw:
            output = Path(raw)
            app = object.__new__(gui.ShowerProgrammerApp)
            app._manual_overrides_session_output = output
            app._manual_overrides_session_data = {
                'item_overrides': {'900001': {'_order_checked': True,
                                             '1': {'checked': True, 'label_x': 42},
                                             '2': {'label_text': 'keep'}},
                                   '900002': {'_order_checked': True}}}
            panel = self.panel()
            app.set_waterjet_size_bypass('900001', panel, self.config, output, approved=True)
            data = app.load_manual_overrides_for_output(output)
            order = data['item_overrides']['900001']
            self.assertNotIn('_order_checked', order)
            self.assertNotIn('checked', order['1'])
            self.assertEqual(order['1']['label_x'], 42)
            self.assertEqual(order['2']['label_text'], 'keep')
            self.assertTrue(data['item_overrides']['900002']['_order_checked'])
            self.assertEqual(data, app._manual_overrides_session_data)
            app.set_waterjet_size_bypass('900001', panel, self.config, output, approved=False)
            self.assertNotIn('waterjet_size_bypass', app.load_manual_overrides_for_output(output)
                             ['item_overrides']['900001']['1'])

    def test_reinstating_limit_retires_existing_output_and_keeps_a_recoverable_copy(self):
        with workspace_temporary_directory(prefix='wj-reinstate') as raw:
            output = Path(raw)
            app = object.__new__(gui.ShowerProgrammerApp)
            panel = self.panel(output_dxf=output / 'Programs/90000101.dxf')
            panel.output_dxf.parent.mkdir()
            panel.output_dxf.write_bytes(b'edited program preserved')
            app.set_waterjet_size_bypass('900001', panel, self.config, output, approved=True)
            app.set_waterjet_size_bypass('900001', panel, self.config, output, approved=False)
            self.assertFalse(panel.output_dxf.exists())
            copies = list(output.rglob('*.dxf'))
            self.assertTrue(copies)
            self.assertTrue(any(p.read_bytes() == b'edited program preserved' for p in copies))


if __name__ == '__main__':
    unittest.main()
