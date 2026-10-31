#!/usr/bin/env python3
"""Inventário sintético identificado; bytes da fixture fixa, sem rede real."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from fetch_mt_historico import catalog
from acquire_2026 import fetch, limits_at
import test_acquire_2026 as acquisition_tests

URL = acquisition_tests.URL

BODY = (Path(__file__).resolve().parents[1]/"tests/fixtures/audit-2026/synthetic.csv").read_bytes()


class HistoricalFetchTests(unittest.TestCase):
    def test_aliases_preserved_and_bad_official_digest_blocks_promotion(self):
        item = {"url": URL, "name": "synthetic-not-TSE"}
        side = {"url": URL+".sha512", "name": "synthetic-sidecar-not-TSE"}
        result = catalog({"items": [item, dict(item, name="synthetic-alias"), side]})
        self.assertEqual(len(result["items"]), 2)
        data = next(i for i in result["items"] if i["url"] == URL)
        self.assertEqual(len(data["references"]), 2)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root/data["path"]
            target.parent.mkdir(parents=True)
            target.with_name(target.name+".sha512").write_text(hashlib.sha512(BODY+b"different").hexdigest()+"  "+target.name+"\n")
            record = fetch(data, root, {i["url"] for i in result["items"]}, limits_at(Path(__file__).with_name("limits.env")), acquisition_tests.AcquisitionTests().opener(BODY))
            self.assertEqual(record["status"], "error")
            self.assertIn("oficial", record["error"])
            self.assertFalse(target.exists())
            self.assertTrue(target.with_name(target.name+".partial").exists())

    def test_empty_negative_limit_and_unsafe_urls_fail(self):
        for items, kwargs in (([], {}), ([{"url": URL}], {"limit": -1}),
                              ([{"url": "https://example.invalid/fixture.csv"}], {})):
            with self.assertRaises(ValueError):
                catalog({"items": items}, **kwargs)


if __name__ == "__main__":
    unittest.main()
