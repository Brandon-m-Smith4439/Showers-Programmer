"""Preserve operator DXF geometry using verified generation coordinates."""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Callable

import shower_cache


def history_dir(output: Path) -> Path:
    name = '.Sketch History' if output.suffix.casefold() == '.pdf' else '.DXF History'
    return output.parent / name / output.stem


def verified_program_for_source(source: Path, output: Path) -> Path | None:
    """Use saved output for review only when its generation source is still current."""
    source, output = Path(source), Path(output)
    try:
        if not source.is_file() or not output.is_file():
            return None
        metadata = history_dir(output) / 'state.json'
        if any(path.is_symlink() or getattr(path, 'is_junction', lambda: False)()
               for path in (output, metadata, *metadata.parents)):
            return None
        state = json.loads(metadata.read_text(encoding='utf-8'))
        rotation, scale = float(state['rotation']), float(state['scale'])
        if (state['schema'] == 1 and state['output_name'] == output.name
                and state['source_sha256'] == shower_cache.file_sha256(source)
                and math.isfinite(rotation) and math.isfinite(scale) and scale > 0):
            return output
    except (OSError, ValueError, TypeError, KeyError):
        pass
    return None


def preserve_version(output: Path) -> Path:
    directory = history_dir(output)
    if any(path.is_symlink() or getattr(path, 'is_junction', lambda: False)()
           for path in (output, directory, *directory.parents)):
        raise RuntimeError('Cannot preserve output through linked folders or files.')
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f'{shower_cache.file_sha256(output)}{output.suffix.lower()}'
    if target.is_symlink():
        raise RuntimeError('Preserved output path is a link.')
    if not target.exists():
        shutil.copy2(output, target)
    if shower_cache.file_sha256(target) != shower_cache.file_sha256(output):
        raise RuntimeError(f'Could not verify the preserved output copy: {target}')
    return target


def write_program(
    source: Path, output: Path, rotation: float, scale: float, insunits: str,
    measurement: str, force: bool, transform: Callable[..., None],
    read_pairs: Callable[..., list[list[str]]] | None = None,
) -> bool:
    """Return whether edited geometry was retained. Never guess legacy orientation."""
    source, output = Path(source), Path(output)
    if source.resolve() == output.resolve():
        raise ValueError('Source and output DXFs must be different files.')
    if output.exists() and not force:
        raise FileExistsError(f'{output} already exists. Use --force to overwrite.')
    rotation, scale = float(rotation), float(scale)
    if not math.isfinite(rotation) or not math.isfinite(scale) or scale <= 0:
        raise ValueError('Invalid DXF rotation or output scale.')
    directory = history_dir(output)
    if any(path.is_symlink() or getattr(path, 'is_junction', lambda: False)()
           for path in (output, directory, *directory.parents)):
        raise RuntimeError('DXF output/history must not use linked folders or files.')
    directory.mkdir(parents=True, exist_ok=True)
    state_path = directory / 'state.json'
    if state_path.is_symlink():
        raise RuntimeError('DXF orientation history must not be a linked file.')
    source_hash = shower_cache.file_sha256(source)
    output_hash = shower_cache.file_sha256(output) if output.exists() else ''
    state = None
    if output_hash and state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding='utf-8'))
            if state['schema'] != 1 or state['output_name'] != output.name:
                raise ValueError('Unexpected program identity')
            if any(not re.fullmatch(r'[a-f0-9]{64}', str(state.get(key, '')))
                   for key in ('source_sha256', 'output_sha256')):
                raise ValueError('Missing content verification')
            old_rotation, old_scale = float(state['rotation']), float(state['scale'])
            if not math.isfinite(old_rotation) or not math.isfinite(old_scale) or old_scale <= 0:
                raise ValueError('Invalid generation coordinates')
        except Exception as exc:
            raise RuntimeError(f'DXF orientation history is invalid; kept {output.name} unchanged.') from exc
    edited = bool(state and (state.get('manual_geometry') or output_hash != state.get('output_sha256')))
    if edited and source_hash != state.get('source_sha256'):
        raise RuntimeError(f'The source DXF changed while {output.name} has manual edits. Kept the edited program; verify the source revision first.')
    basis, delta_rotation, delta_scale = source, rotation, scale
    if edited:
        if read_pairs is not None:
            pairs = read_pairs(output)
            for index, pair in enumerate(pairs):
                if pair[0].strip() == '9' and pair[1].strip().upper() == '$INSUNITS':
                    unit_pair = next((value for value in pairs[index + 1:index + 8] if value[0].strip() == '70'), None)
                    if unit_pair is None or unit_pair[1].strip() != str(state.get('insunits')):
                        raise RuntimeError('Edited DXF units changed outside the programmer. Kept the file; verify its units before reprocessing.')
                    break
            else:
                raise RuntimeError('Edited DXF has no verified units. Kept the file unchanged.')
        basis = output
        delta_rotation = rotation - old_rotation
        delta_scale = scale / old_scale
    token = uuid.uuid4().hex
    staged = directory / f'.write-{token}.part'
    staged_state = directory / f'.state-{token}.part'
    backup = None
    replaced = False
    try:
        if edited and abs(delta_rotation) < 1e-10 and abs(delta_scale - 1) < 1e-10 and str(state.get('insunits')) == insunits:
            shutil.copy2(output, staged)
        else:
            transform(basis, staged, delta_rotation, force=True, scale=delta_scale,
                      insunits=insunits, measurement=measurement)
        if output_hash and state is None and shower_cache.file_sha256(staged) != output_hash:
            raise RuntimeError(f'No reliable DXF orientation history exists for {output.name}. Kept the existing program unchanged; review it before resetting or reprocessing.')
        payload = {
            'schema': 1, 'output_name': output.name,
            'source_sha256': source_hash, 'source_path': str(source.resolve()),
            'rotation': rotation, 'scale': scale, 'insunits': insunits,
            'output_sha256': shower_cache.file_sha256(staged), 'manual_geometry': edited,
        }
        staged_state.write_text(json.dumps(payload, indent=2), encoding='utf-8')
        # Do not replace files that changed while they were being transformed.
        if shower_cache.file_sha256(source) != source_hash or (
            (shower_cache.file_sha256(output) if output.exists() else '') != output_hash
        ):
            raise RuntimeError('DXF changed during reprocessing; kept the current file. Close the editor and retry.')
        if output_hash:
            backup = preserve_version(output)
            if shower_cache.file_sha256(output) != output_hash:
                raise RuntimeError('DXF changed while preserving its previous version. Kept the current file.')
        os.replace(staged, output)
        replaced = True
        os.replace(staged_state, state_path)
        return edited
    except Exception:
        if replaced and backup is not None:
            shutil.copy2(backup, output)
        raise
    finally:
        for path in (staged, staged_state):
            path.unlink(missing_ok=True)
