#!/usr/bin/env python3
"""Seguimento exploratório de TODOS os alertas CF; não altera scores ou testes."""
import argparse
import collections
import csv
import io
import json
import math
import hashlib
from pathlib import Path
import sys
import zipfile

from acquire_2026 import hashes, safe_path
from check_statistical_suite_2026 import key, nominal_log_p
from validate import load_limits

MODEL = 'crossfit_municipality_beta_binomial'


def csv_rows(archive, info, required, limits, sources):
    if info.file_size > limits['MAX_ZIP_MEMBER_BYTES']:
        raise ValueError('membro acima do limite')
    raw = archive.read(info)  # CRC da entrada ZIP também é conferido.
    sources.append({'member': info.filename, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
    reader = csv.DictReader(io.StringIO(raw.decode('latin-1'), newline=''), delimiter=';', strict=True)
    if len(reader.fieldnames) != len(set(reader.fieldnames)) or not required.issubset(reader.fieldnames):
        raise ValueError('cabeçalho duplicado/incompleto')
    for ordinal, row in enumerate(reader, 1):
        if ordinal > limits['MAX_CSV_RECORDS'] or None in row or any(v is None for v in row.values()):
            raise ValueError('largura ou limite inválido')
        yield ordinal, row


def attach_metadata(alerts, local_rows, correspondence):
    """Preserva todas as correspondências e ausências; nenhuma classificação inferida."""
    attached = {}
    for identity, row in alerts.items():
        matches = local_rows.get(identity, [])
        attached[identity] = {'score_row_all_fields': row, 'official_local_rows_all_fields': matches,
                              'official_correspondence_rows_all_fields': correspondence.get(identity, []),
                              'local_number_matches': bool(matches) and all(int(r['NR_LOCAL_VOTACAO']) == int(row['NR_LOCAL_VOTACAO']) for r in matches)}
    return attached


def place(row):
    return f"{row['SG_UF']}/{int(row['CD_MUNICIPIO']):05}/{int(row['NR_ZONA']):04}/{int(row['NR_LOCAL_VOTACAO']):04}"


def bu_text(item, args, catalog, limits):
    """Lê CSV já extraído ou o mesmo membro no ZIP fixado, sem reescrever fontes."""
    if args.bu_zip_root is None:
        path = Path(item['path'])
        measured = hashes(path, limits['IO_BUFFER_BYTES'])
        if any(measured[k] != item[k] for k in ('bytes', 'sha256')):
            raise ValueError('BU original bytes/SHA-256 divergente')
        return path.open(encoding='latin-1', newline=''), measured
    choices = [r for r in catalog['items'] if r['url'] == item['zip_url']]
    if len(choices) != 1:
        raise ValueError('ZIP BU ausente/duplicado no catálogo')
    selected = choices[0]
    path = safe_path(args.bu_zip_root, selected['path'])
    zip_measured = hashes(path, limits['IO_BUFFER_BYTES'])
    if zip_measured['sha256'] != item['zip_sha256'] or zip_measured['sha256'] != selected['expected_sha256'] or zip_measured['bytes'] != selected['expected_bytes']:
        raise ValueError('ZIP BU bytes/SHA-256 divergente')
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if len(infos) > limits['MAX_ZIP_MEMBERS'] or len({i.filename for i in infos}) != len(infos):
            raise ValueError('índice BU inválido')
        found = [i for i in infos if i.filename == item['member']]
        if len(found) != 1 or found[0].file_size > limits['MAX_ZIP_MEMBER_BYTES']:
            raise ValueError('membro BU ausente ou excessivo')
        raw = archive.read(found[0])
    measured = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'zip': zip_measured}
    if any(measured[k] != item[k] for k in ('bytes', 'sha256')):
        raise ValueError('membro BU bytes/SHA-256 divergente')
    return io.StringIO(raw.decode('latin-1'), newline=''), measured


def run(args):
    root = Path(__file__).resolve().parents[1]
    limits = load_limits(root)
    buffer = limits['IO_BUFFER_BYTES']
    report = json.loads((args.result/'report.json').read_bytes())
    scores_path = args.result/'section_scores.csv'
    measured = hashes(scores_path, buffer)
    expected = report['artifacts']['section_scores.csv']
    if any(measured[k] != expected[k] for k in ('bytes', 'sha256')):
        raise ValueError('scores alterados')
    alpha = report['effective_protocol']['alpha']
    alerts = {}
    with scores_path.open(newline='') as stream:
        for row in csv.DictReader(stream):
            if row[f'ln_holm_{MODEL}'] and float(row[f'ln_holm_{MODEL}']) <= math.log(alpha):
                identity = row['section_key']
                if identity in alerts:
                    raise ValueError('alerta duplicado')
                n, k = int(row['VOTOS_13'])+int(row['VOTOS_22']), int(row['VOTOS_13'])
                independently = nominal_log_p(n, k, float(row['crossfit_mean_13']), float(row['crossfit_rho']))
                if not math.isclose(independently, float(row[f'ln_p_{MODEL}']), abs_tol=1e-7, rel_tol=1e-9):
                    raise ValueError('score independente divergente')
                alerts[identity] = row
    if not alerts:
        raise ValueError('sem alertas selecionados; não inventar casos')
    local_groups = {place(r): [] for r in alerts.values()}
    with scores_path.open(newline='') as stream:
        for row in csv.DictReader(stream):
            if place(row) in local_groups:
                local_groups[place(row)].append(row)
    repeated = {}
    with (args.result/'repeated_urn_identifiers.csv').open(newline='') as stream:
        for row in csv.DictReader(stream):
            if row['section_key'] in repeated:
                raise ValueError('chave repetida no controle de identificadores')
            repeated[row['section_key']] = row
    catalog = json.loads(args.catalog.read_bytes())
    source_records, local_rows, correspondence = [], collections.defaultdict(list), collections.defaultdict(list)
    source_urls = ['https://cdn.tse.jus.br/estatistica/sead/odsele/eleitorado_locais_votacao/eleitorado_local_votacao_2026.zip',
                   'https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/correspefet/CEFT_2t_ZZ_261020261201.zip']
    for url in source_urls:
        candidates = [r for r in catalog['items'] if r['url'] == url]
        if len(candidates) != 1:
            raise ValueError('recurso contextual ausente/duplicado no catálogo')
        source = candidates[0]
        path = safe_path(args.root, source['path'])
        measured = hashes(path, buffer)
        if measured['bytes'] != source['expected_bytes'] or measured['sha256'] != source['expected_sha256']:
            raise ValueError('fonte contextual bytes/SHA-256 divergente')
        record = {'url': url, 'file': measured, 'members_read': [], 'scope_exclusions': collections.Counter()}
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > limits['MAX_ZIP_MEMBERS'] or len({i.filename for i in infos}) != len(infos):
                raise ValueError('índice ZIP excessivo ou nomes repetidos')
            record['all_members'] = [{'ordinal': j, 'name': i.filename, 'bytes': i.file_size, 'crc32': f'{i.CRC:08x}'} for j, i in enumerate(infos)]
            if 'eleitorado_local' in url:
                selected = {f"eleitorado_local_votacao_2026_{r['SG_UF']}.csv" for r in alerts.values()}
                if not selected.issubset({i.filename for i in infos}):
                    raise ValueError('UF contextual ausente')
                for info in infos:
                    if info.filename not in selected:
                        record['scope_exclusions']['members_outside_selected_UFs_or_BRASIL_alias'] += 1
                        continue
                    for _, row in csv_rows(archive, info, {'SG_UF', 'CD_MUNICIPIO', 'NR_ZONA', 'NR_SECAO', 'AA_ELEICAO', 'NR_TURNO', 'NR_LOCAL_VOTACAO', 'DS_TIPO_LOCAL'}, limits, record['members_read']):
                        if row['AA_ELEICAO'] != '2026' or row['NR_TURNO'] != '2':
                            record['scope_exclusions']['rows_outside_2026_second_round'] += 1
                        elif key(row) in alerts:
                            local_rows[key(row)].append(row)
                        else:
                            record['scope_exclusions']['rows_not_alerted'] += 1
            else:
                targets = set(alerts)|set(repeated)
                for info in infos:
                    if not info.filename.lower().endswith('.csv'):
                        continue
                    for _, row in csv_rows(archive, info, {'SG_UF', 'CD_MUNICIPIO', 'NR_ZONA', 'NR_SECAO', 'CD_PLEITO', 'CD_ORIGEM_VOTO', 'NR_URNA_EFETIVADA'}, limits, record['members_read']):
                        if row['CD_PLEITO'] != '3221':
                            record['scope_exclusions']['correspondence_other_election'] += 1
                        elif key(row) in targets:
                            correspondence[key(row)].append(row)
                        else:
                            record['scope_exclusions']['correspondence_not_selected'] += 1
        source_records.append(record)

    # Releitura independente dos CSVs originais extraídos do TSE para todos os alertas.
    manifest = json.loads(args.bu_manifest.read_bytes())
    bu_sources = []
    original_rows = collections.defaultdict(list)
    wanted_ufs = {r['SG_UF'] for r in alerts.values()}
    for item in manifest['inputs']:
        if item['uf'] not in wanted_ufs:
            continue
        stream, measured = bu_text(item, args, catalog, limits)
        selected = 0
        with stream:
            reader = csv.DictReader(stream, delimiter=';', strict=True)
            if len(reader.fieldnames) != len(set(reader.fieldnames)):
                raise ValueError('cabeçalho BU duplicado')
            for ordinal, row in enumerate(reader, 1):
                if ordinal > limits['MAX_CSV_RECORDS'] or None in row or any(v is None for v in row.values()):
                    raise ValueError('largura BU inválida')
                if row['CD_CARGO_PERGUNTA'] != '1' or key(row) not in alerts:
                    continue
                if row['ANO_ELEICAO'] != '2026' or row['CD_PLEITO'] != '3221' or row['NR_TURNO'] != '2':
                    raise ValueError('pleito/turno BU divergente')
                original_rows[key(row)].append({'record_ordinal': ordinal, 'all_fields': row})
                selected += 1
        bu_sources.append(dict(item, measured=measured, retained_records=selected))
    cases = attach_metadata(alerts, local_rows, correspondence)
    for identity, case in cases.items():
        case['voting_place_context_key'] = place(alerts[identity])
        raw_rows = original_rows.get(identity, [])
        if not raw_rows:
            raise ValueError('alerta sem BU original: '+identity)
        votes = {}
        for entry in raw_rows:
            r = entry['all_fields']
            candidate = r['NR_VOTAVEL']
            if candidate not in ('13', '22', '95', '96') or candidate in votes:
                raise ValueError('ocorrência/candidato BU inesperado')
            votes[candidate] = int(r['QT_VOTOS'])
            for name in ['QT_APTOS', 'QT_COMPARECIMENTO', 'QT_ABSTENCOES', 'QT_ELEI_BIOM_SEM_HABILITACAO', 'NR_LOCAL_VOTACAO', 'NR_URNA_EFETIVADA']:
                if int(r[name]) != int(alerts[identity][name]):
                    raise ValueError('contexto BU divergente: '+identity)
            if r['DT_ENCERRAMENTO'] != alerts[identity]['DT_ENCERRAMENTO']:
                raise ValueError('encerramento BU divergente: '+identity)
        for candidate, name in [('13', 'VOTOS_13'), ('22', 'VOTOS_22'), ('95', 'VOTOS_BRANCOS'), ('96', 'VOTOS_NULOS')]:
            if votes.get(candidate, 0) != int(alerts[identity][name]):
                raise ValueError('votos BU divergentes: '+identity)
        case['original_bu_rows_all_fields'] = raw_rows
        case['original_bu_counts_match'] = True
    repeated_context = {}
    for identity, row in repeated.items():
        matches = correspondence.get(identity, [])
        if not matches or any(int(r['NR_URNA_EFETIVADA']) != int(row['urn_identifier']) for r in matches):
            raise ValueError('identificador repetido sem conciliação CEFT: '+identity)
        repeated_context[identity] = {'repeated_identifier_row': row, 'official_correspondence_rows_all_fields': matches}
    types = collections.Counter()
    for case in cases.values():
        labels = sorted({r['DS_TIPO_LOCAL'] for r in case['official_local_rows_all_fields']})
        types[' | '.join(labels) if labels else 'SEM_CORRESPONDENCIA'] += 1
    return {'format_version': 1, 'success': True, 'scope': 'Seguimento exploratório posterior à bateria: todos os alertas CF após Holm, ambos os candidatos, sem modificar scores ou testes. Contexto cadastral não comprova causa do padrão nem comportamento individual.',
            'scores_file': hashes(scores_path, buffer), 'catalog_file': hashes(args.catalog, buffer), 'bu_manifest_file': hashes(args.bu_manifest, buffer),
            'sources': source_records, 'original_bu_sources': bu_sources, 'alerts_count': len(alerts), 'all_alerts_original_bu_counts_match': True,
            'alerts_with_local_metadata': sum(bool(c['official_local_rows_all_fields']) for c in cases.values()), 'official_local_type_labels_per_case': types,
            'correspondence_scope': 'Somente CEFT ZZ, para contextualizar identificadores reutilizados. Lista vazia em outras UFs significa fora deste recorte de correspondência.',
            'voting_place_context_all_score_rows': local_groups,
            'all_repeated_identifiers_origin_C': bool(repeated_context) and all(all(r['CD_ORIGEM_VOTO'] == 'C' for r in c['official_correspondence_rows_all_fields']) for c in repeated_context.values()),
            'repeated_identifiers_context': repeated_context, 'cases': cases}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result', type=Path, required=True)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--bu-manifest', type=Path, required=True)
    parser.add_argument('--bu-zip-root', type=Path, help='Alternativa portátil: ler BU diretamente dos ZIPs fixados no catálogo')
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
    print(json.dumps({k: v for k, v in report.items() if k not in ('cases', 'sources', 'original_bu_sources', 'repeated_identifiers_context', 'voting_place_context_all_score_rows')}, ensure_ascii=False))
    return 0 if report['success'] else 1


if __name__ == '__main__':
    sys.exit(main())
