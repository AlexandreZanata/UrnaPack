#!/usr/bin/env python3
"""Regressões do validador canônico da BU web (Etapa 2, sem dados reais).

CSV sintéticos montados no teste a partir do cabeçalho canônico único
(`map_raw_data.KNOWN_LAYOUTS`); nenhum registro real do TSE versionado.
"""

import csv
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "validate_bweb.py")

sys.path.insert(0, os.path.join(ROOT, "scripts"))
from map_raw_data import KNOWN_LAYOUTS  # noqa: E402

HEADER = KNOWN_LAYOUTS["bweb"]


def base_row(**over):
    row = {c: "X" for c in HEADER}
    row.update({
        "DT_GERACAO": "05/10/2026", "HH_GERACAO": "14:03:43",
        "ANO_ELEICAO": "2026", "CD_TIPO_ELEICAO": "0",
        "NM_TIPO_ELEICAO": "Eleição Ordinária", "CD_PLEITO": "3220",
        "DT_PLEITO": "2026-10-04 00:00:00", "NR_TURNO": "1",
        "CD_ELEICAO": "6259", "DS_ELEICAO": "Eleições Gerais Estaduais 2026",
        "SG_UF": "MT", "CD_MUNICIPIO": "90670", "NM_MUNICIPIO": "CUIABÁ",
        "NR_ZONA": "51", "NR_SECAO": "355", "NR_LOCAL_VOTACAO": "1104",
        "CD_CARGO_PERGUNTA": "7", "DS_CARGO_PERGUNTA": "Deputado Estadual",
        "NR_PARTIDO": "44", "SG_PARTIDO": "UNIÃO", "NM_PARTIDO": "UNIÃO BRASIL",
        "DT_BU_RECEBIDO": "2026-10-04 17:34:33",
        "QT_APTOS": "300", "QT_COMPARECIMENTO": "200", "QT_ABSTENCOES": "100",
        "CD_TIPO_URNA": "1", "DS_TIPO_URNA": "Apurada",
        "CD_TIPO_VOTAVEL": "1", "DS_TIPO_VOTAVEL": "Nominal",
        "NR_VOTAVEL": "44444", "NM_VOTAVEL": "CANDIDATA SINTÉTICA",
        "QT_VOTOS": "10", "NR_URNA_EFETIVADA": "1763024",
        "CD_CARGA_1_URNA_EFETIVADA": "769.496.008.595.567.719.",
        "CD_CARGA_2_URNA_EFETIVADA": "184.873",
        "CD_FLASHCARD_URNA_EFETIVADA": "06840A72",
        "DT_CARGA_URNA_EFETIVADA": "2026-09-23 09:23:00",
        "DS_CARGO_PERGUNTA_SECAO": "Deputado Estadual",
        "DS_SECOES_AGREGADAS": "#NULO#", "DT_ABERTURA": "2026-10-04 07:00:01",
        "DT_ENCERRAMENTO": "2026-10-04 16:03:19",
        "QT_ELEI_BIOM_SEM_HABILITACAO": "0",
        "DT_EMISSAO_BU": "2026-10-04 16:09:50",
        "NR_JUNTA_APURADORA": "-1", "NR_TURMA_APURADORA": "-1",
    })
    row.update(over)
    return [row[c] for c in HEADER]


def write_csv(path, rows):
    buf = io.StringIO(newline="")
    w = csv.writer(buf, delimiter=";", quotechar='"', doublequote=True, lineterminator="\r\n")
    w.writerow(HEADER)
    w.writerows(rows)
    with open(path, "wb") as f:
        f.write(buf.getvalue().encode("latin-1"))


def run_bweb(*args):
    return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True)


