"""Testes reais do conferidor independente com fixture identificada como sintética."""
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from types import SimpleNamespace

import check_statistical_suite_2026 as checker
import render_statistical_suite_2026 as renderer
import contextualize_statistical_alerts_2026 as contextualizer
import compare_mt_presidential_profiles_2026 as temporal

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

    def test_zero_expected_digit_with_positive_observed_mass_fails(self):
        destination = self.base/self._testMethodName
        shutil.copytree(self.result, destination)
        p = destination/'report.json'
        report = json.loads(p.read_bytes())
        counts = report['predictive_reference']['observed_counts']
        index = next(i for i in range(6, 26) if counts[i] > 0)
        report['predictive_reference']['expected_counts'][index] = 0
        p.write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError, 'expectativa numérica zero'):
            checker.check(self.protocol, self.sections, destination)

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

    def test_context_followup_preserves_unknown_fields_duplicates_and_absences(self):
        path = ROOT/'tests/fixtures/statistical-suite/context-synthetic.json'
        data = json.loads(path.read_bytes())
        result = contextualizer.attach_metadata(data['alerts'], data['local_rows'], data['correspondence'])
        self.assertEqual(len(result), 2)
        first = result['MT/10000/0001/0001']
        self.assertEqual(len(first['official_local_rows_all_fields']), 2)
        self.assertEqual(first['official_local_rows_all_fields'][0]['UNKNOWN_FIELD'], 'preservar')
        self.assertTrue(first['local_number_matches'])
        second = result['MT/10000/0001/0002']
        self.assertEqual(second['official_local_rows_all_fields'], [])
        self.assertFalse(second['local_number_matches'])

    def test_all_context_fixture_hashes_are_real(self):
        base = ROOT/'tests/fixtures/statistical-suite'
        manifest = json.loads((base/'manifest.json').read_bytes())
        for name, expected in manifest['files'].items():
            raw = (base/name).read_bytes()
            self.assertEqual(len(raw), expected['bytes'])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), expected['sha256'])

    def test_context_csv_rejects_wrong_width_and_zip_crc(self):
        data = json.loads((ROOT/'tests/fixtures/statistical-suite/context-synthetic.json').read_bytes())
        rows = data['local_rows']['MT/10000/0001/0001']
        text = io.StringIO(newline='')
        writer = csv.DictWriter(text, list(rows[0]), delimiter=';')
        writer.writeheader()
        writer.writerows(rows)
        raw = text.getvalue().encode('latin-1')
        limits = {'MAX_ZIP_MEMBER_BYTES': len(raw)*2, 'MAX_CSV_RECORDS': 10}
        def archive_bytes(body):
            output = io.BytesIO()
            with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED) as archive:
                archive.writestr('synthetic.csv', body)
            return output.getvalue()
        zipped = archive_bytes(raw)
        with zipfile.ZipFile(io.BytesIO(zipped)) as archive:
            evidence = []
            parsed = list(contextualizer.csv_rows(archive, archive.infolist()[0], {'NR_LOCAL_VOTACAO'}, limits, evidence))
            self.assertEqual([row for _, row in parsed], rows)
            self.assertEqual(evidence[0]['sha256'], hashlib.sha256(raw).hexdigest())
        with zipfile.ZipFile(io.BytesIO(archive_bytes(raw+b'extra;wrong;width;field\n'))) as archive:
            with self.assertRaisesRegex(ValueError, 'largura'):
                list(contextualizer.csv_rows(archive, archive.infolist()[0], {'NR_LOCAL_VOTACAO'}, limits, []))
        changed = bytearray(zipped)
        changed[changed.index(raw)+3] ^= 1
        with zipfile.ZipFile(io.BytesIO(changed)) as archive:
            with self.assertRaises(zipfile.BadZipFile):
                list(contextualizer.csv_rows(archive, archive.infolist()[0], {'NR_LOCAL_VOTACAO'}, limits, []))

    def test_context_bu_zip_checks_whole_zip_and_member_bytes(self):
        raw = self.sections.read_bytes()
        directory = self.base/'synthetic-bu-zip'
        directory.mkdir()
        path = directory/'synthetic.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('synthetic.csv', raw)
        zipped = path.read_bytes()
        actual = hashlib.sha256(zipped).hexdigest()
        item = {'zip_url': 'synthetic:not-TSE', 'zip_sha256': actual, 'member': 'synthetic.csv', 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        catalog = {'items': [{'url': item['zip_url'], 'path': path.name, 'expected_bytes': len(zipped), 'expected_sha256': actual}]}
        limits = {'IO_BUFFER_BYTES': 1024, 'MAX_ZIP_MEMBERS': 10, 'MAX_ZIP_MEMBER_BYTES': len(raw)*2}
        stream, measured = contextualizer.bu_text(item, SimpleNamespace(bu_zip_root=directory), catalog, limits)
        with stream:
            self.assertEqual(stream.read(), raw.decode('latin-1'))
        self.assertEqual(measured['sha256'], item['sha256'])
        wrong = dict(item, sha256=hashlib.sha256((ROOT/'tests/fixtures/statistical-suite/context-synthetic.json').read_bytes()).hexdigest())
        with self.assertRaisesRegex(ValueError, 'membro BU bytes/SHA-256'):
            contextualizer.bu_text(wrong, SimpleNamespace(bu_zip_root=directory), catalog, limits)

    def test_temporal_control_preserves_equal_different_and_unmatched_profiles(self):
        with self.sections.open(newline='') as stream:
            rows = list(csv.DictReader(stream))
        def profile(row):
            return {'votes': [int(row[n]) for n in ('VOTOS_13', 'VOTOS_22', 'VOTOS_BRANCOS', 'VOTOS_NULOS')], 'turnout': int(row['QT_COMPARECIMENTO']), 'registered': int(row['QT_APTOS'])}
        before = {str(i): profile(row) for i, row in enumerate(rows[:3])}
        after = {str(i): profile(row) for i, row in enumerate(rows[:2])}
        after['1']['votes'][0] += 1
        after['1']['votes'][1] -= 1
        after['extra'] = profile(rows[4])
        result = temporal.compare_profiles(before, after)
        self.assertEqual(result['shared_numeric_keys'], 2)
        self.assertEqual(result['identical_four_vote_counts'], 1)
        self.assertEqual(result['only_before'], ['2'])
        self.assertEqual(result['only_after'], ['extra'])


def math_exp(value):
    import math
    return math.exp(value)


if __name__ == '__main__':
    unittest.main()
