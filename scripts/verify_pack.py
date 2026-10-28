#!/usr/bin/env python3
"""Verificador independente em streaming; nenhuma verificação depende de assert."""
import argparse
from contextlib import ExitStack
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import sys
from map_raw_data import KNOWN_LAYOUTS, HashingReader, CsvLines, load_limits, DEFAULT_LIMITS, MappingError

QUOTED = {
    'DT_GERACAO','HH_GERACAO','NM_TIPO_ELEICAO','DT_PLEITO','DS_ELEICAO','SG_UF',
    'NM_MUNICIPIO','DS_CARGO_PERGUNTA','SG_PARTIDO','NM_PARTIDO','DT_BU_RECEBIDO',
    'DS_TIPO_URNA','DS_TIPO_VOTAVEL','NM_VOTAVEL','CD_CARGA_1_URNA_EFETIVADA',
    'CD_CARGA_2_URNA_EFETIVADA','CD_FLASHCARD_URNA_EFETIVADA','DT_CARGA_URNA_EFETIVADA',
    'DS_CARGO_PERGUNTA_SECAO','DS_SECOES_AGREGADAS','DT_ABERTURA','DT_ENCERRAMENTO',
    'QT_ELEI_BIOM_SEM_HABILITACAO','DT_EMISSAO_BU','NR_JUNTA_APURADORA','NR_TURMA_APURADORA',
}
ROOT_FIELDS = {'artifact_kind','format_version','family','header','quoted','rows','encoding',
               'lineterminator','quoting_rule','source_member_sha256','columns'}
COL_FIELDS = {'file','rows','bytes','sha256'}

def require(condition, message):
    if not condition:
        raise ValueError(message)

