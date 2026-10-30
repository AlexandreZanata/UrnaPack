#!/usr/bin/env python3
"""Regressões da análise histórica MT (stdlib, sem Rust, dados sintéticos)."""
import csv
import io
import unittest
import zipfile

import analyze_mt_historico as hist


def make_zip(rows, header):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as zf:
        text = io.StringIO()
        writer = csv.writer(text, delimiter=";", quotechar='"', lineterminator="\r\n")
        writer.writerow(header)
        writer.writerows(rows)
        zf.writestr("sintetico.csv", text.getvalue().encode("latin-1"))
    buffer.seek(0)
    return zipfile.ZipFile(buffer)


VOT23 = ["DT_GERACAO", "HH_GERACAO", "ANO_ELEICAO", "CD_TIPO_ELEICAO", "NM_TIPO_ELEICAO",
         "NR_TURNO", "CD_ELEICAO", "DS_ELEICAO", "DT_ELEICAO", "TP_ABRANGENCIA", "SG_UF",
         "SG_UE", "NM_UE", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA", "NR_SECAO",
         "CD_CARGO", "DS_CARGO", "NR_VOTAVEL", "NM_VOTAVEL", "QT_VOTOS", "NR_LOCAL_VOTACAO"]


class TestHistorico(unittest.TestCase):
    def test_votacao_23_soma_sem_contexto(self):
        rows = [
            ["31/01/2022", "16:47:38", "2000", "2", "Eleição Ordinária", "1", "2000001",
             "Eleições Ordinárias - 2000", "01/10/2000", "M", "MT", "91910", "AGUA BOA",
             "91910", "AGUA BOA", "30", "1", "11", "Prefeito", "12", "A", "100", "-3"],
            ["31/01/2022", "16:47:38", "2000", "2", "Eleição Ordinária", "1", "2000001",
             "Eleições Ordinárias - 2000", "01/10/2000", "M", "MT", "91910", "AGUA BOA",
             "91910", "AGUA BOA", "30", "1", "11", "Prefeito", "45", "B", "50", "-3"],
        ]
        zf = make_zip(rows, VOT23)
        member = hist.analyze_member(zf, zf.infolist()[0], hist.load_limits())
        self.assertEqual(member["records"], 2)
        self.assertFalse(member["has_context"])
        self.assertEqual(
            member["votes_by_eleicao_turno_cargo"],
            [{"eleicao": "2000001", "turno": "1", "cargo": "11", "votos": 150}],
        )
        self.assertEqual(member["duplicates"], 0)

    def test_bweb_senador_2x_nao_e_erro(self):
        header = ["DT_GERACAO", "HH_GERACAO", "ANO_ELEICAO", "CD_PLEITO", "DT_PLEITO",
                  "NR_TURNO", "CD_ELEICAO", "DS_ELEICAO", "SG_UF", "CD_MUNICIPIO",
                  "NM_MUNICIPIO", "NR_ZONA", "NR_SECAO", "CD_CARGO_PERGUNTA",
                  "DS_CARGO_PERGUNTA", "NR_VOTAVEL", "NM_VOTAVEL", "QT_VOTOS",
                  "QT_APTOS", "QT_COMPARECIMENTO", "QT_ABSTENCOES"]
        base = ["05/10/2026", "14:03:43", "2026", "3220", "2026-10-04 00:00:00",
                "1", "6259", "Estaduais 2026", "MT", "0001", "MUN", "0001", "0001",
                "5", "Senador"]
        rows = [base + ["1", "A", "60", "100", "60", "40"],
                base + ["2", "B", "60", "100", "60", "40"]]
        zf = make_zip(rows, header)
        member = hist.analyze_member(zf, zf.infolist()[0], hist.load_limits())
        self.assertEqual(member["arithmetic_fail"], 0)
        self.assertEqual(member["grupos_votos_vs_comparecimento_divergentes"], 1)
        self.assertEqual(member["grupos_votos_igual_dobro_comparecimento"], 1)

    def test_aritmetica_e_duplicata_sao_flags(self):
        header = ["DT_GERACAO", "HH_GERACAO", "ANO_ELEICAO", "CD_PLEITO", "DT_PLEITO",
                  "NR_TURNO", "CD_ELEICAO", "DS_ELEICAO", "SG_UF", "CD_MUNICIPIO",
                  "NM_MUNICIPIO", "NR_ZONA", "NR_SECAO", "CD_CARGO_PERGUNTA",
                  "DS_CARGO_PERGUNTA", "NR_VOTAVEL", "NM_VOTAVEL", "QT_VOTOS",
                  "QT_APTOS", "QT_COMPARECIMENTO", "QT_ABSTENCOES"]
        base = ["05/10/2026", "14:03:43", "2026", "3220", "2026-10-04 00:00:00",
                "1", "6259", "Estaduais 2026", "MT", "0001", "MUN", "0001", "0001",
                "3", "Governador"]
        rows = [base + ["1", "A", "60", "100", "60", "40"],
                base + ["1", "A", "60", "100", "60", "40"]]
        zf = make_zip(rows, header)
        member = hist.analyze_member(zf, zf.infolist()[0], hist.load_limits())
        self.assertEqual(member["duplicates"], 1)
        self.assertEqual(member["repeated"], 1)


if __name__ == "__main__":
    unittest.main()
