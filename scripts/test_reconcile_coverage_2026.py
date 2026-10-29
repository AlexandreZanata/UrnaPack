#!/usr/bin/env python3
"""Dados sintéticos de controle, sem representar seções do TSE."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from reconcile_coverage_2026 import reconcile


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


if __name__ == "__main__":
    unittest.main()
