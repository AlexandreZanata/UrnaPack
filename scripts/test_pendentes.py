#!/usr/bin/env python3
"""Regressões da inspeção 2020 e da reconciliação Senado 2018 (sintéticas)."""
import unittest
from pathlib import Path
import tempfile
import test_analyze_mt_historico as synthetic_hist
import io
import json
import zipfile
from unittest.mock import patch
from contextlib import redirect_stdout

import inspect_2020_bweb_quoting as inspect
import reconcile_senado_2018 as reconc


class TestPendentes(unittest.TestCase):
    def test_empty_reconciliation_is_not_success_and_existing_output_is_preserved(self):
        fields=["NR_TURNO","CD_CARGO","CD_CARGO_PERGUNTA","CD_ELEICAO","CD_MUNICIPIO","NR_ZONA","NR_SECAO","NR_VOTAVEL","QT_VOTOS"]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/"synthetic-not-TSE.zip";output=root/"result.json"
            with synthetic_hist.make_zip([],fields) as z:
                source.write_bytes(z.fp.getvalue())
            argv=["reconcile_senado_2018.py","--bu-zip",str(source),"--vot-zip",str(source),"--bu-member","sintetico.csv","--output",str(output)]
            with patch("sys.argv",argv),redirect_stdout(io.StringIO()):
                self.assertEqual(reconc.main(),1)
            self.assertFalse(json.loads(output.read_text())["success"])
            prior=output.read_bytes()
            with patch("sys.argv",argv),self.assertRaises(ValueError):
                reconc.main()
            self.assertEqual(output.read_bytes(),prior)

    def test_inspection_measures_csv_record_ordinal_independently_of_physical_lines(self):
        raw=b'a;b\n"hello\nworld";"ok"\n"1";"ELIEL ROCHA " O GORDINHO"";"2"\n'
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/"synthetic-not-TSE.zip";output=root/"inspection.json"
            with zipfile.ZipFile(source,"w") as z:
                z.writestr("synthetic.csv",raw)
            with patch("sys.argv",["inspect_2020_bweb_quoting.py","--zip",str(source),"--member","synthetic.csv","--output",str(output)]),redirect_stdout(io.StringIO()):
                self.assertEqual(inspect.main(),0)
            report=json.loads(output.read_text())
            self.assertEqual(report["strict_records_accepted"],1)
            self.assertEqual(report["strict_error_next_record_ordinal"],2)
            self.assertEqual(report["pattern_physical_line"],4)

    def test_aggregate_checks_occurrences_required_fields_and_nonnegative_votes(self):
        header=["NR_TURNO","CD_CARGO","CD_ELEICAO","CD_MUNICIPIO","NR_ZONA","NR_SECAO","NR_VOTAVEL","QT_VOTOS"]
        rows=[["1","5","297","0001","0001","0001","12","100"],
              ["1","5","297","0001","0001","0001","45","50"]]
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"synthetic-not-TSE.zip"
            def save(records,fields=header):
                with synthetic_hist.make_zip(records,fields) as z:
                    path.write_bytes(z.fp.getvalue())
            save(rows)
            self.assertEqual(reconc.aggregate(path,"sintetico.csv","CD_CARGO","297"),{("0001","0001","0001"):150})
            for records,fields in ((rows+[rows[0]],header),([rows[0][:-1]+["-1"]],header),([rows[0][:-1]],header[:-1])):
                save(records,fields)
                with self.assertRaises(ValueError):
                    reconc.aggregate(path,"sintetico.csv","CD_CARGO","297")

    def test_localiza_quoting(self):
        raw = b'a;"x"\n"1";"ELIEL ROCHA " O GORDINHO"";"2"\n'
        offset, ordinal = inspect.locate(raw)
        self.assertIsNotNone(offset)
        self.assertEqual(ordinal, 1)

    def test_localiza_ausente(self):
        offset, ordinal = inspect.locate(b'a;"ok"\n')
        self.assertIsNone(offset)
        self.assertIsNone(ordinal)

    def test_compare_igual_e_divergente(self):
        bu = {("a", "1", "1"): 100}
        vot = {("a", "1", "1"): 100}
        self.assertEqual(reconc.compare(bu, vot)["divergentes"], 0)
        vot2 = {("a", "1", "1"): 150}
        result = reconc.compare(bu, vot2)
        self.assertEqual(result["divergentes"], 1)
        self.assertEqual(result["comuns"], 1)


if __name__ == "__main__":
    unittest.main()
