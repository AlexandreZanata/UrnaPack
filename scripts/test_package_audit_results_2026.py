#!/usr/bin/env python3
"""Executa empacotamento/restauração com fixture identificada e mutações negativas."""
import hashlib
from pathlib import Path
import tempfile
import unittest
import zipfile

from package_audit_results_2026 import package, verify_bundle
from validate import load_limits

ROOT = Path(__file__).resolve().parents[1]
BODY = (ROOT/"tests/fixtures/audit-2026/synthetic.csv").read_bytes()
LIMITS = load_limits(ROOT)


class ResultPackageTests(unittest.TestCase):
    def test_actual_restore_selection_hash_and_tamper_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root/"source"; source.mkdir()
            (source/"synthetic.csv").write_bytes(BODY)
            (source/"not-selected.csv").write_bytes(BODY)
            report = package(source, root/"output", ["synthetic.csv"], "synthetic-fixture-not-TSE", LIMITS)
            self.assertTrue(report["success"], report)
            asset = root/"output/resultados-auditoria-2026.zip"
            self.assertEqual(report["release_asset"]["sha256"], hashlib.sha256(asset.read_bytes()).hexdigest())
            with zipfile.ZipFile(asset) as archive:
                self.assertEqual(set(archive.namelist()), {"synthetic.csv", "_inventory.json"})
                archive.extract("synthetic.csv", root/"restored")
            self.assertEqual((root/"restored/synthetic.csv").read_bytes(), BODY)
            changed = root/"changed.zip"
            with zipfile.ZipFile(changed, "w") as archive:
                archive.writestr("synthetic.csv", BODY+b"changed")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                verify_bundle(changed, report["files"], LIMITS["IO_BUFFER_BYTES"])

    def test_limits_overlap_symlinks_and_output_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);source = root/"source";source.mkdir()
            (source/"synthetic.csv").write_bytes(BODY)
            report = package(source, root/"limited", ["synthetic.csv"], "synthetic-fixture-not-TSE", dict(LIMITS, MAX_RELEASE_ASSET_BYTES=1))
            self.assertFalse(report["success"])
            self.assertTrue((root/"limited/resultados-auditoria-2026.zip.partial").is_file())
            self.assertFalse((root/"limited/resultados-auditoria-2026.zip").exists())
            for selected in (["synthetic.csv", "synthetic.csv"], ["../source/synthetic.csv"]):
                with self.assertRaises(ValueError):
                    package(source, root/"bad", selected, "synthetic-fixture-not-TSE", LIMITS)
                self.assertFalse((root/"bad").exists())
            (source/"link.csv").symlink_to(source/"synthetic.csv")
            with self.assertRaises(ValueError):
                package(source, root/"bad", ["link.csv"], "synthetic-fixture-not-TSE", LIMITS)
            with self.assertRaisesRegex(ValueError, "dentro da origem"):
                package(source, source/"output", ["synthetic.csv"], "synthetic-fixture-not-TSE", LIMITS)
            self.assertFalse((source/"output").exists())


if __name__ == "__main__":
    unittest.main()
