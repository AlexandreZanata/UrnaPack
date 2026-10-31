#!/usr/bin/env python3
"""Regressões do verificador independente da Etapa 5A (stdlib, sem Rust)."""

import unittest
import tempfile
from pathlib import Path

import analyze_check

FIXTURES = Path(__file__).resolve().parent.parent / "tests/fixtures/analyze"


class TestAnalyzeCheck(unittest.TestCase):
    def test_existing_receipt_is_preserved_before_any_recalculation(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/"existing.json";before=b"synthetic-existing-receipt-not-TSE"
            output.write_bytes(before)
            with self.assertRaisesRegex(ValueError,"saída existente"):
                analyze_check.main(["--csv","absent.csv","--results","absent-results.json","--quality","absent-quality.json","--output",str(output)])
            self.assertEqual(output.read_bytes(),before)

    def check(self, name):
        _, _, checker = analyze_check.parse_csv(
            FIXTURES / name, analyze_check.load_limits()
        )
        return checker

    def test_taxa_com_denominador_zero_nao_e_artificial(self):
        self.assertEqual(analyze_check.ratio(7, 10), ("0.700000", None))
        self.assertEqual(analyze_check.ratio(0, 0), (None, "denominator_zero"))

    def test_fixture_valida_conta_contexto_uma_vez(self):
        checker = self.check("mt-valid.csv")
        self.assertEqual(checker.records, 8)
        self.assertEqual(len(checker.occurrences), 8)
        self.assertEqual(checker.duplicates, 0)
        self.assertEqual(len(checker.contexts), 4)
        self.assertEqual(checker.zero_denominator_groups, 2)
        self.assertEqual(sum(checker.votes_office.values()), 19)
        self.assertEqual(checker.sentinels["NR_JUNTA_APURADORA"]["-1"], 8)
        rows = analyze_check.context_aggregate(checker)
        cargo7 = [
            row
            for row in rows
            if row["cargo"] == "7" and row["municipio"] is None
        ][0]
        self.assertEqual(cargo7["grupos_contexto"], 3)
        self.assertEqual(cargo7["aptos"], "10")
        self.assertEqual(cargo7["comparecimento"], "7")

    def test_contexto_divergente_e_duplicatas_sao_classificados(self):
        self.assertEqual(
            self.check("mt-context-divergent.csv").context_divergences, 1
        )
        duplicate = self.check("mt-duplicate-exact.csv")
        self.assertEqual((duplicate.duplicates, duplicate.repeated, duplicate.conflicts), (1, 1, 0))
        conflict = self.check("mt-duplicate-conflict.csv")
        self.assertEqual((conflict.duplicates, conflict.repeated, conflict.conflicts), (1, 0, 1))

    def test_conflito_de_nome_municipal_e_contado(self):
        checker = self.check("mt-valid.csv")
        self.assertEqual(checker.municipality_name_conflicts, 0)

    def test_limites_centrais_sao_respeitados(self):
        limits = analyze_check.load_limits()
        for key in (
            "MAX_CSV_RECORDS",
            "MAX_FIELD_BYTES",
            "MAX_BWEB_OCCURRENCE_KEYS",
            "MAX_ANALYZE_DISTINCT_VALUES",
        ):
            self.assertIn(key, limits)
            self.assertGreater(int(limits[key]), 0)


if __name__ == "__main__":
    unittest.main()
