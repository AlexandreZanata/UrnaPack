#!/usr/bin/env python3
"""Regressões da inspeção 2020 e da reconciliação Senado 2018 (sintéticas)."""
import unittest

import inspect_2020_bweb_quoting as inspect
import reconcile_senado_2018 as reconc


class TestPendentes(unittest.TestCase):
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
