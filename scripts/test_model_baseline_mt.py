#!/usr/bin/env python3
"""Regressões do baseline binomial (sintético, sem dados reais)."""
import unittest

import model_baseline_mt as model


class TestBaseline(unittest.TestCase):
    def test_p_valor_extremo_e_nulo(self):
        # n=100, p=0.5: k=50 deve ter p alto; k=100 deve ter p ~0
        self.assertGreater(model.two_sided_p(50, 100, 0.5), 0.5)
        self.assertLess(model.two_sided_p(100, 100, 0.5), 1e-6)
        self.assertEqual(model.two_sided_p(0, 0, 0.5), 1.0)

    def test_bh_controla_fdr(self):
        # 100 p-valores nulos uniformes simulados: BH raramente flagra;
        # com 1 sinal forte, deve flagrar o sinal.
        pvalues = [0.9] * 99 + [1e-9]
        flagged = model.bh_flags(pvalues, q=0.05)
        self.assertTrue(flagged[-1])
        self.assertLessEqual(sum(flagged), 5)

    def test_calibracao_e_falsificacao_sinteticas(self):
        import random
        rng = random.Random(42)
        n = [200] * 50
        p = 0.7
        null = [sum(1 for _ in range(ni) if rng.random() < p) for ni in n]
        p_null = [model.two_sided_p(k, ni, p) for k, ni in zip(null, n)]
        # sob H0 global, BH deve flagrar 0 na maioria das sementes; aceita <=2
        self.assertLessEqual(sum(model.bh_flags(p_null)), 2)


if __name__ == "__main__":
    unittest.main()
