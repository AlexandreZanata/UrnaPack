#!/usr/bin/env python3
"""Controle adicional exploratório de igualdade de perfis MT 2022/t2 × 2026/t2."""
import argparse
import csv
import json
from pathlib import Path
import sys
import zipfile

from acquire_2026 import hashes, safe_path
from check_statistical_suite_2026 import key
from contextualize_statistical_alerts_2026 import csv_rows
from validate import load_limits


def compare_profiles(before, after):
    shared = sorted(before.keys() & after.keys())
    comparisons = [{'section_key': k, 'before': before[k], 'after': after[k],
                    'same_four_vote_counts': before[k]['votes'] == after[k]['votes'],
                    'same_profile_including_turnout_registered': before[k] == after[k]} for k in shared]
    return {'before_sections': len(before), 'after_sections': len(after), 'shared_numeric_keys': len(shared),
            'identical_four_vote_counts': sum(r['same_four_vote_counts'] for r in comparisons),
            'identical_profiles_including_turnout_registered': sum(r['same_profile_including_turnout_registered'] for r in comparisons),
            'only_before': sorted(before.keys()-after.keys()), 'only_after': sorted(after.keys()-before.keys()), 'comparisons': comparisons}


def run(args):
    limits = load_limits(Path(__file__).resolve().parents[1])
    buffer = limits['IO_BUFFER_BYTES']
    catalog = json.loads(args.historical_catalog.read_bytes())
    candidates = [r for r in catalog['items'] if r['url'].endswith('/bweb_2t_MT_311020221535.zip')]
    if len(candidates) != 1:
        raise ValueError('fonte histórica ausente/duplicada')
    selected = candidates[0]
    path = safe_path(args.root, selected['path'])
    measured = hashes(path, buffer)
    if measured['bytes'] != selected['expected_bytes'] or measured['sha256'] != selected['expected_sha256']:
        raise ValueError('fonte histórica bytes/SHA-256 divergente')
    before = {}
    members = []
    election_ids = set()
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if len(infos) > limits['MAX_ZIP_MEMBERS'] or len({i.filename for i in infos}) != len(infos):
            raise ValueError('índice histórico inválido')
        index = [{'name': i.filename, 'bytes': i.file_size, 'crc32': f'{i.CRC:08x}'} for i in infos]
        for info in infos:
            if not info.filename.lower().endswith('.csv'):
                continue
            for _, r in csv_rows(archive, info, {'ANO_ELEICAO', 'CD_CARGO_PERGUNTA', 'NR_TURNO', 'CD_ELEICAO', 'QT_VOTOS', 'NR_VOTAVEL'}, limits, members):
                if r['CD_CARGO_PERGUNTA'] != '1':
                    continue
                if r['ANO_ELEICAO'] != '2022' or r['NR_TURNO'] != '2' or r['SG_UF'] != 'MT':
                    raise ValueError('escopo histórico divergente')
                election_ids.add(r['CD_ELEICAO'])
                if len(election_ids) != 1:
                    raise ValueError('não misturar eleições históricas')
                identity = key(r)
                context = {'turnout': int(r['QT_COMPARECIMENTO']), 'registered': int(r['QT_APTOS'])}
                profile = before.setdefault(identity, dict(context, votes={}))
                if any(profile[k] != v for k, v in context.items()):
                    raise ValueError('contexto histórico divergente')
                candidate = r['NR_VOTAVEL']
                if candidate not in ('13', '22', '95', '96') or candidate in profile['votes'] or int(r['QT_VOTOS']) < 0:
                    raise ValueError('voto/ocorrência histórica inesperada')
                profile['votes'][candidate] = int(r['QT_VOTOS'])
    for profile in before.values():
        profile['votes'] = [profile['votes'].get(c, 0) for c in ('13', '22', '95', '96')]
        if sum(profile['votes']) != profile['turnout']:
            raise ValueError('aritmética histórica divergente')
    report = json.loads((args.result/'report.json').read_bytes())
    scores = args.result/'section_scores.csv'
    actual_scores = hashes(scores, buffer)
    if any(actual_scores[k] != report['artifacts']['section_scores.csv'][k] for k in ('bytes', 'sha256')):
        raise ValueError('scores alterados')
    after = {}
    with scores.open(newline='') as stream:
        for r in csv.DictReader(stream):
            if r['SG_UF'] == 'MT':
                identity = r['section_key']
                if identity in after:
                    raise ValueError('chave 2026 repetida')
                after[identity] = {'votes': [int(r[n]) for n in ('VOTOS_13', 'VOTOS_22', 'VOTOS_BRANCOS', 'VOTOS_NULOS')],
                                   'turnout': int(r['QT_COMPARECIMENTO']), 'registered': int(r['QT_APTOS'])}
    if not before or not after:
        raise ValueError('controle vazio')
    return dict(compare_profiles(before, after), format_version=1, success=True,
        scope='Controle adicional, posterior ao protocolo: igualdade semântica de quatro contagens por chaves numéricas MT entre anos. Compara números 13/22, sem pressupor identidade de candidatos. Chave igual não garante a mesma população/local; não é teste de probabilidade de fraude. Apenas MT, sem extrapolação nacional.',
        projection='Campos conhecidos não projetados continuam nos CSVs originais preservados e vinculados pelos hashes. Ocorrência ausente de candidato/categoria é representada por zero, explicitamente; duplicatas reprovam. Zero semântico não é restauração de bytes.',
        historical_source=dict(selected, measured=measured, member_index=index, members_read=members, election_ids=sorted(election_ids)), scores_file=actual_scores)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--historical-catalog', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--result', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('saída existente; preservar evidência')
    try:
        report = run(args)
    except Exception as exc:
        report = {'format_version': 1, 'success': False, 'error': f'{type(exc).__name__}: {exc}'}
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({k: v for k, v in report.items() if not isinstance(v, (dict, list))}, ensure_ascii=False))
    return 0 if report['success'] else 1


if __name__ == '__main__':
    sys.exit(main())
