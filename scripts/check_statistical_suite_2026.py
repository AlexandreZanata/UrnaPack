#!/usr/bin/env python3
"""Conferência independente, em stdlib, da bateria Rust e de seus artefatos."""
import argparse
import collections
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

from acquire_2026 import hashes
from validate import load_limits


def key(row):
    return f"{row['SG_UF']}/{int(row['CD_MUNICIPIO']):05}/{int(row['NR_ZONA']):04}/{int(row['NR_SECAO']):04}"


def holm(pairs, total=None):
    total = len(pairs) if total is None else total
    order = sorted(range(len(pairs)), key=lambda j: (pairs[j], j))
    result = [0.0]*len(pairs)
    running = -math.inf
    for rank, index in enumerate(order):
        running = max(running, pairs[index]+math.log(total-rank))
        result[index] = min(0.0, running)
    return result


def nominal_log_p(n, k, mean, rho):
    """Fórmula independente com math.lgamma, sem statrs ou aproximação normal."""
    if rho:
        concentration = 1/rho-1
        a, b = mean*concentration, (1-mean)*concentration
        beta = math.lgamma(a)+math.lgamma(b)-math.lgamma(a+b)
        lp = [math.lgamma(n+1)-math.lgamma(j+1)-math.lgamma(n-j+1)
              + math.lgamma(j+a)+math.lgamma(n-j+b)-math.lgamma(n+a+b)-beta
              for j in range(n+1)]
    else:
        lp = [math.lgamma(n+1)-math.lgamma(j+1)-math.lgamma(n-j+1)
              + j*math.log(mean)+(n-j)*math.log1p(-mean) for j in range(n+1)]

    def logsum(values):
        largest = max(values)
        return largest+math.log(math.fsum(math.exp(v-largest) for v in values))

    norm = logsum(lp)
    return min(0.0, math.log(2)+min(logsum(lp[:k+1]), logsum(lp[k:]))-norm)


def fingerprint(values):
    return hashlib.sha256(json.dumps(values, ensure_ascii=True, separators=(",", ":")).encode()).digest()