def digest(path, buffer_bytes):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(buffer_bytes), b''):
            h.update(chunk)
    return h.hexdigest()

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pack', required=True)
    parser.add_argument('--original', required=True)
    args = parser.parse_args(argv)
    previous_limit = csv.field_size_limit()
    try:
        limits = load_limits(os.environ.get('URNAPACK_LIMITS_FILE', DEFAULT_LIMITS),
                             ('IO_BUFFER_BYTES', 'MAX_PACK_MANIFEST_BYTES', 'MAX_PACK_BYTES'))
        csv.field_size_limit(limits['MAX_FIELD_BYTES'])
        root = Path(args.pack).resolve(strict=True)
        manifest_path = root / 'pack.json'
        require(not manifest_path.is_symlink(), 'symlink no manifesto')
        require(manifest_path.stat().st_size <= limits['MAX_PACK_MANIFEST_BYTES'], 'manifesto excessivo')
        m = json.loads(manifest_path.read_text())
        header = KNOWN_LAYOUTS['bweb']
        quoted = [name in QUOTED for name in header]
        require(set(m) == ROOT_FIELDS, 'campos desconhecidos/ausentes no manifesto')
        require(m['artifact_kind'] == 'bweb_columnar_pack' and type(m['format_version']) is int and m['format_version'] in (1,2), 'versão/tipo incompatível')
        require(all(type(value) is bool for value in m['quoted']), 'quoting exige booleanos')
        require(m['family'] == 'bweb' and m['header'] == header and m['quoted'] == quoted, 'layout/quoting divergente')
        require(m['encoding'] == 'latin-1' and m['lineterminator'] == '\r\n' and m['quoting_rule'] == 'tse-text-columns-v1', 'regra de emissão divergente')
        require(type(m['rows']) is int and 0 <= m['rows'] <= limits['MAX_CSV_RECORDS'], 'contagem inválida')
        require(len(m['columns']) == len(header), 'quantidade de colunas inválida')
        require(isinstance(m['source_member_sha256'], str) and len(m['source_member_sha256']) == 64, 'hash da origem obrigatório')
        expected = {'pack.json'} | {f'columns/{i:02}.bin' for i in range(len(header))}
        found = set()
        def walk_error(error):
            raise error
        for parent, dirs, files in os.walk(root, onerror=walk_error, followlinks=False):
            for name in dirs + files:
                path = Path(parent) / name
                require(not path.is_symlink(), f'symlink interno: {path.name}')
                if path.is_dir():
                    continue
                require(path.is_file(), 'arquivo especial no pacote')
                found.add(path.relative_to(root).as_posix())
        require(found == expected, 'pacote incompleto ou com arquivos desconhecidos')
        with ExitStack() as stack:
            streams = []
            total_bytes = 0
            for i, col in enumerate(m['columns']):
                require(set(col) == COL_FIELDS and col['file'] == f'columns/{i:02}.bin', 'caminho/campos de coluna divergentes')
                require(type(col['rows']) is int and type(col['bytes']) is int and col['bytes'] >= 0, 'tipos de metadados de coluna inválidos')
                path = root / col['file']
                total_bytes += path.stat().st_size
                require(path.stat().st_size <= limits['MAX_SOURCE_FILE_BYTES'] and total_bytes <= limits['MAX_PACK_BYTES'], 'limite de tamanho do pacote excedido')
                require(col['rows'] == m['rows'] and col['bytes'] == path.stat().st_size, 'metadados de coluna divergentes')
                require(col['sha256'] == digest(path, limits['IO_BUFFER_BYTES']), f'SHA-256 diverge: {col["file"]}')
                streams.append(stack.enter_context(path.open('rb')))
            raw = stack.enter_context(open(args.original, 'rb'))
            hashed = HashingReader(raw)
            text = stack.enter_context(io.TextIOWrapper(io.BufferedReader(hashed), encoding='latin-1', newline=''))
            lines = CsvLines(text, limits['MAX_RECORD_BYTES'])
            reader = csv.reader(lines, delimiter=';', strict=True)
            require(next(reader, None) == header, 'cabeçalho de origem divergente')
            reconstructed = hashlib.sha256()
            reconstructed.update(b';'.join(b'"'+name.encode()+b'"' for name in header)+b'\r\n')
            count = 0
            while True:
                lines.start_record()
                row = next(reader, None)
                if row is None:
                    break
                count += 1
                require(count <= m['rows'] and len(row) == len(header), f'contagem divergente no registro {count}')
                physical = []
                for i, (value, stream) in enumerate(zip(row, streams)):
                    prefix = stream.read(4)
                    require(len(prefix) == 4, f'coluna truncada: {i}')
                    size = struct.unpack('<I', prefix)[0]
                    require(size <= limits['MAX_FIELD_BYTES'], 'comprimento de campo excessivo')
                    stored = stream.read(size)
                    require(len(stored) == size and stored == value.encode('latin-1'), f'DIVERGÊNCIA semântica registro {count}, coluna {i}')
                    if quoted[i]:
                        physical.append(b'"'+stored.replace(b'"',b'""')+b'"')
                    else:
                        require(not any(b in stored for b in (b';',b'"',b'\r',b'\n')), 'especial em coluna B')
                        physical.append(stored)
                reconstructed.update(b';'.join(physical)+b'\r\n')
                if count % 100000 == 0:
                    print(f'verify_pack: {count} registros conferidos', file=sys.stderr)
            require(count == m['rows'], 'registros ausentes')
            require(all(stream.read(1) == b'' for stream in streams), 'bytes residuais em coluna')
            source_sha = hashed.hexdigest()
            require(source_sha == m['source_member_sha256'] == reconstructed.hexdigest(), 'SHA-256 da origem/emissão diverge')
        print(f'verify_pack: OK ({count} registros; valores, bytes e hashes conferidos)')
        return 0
    except (MappingError, OSError, ValueError, KeyError, TypeError, csv.Error, EOFError, struct.error) as error:
        print(f'verify_pack: FALHA: {error}', file=sys.stderr)
        return 1
    finally:
        csv.field_size_limit(previous_limit)

if __name__ == '__main__':
    sys.exit(main())
