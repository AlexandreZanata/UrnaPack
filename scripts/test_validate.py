#!/usr/bin/env python3
"""Regressões do validador do repositório (Etapa 1).

Cobre: preservação de erros acumulados quando o índice é válido e falha
explícita quando a validação completa de schema está indisponível.
"""

import argparse
import json
import os
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import validate as V


class TestAcumuloErros(unittest.TestCase):
    def test_repo_preserva_erro_com_indice_valido(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Estrutura mínima de repo: scripts/limits.env + data/index.json válido.
            os.makedirs(os.path.join(tmp, "scripts"))
            os.makedirs(os.path.join(tmp, "data"))
            with open(os.path.join(ROOT, "scripts", "limits.env"), encoding="utf-8") as f:
                limits = f.read()
            with open(os.path.join(tmp, "scripts", "limits.env"), "w", encoding="utf-8") as f:
                f.write(limits)
            # Índice válido (vazio não dispara duplicata; cmd_repo só checa duplicatas).
            idx = {"format_version": 1, "datasets": []}
            with open(os.path.join(tmp, "data", "index.json"), "w", encoding="utf-8") as f:
                f.write(json.dumps(idx))
            # Arquivo proibido (.upk) deve gerar erro que não pode sumir.
            with open(os.path.join(tmp, "pacote.upk.zst"), "wb") as f:
                f.write(b"fake")
            # Schemas mínimos para não mascarar o erro principal.
            os.makedirs(os.path.join(tmp, "spec"), exist_ok=True)
            for name in ("manifest.schema.json", "index.schema.json"):
                with open(os.path.join(ROOT, "spec", name), encoding="utf-8") as f:
                    content = f.read()
                with open(os.path.join(tmp, "spec", name), "w", encoding="utf-8") as g:
                    g.write(content)
            # Executa cmd_repo no repo sintético.
            errors = V.cmd_repo(argparse.Namespace(root=tmp))
            self.assertTrue(any("pacote binário" in e for e in errors),
                            msg=f"erros: {errors}")


class TestSchemaIndisponivel(unittest.TestCase):
    def test_dataset_v2_migrado_aprova_e_vincula_origem(self):
        good = os.path.join(ROOT, "tests", "fixtures", "dataset-v2-good.json")
        origin = os.path.join(ROOT, "tests", "fixtures", "origin-v2-good.json")
        ns = argparse.Namespace(manifest=good, data_root=None, max_bytes=10**12,
                                max_assets=1000, require_status=None,
                                schema_version="auto", source_manifest=origin)
        self.assertEqual(V.cmd_manifest(ns), [])

    def test_dataset_v1_nao_passa_em_v2(self):
        v1 = os.path.join(ROOT, "tests", "fixtures", "manifest-good.json")
        ns = argparse.Namespace(manifest=v1, data_root=None, max_bytes=10**12,
                                max_assets=1000, require_status=None,
                                schema_version="2", source_manifest=None)
        errs = V.cmd_manifest(ns)
        self.assertTrue(errs, "v1 deveria reprovar no schema v2")

    def test_dataset_v2_campo_desconhecido_reprova(self):
        import copy
        good = os.path.join(ROOT, "tests", "fixtures", "dataset-v2-good.json")
        with open(good, encoding="utf-8") as f:
            doc = json.load(f)
        doc["garantia_futura"] = "nao-transportar"
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(doc, f)
            tmp = f.name
        try:
            ns = argparse.Namespace(manifest=tmp, data_root=None, max_bytes=10**12,
                                    max_assets=1000, require_status=None,
                                    schema_version="2", source_manifest=None)
            errs = V.cmd_manifest(ns)
            self.assertTrue(any("fora do schema" in e or "obrigatório" in e or "schema" in e for e in errs),
                            msg=f"erros: {errs}")
        finally:
            os.remove(tmp)

    def test_dataset_v2_vinculo_divergente_reprova(self):
        good = os.path.join(ROOT, "tests", "fixtures", "dataset-v2-good.json")
        other = os.path.join(ROOT, "tests", "fixtures", "manifest-good.json")
        ns = argparse.Namespace(manifest=good, data_root=None, max_bytes=10**12,
                                max_assets=1000, require_status=None,
                                schema_version="auto", source_manifest=other)
        errs = V.cmd_manifest(ns)
        self.assertTrue(any("não confere" in e for e in errs), msg=f"erros: {errs}")

    def test_execution_bom_e_ruim(self):
        fx = os.path.join(ROOT, "tests", "fixtures")
        ok = V.cmd_execution(argparse.Namespace(receipt=f"{fx}/execution-good.json"))
        self.assertEqual(ok, [])
        bad = V.cmd_execution(argparse.Namespace(receipt=f"{fx}/execution-bad.json"))
        self.assertTrue(bad, "recibo sem tool deveria reprovar")

    def test_sem_jsonschema_reprova_com_instrucao(self):
        prev = V.HAVE_JSONSCHEMA
        V.HAVE_JSONSCHEMA = False
        try:
            errors = []
            V.check_schema({"format_version": 1},
                           os.path.join(ROOT, "spec", "index.schema.json"),
                           errors, "index")
            self.assertTrue(errors, "sem jsonschema deveria reprovar")
            joined = " ".join(errors)
            self.assertIn("jsonschema", joined)
            self.assertIn("CI", joined)
        finally:
            V.HAVE_JSONSCHEMA = prev


if __name__ == "__main__":
    unittest.main()