def observed_associations(sections, level, width, policy):
    """Resíduos por Welford online, independente da centralização em lote Rust."""
    groups = {}
    with sections.open(newline='') as stream:
        for r in csv.DictReader(stream):
            n = int(r['VOTOS_13'])+int(r['VOTOS_22'])
            if not n:
                continue
            uf = r['SG_UF']
            municipality = f"{uf}/{int(r['CD_MUNICIPIO']):05}"
            zone = f"{municipality}/{int(r['NR_ZONA']):04}"
            local = f"{zone}/{int(r['NR_LOCAL_VOTACAO']):04}"
            registered, turnout = int(r['QT_APTOS']), int(r['QT_COMPARECIMENTO'])
            shift = policy['municipality_overrides'].get(municipality, policy['brt_shift_seconds_by_uf'][uf])
            t = r['DT_ENCERRAMENTO']
            closing = int(t[11:13])*3600+int(t[14:16])*60+int(t[17:19])+shift if t and shift is not None else None
            x = [turnout/registered if registered else None, int(r['QT_ELEI_BIOM_SEM_HABILITACAO'])/turnout if turnout else None,
                 (int(r['VOTOS_BRANCOS'])+int(r['VOTOS_NULOS']))/turnout if turnout else None, closing]
            mask = sum((value is not None) << j for j, value in enumerate(x))
            group = (uf, {'municipality_size': municipality, 'municipality_zone_size': zone, 'voting_place_size': local}[level], n//width, mask)
            moments = groups.setdefault(group, [[0.0]*6 for _ in range(4)])
            y = int(r['VOTOS_13'])/n
            for j, value in enumerate(x):
                if value is None:
                    continue
                m = moments[j]
                count = m[0]+1
                dx, dy = value-m[1], y-m[2]
                m[1] += dx/count
                m[2] += dy/count
                m[3] += dx*(value-m[1])
                m[4] += dy*(y-m[2])
                m[5] += dx*(y-m[2])
                m[0] = count
    sums = collections.defaultdict(lambda: [[0.0]*5 for _ in range(4)])
    for group, moments in groups.items():
        for j, m in enumerate(moments):
            for scope in (group[0], 'BR'):
                s = sums[scope][j]
                s[0] += m[0]
                s[1] += m[0] if m[0] > 1 else 0
                for k in range(2, 5):
                    s[k] += m[k+1]
    result = {}
    for scope, moments in sums.items():
        for j, m in enumerate(moments):
            denominator = math.sqrt(max(0, m[2])*max(0, m[3]))
            result[(scope, ['turnout_rate', 'biometric_rate', 'invalid_rate', 'closing_brt_seconds'][j])] = (int(m[0]), int(m[1]), m[4]/denominator if denominator else None)
    return result


def check(protocol, sections, directory):
    limits = load_limits(Path(__file__).resolve().parents[1])
    buffer = limits['IO_BUFFER_BYTES']
    meta = json.loads(protocol.read_bytes())
    report = json.loads((directory/'report.json').read_bytes())
    checks = []

    def require(condition, name):
        if not condition:
            raise ValueError(name)
        checks.append(name)

    actual = hashes(sections, buffer)
    require(all(actual[k] == meta['sections'][k] for k in ('bytes', 'sha256')), 'entrada bytes/SHA-256')
    require(report['protocol_sha256'] == hashlib.sha256(protocol.read_bytes()).hexdigest(), 'protocolo SHA-256')
    require(report['execution_success'] is True, 'execução concluída declarada')
    require(report['source_kind'] == meta['source_kind'], 'origem observada/sintética explícita')
    for name, expected in report['artifacts'].items():
        path = directory/name
        require(path.resolve().is_relative_to(directory.resolve()), 'caminho seguro: '+name)
        actual = hashes(path, buffer)
        require(all(actual[k] == expected[k] for k in ('bytes', 'sha256')), 'artefato bytes/SHA-256: '+name)

    totals = collections.Counter()
    identities = {}
    pools = collections.defaultdict(lambda: [0, 0])
    moments = collections.defaultdict(lambda: [0.0]*6)
    folds = collections.defaultdict(lambda: [0.0]*6)
    observed = [0]*26
    expected_fields = None
    with sections.open(newline='') as stream:
        reader = csv.DictReader(stream)
        expected_fields = reader.fieldnames
        for row in reader:
            identity = key(row)
            if identity in identities:
                raise ValueError('duplicata na entrada')
            identities[identity] = fingerprint([row[name] for name in expected_fields])
            k, other, blank, null, turnout, aptos, absence, bio = [int(row[c]) for c in
                ['VOTOS_13', 'VOTOS_22', 'VOTOS_BRANCOS', 'VOTOS_NULOS', 'QT_COMPARECIMENTO', 'QT_APTOS', 'QT_ABSTENCOES', 'QT_ELEI_BIOM_SEM_HABILITACAO']]
            if min(k, other, blank, null, turnout, aptos, absence, bio) < 0 or turnout != k+other+blank+null or aptos != turnout+absence or bio > turnout:
                raise ValueError('aritmética de entrada inválida')
            totals.update({'registered': aptos, 'turnout': turnout, 'biometric': bio, 'votes_13': k, 'votes_22': other, 'invalid': blank+null})
            n = k+other
            if n:
                municipal = f"{row['SG_UF']}/{int(row['CD_MUNICIPIO']):05}"
                for group in ('BR', row['SG_UF'], municipal):
                    pools[group][0] += k
                    pools[group][1] += n
                fold = int.from_bytes(hashlib.sha256(identity.encode()).digest()[:8], 'little') % meta['folds']
                values = [1, k, n, k/n, (k/n)**2, 1/n]
                for group in (row['SG_UF'], municipal):
                    for j, value in enumerate(values):
                        moments[group][j] += value
                        folds[(group, fold)][j] += value
                for index, value in enumerate([k == n, k == 0, 10*k > 9*n, 10*other > 9*n, 20*k % n == 0, 20*other % n == 0]):
                    observed[index] += value
                observed[6+k % 10] += 1
                observed[16+other % 10] += 1
    require(dict(totals) == report['totals'], 'todos os totais independentes')
    require(observed == report['predictive_reference']['observed_counts'], 'extremos/grade/dígitos independentes')
    require(len(identities) == report['descriptive']['sections'], 'número independente de seções')

    # Confronta os 21 campos em todas as linhas; não compara somente os totais.
    raw_p, actual_adjusted = [], []
    score_sample = 0
    zero = 0
    with (directory/'section_scores.csv').open(newline='') as stream:
        reader = csv.DictReader(stream)
        fields = [f'ln_p_{name}' for name in report['models']['model_order']]
        adjusted_fields = [f'ln_holm_{name}' for name in report['models']['model_order']]
        for row in reader:
            identity = row['section_key']
            if identities.pop(identity, None) != fingerprint([row[name] for name in expected_fields]):
                raise ValueError('campos da seção ausentes, repetidos ou alterados: '+identity)
            digest = hashlib.sha256(identity.encode()).digest()
            expected_fold = int.from_bytes(digest[:8], 'little') % meta['folds']
            if int(row['fold']) != expected_fold:
                raise ValueError('fold divergente')
            n, k = int(row['VOTOS_13'])+int(row['VOTOS_22']), int(row['VOTOS_13'])
            if not n:
                zero += 1
                if row['score_status'] != 'not_tested_zero_valid_votes' or any(row[x] for x in fields+adjusted_fields):
                    raise ValueError('denominador zero não declarado')
                continue
            values, adjusted = [float(row[x]) for x in fields], [float(row[x]) for x in adjusted_fields]
            if not all(math.isfinite(p) and p <= 0 for p in values+adjusted):
                raise ValueError('log-probabilidade inválida')
            raw_p.extend(values)
            actual_adjusted.extend(adjusted)
            municipal = f"{row['SG_UF']}/{int(row['CD_MUNICIPIO']):05}"
            training = [a-b for a, b in zip(moments[municipal], folds[(municipal, expected_fold)])]
            fallback = training[0] < meta['minimum_training_sections']
            if fallback:
                training = [a-b for a, b in zip(moments[row['SG_UF']], folds[(row['SG_UF'], expected_fold)])]
            if training[0] <= 0 or int(row['training_sections']) != training[0] or row['training_fallback_uf'] != str(fallback).lower():
                raise ValueError('contagem de treino/fallback divergente')
            s, _, _, ps, p2, inverse_n = training
            raw_mean = ps/s
            mean = (ps+0.5)/(s+1)
            variance = max(0, p2/s-raw_mean**2)
            inverse_n /= s
            rho = min(meta['maximum_rho'], max(0, (variance/(raw_mean*(1-raw_mean))-inverse_n)/(1-inverse_n))) if 0 < raw_mean < 1 and inverse_n < 1 else 0
            if rho < 1e-6:
                rho = 0
            if not math.isclose(mean, float(row['crossfit_mean_13']), abs_tol=1e-9) or not math.isclose(rho, float(row['crossfit_rho']), abs_tol=1e-8):
                raise ValueError('ajuste fora do fold divergente')
            # Seleção determinística por hash, fixada no código, sem escolher resultados.
            if int.from_bytes(digest[:8], 'little') % 1024 == 0 or meta['source_kind'] == 'synthetic_fixture':
                municipal = f"{row['SG_UF']}/{int(row['CD_MUNICIPIO']):05}"
                for j, group in enumerate(['BR', row['SG_UF'], municipal]):
                    ks, ns = pools[group]
                    expected = nominal_log_p(n, k, (ks+0.5)/(ns+1), 0)
                    if not math.isclose(expected, values[j], abs_tol=1e-7, rel_tol=1e-9):
                        raise ValueError('score binomial divergente: '+identity)
                expected = nominal_log_p(n, k, float(row['crossfit_mean_13']), float(row['crossfit_rho']))
                if not math.isclose(expected, values[3], abs_tol=1e-7, rel_tol=1e-9):
                    raise ValueError('score beta-binomial divergente: '+identity)
                score_sample += 1
    require(not identities, 'todos os 21 campos de todas as seções preservados')
    require(zero == report['descriptive']['zero_valid_sections'], 'denominadores zero conferidos')
    computed = holm(raw_p)
    require(all(math.isclose(a, b, abs_tol=1e-9, rel_tol=1e-10) for a, b in zip(computed, actual_adjusted)), 'Holm de todos os scores recalculado')
    del raw_p, actual_adjusted, computed

    associations = json.loads((directory/'associations.json').read_bytes())
    family = report['association_family']
    require(family['planned_tests'] == len(associations), 'família completa de associações')
    levels = sorted({r['stratum_level'] for r in associations})
    policy_source = report['effective_protocol']['time_policy']
    actual_policy = hashes(Path(policy_source['path']), buffer)
    require(all(actual_policy[k] == meta['time_policy'][k] for k in ('bytes', 'sha256')), 'política de horário conferida')
    policy = json.loads(Path(policy_source['path']).read_bytes())
    for level in levels:
        tests = [r for r in associations if r['stratum_level'] == level]
        calculated = observed_associations(sections, level, meta['size_bin_width'], policy)
        for test in tests:
            available, permutable, r = calculated.get((test['scope'], test['variable']), (0, 0, None))
            if available != test['available_sections'] or permutable != test['permutable_sections']:
                raise ValueError('cobertura residual divergente: '+level)
            actual_r = test['partial_pearson_13']
            if (r is None) != (actual_r is None) or (r is not None and not math.isclose(r, actual_r, abs_tol=1e-8, rel_tol=1e-7)):
                raise ValueError('correlação residual independente divergente: '+level+':'+test['scope']+':'+test['variable'])
        checks.append('correlações residuais independentes: '+level)
        counts = [0]*len(tests)
        replicates = 0
        with (directory/f'permutations-{level}.csv').open(newline='') as stream:
            reader = csv.reader(stream)
            header = next(reader)
            require(header[1:] == [r['scope']+':'+r['variable'] for r in tests], 'cabeçalho das permutações: '+level)
            for values in reader:
                if len(values) != len(header) or int(values[0]) != replicates:
                    raise ValueError('réplica ausente ou repetida')
                replicates += 1
                for j, test in enumerate(tests):
                    r = test['partial_pearson_13']
                    if r is None:
                        if values[j+1] or test['p_mc'] is not None:
                            raise ValueError('teste sem variância ganhou p fictício')
                    else:
                        counts[j] += abs(float(values[j+1]))+1e-12 >= abs(r)
                        if not math.isclose(r, -test['partial_pearson_22'], abs_tol=1e-12):
                            raise ValueError('assimetria entre candidatos')
        require(replicates == meta['permutations'], 'todas as réplicas: '+level)
        require(all(t['p_mc'] is None or math.isclose(t['p_mc'], (counts[j]+1)/(replicates+1), abs_tol=1e-12) for j, t in enumerate(tests)), 'p de Monte Carlo recalculado: '+level)
    testable = [r for r in associations if r['p_mc'] is not None]
    adjusted = holm([math.log(r['p_mc']) for r in testable], len(associations))
    require(all(math.isclose(math.exp(a), r['p_holm'], abs_tol=1e-12) for a, r in zip(adjusted, testable)), 'Holm de todas as associações recalculado')
    require(sum(r['p_holm'] <= meta['alpha'] for r in testable) == family['holm_rejections'], 'rejeições de associação conferidas')

    reference = report['predictive_reference']
    expected = reference['expected_counts']
    def statistics(values):
        return [abs(values[i]-expected[i]) for i in range(6)]+[
            sum((values[i]-expected[i])**2/expected[i] for i in range(start, start+10) if expected[i] > 0) for start in (6, 16)]
    observed_statistics = statistics(observed)
    exceed = [0]*8
    replicates = 0
    with (directory/'predictive_replicates.csv').open(newline='') as stream:
        reader = csv.reader(stream)
        next(reader)
        for row in reader:
            if len(row) != 27 or int(row[0]) != replicates:
                raise ValueError('réplica preditiva ausente ou malformada')
            replicates += 1
            for j, value in enumerate(statistics(list(map(int, row[1:])))):
                exceed[j] += value+1e-9 >= observed_statistics[j]
    require(replicates == meta['predictive_replicates'], 'todas as réplicas preditivas')
    probabilities = [(b+1)/(replicates+1) for b in exceed]
    require(all(math.isclose(a, b, abs_tol=1e-12) for a, b in zip(probabilities, reference['mc_tail_fraction'])), 'frações de referência preditiva recalculadas')
    require(all(math.isclose(math.exp(a), b, abs_tol=1e-12) for a, b in zip(holm(list(map(math.log, probabilities))), reference['holm_nominal_tail_fraction'])), 'Holm preditivo recalculado')
    return {'format_version': 1, 'success': True, 'scope': 'Conferência independente de bytes, campos, totais, scores nominais amostrados e correções/referências completas; não autentica a votação nem valida os pressupostos dos modelos.', 'checks': checks, 'sampled_sections_math_lgamma': score_sample, 'sections_compared_all_fields': report['descriptive']['sections'], 'input_sha256': meta['sections']['sha256']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--sections', type=Path)
    parser.add_argument('--result', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('saída existente; preservar bytes')
    meta = json.loads(args.protocol.read_bytes())
    try:
        report = check(args.protocol, args.sections or Path(meta['sections']['path']), args.result)
    except Exception as exc:
        report = {'format_version': 1, 'success': False, 'error': f'{type(exc).__name__}: {exc}'}
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'checks'}, ensure_ascii=False))
    return 0 if report['success'] else 1


if __name__ == '__main__':
    sys.exit(main())
