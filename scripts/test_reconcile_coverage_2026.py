#!/usr/bin/env python3
"""Dados sintéticos de controle, sem representar seções do TSE."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
import csv
from reconcile_coverage_2026 import reconcile, reconcile_origins


class CoverageTests(unittest.TestCase):
    def setUp(self):
        fixture = json.loads((Path(__file__).resolve().parents[1] / "tests/fixtures/audit-2026/coverage-synthetic.json").read_text())
        self.rows, self.sentinels = fixture["rows"], fixture["sentinels"]
        self.report, self.official = fixture["report"], fixture["official"]

    def test_zero_turnout_section_counts_without_adding_votes(self):
        result = reconcile(self.rows, self.sentinels, self.report, self.official)
        self.assertEqual(result["union_geographic_sections"], 2)
        self.assertEqual(result["union_turnout"], 90)
        self.assertEqual(result["union_aptos"], 110)

    def test_numeric_identifier_collision_fails(self):
        duplicate = deepcopy(self.rows[0])
        duplicate["NR_SECAO"] = "0001"
        with self.assertRaisesRegex(ValueError, "repetida"):
            reconcile(self.rows + [duplicate], self.sentinels, self.report, self.official)

    def test_cannot_add_nonzero_votes_as_empty_sentinel(self):
        bad = deepcopy(self.sentinels)
        bad[0]["QT_VOTOS"] = "1"
        with self.assertRaisesRegex(ValueError, "fora da definição"):
            reconcile(self.rows, bad, self.report, self.official)

    def test_different_official_count_fails(self):
        bad = deepcopy(self.official)
        bad["s"]["si"] = "3"
        with self.assertRaisesRegex(ValueError, "não confere"):
            reconcile(self.rows, self.sentinels, self.report, bad)

    def test_origin_join_preserves_extra_fields_and_requires_exact_keys(self):
        path = Path(__file__).resolve().parents[1] / "tests/fixtures/audit-2026/correspondence-synthetic.csv"
        with path.open() as stream:
            ceft = list(csv.DictReader(stream, delimiter=";"))
        rows = [dict(row, SG_UF="ZZ", DT_ENCERRAMENTO="") for row in self.rows]
        result = reconcile_origins(ceft, rows, self.sentinels)
        self.assertEqual(result["nonzero_system_sections"], 1)
        self.assertEqual(result["by_origin"]["C"]["turnout"], 90)
        self.assertEqual(result["by_origin"]["C"]["sections"], 2)
        self.assertEqual(result["system_of_counting_rows"][0]["ceft_row_all_fields"]["EXTRA_FIXTURE_PRESERVADO"], "SINTÉTICO NÃO TSE")
        with self.assertRaisesRegex(ValueError, "duplicada"):
            reconcile_origins(ceft+ceft[:1], rows, self.sentinels)
        with self.assertRaisesRegex(ValueError, "incompleta"):
            reconcile_origins(ceft[:1], rows, self.sentinels)
        rows[0]["DT_ENCERRAMENTO"] = "2026-10-25 17:00:00"
        with self.assertRaisesRegex(ValueError, "difere das chaves"):
            reconcile_origins(ceft, rows, self.sentinels)


if __name__ == "__main__":
    unittest.main()