class TestValidateBweb(unittest.TestCase):
    def test_valido_aprova(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = os.path.join(tmp, "b.csv")
            write_csv(csv_path, [base_row(), base_row(NR_SECAO="356", NR_VOTAVEL="55555")])
            out = os.path.join(tmp, "r.json")
            r = run_bweb("--csv", csv_path, "--output", out)
            self.assertEqual(r.returncode, 0, msg=r.stderr)
            rep = json.load(open(out, encoding="utf-8"))
            self.assertTrue(rep["success"])
            self.assertEqual(rep["records"], 2)
            self.assertEqual(rep["distinct_keys"], 2)
            self.assertEqual(rep["duplicate_keys"], 0)

    def test_cabecalho_divergente_reprova(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = os.path.join(tmp, "b.csv")
            buf = io.StringIO(newline="")
            w = csv.writer(buf, delimiter=";", quotechar='"', doublequote=True, lineterminator="\r\n")
            bad = HEADER.copy()
            bad[0] = "DT_X"
            w.writerow(bad)
            w.writerow(["x"] * len(bad))
            with open(csv_path, "wb") as f:
                f.write(buf.getvalue().encode("latin-1"))
            r = run_bweb("--csv", csv_path)
            self.assertNotEqual(r.returncode, 0)

    def test_dominio_divergente_reprova(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = os.path.join(tmp, "b.csv")
            write_csv(csv_path, [base_row(NR_TURNO="9")])
            out = os.path.join(tmp, "r.json")
            r = run_bweb("--csv", csv_path, "--output", out)
            self.assertNotEqual(r.returncode, 0)
            rep = json.load(open(out, encoding="utf-8"))
            self.assertTrue(any("domínio" in e for e in rep["errors"]))

    def test_inconsistencia_cruzada_reprova(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = os.path.join(tmp, "b.csv")
            write_csv(csv_path, [base_row(CD_TIPO_VOTAVEL="1", DS_TIPO_VOTAVEL="Branco")])
            out = os.path.join(tmp, "r.json")
            r = run_bweb("--csv", csv_path, "--output", out)
            self.assertNotEqual(r.returncode, 0)
            rep = json.load(open(out, encoding="utf-8"))
            self.assertTrue(any("inconsistência" in e for e in rep["errors"]))

    def test_aritmetica_divergente_reprova(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = os.path.join(tmp, "b.csv")
            write_csv(csv_path, [base_row(QT_APTOS="300", QT_COMPARECIMENTO="200", QT_ABSTENCOES="50")])
            out = os.path.join(tmp, "r.json")
            r = run_bweb("--csv", csv_path, "--output", out)
            self.assertNotEqual(r.returncode, 0)
            rep = json.load(open(out, encoding="utf-8"))
            self.assertTrue(any("aritmética" in e for e in rep["errors"]))

    def test_chave_duplicada_reprova_com_ordinal_sem_remover(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = os.path.join(tmp, "b.csv")
            write_csv(csv_path, [base_row(), base_row()])
            out = os.path.join(tmp, "r.json")
            r = run_bweb("--csv", csv_path, "--output", out)
            self.assertNotEqual(r.returncode, 0)
            rep = json.load(open(out, encoding="utf-8"))
            self.assertEqual(rep["duplicate_keys"], 1)
            self.assertEqual(rep["duplicate_evidence"][0]["record"], 2)

    def test_linha_divergente_reprova(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = os.path.join(tmp, "b.csv")
            buf = io.StringIO(newline="")
            w = csv.writer(buf, delimiter=";", quotechar='"', doublequote=True, lineterminator="\r\n")
            w.writerow(HEADER)
            w.writerow(["x"] * (len(HEADER) - 1))
            with open(csv_path, "wb") as f:
                f.write(buf.getvalue().encode("latin-1"))
            r = run_bweb("--csv", csv_path)
            self.assertNotEqual(r.returncode, 0)

    def test_via_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = os.path.join(tmp, "b.csv")
            write_csv(csv_path, [base_row()])
            zpath = os.path.join(tmp, "a.zip")
            with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr("bweb.csv", open(csv_path, "rb").read())
            r = run_bweb("--zip", zpath, "--member", "bweb.csv")
            self.assertEqual(r.returncode, 0, msg=r.stderr)


if __name__ == "__main__":
    unittest.main()
