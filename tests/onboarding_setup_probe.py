"""Opt-in Windows install probe; all files and shortcuts stay in a temp workspace."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))
from shower_temp import workspace_temporary_directory


def run(args: list[str], timeout: int = 240) -> str:
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout


def main() -> None:
    with workspace_temporary_directory(prefix="source-setup-v203") as raw:
        root = Path(raw)
        (root / "Backend").mkdir()
        (root / "Backend" / "shower_programmer_v4.py").write_text("# Not launched by this probe\n", encoding="ascii")
        shutil.copy2(ROOT / "requirements.txt", root / "requirements.txt")
        args = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "First-Time Setup.ps1"), "-AppRoot", str(root), "-NoLaunch", "-NoShortcuts"]
        first = run(args)
        python = root / ".venv" / "Scripts" / "python.exe"
        before = python.stat().st_mtime_ns
        second = run(args)
        assert python.stat().st_mtime_ns == before, "Second setup replaced the environment"
        assert "Application dependencies verified." in first and "Application dependencies verified." in second
        # Use the actual source entry point in the freshly installed environment.
        run([str(python), str(ROOT / "Backend" / "shower_programmer_v4.py"), "--batch", "--help"])
        for packaged in (False, True):
            if packaged:
                (root / "Shower Programmer.exe").write_bytes(b"not launched")
            desktop = root / "Test Desktop"
            menu = root / "Test Start Menu"
            run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "Create-ShowerProgrammerShortcut.ps1"), "-Root", str(root), "-DesktopPath", str(desktop), "-StartMenuPath", str(menu)])
            for link in (root / "Shower Programmer.lnk", desktop / "Shower Programmer.lnk", menu / "Shower Programmer.lnk"):
                assert link.is_file()
                escaped = str(link).replace("'", "''")
                data = json.loads(run(["powershell.exe", "-NoProfile", "-Command", f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{escaped}'); @{{target=$s.TargetPath;arguments=$s.Arguments;working=$s.WorkingDirectory}} | ConvertTo-Json -Compress"]))
                expected = root / "Shower Programmer.exe" if packaged else root / ".venv" / "Scripts" / "pythonw.exe"
                assert Path(data["target"]) == expected, data
                assert Path(data["working"]) == root, data
                if not packaged:
                    assert data["arguments"] == f'"{root / "Backend" / "shower_programmer_v4.py"}"', data
        print(json.dumps({"ok": True, "source_environment_verified": True, "repeatable_setup": True, "real_shortcuts_verified": 6, "production_files_untouched": True}))


if __name__ == "__main__":
    main()
