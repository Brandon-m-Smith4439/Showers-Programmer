"""Explicit, recoverable reflection of the current planar CNC program."""
from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path

import shower_cache
import shower_dxf_history


def mirror_program(output: Path, direction: str) -> Path:
    if direction not in {'horizontal', 'vertical'}:
        raise ValueError('Choose horizontal or vertical mirroring.')
    # Loaded only for this explicit action, never on startup or during a scan.
    import ezdxf
    from ezdxf import bbox, transform
    from ezdxf.math import Matrix44
    from ezdxf.upright import upright_all

    output = Path(output)
    backup = shower_dxf_history.preserve_version(output)
    before = shower_cache.file_sha256(output)
    if shower_cache.file_sha256(backup) != before:
        raise RuntimeError('The program changed while preserving its previous version. Close the editor and retry.')
    directory = shower_dxf_history.history_dir(output)
    state_path = directory / 'state.json'
    old_state = state_path.read_bytes() if state_path.exists() else None
    state = json.loads(old_state) if old_state is not None else None
    if state is not None and (state.get('schema') != 1 or state.get('output_name') != output.name):
        raise RuntimeError('The program history does not match this DXF. Nothing was mirrored.')
    doc = ezdxf.readfile(output)
    entities = list(doc.modelspace())
    supported = {'LINE', 'ARC', 'CIRCLE', 'ELLIPSE', 'LWPOLYLINE', 'POLYLINE', 'SPLINE', 'POINT'}
    if not entities or any(entity.dxftype() not in supported for entity in entities):
        raise RuntimeError('This DXF contains text, blocks or unsupported geometry. Mirror it in your CAD editor instead; the program was kept unchanged.')
    extents = bbox.extents(entities, fast=False)
    if not extents.has_data or abs(extents.extmax.z - extents.extmin.z) > 1e-8 or abs(extents.extmin.z) > 1e-8:
        raise RuntimeError('Only flat, two-dimensional CNC geometry can be mirrored.')
    for entity in entities:
        extrusion = entity.dxf.get('extrusion', (0, 0, 1))
        if abs(extrusion[0]) > 1e-8 or abs(extrusion[1]) > 1e-8:
            raise RuntimeError('Tilted entity coordinate systems cannot be mirrored safely.')
    cx = (extents.extmin.x + extents.extmax.x) / 2
    cy = (extents.extmin.y + extents.extmax.y) / 2
    matrix = (Matrix44.translate(-cx, -cy, 0)
              @ Matrix44.scale(-1 if direction == 'horizontal' else 1,
                               -1 if direction == 'vertical' else 1, 1)
              @ Matrix44.translate(cx, cy, 0))
    errors = transform.inplace(entities, matrix)
    if errors:
        raise RuntimeError('DXF mirror was refused: ' + '; '.join(errors.messages()))
    # The preview/core reader expects a positive planar extrusion. Restore this
    # representation after reflection without losing arc or bulge geometry.
    upright_all(entities)
    token = uuid.uuid4().hex
    staged = directory / f'.mirror-{token}.dxf'
    staged_state = directory / f'.mirror-{token}.json'
    replaced = False
    try:
        doc.saveas(staged)
        verified = ezdxf.readfile(staged)
        if len(verified.modelspace()) != len(entities) or verified.header.get('$INSUNITS') != doc.header.get('$INSUNITS'):
            raise RuntimeError('Mirrored DXF did not pass the geometry/unit check.')
        if state is not None:
            state['manual_geometry'] = True
            state['output_sha256'] = shower_cache.file_sha256(staged)
            staged_state.write_text(json.dumps(state, indent=2), encoding='utf-8')
        if shower_cache.file_sha256(output) != before or (state_path.read_bytes() if state_path.exists() else None) != old_state:
            raise RuntimeError('The program changed during mirroring. Close the editor and retry.')
        os.replace(staged, output)
        replaced = True
        if state is not None:
            os.replace(staged_state, state_path)
        return backup
    except Exception:
        if replaced:
            shutil.copy2(backup, output)
        raise
    finally:
        staged.unlink(missing_ok=True)
        staged_state.unlink(missing_ok=True)
