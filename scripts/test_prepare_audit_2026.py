#!/usr/bin/env python3
"""Testa extração/hash/cobertura usando apenas a fixture sintética declarada."""
from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from acquire_2026 import hashes, limits_at, relative_url, write_json
from prepare_audit_2026 import prepare

FIXTURE = Path(__file__).resolve().parents[1] / "tests/fixtures/audit-2026/synthetic.csv"
LIMITS = limits_at(Path(__file__).with_name("limits.env"))


class PreparationTests(unittest.TestCase):
    def build(self, root):
        # URL simulada só para teste; não é uma alegação de publicação no TSE.
        url = "https://cdn.tse.jus.br/synthetic-fixture/buweb/bweb_2t_MT_261020260742.zip"
        path = root / relative_url(url)
        path.parent.mkdir(parents=True)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("synthetic.csv", FIXTURE.read_bytes())
        actual = hashes(path, LIMITS["IO_BUFFER_BYTES"])
        write_json(path.with_name(path.name + ".receipt.json"), actual)
        path.with_name(path.name + ".sha512").write_text(actual["sha512"] + "  " + path.name + "\n")
        return {"items": [{"url": url, "path": relative_url(url)}]}, path

    def test_unchanged_member_bytes_and_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            catalog, _ = self.build(base / "root")
            evidence = base / "evidence"
            evidence.mkdir()
            with patch("prepare_audit_2026.UFS", {"MT"}):
                result = prepare(catalog, base / "root", base / "csv", evidence, LIMITS)
            member = result["inputs"][0]
            self.assertEqual(Path(member["path"]).read_bytes(), FIXTURE.read_bytes())
            self.assertEqual(member["sha256"], hashlib.sha256(FIXTURE.read_bytes()).hexdigest())
            self.assertTrue((evidence / "membros-buweb.json").is_file())

    def test_bad_zip_hash_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            catalog, path = self.build(base / "root")
            with open(path, "ab") as stream:
                stream.write(b"alteracao sintetica")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                prepare(catalog, base / "root", base / "csv", base, LIMITS)

    def test_incomplete_coverage_cannot_produce_national_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            catalog, _ = self.build(base / "root")
            with self.assertRaisesRegex(ValueError, "cobertura incompleta"):
                prepare(catalog, base / "root", base / "csv", base, LIMITS)


if __name__ == "__main__":
    unittest.main()
