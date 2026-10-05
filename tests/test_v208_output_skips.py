from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
import shower_batch
import shower_programmer as programmer
import shower_programmer_gui as gui
from pypdf import PdfReader, PdfWriter
from shower_temp import workspace_temporary_directory


class OutputSkipTests(unittest.TestCase):
    def test_independent_skips_write_only_requested_files_and_exclude_old_output(self):
        import ezdxf
        for skip_pdf, skip_dxf in ((False, False), (True, False), (False, True), (True, True)):
            with self.subTest(skip_pdf=skip_pdf, skip_dxf=skip_dxf), workspace_temporary_directory(prefix='skip-v208') as raw:
                root = Path(raw)
                output = root / 'Output'
                run = output / 'Runs/10.5.26/Batch QA'
                sketches, programs, reports = (run / name for name in ('Sketches', 'Programs', 'Reports'))
                for directory in (sketches, programs, reports):
                    directory.mkdir(parents=True)
                pdf = root / 'Glass Order QA.pdf'
                writer = PdfWriter()
                writer.add_blank_page(612, 792)
                writer.write(pdf)
                writer.close()
                source = root / 'QA__P1.dxf'
                doc = ezdxf.new('R2018')
                doc.header['$INSUNITS'] = 1
                doc.modelspace().add_lwpolyline([(0,0),(80,0),(80,28),(0,28)], close=True)
                doc.saveas(source)
                panel = programmer.Panel(1, 0, 'Mirror NOTCH', 80, 28, 'WJ', mirror_glass=True,
                    source_dxf=source, output_dxf=programs/'90000101.dxf', rotation_degrees=0)
                job = programmer.Job(pdf, '900001', 'QA', [panel], sketches/'900001.pdf', reports/'900001.txt')
                order = shower_batch.ProcessOrder('900001', 'QA', 'QA')
                order.items[1] = shower_batch.ProcessItem(1, width_text='80', height_text='28', processing=['WJ'])
                with mock.patch.object(shower_batch, 'prepare_job', return_value=(job, PdfReader(pdf), [])):
                    result = shower_batch.process_one_order(order, root, sketches, programs, reports, {},
                        apply=True, force=True, skip_pdf=skip_pdf, skip_dxf=skip_dxf)
                self.assertNotEqual(result.status, 'FAILED', result.issues)
                self.assertEqual(job.output_pdf.exists(), not skip_pdf)
                self.assertEqual(panel.output_dxf.exists(), not skip_dxf)
                old = output / 'Runs/10.4.26/Batch QA'
                for relative in ('Sketches/900001.pdf', 'Programs/90000101.dxf'):
                    path = old / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b'older output must not bypass latest skips')
                entry = {'run_folder':str(run), 'sketch_output_skipped':skip_pdf, 'dxf_output_skipped':skip_dxf}
                history = {'orders': {'900001':entry}}
                app = gui.ShowerProgrammerApp.__new__(gui.ShowerProgrammerApp)
                app.last_run_folder = run
                app.history_for_order = lambda _aw: entry
                app.tree_issue_text_for_order = lambda _aw: ''
                pdf_paths = app.generated_sketch_paths_for_orders(['900001'], output, history)
                dxf_paths = app.generated_dxf_paths_for_orders(['900001'], output, history)
                self.assertEqual(pdf_paths, [] if skip_pdf else [job.output_pdf])
                self.assertEqual(dxf_paths, [] if skip_dxf else [panel.output_dxf])
                self.assertEqual(app.send_plan_warnings_for_order(order, include_sketches=True,
                    include_programs=True, sketch_paths=pdf_paths, dxf_paths=dxf_paths), [])


if __name__ == '__main__':
    unittest.main()
