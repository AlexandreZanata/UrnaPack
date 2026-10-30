#!/usr/bin/env python3
"""Testa o confronto com saídas REAIS versionadas; mutações são só testes."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from check_audit_2026 import check, percent

ROOT = Path(__file__).resolve().parents[1] / "auditoria/2026"


class ConfrontationTests(unittest.TestCase):
    def setUp(self):
        self.report = json.loads((ROOT / "resultados/presidente-2t.json").read_text())
        self.official = json.loads((ROOT / "evidencias/totalizacao-presidente-2t.json").read_text())

    def test_real_totals_and_documented_boundary_disagreement(self):
        result = check(self.report, self.official)
        self.assertEqual(result["bu_vs_totalization"], "matched_votes_and_turnout")
        boundary = next(i for i in result["numeric_assertions"] if i["id"] == "N12-13")
        self.assertEqual(boundary["observed"], self.report["extremes"]["above_90_13"])
        self.assertEqual(boundary["status"], "não reproduzido nesta definição")

    def test_vote_mutation_rejected(self):
        altered = deepcopy(self.report)
        altered["presidential"]["votes"]["13"] += 1
        with self.assertRaisesRegex(ValueError, "BU x totalização"):
            check(altered, self.official)

    def test_missing_uf_rejected(self):
        altered = deepcopy(self.report)
        del altered["by_uf"]["ZZ"]
        with self.assertRaisesRegex(ValueError, "cobertura"):
            check(altered, self.official)

    def test_zero_denominator_not_reported_as_zero_percent(self):
        self.assertIsNone(percent({}))


if __name__ == "__main__":
    unittest.main()
