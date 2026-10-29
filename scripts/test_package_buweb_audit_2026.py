#!/usr/bin/env python3
"""Executa o empacotamento Rust completo sobre bytes sintéticos identificados."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests/fixtures/audit-2026/synthetic.csv"


class PackageTests(unittest.TestCase):
    def test_actual_roundtrip_and_extra_file_rejection(self):
        binary = REPO / "target/debug/tsepack"
        self.assertTrue(binary.is_file(), "cargo test deve construir o binário")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            (source / "MT").mkdir(parents=True)
            csv = source / "MT/synthetic.csv"
            shutil.copyfile(FIXTURE, csv)
            body = csv.read_bytes()
            expected = root / "expected.json"
            expected.write_text(json.dumps({"format_version": 1, "inputs": [
                {"path": str(csv), "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}]}))
            output = root / "output"
            def run(destination):
                return subprocess.run([sys.executable, str(REPO / "scripts/package_buweb_audit_2026.py"),
                    "--input", str(source), "--expected-manifest", str(expected), "--output", str(destination),
                    "--binary", str(binary), "--method", "zstd-3", "--source", "fixture-sintetica-nao-TSE"],
                    capture_output=True, text=True)
            result = run(output)
            self.assertEqual(result.returncode, 0, result.stderr+result.stdout)
            report = json.loads((output/"package-run.json").read_text())
            self.assertTrue(report["success"])
            self.assertEqual(report["selected_files"], 1)
            self.assertEqual((output/"restored/MT/synthetic.csv").read_bytes(), body)
            asset = output/report["release_asset"]["file"]
            self.assertEqual(hashlib.sha256(asset.read_bytes()).hexdigest(), report["release_asset"]["sha256"])
            with zipfile.ZipFile(asset) as bundle:
                self.assertEqual(set(bundle.namelist()), set(report["bundle_members"]))
                for name, expected_member in report["bundle_members"].items():
                    restored = bundle.read(name)
                    self.assertEqual(hashlib.sha256(restored).hexdigest(), expected_member["sha256"])
            shutil.copyfile(FIXTURE, source/"extra.csv")
            bad = root/"bad"
            result = run(bad)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((bad/"buweb-csv-comprimido.zip").exists())
            self.assertIn("sem descartar extras", json.loads((bad/"package-run.json").read_text())["error"])


if __name__ == "__main__":
    unittest.main()
