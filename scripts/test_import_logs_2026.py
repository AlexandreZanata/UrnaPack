#!/usr/bin/env python3
"""Integração da automação e do parser Rust com ZIP e corpos sintéticos rotulados."""
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

from acquire_2026 import hashes, relative_url, write_json
from import_logs_2026 import expected_sections, load_limits, section_key, shift, text_members
from build_time_policy_2026 import build
from collect_logs_2026 import collect

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests/fixtures/audit-2026"
LIMITS = load_limits(REPO / "scripts/limits.env")


class ImportTests(unittest.TestCase):
    def test_nested_zip_bytes_are_not_recoded(self):
        with zipfile.ZipFile(FIXTURE / "logs-synthetic.zip") as outer:
            body = outer.read(outer.infolist()[0])
        members = list(text_members(body, LIMITS))
        self.assertEqual(members, [("logd.dat", (FIXTURE / "logd-synthetic.dat").read_bytes())])

    def test_unknown_inner_member_is_not_discarded(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            archive.writestr("unexpected.binary", (FIXTURE / "logd-synthetic.dat").read_bytes())
        with self.assertRaisesRegex(ValueError, "sem descarte"):
            list(text_members(data.getvalue(), LIMITS))

    def test_real_municipality_policy_and_missing_exception(self):
        original = json.loads((REPO / "auditoria/2026/evidencias/municipios-2t.json").read_text())
        policy = build(original)
        am = next(a for a in original["abr"] if a["cd"] == "am")
        tabatinga = next(m for m in am["mu"] if m["nm"] == "TABATINGA")
        manaus = next(m for m in am["mu"] if m["nm"] == "MANAUS")
        self.assertEqual(shift(policy, "AM", tabatinga["cd"]), 7200)
        self.assertEqual(shift(policy, "AM", manaus["cd"]), 3600)
        am["mu"] = [m for m in am["mu"] if m != tabatinga]
        with self.assertRaisesRegex(ValueError, "exceções municipais incompletas"):
            build(original)

    def test_full_python_rust_pipeline_checks_wire_and_expected_sections(self):
        binary = REPO / "target/debug/audit_logs_2026"
        self.assertTrue(binary.is_file(), "cargo test deve gerar o binário de integração")
        fixture = json.loads((FIXTURE / "log-frame-synthetic.json").read_text())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            url = fixture["header"]["source_zip_url"]
            relative = relative_url(url)
            source = root / "data" / relative
            source.parent.mkdir(parents=True)
            shutil.copyfile(FIXTURE / "logs-synthetic.zip", source)
            actual = hashes(source, LIMITS["IO_BUFFER_BYTES"])
            write_json(source.with_name(source.name + ".receipt.json"), dict(actual, status="synthetic_fixture_not_downloaded"))
            catalog = root / "catalog.json"
            write_json(catalog, {"format_version": 1, "items": [{"url": url, "path": relative}]})
            export = root / "export.json"
            body = (FIXTURE / "log-sections-synthetic.csv").read_bytes()
            write_json(export, {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()})
            out = root / "out"
            result = subprocess.run([sys.executable, str(REPO / "scripts/import_logs_2026.py"),
                "--uf", "MT", "--root", str(root / "data"), "--catalog", str(catalog),
                "--sections", str(FIXTURE / "log-sections-synthetic.csv"), "--export-receipt", str(export),
                "--policy", str(FIXTURE / "log-policy-synthetic.json"), "--binary", str(binary), "--out-dir", str(out)],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout + (out / "parser.stderr.txt").read_text())
            analysis = json.loads((out / "analysis.json").read_text())
            receipt = json.loads((out / "import-run.json").read_text())
            self.assertTrue(analysis["success"] and analysis["coverage_complete"])
            self.assertEqual(analysis["wire_sha256"], receipt["wire_sha256"])
            self.assertEqual(analysis["all_parsed_events"]["completed_after_17_brt"], 1)
            with gzip.open(out / "members.jsonl.gz", "rt") as stream:
                manifest = [json.loads(line) for line in stream]
            self.assertEqual([m["kind"] for m in manifest], ["outer_member", "log"])
            self.assertEqual(receipt["binary"]["sha256"], hashes(binary, LIMITS["IO_BUFFER_BYTES"])["sha256"])
            zeros = root / "zero.json"
            write_json(zeros, {"rows": []})
            batch = root / "batch"
            result = subprocess.run([sys.executable, str(REPO / "scripts/run_logs_2026.py"),
                "--ufs", "MT", "--root", str(root / "data"), "--catalog", str(catalog),
                "--sections", str(FIXTURE / "log-sections-synthetic.csv"), "--export-receipt", str(export),
                "--policy", str(FIXTURE / "log-policy-synthetic.json"), "--binary", str(binary),
                "--zero-sections", str(zeros), "--out-root", str(batch)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            runs = json.loads((batch / "runs.json").read_text())
            self.assertTrue(runs["complete"])
            self.assertEqual(runs["expected_ufs"], ["MT"])
            self.assertEqual(runs["runs"][0]["exit_code"], 0)
            official = REPO / "auditoria/2026/evidencias/totalizacao-presidente-2t.json"
            selected = collect([out], official, LIMITS["IO_BUFFER_BYTES"])
            self.assertEqual(selected["inputs"][0]["sha256"], receipt["outputs"]["analysis.json"]["sha256"])
            with self.assertRaisesRegex(ValueError, "UF duplicada"):
                collect([out, out], official, LIMITS["IO_BUFFER_BYTES"])
            with (out / "analysis.json").open("ab") as stream:
                stream.write(b" ")
            with self.assertRaisesRegex(ValueError, "diverge"):
                collect([out], official, LIMITS["IO_BUFFER_BYTES"])


if __name__ == "__main__":
    unittest.main()
