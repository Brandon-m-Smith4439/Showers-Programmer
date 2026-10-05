from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
from shower_temp import workspace_temporary_directory


@unittest.skipUnless(sys.platform == 'win32', 'Windows onboarding')
class FirstTimeExeTests(unittest.TestCase):
    def fixture(self, root):
        shutil.copy2(ROOT / 'First-Time Setup.ps1', root / 'First-Time Setup.ps1')
        # Exercise real extraction/validation/allowlisting without executing a fake EXE.
        repair = (ROOT / 'Repair Programmer.ps1').read_text()
        repair += "\nfunction Test-ProgrammerRuntime([string]$Folder,[string]$Report) { Assert-ProgrammerBundle $Folder; '{\"ok\":true}' | Set-Content -LiteralPath $Report }\n"
        (root / 'Repair Programmer.ps1').write_text(repair)
        (root / 'Backend').mkdir()
        (root / 'Backend/version.json').write_text(json.dumps({'version_number': 208}))
        (root / 'Recovery').mkdir()
        return root / 'Recovery/program.zip'

    def package(self, zip_path, version=208, extra=None):
        with zipfile.ZipFile(zip_path, 'w') as archive:
            for relative in ('Shower Programmer.exe', 'Assets/ShowersProgrammer.ico',
                             '_internal/pypdfium2_raw/pdfium.dll', '_internal/_tcl_data/init.tcl',
                             '_internal/_tk_data/tk.tcl'):
                archive.writestr('Shower Programmer/' + relative, b'fixture not launched')
            archive.writestr('Shower Programmer/.shower_update.json', json.dumps({'version': f'Version {version//100}.{version%100:02d}'}))
            archive.writestr('Shower Programmer/Input/Orders/Do not import.pdf', b'private')
            if extra:
                archive.writestr('Shower Programmer/' + extra, b'unsafe')

    def run_setup(self, root):
        return subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
            str(root / 'First-Time Setup.ps1'), '-AppRoot', str(root), '-NoLaunch', '-NoShortcuts'],
            capture_output=True, text=True, timeout=25)

    def test_recovers_matching_exe_and_preserves_input_without_importing_zip_data(self):
        with workspace_temporary_directory(prefix='setup-exe-v208') as raw:
            root = Path(raw)
            archive = self.fixture(root)
            self.package(archive)
            sentinel = root / 'Shower Programmer/Input/Orders/Keep.pdf'
            sentinel.parent.mkdir(parents=True)
            sentinel.write_bytes(b'operator work')
            for _ in range(2):
                result = self.run_setup(root)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(sentinel.read_bytes(), b'operator work')
                self.assertTrue((root / 'Shower Programmer/Shower Programmer.exe').is_file())
                self.assertFalse((sentinel.parent / 'Do not import.pdf').exists())
                self.assertTrue((root / 'Shower Programmer/Input/Process List').is_dir())
            self.assertFalse(list(root.glob('.__sp_setup_*')))

    def test_rejects_stale_recovery_package_and_does_not_launch_python(self):
        with workspace_temporary_directory(prefix='setup-stale-v208') as raw:
            root = Path(raw)
            archive = self.fixture(root)
            self.package(archive, version=207)
            result = self.run_setup(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('No complete current Windows package', result.stderr)
            self.assertFalse((root / 'Shower Programmer/Shower Programmer.exe').exists())

    def test_refuses_archive_traversal_before_installing(self):
        with workspace_temporary_directory(prefix='setup-unsafe-v208') as raw:
            root = Path(raw)
            archive = self.fixture(root)
            self.package(archive, extra='../escaped.txt')
            result = self.run_setup(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Unsafe path', result.stderr)
            self.assertFalse((root / 'escaped.txt').exists())
            self.assertFalse(list(root.glob('.__sp_setup_*')))

    def test_setup_fingerprint_matches_real_builder_metadata(self):
        with workspace_temporary_directory(prefix='setup-fingerprint') as raw:
            root = Path(raw)
            self.fixture(root)
            (root / 'Assets').mkdir()
            (root / 'Assets/TestIcon.png').write_bytes(b'asset')
            (root / 'requirements.txt').write_text('dependencies')
            (root / 'Backend/shower_programmer_v4.py').write_text('entrypoint')
            (root / 'Backend/rules').mkdir()
            for name in ('__init__.py', 'archive.py'):
                (root / 'Backend/rules' / name).write_text(name)
            (root / 'Backend/version.json').write_text(json.dumps({'version_number':208,
                'version':'Version 2.08', 'release_name':'QA', 'marker':'QA'}))
            package = root / 'Bundle'
            package.mkdir()
            (package / 'Shower Programmer.exe').write_bytes(b'not launched')
            line = next(line for line in (ROOT / 'Rebuild Shower Programmer EXE.bat').read_text().splitlines()
                        if 'fingerprint=hashlib.sha256' in line)
            snippet = re.search(r'-c "(.*)" "%STAGED_DIR%', line).group(1)
            built = subprocess.run([sys.executable, '-c', snippet, str(package), str(root / 'Backend/version.json'),
                                    str(root / 'Backend/shower_programmer_v4.py'), 'QA'], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            command = f". '{root / 'First-Time Setup.ps1'}'; Get-SetupSourceFingerprint '{root}'"
            checked = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy','Bypass', '-Command',command],
                                     capture_output=True, text=True, timeout=15)
            self.assertEqual(checked.returncode, 0, checked.stderr)
            self.assertEqual(checked.stdout.strip(), json.loads((package / '.shower_update.json').read_text())['source_sha256'])

    def test_modified_source_cannot_reuse_same_version_stale_exe(self):
        with workspace_temporary_directory(prefix='setup-changed-source') as raw:
            root = Path(raw)
            archive = self.fixture(root)
            self.package(archive)
            self.assertEqual(self.run_setup(root).returncode, 0)
            (root / 'Backend/shower_programmer_v4.py').write_text('new source code')
            result = self.run_setup(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('No complete current Windows package', result.stderr)


if __name__ == '__main__':
    unittest.main()
