#!/usr/bin/env python3
"""Respostas CKAN sintéticas; nenhum acesso à rede ou dado eleitoral simulado como real."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stdout
from unittest.mock import patch

import inventory_mt_historico as inventory


class InventoryTests(unittest.TestCase):
    def test_aliases_and_original_response_preserved_404_is_distinct(self):
        resource={"url":"https://cdn.tse.jus.br/synthetic_MT_fixture.zip","name":"MT synthetic fixture","id":"synthetic-ref"}
        raw=json.dumps({"success":True,"result":{"resources":[resource,resource]}}).encode()
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/"synthetic-inventory.json"
            missing=urllib.error.HTTPError(inventory.BASE+"missing",404,"synthetic missing",{},None)
            with patch.object(inventory,"DATASETS",["synthetic-missing","synthetic-present"]),patch("sys.argv",["inventory_mt_historico.py","--output",str(output)]),patch.object(inventory.urllib.request,"urlopen",side_effect=[missing,io.BytesIO(raw)]),redirect_stdout(io.StringIO()):
                self.assertEqual(inventory.main(),0)
            result=json.loads(output.read_text())
            self.assertEqual(len(result["items"]),2)
            self.assertEqual(len(result["unavailable"]),1)
            self.assertFalse(result["errors"])
            self.assertEqual(result["responses"][0]["sha256"],hashlib.sha256(raw).hexdigest())
            self.assertEqual((output.with_name(output.stem+"-ckan")/"synthetic-present.json").read_bytes(),raw)

    def test_network_failure_is_not_missing_dataset_or_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/"synthetic-inventory.json"
            with patch.object(inventory,"DATASETS",["synthetic-failure"]),patch("sys.argv",["inventory_mt_historico.py","--output",str(output)]),patch.object(inventory.urllib.request,"urlopen",side_effect=urllib.error.URLError("synthetic transport failure")),redirect_stdout(io.StringIO()):
                self.assertEqual(inventory.main(),1)
            result=json.loads(output.read_text())
            self.assertTrue(result["errors"])
            self.assertFalse(result["unavailable"])


if __name__ == "__main__":
    unittest.main()
