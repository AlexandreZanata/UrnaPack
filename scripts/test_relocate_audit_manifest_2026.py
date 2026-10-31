#!/usr/bin/env python3
"""Confronto efetivo dos bytes sintéticos na realocação do manifesto."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from relocate_audit_manifest_2026 import relocate

FIXTURE = Path(__file__).resolve().parents[1]/"tests/fixtures/audit-2026/synthetic.csv"


class RelocateTests(unittest.TestCase):
    def test_actual_hash_and_metadata_preservation_then_tamper_failure(self):
        body = FIXTURE.read_bytes()
        manifest = {"format_version": 1, "inputs": [{"uf": "MT", "member": "synthetic.csv",
            "path": "old-fixture-path", "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
            "fixture_label": "synthetic-not-TSE"}]}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/"MT").mkdir()
            restored = root/"MT/synthetic.csv"
            restored.write_bytes(body)
            result = relocate(manifest, root, len(body))
            self.assertEqual(result["inputs"][0]["path"], str(restored))
            self.assertEqual(result["inputs"][0]["fixture_label"], manifest["inputs"][0]["fixture_label"])
            self.assertEqual(manifest["inputs"][0]["path"], "old-fixture-path")
            restored.write_bytes(body[:-1]+bytes([body[-1]^1]))
            with self.assertRaisesRegex(ValueError, "diverge"):
                relocate(manifest, root, len(body))


if __name__ == "__main__":
    unittest.main()
