from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUI = ROOT / "Backend" / "shower_programmer_gui.py"
VERSION = ROOT / "Backend" / "version.json"
FLAGS = ROOT / "Backend" / "release_required_flags.txt"


class PackagedSelfTestReliabilityTests(unittest.TestCase):
    def test_reconciliation_selftest_uses_filesystem_readback_and_scoped_warning_check(self) -> None:
        source = GUI.read_text(encoding="utf-8")
        self.assertIn("production_process_mtime = production_process_file.stat().st_mtime", source)
        self.assertIn("updated_production_mtime = production_stale_b.stat().st_mtime", source)
        self.assertIn("stale_second_warnings", source)
        self.assertNotIn(
            'if [order.aw_order for order in second_reconciled] != ["236506"] or second_warnings:',
            source,
        )
        self.assertIn('set(second_matches) != {"236506"}', source)
        self.assertIn("second_checked != 1", source)

    def test_failure_message_carries_packaged_runtime_diagnostics(self) -> None:
        source = GUI.read_text(encoding="utf-8")
        self.assertIn('f"reconciled={second_aw!r}, matches={sorted(second_matches)!r}, "', source)
        self.assertIn('f"checked={second_checked!r}, warnings={second_warnings!r}, "', source)
        self.assertIn('f"updated_sketch_mtime={updated_production_mtime!r}."', source)

    def test_version_183_release_metadata_and_flags(self) -> None:
        version = json.loads(VERSION.read_text(encoding="utf-8"))
        self.assertGreaterEqual(version["version_number"], 183)
        self.assertIn("VERSION_1_83_PACKAGED_SELFTEST_RELIABILITY", (ROOT / "Backend" / "shower_v4_features.py").read_text(encoding="utf-8"))
        flags = FLAGS.read_text(encoding="utf-8")
        self.assertIn("packaged_reconciliation_selftest_stability", flags)
        self.assertIn("version_1_83_packaged_selftest_reliability", flags)


if __name__ == "__main__":
    unittest.main()
