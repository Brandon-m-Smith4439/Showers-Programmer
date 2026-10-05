from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
import shower_cache
import shower_dxf_history as history
from shower_temp import workspace_temporary_directory


class DxfMirrorTests(unittest.TestCase):
    def test_review_unchecks_order_before_changing_program_geometry(self):
        source = (ROOT / 'Backend/shower_programmer_gui.py').read_text()
        handler = source.split('        def mirror_current_dxf() -> None:', 1)[1].split(
            '        def open_current_dxf() -> None:', 1)[0]
        self.assertLess(handler.index('self.set_selected_orders_checked(False'),
                        handler.index('shower_dxf_mirror.mirror_program('))

    def test_reflection_preserves_arcs_units_and_history_for_reprocessing(self):
        import ezdxf
        import shower_dxf_mirror
        from ezdxf.math import Vec3
        with workspace_temporary_directory(prefix='mirror-v208') as raw:
            root = Path(raw)
            output = root / '90000101.dxf'
            doc = ezdxf.new('R2018')
            doc.header['$INSUNITS'] = 4
            msp = doc.modelspace()
            msp.add_lwpolyline([(0, 0), (80, 0), (80, 28), (0, 28)], close=True)
            arc = msp.add_arc((10, 10), 3, 0, 90)
            start, end = arc.start_point, arc.end_point
            doc.saveas(output)
            original = output.read_bytes()
            state_path = history.history_dir(output) / 'state.json'
            state_path.parent.mkdir(parents=True)
            state = {'schema': 1, 'output_name': output.name, 'rotation': 0, 'scale': 25.4,
                     'insunits': '4', 'output_sha256': shower_cache.file_sha256(output),
                     'source_sha256': '0' * 64}
            state_path.write_text(json.dumps(state))
            backup = shower_dxf_mirror.mirror_program(output, 'horizontal')
            self.assertEqual(backup.read_bytes(), original)
            reflected = ezdxf.readfile(output)
            arc = reflected.modelspace().query('ARC')[0]
            self.assertTrue(arc.start_point.isclose(Vec3(80-end.x, end.y, 0)))
            self.assertTrue(arc.end_point.isclose(Vec3(80-start.x, start.y, 0)))
            self.assertEqual(arc.dxf.extrusion, Vec3(0, 0, 1))
            self.assertEqual(reflected.header['$INSUNITS'], 4)
            self.assertEqual(reflected.dxfversion, 'AC1032')
            state = json.loads(state_path.read_text())
            self.assertTrue(state['manual_geometry'])
            self.assertEqual(state['output_sha256'], shower_cache.file_sha256(output))
            shower_dxf_mirror.mirror_program(output, 'vertical')
            arc = ezdxf.readfile(output).modelspace().query('ARC')[0]
            self.assertTrue(arc.start_point.isclose(Vec3(80-start.x, 28-start.y, 0)))

    def test_unsupported_or_three_dimensional_geometry_is_not_replaced(self):
        import ezdxf
        import shower_dxf_mirror
        with workspace_temporary_directory(prefix='mirror-reject') as raw:
            output = Path(raw) / 'program.dxf'
            for kind in ('text', '3d'):
                doc = ezdxf.new('R2018')
                doc.modelspace().add_line((0, 0), (80, 28, 1 if kind == '3d' else 0))
                if kind == 'text':
                    doc.modelspace().add_text('Do not silently mirror text')
                doc.saveas(output)
                before = output.read_bytes()
                with self.assertRaises(RuntimeError):
                    shower_dxf_mirror.mirror_program(output, 'horizontal')
                self.assertEqual(output.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
