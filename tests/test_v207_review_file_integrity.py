from __future__ import annotations

import inspect
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Backend'))
import shower_cache
import shower_programmer as programmer
import shower_programmer_gui as gui
import shower_batch
import shower_v4_features
import shower_dxf_history
from shower_temp import workspace_temporary_directory


def dxf(path: Path, radius: float = 0.3125) -> None:
    pairs = [['0', 'SECTION'], ['2', 'HEADER'], ['9', '$INSUNITS'], ['70', '1'],
             ['0', 'ENDSEC'], ['0', 'SECTION'], ['2', 'ENTITIES']]
    for x1, y1, x2, y2 in ((0, 0, 80, 0), (80, 0, 80, 28), (80, 28, 0, 28), (0, 28, 0, 0)):
        pairs.extend([['0', 'LINE'], ['10', str(x1)], ['20', str(y1)], ['11', str(x2)], ['21', str(y2)]])
    pairs.extend([['0', 'ARC'], ['10', '10'], ['20', '27'], ['40', str(radius)],
                  ['50', '180'], ['51', '270'], ['0', 'ENDSEC'], ['0', 'EOF']])
    programmer.write_dxf_pairs(path, pairs)


class ReviewFileIntegrityTests(unittest.TestCase):
    def tearDown(self):
        shower_cache.configure(None)

    def test_context_menu_fits_bottom_of_negative_monitor_work_area(self):
        work = (-1920, -100, 1920, 1000)
        x, y, width, height = gui.ShowerProgrammerApp.context_menu_geometry(-20, 895, 330, 550, work)
        self.assertGreaterEqual(x, -1912)
        self.assertGreaterEqual(y, -92)
        self.assertLessEqual(x + width, -8)
        self.assertLessEqual(y + height, 892)

    def test_oversized_menu_is_bounded_and_uses_scrollable_actions(self):
        _x, _y, width, height = gui.ShowerProgrammerApp.context_menu_geometry(10, 740, 360, 1200, (0, 0, 1280, 760))
        self.assertLessEqual(height, 744)
        self.assertEqual(width, 360)
        source = inspect.getsource(gui.ShowerProgrammerApp.show_themed_context_menu)
        self.assertIn('monitor_work_area_for_window', source)
        self.assertIn('CTkScrollableFrame', source)

    def test_explicit_refresh_rechecks_radii_even_if_file_timestamp_and_size_are_unchanged(self):
        with workspace_temporary_directory(prefix='dxf-refresh') as raw:
            root = Path(raw)
            path = root / 'piece.dxf'
            shower_cache.configure(root / 'cache')
            dxf(path, 0.3125)
            app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
            state = {}
            before = app.order_review_dxf_preview_data(path, state)
            stat = path.stat()
            dxf(path, 0.3750)
            # Keep this equal-length AutoCAD-style rewrite deliberately invisible to stat caches.
            contents = path.read_bytes().replace(b'0.375\r', b'0.3750\r')
            path.write_bytes(contents)
            self.assertEqual(path.stat().st_size, stat.st_size)
            os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
            after = app.order_review_dxf_preview_data(path, state, force_refresh=True)
            self.assertNotEqual(before['internal_radii'], after['internal_radii'])
            self.assertAlmostEqual(after['internal_radii'][0], 0.375)
            self.assertEqual(app.order_review_dxf_preview_data(path, state)['internal_radii'], after['internal_radii'])

    def test_refresh_button_forces_disk_geometry_read(self):
        source = inspect.getsource(gui.ShowerProgrammerApp.open_order_review)
        self.assertIn('force_refresh=True', source)

    def test_manual_radius_edits_survive_reprocess_rotation_and_wj_unit_changes(self):
        with workspace_temporary_directory(prefix='dxf-edits') as raw:
            root = Path(raw)
            source, output = root / 'source.dxf', root / 'Programs' / '23900101.dxf'
            dxf(source)
            panel = programmer.Panel(1, 1, '', 80, 28, 'DENVER 2', source_dxf=source, output_dxf=output, rotation_degrees=0)
            programmer.write_panel_dxf(panel, True, {})
            output.write_bytes(output.read_bytes().replace(b'0.3125', b'0.3750'))
            programmer.write_panel_dxf(panel, True, {})
            self.assertAlmostEqual(programmer.collect_dxf_internal_cut_radii(output)[0], 0.375)
            panel.rotation_degrees = 180
            programmer.write_panel_dxf(panel, True, {})
            self.assertAlmostEqual(programmer.collect_dxf_internal_cut_radii(output)[0], 0.375)
            panel.machine = 'WJ'
            programmer.write_panel_dxf(panel, True, {})
            self.assertAlmostEqual(programmer.collect_dxf_internal_cut_radii(output)[0] / 25.4, 0.375)
            panel.machine = 'DENVER 2'
            programmer.write_panel_dxf(panel, True, {})
            self.assertAlmostEqual(programmer.collect_dxf_internal_cut_radii(output)[0], 0.375)
            self.assertAlmostEqual(programmer.collect_dxf_internal_cut_radii(source)[0], 0.3125)

    def test_unknown_legacy_edited_program_is_not_overwritten_by_guessing(self):
        with workspace_temporary_directory(prefix='dxf-legacy') as raw:
            root = Path(raw)
            source, output = root / 'source.dxf', root / 'Programs' / '23900101.dxf'
            dxf(source)
            programmer.transform_dxf(source, output, 0, True)
            output.write_bytes(output.read_bytes().replace(b'0.3125', b'0.3750'))
            before = output.read_bytes()
            panel = programmer.Panel(1, 1, '', 80, 28, 'DENVER 2', source_dxf=source, output_dxf=output, rotation_degrees=180)
            with self.assertRaisesRegex(RuntimeError, 'orientation history'):
                programmer.write_panel_dxf(panel, True, {})
            self.assertEqual(output.read_bytes(), before)

    def test_source_revision_conflict_keeps_manually_edited_output(self):
        with workspace_temporary_directory(prefix='dxf-conflict') as raw:
            root = Path(raw)
            source, output = root / 'source.dxf', root / 'Programs' / '23900101.dxf'
            dxf(source)
            panel = programmer.Panel(1, 1, '', 80, 28, 'DENVER 2', source_dxf=source, output_dxf=output, rotation_degrees=0)
            programmer.write_panel_dxf(panel, True, {})
            output.write_bytes(output.read_bytes().replace(b'0.3125', b'0.3750'))
            before = output.read_bytes()
            dxf(source, 0.5)
            with self.assertRaisesRegex(RuntimeError, 'source DXF changed'):
                programmer.write_panel_dxf(panel, True, {})
            self.assertEqual(output.read_bytes(), before)

    def test_force_batch_processing_does_not_delete_saved_runs_before_reprocessing(self):
        source = inspect.getsource(gui.ShowerProgrammerApp.worker_run_batch)
        self.assertNotIn('self.clear_existing_outputs_for_orders(', source)

    def test_archived_outputs_use_exact_aw_identity_and_never_return_import_sources(self):
        with workspace_temporary_directory(prefix='archive-outputs') as raw:
            root = Path(raw)
            runs = root / 'Runs' / '10.5.26'
            run = runs / 'Batch 8671'
            for section in ('Sketches', 'Programs'):
                (run / section).mkdir(parents=True)
            wanted_pdf = run / 'Sketches' / '237774.pdf'
            wanted_dxf = run / 'Programs' / '23777401.dxf'
            for path in (wanted_pdf, wanted_dxf, run / 'Sketches' / '2377740.pdf', run / 'Programs' / '237774001.dxf'):
                path.write_bytes(b'saved')
            files = gui.ShowerProgrammerApp.archived_programmed_output_files(root, ['237774'])
            self.assertEqual({entry['path'] for entry in files}, {wanted_pdf, wanted_dxf})
            self.assertEqual({entry['kind'] for entry in files}, {'Sketch', 'DXF'})

    def test_excluded_old_program_is_preserved_but_not_available_for_send(self):
        with workspace_temporary_directory(prefix='dxf-excluded') as raw:
            root = Path(raw)
            source, output = root / 'source.dxf', root / 'Programs' / '23900101.dxf'
            dxf(source)
            panel = programmer.Panel(1, 1, '', 80, 28, 'DENVER 2', source_dxf=source, output_dxf=output, rotation_degrees=0)
            programmer.write_panel_dxf(panel, True, {})
            stale = root / 'Programs' / '23900102.dxf'
            stale.write_bytes(output.read_bytes())
            other = root / 'Programs' / '239001001.dxf'
            other.write_bytes(output.read_bytes())
            job = programmer.Job(root / 'source.pdf', '239001', 'JOB', [panel], root / 'Sketches' / '239001.pdf', root / 'Reports' / '239001_programming_report.txt')
            self.assertEqual(shower_batch.write_dxfs_with_issue_collection(job, True, {}), [])
            self.assertFalse(stale.exists())
            self.assertTrue(other.exists())
            self.assertTrue(list((stale.parent / '.DXF History' / stale.stem).glob('*.dxf')))

    def test_current_output_radius_validation_not_original_radius(self):
        with workspace_temporary_directory(prefix='radius-review') as raw:
            root = Path(raw)
            source, output = root / 'source.dxf', root / 'edited.dxf'
            dxf(source, .3125)
            dxf(output, .375)
            panel = programmer.Panel(1, 1, '3/8" Clear Tempered NOTCH', 80, 28, 'WJ', source_dxf=source)
            self.assertFalse(shower_v4_features.validate_waterjet_internal_radius(panel, {}, programmer))
            self.assertTrue(shower_v4_features.validate_waterjet_internal_radius(panel, {}, programmer, dxf_path=output))
            self.assertFalse(any(w.startswith(shower_v4_features.WJ_RADIUS_WARNING_PREFIX) for w in panel.warnings))

    def test_reopened_radius_validation_uses_verified_program_but_not_other_source_revisions(self):
        with workspace_temporary_directory(prefix='radius-reopen') as raw:
            root = Path(raw)
            source, output = root / 'source.dxf', root / 'Programs' / '23900101.dxf'
            dxf(source, .3125)
            panel = programmer.Panel(1, 1, '3/8" Clear Tempered NOTCH', 80, 28, 'WJ',
                                     source_dxf=source, output_dxf=output, rotation_degrees=0)
            programmer.write_panel_dxf(panel, True, {})
            pairs = programmer.read_dxf_pairs(output)
            for pair in pairs:
                if pair[0] == '40':
                    pair[1] = str(.375 * 25.4)
            programmer.write_dxf_pairs(output, pairs)
            self.assertTrue(shower_v4_features.validate_waterjet_internal_radius(panel, {}, programmer))
            dxf(source, .25)
            self.assertFalse(shower_v4_features.validate_waterjet_internal_radius(panel, {}, programmer))

    def test_overwriting_programmed_sketch_keeps_previous_pdf(self):
        with workspace_temporary_directory(prefix='sketch-history') as raw:
            root = Path(raw)
            output = root / 'Sketches' / '239001.pdf'
            output.parent.mkdir()
            output.write_bytes(b'previous operator sketch')
            job = programmer.Job(root / 'source.pdf', '239001', 'JOB', [], output, root / 'report.txt')
            writer = programmer.PdfWriter()
            writer.add_blank_page(width=612, height=792)
            source = root / 'source.pdf'
            writer.write(source)
            programmer.write_marked_pdf(job, programmer.PdfReader(source), {}, True)
            saved = list(shower_dxf_history.history_dir(output).glob('*.pdf'))
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0].read_bytes(), b'previous operator sketch')
            self.assertEqual(len(programmer.PdfReader(output).pages), 1)

    def test_previous_run_manual_geometry_is_available_to_new_run_reprocessing(self):
        with workspace_temporary_directory(prefix='dxf-carry') as raw:
            root = Path(raw)
            source, old = root / 'source.dxf', root / 'Runs' / 'old' / 'Programs' / '23900101.dxf'
            dxf(source)
            panel = programmer.Panel(1, 1, '', 80, 28, 'DENVER 2', source_dxf=source, output_dxf=old, rotation_degrees=0)
            programmer.write_panel_dxf(panel, True, {})
            old.write_bytes(old.read_bytes().replace(b'0.3125', b'0.3750'))
            new = root / 'Runs' / 'new' / 'Programs' / old.name
            gui.ShowerProgrammerApp.carry_program_to_new_run(old, new, root)
            panel.output_dxf = new
            panel.machine = 'WJ'
            programmer.write_panel_dxf(panel, True, {})
            self.assertAlmostEqual(programmer.collect_dxf_internal_cut_radii(new)[0] / 25.4, .375)
            self.assertAlmostEqual(programmer.collect_dxf_internal_cut_radii(old)[0], .375)

    def test_corrupt_history_and_changed_units_never_replace_edited_file(self):
        with workspace_temporary_directory(prefix='dxf-history-safe') as raw:
            root = Path(raw)
            source, output = root / 'source.dxf', root / 'Programs' / '23900101.dxf'
            dxf(source)
            panel = programmer.Panel(1, 1, '', 80, 28, 'DENVER 2', source_dxf=source, output_dxf=output, rotation_degrees=0)
            programmer.write_panel_dxf(panel, True, {})
            pairs = programmer.read_dxf_pairs(output)
            unit_index = next(i for i, pair in enumerate(pairs) if pair[1] == '$INSUNITS')
            pairs[unit_index + 1][1] = '4'
            programmer.write_dxf_pairs(output, pairs)
            before = output.read_bytes()
            with self.assertRaisesRegex(RuntimeError, 'units changed'):
                programmer.write_panel_dxf(panel, True, {})
            self.assertEqual(output.read_bytes(), before)
            (shower_dxf_history.history_dir(output) / 'state.json').write_text('{}')
            with self.assertRaisesRegex(RuntimeError, 'orientation history is invalid'):
                programmer.write_panel_dxf(panel, True, {})
            self.assertEqual(output.read_bytes(), before)

    def test_history_write_failure_rolls_back_previous_program(self):
        with workspace_temporary_directory(prefix='dxf-rollback') as raw:
            root = Path(raw)
            source, output = root / 'source.dxf', root / 'Programs' / '23900101.dxf'
            dxf(source)
            panel = programmer.Panel(1, 1, '', 80, 28, 'DENVER 2', source_dxf=source, output_dxf=output, rotation_degrees=0)
            programmer.write_panel_dxf(panel, True, {})
            before = output.read_bytes()
            metadata = shower_dxf_history.history_dir(output) / 'state.json'
            state_before = metadata.read_bytes()
            panel.rotation_degrees = 180
            replace = os.replace
            def fail_metadata(src, dst):
                if Path(dst) == metadata:
                    raise PermissionError('history locked')
                replace(src, dst)
            with patch.object(shower_dxf_history.os, 'replace', side_effect=fail_metadata):
                with self.assertRaises(PermissionError):
                    programmer.write_panel_dxf(panel, True, {})
            self.assertEqual(output.read_bytes(), before)
            self.assertEqual(metadata.read_bytes(), state_before)
            self.assertFalse(list(metadata.parent.glob('*.part')))

    def test_dxf_changing_during_transform_is_not_overwritten(self):
        with workspace_temporary_directory(prefix='dxf-concurrent') as raw:
            root = Path(raw)
            source, output = root / 'source.dxf', root / 'Programs' / '23900101.dxf'
            dxf(source)
            panel = programmer.Panel(1, 1, '', 80, 28, 'DENVER 2', source_dxf=source, output_dxf=output, rotation_degrees=0)
            programmer.write_panel_dxf(panel, True, {})
            transform = programmer.transform_dxf
            def concurrent_edit(*args, **kwargs):
                transform(*args, **kwargs)
                output.write_bytes(output.read_bytes().replace(b'0.3125', b'0.3750'))
            panel.rotation_degrees = 180
            with patch.object(programmer, 'transform_dxf', side_effect=concurrent_edit):
                with self.assertRaisesRegex(RuntimeError, 'changed during reprocessing'):
                    programmer.write_panel_dxf(panel, True, {})
            self.assertAlmostEqual(programmer.collect_dxf_internal_cut_radii(output)[0], .375)

    def test_preserved_programmed_sketch_and_dxf_versions_are_visible_in_archives(self):
        with workspace_temporary_directory(prefix='archive-versions') as raw:
            root = Path(raw)
            run = root / 'Runs' / '10.5.26' / 'Batch 8671'
            sketch, program = run / 'Sketches' / '239001.pdf', run / 'Programs' / '23900101.dxf'
            sketch.parent.mkdir(parents=True)
            sketch.write_bytes(b'programmed sketch')
            dxf(program)
            saved_pdf = shower_dxf_history.preserve_version(sketch)
            saved_dxf = shower_dxf_history.preserve_version(program)
            self.assertEqual(saved_pdf.suffix, '.pdf')
            files = gui.ShowerProgrammerApp.archived_programmed_output_files(root, ['239001'])
            self.assertEqual({entry['path'] for entry in files}, {sketch, program, saved_pdf, saved_dxf})


if __name__ == '__main__':
    unittest.main()
