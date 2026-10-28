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
