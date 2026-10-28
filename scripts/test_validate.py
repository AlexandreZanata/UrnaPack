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



class TestVinculosRevisados(unittest.TestCase):
    def test_duplicatas_nao_sao_ocultadas_por_comparacao_de_conjuntos(self):
        import copy
        import pathlib
        doc=json.loads((pathlib.Path(ROOT)/"tests/fixtures/dataset-v2-good.json").read_text())
        doc["source_files"].append(copy.deepcopy(doc["source_files"][0]))
        doc["packages"].append(copy.deepcopy(doc["packages"][0]))
        errors=[]
        V.validate_manifest_doc(doc,errors,schema_version=2)
        self.assertTrue(any("origem duplicados" in error for error in errors))
        self.assertTrue(any("pacote duplicados" in error for error in errors))

    def test_hash_do_documento_nao_basta_se_source_files_divergem(self):
        import pathlib
        root=pathlib.Path(ROOT)/"tests/fixtures"
        doc=json.loads((root/"dataset-v2-good.json").read_text())
        doc["source_files"][0]["path"]="outro-arquivo.bin"
        with tempfile.TemporaryDirectory() as tmp:
            path=pathlib.Path(tmp)/"manifest.json";path.write_text(json.dumps(doc))
            args=argparse.Namespace(manifest=str(path),schema_version="auto",source_manifest=str(root/"origin-v2-good.json"),require_status=None,data_root=None)
            errors=V.cmd_manifest(args)
            self.assertTrue(any("source_files divergem" in error for error in errors))

    def test_stub_de_execution_nao_libera_publicacao(self):
        import pathlib
        root=pathlib.Path(ROOT)/"tests/fixtures"
        args=argparse.Namespace(manifest=str(root/"dataset-v2-good.json"),schema_version="auto",source_manifest=str(root/"origin-v2-good.json"),require_status="validated",data_root=None)
        self.assertTrue(any("recibo" in error for error in V.cmd_manifest(args)))

    def test_sucesso_com_erros_nao_e_recibo_aprovado(self):
        import pathlib
        doc=json.loads((pathlib.Path(ROOT)/"tests/fixtures/execution-good.json").read_text())
        doc["errors"]=["falha sintética"]
        with tempfile.TemporaryDirectory() as tmp:
            path=pathlib.Path(tmp)/"run.json";path.write_text(json.dumps(doc))
            self.assertTrue(any("contradiz" in error for error in V.cmd_execution(argparse.Namespace(receipt=str(path)))))

if __name__ == "__main__":
    unittest.main()
