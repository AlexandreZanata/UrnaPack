"""Testes reais do conferidor independente com fixture identificada como sintética."""
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import check_statistical_suite_2026 as checker
import render_statistical_suite_2026 as renderer

ROOT = Path(__file__).resolve().parents[1]


class StatisticalCheckerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='urnapack-synthetic-stats-')
        cls.base = Path(cls.temp.name)
        fixture = ROOT/'tests/fixtures/statistical-suite/synthetic.csv'
        p = json.loads((ROOT/'auditoria/2026/suite/protocolo.json').read_bytes())
        p.update(source_kind='synthetic_fixture', scope='Fixture artificial, não é observação eleitoral', permutations=39, predictive_replicates=19, minimum_training_sections=8)
        raw = fixture.read_bytes()
        p['sections'] = {'path': str(fixture), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        p['time_policy']['path'] = str(ROOT/p['time_policy']['path'])
        p['log_report'] = None
        cls.protocol = cls.base/'protocol.json'
        cls.protocol.write_text(json.dumps(p))
        cls.sections = fixture
        cls.result = cls.base/'result'
        target = Path(os.environ.get('CARGO_TARGET_DIR', str(ROOT/'target')))
        binary = target/'debug/statistical_suite_2026'
        if not binary.exists():
            raise RuntimeError('Execute cargo test antes dos testes Python: binário estatístico ausente')
        subprocess.run([str(binary), '--protocol', str(cls.protocol), '--output', str(cls.result)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def changed(self, filename, transform):
        destination = self.base/self._testMethodName
        shutil.copytree(self.result, destination)
        path = destination/filename
        transform(path)
        report = json.loads((destination/'report.json').read_bytes())
        raw = path.read_bytes()
        report['artifacts'][filename] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        (destination/'report.json').write_text(json.dumps(report))
        return destination

    def test_independent_check_executes_every_family(self):
        r = checker.check(self.protocol, self.sections, self.result)
        self.assertTrue(r['success'])
        self.assertEqual(r['sections_compared_all_fields'], 64)
        self.assertEqual(r['sampled_sections_math_lgamma'], 63)
        self.assertIn('Holm de todos os scores recalculado', r['checks'])

    def test_altered_field_fails_even_after_rehashing_artifact(self):
        def mutate(path):
            with path.open(newline='') as f:
                rows = list(csv.reader(f))
            rows[1][14] = str(int(rows[1][14])+1)
            with path.open('w', newline='') as f:
                csv.writer(f).writerows(rows)
        result = self.changed('section_scores.csv', mutate)
        with self.assertRaisesRegex(ValueError, 'campos da seção'):
            checker.check(self.protocol, self.sections, result)

    def test_wrong_training_parameter_fails_after_rehashing(self):
        def mutate(path):
            with path.open(newline='') as f:
                rows = list(csv.reader(f))
            index = rows[0].index('crossfit_mean_13')
            rows[1][index] = str(float(rows[1][index])+0.001)
            with path.open('w', newline='') as f:
                csv.writer(f).writerows(rows)
        result = self.changed('section_scores.csv', mutate)
        with self.assertRaisesRegex(ValueError, 'ajuste fora do fold'):
            checker.check(self.protocol, self.sections, result)

    def test_wrong_residual_correlation_fails_after_rehashing(self):
        def mutate(path):
            data = json.loads(path.read_bytes())
            target = next(r for r in data if r['scope'] == 'BR' and r['partial_pearson_13'] is not None)
            target['partial_pearson_13'] += 0.01
            target['partial_pearson_22'] = -target['partial_pearson_13']
            path.write_text(json.dumps(data))
        result = self.changed('associations.json', mutate)
        with self.assertRaisesRegex(ValueError, 'correlação residual'):
            checker.check(self.protocol, self.sections, result)

    def test_existing_receipt_is_preserved(self):
        receipt = self.base/'existing-receipt'
        receipt.write_bytes(b'synthetic existing bytes')
        r = subprocess.run(['python3', str(ROOT/'scripts/check_statistical_suite_2026.py'), '--protocol', str(self.protocol), '--result', str(self.result), '--output', str(receipt)], capture_output=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(receipt.read_bytes(), b'synthetic existing bytes')

    def test_reference_math_matches_small_enumeration(self):
        self.assertAlmostEqual(math_exp(checker.nominal_log_p(4, 0, 0.5, 0)), 0.125)
        self.assertAlmostEqual(math_exp(checker.nominal_log_p(10, 0, 0.5, 1/3)), 2/11)

    def test_report_exposes_synthetic_origin_and_all_test_families(self):
        report = json.loads((self.result/'report.json').read_bytes())
        tests = json.loads((self.result/'associations.json').read_bytes())
        text = renderer.render(report, tests)
        for term in ['synthetic_fixture', 'fora do fold', 'Holm global', 'Dígitos', 'Controles de repetição']:
            self.assertIn(term, text)

    def test_report_refuses_incomplete_execution(self):
        with self.assertRaisesRegex(ValueError, 'incompleta'):
            renderer.render({'execution_success': False}, [])

    def test_reproduction_usage_and_existing_output_are_non_destructive(self):
        script = ROOT/'scripts/reproduce_statistical_suite_2026.sh'
        self.assertNotEqual(subprocess.run(['bash', str(script)], capture_output=True).returncode, 0)
        output = self.base/'existing-reproduction'
        output.mkdir()
        (output/'preserve').write_bytes(b'synthetic preserved bytes')
        result = subprocess.run(['bash', str(script), str(self.sections.parent), str(output)], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((output/'preserve').read_bytes(), b'synthetic preserved bytes')


def math_exp(value):
    import math
    return math.exp(value)


if __name__ == '__main__':
    unittest.main()
