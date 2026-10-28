#!/usr/bin/env python3
"""Etapa 4: experimentos locais retomáveis; codecs e arquivo de produção em Rust.

PyArrow/DuckDB são ferramentas de comparação, sem substituir a evidência bruta.
Nenhum resultado é marcado completo sem conferência de bytes ou das consultas.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import time
import tempfile
import zipfile

from map_raw_data import KNOWN_LAYOUTS
from verify_pack import QUOTED
from validate import load_limits, sha256_file

REPO = Path(__file__).resolve().parent.parent
HEADER = KNOWN_LAYOUTS['bweb']
LIMITS = load_limits(str(REPO))
BWEB_METHODS=('zstd-1','zstd-3','zstd-10','zstd-19','xz-6','xz-9e','brotli-5','zstd-3-blocks','zstd-19-blocks','brotli-11')
COLUMN_METHODS=('xz-6','xz-9e','brotli-5','zstd-19-blocks')
RAW_SOLID_METHODS=('zstd-3','zstd-19','xz-6','xz-9e','brotli-5')

def require(condition, message):
    if not condition:
        raise ValueError(message)

def read_json(path):
    def unique(pairs):
        result={}
        for key,value in pairs:
            require(key not in result,f'chave JSON duplicada: {key}')
            result[key]=value
        return result
    return json.loads(Path(path).read_text(encoding='utf-8'),object_pairs_hook=unique)

def save(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.partial-json')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n',encoding='utf-8',newline='\n')
    os.replace(temporary, path)

def describe(path):
    path = Path(path)
    return {'path': str(path.resolve()), 'bytes': path.stat().st_size, 'sha256': sha256_file(path)}

def encode_row(row, header=False):
    require(len(row) == len(HEADER), 'quantidade de campos divergente')
    values = []
    for name, value in zip(HEADER, row):
        require(isinstance(value, str), 'nulo/campo não textual inesperado')
        raw = value.encode('latin-1')
        if header or name in QUOTED:
            raw = b'"' + raw.replace(b'"', b'""') + b'"'
        else:
            require(not any(c in raw for c in (b';', b'"', b'\r', b'\n')), 'especial em coluna sem aspas')
        values.append(raw)
    return b';'.join(values) + b'\r\n'

def logical_rows(path):
    previous=csv.field_size_limit(LIMITS['MAX_FIELD_BYTES'])
    try:
        with open(path, encoding='latin-1', newline='') as source:
            reader = csv.reader(source, delimiter=';', strict=True)
            require(next(reader, None) == HEADER, 'layout BU web incompatível')
            for row in reader:
                require(len(row) == len(HEADER), 'campos divergentes')
                yield row
    finally:csv.field_size_limit(previous)

def disk_bytes(root):
    total=0
    for path in Path(root).rglob('*'):
        try:
            if path.is_file() and not path.is_symlink():total+=path.stat().st_size
        except FileNotFoundError:pass  # Apenas amostragem de temporários sujeitos a rename.
    return total

def measured(command, folder, name):
    """Mede processo + descendentes. RSS somado é conservador sobre páginas compartilhadas."""
    import psutil
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    log = folder / (name + '.stderr.log')
    stdout = folder / (name + '.stdout.json')
    executable_sha256=sha256_file(command[0])
    start = time.perf_counter_ns()
    peak_rss = 0
    peak_disk = disk_bytes(folder)
    with stdout.open('wb') as out, log.open('wb') as err:
        process = subprocess.Popen([str(a) for a in command], stdout=out, stderr=err)
        parent = psutil.Process(process.pid)
        while process.poll() is None:
            try:
                tree = [parent] + parent.children(recursive=True)
                rss = 0
                for child in tree:
                    try:
                        rss += child.memory_info().rss
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                peak_rss = max(peak_rss, rss)
            except psutil.NoSuchProcess:
                pass
            peak_disk = max(peak_disk, disk_bytes(folder))
            time.sleep(LIMITS['BENCH_POLL_MILLIS'] / 1000)
        code = process.wait()
    wall = time.perf_counter_ns() - start
    peak_disk = max(peak_disk, disk_bytes(folder))
    result={'wall_ns': wall, 'peak_tree_rss_bytes': peak_rss or None,
            'peak_case_disk_bytes': peak_disk, 'stdout': str(stdout), 'stderr': str(log),
            'command':[str(a) for a in command],'executable_sha256':executable_sha256}
    require(code == 0, f'comando reprovado ({code}): {command}; diagnóstico: {log}')
    return result

def stats(values):
    return {'runs': len(values), 'min_ns': min(values), 'median_ns': statistics.median(values),
            'max_ns': max(values), 'stdev_ns': statistics.pstdev(values)}

def split_dictionary(source, folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    report = folder / 'split.json'
    source_hash = sha256_file(source)
    if report.exists():
        result = read_json(report)
        require(result['source_sha256'] == source_hash, 'split de outra origem')
        for part in result['parts'].values():
            require(sha256_file(part['path']) == part['sha256'], 'split corrompido')
        return result
    groups = {name: set() for name in ('train', 'validation', 'test')}
    counts = dict.fromkeys(groups, 0)
    streams = {}
    try:
        for name in groups:
            path = folder / (name + '.csv')
            require(not path.exists(), 'split parcial: preservar diagnóstico e usar outra saída')
            streams[name] = path.open('xb')
            streams[name].write(encode_row(HEADER, header=True))
        for row in logical_rows(source):
            key = tuple(row[i] for i in (5, 7, 10, 11, 13, 14))
            identity = json.dumps(key, ensure_ascii=False, separators=(',', ':')).encode()
            digest = hashlib.sha256(identity).digest()
            fold = int.from_bytes(digest[:8], 'big') % 10
            name = 'train' if fold < 6 else 'validation' if fold < 8 else 'test'
            groups[name].add(digest.hex())
            counts[name] += 1
            streams[name].write(encode_row(row))
    finally:
        for stream in streams.values():
            stream.close()
    require(all(counts.values()), 'não há grupos suficientes para treino/validação/teste')
    require(not (groups['train'] & groups['validation'] or groups['train'] & groups['test'] or groups['validation'] & groups['test']), 'vazamento entre partições')
    result = {'artifact_kind': 'bweb_dictionary_split', 'format_version': 1,
              'source_sha256': source_hash, 'group_key': [HEADER[i] for i in (5, 7, 10, 11, 13, 14)],
              'rule': 'sha256(JSON compacto UTF-8 da chave); u64 big-endian inicial modulo 10; 0..5 train, 6..7 validation, 8..9 test',
              'parts': {name: dict(describe(folder / (name + '.csv')), records=counts[name], groups=len(groups[name]),
                                    group_set_sha256=hashlib.sha256('\n'.join(sorted(groups[name])).encode()).hexdigest()) for name in groups}}
    save(report, result)
    return result

def parquet_encode(source, output, row_group, level):
    import pyarrow as pa
    import pyarrow.parquet as pq
    pa.set_cpu_count(1)
    require(not Path(output).exists(), 'Parquet existente recusado')
    source_hash = sha256_file(source)
    metadata = {b'urnapack_format': b'bweb-parquet-v1', b'source_member_sha256': source_hash.encode(),
                b'encoding': b'latin-1', b'lineterminator': b'CRLF', b'quoting_rule': b'tse-text-columns-v1'}
    schema = pa.schema([pa.field(name, pa.string(), nullable=False) for name in HEADER], metadata=metadata)
    start = time.perf_counter_ns()
    records = 0
    rows = []
    with pq.ParquetWriter(output, schema, compression='zstd', compression_level=level,
                          use_dictionary=True, write_statistics=True) as writer:
        for row in logical_rows(source):
            rows.append(row)
            records += 1
            if len(rows) == row_group:
                writer.write_table(pa.Table.from_arrays([pa.array(col, type=pa.string()) for col in zip(*rows)], schema=schema), row_group_size=row_group)
                rows.clear()
        if rows:
            writer.write_table(pa.Table.from_arrays([pa.array(col, type=pa.string()) for col in zip(*rows)], schema=schema), row_group_size=row_group)
    encode_ns = time.perf_counter_ns() - start
    start = time.perf_counter_ns()
    restored_hash = hashlib.sha256(encode_row(HEADER, header=True))
    checked = 0
    table = pq.ParquetFile(output)
    require(table.schema_arrow.equals(schema, check_metadata=True), 'schema/metadata Parquet divergente')
    for batch in table.iter_batches(batch_size=LIMITS['PARQUET_ROW_GROUP_SMALL'], use_threads=False):
        columns = [batch.column(i).to_pylist() for i in range(len(HEADER))]
        for row in zip(*columns):
            restored_hash.update(encode_row(row))
            checked += 1
    require(checked == records and restored_hash.hexdigest() == source_hash, 'round-trip Parquet diverge')
    return {'artifact_kind': 'bweb_parquet_measurement', 'format_version': 1, 'codec': 'parquet-zstd',
            'row_group_rows': row_group, 'level': level, 'input_bytes': Path(source).stat().st_size,
            'source_sha256': source_hash, 'records': records, 'output_bytes': Path(output).stat().st_size,
            'encoded_sha256': sha256_file(output), 'compress_ns': encode_ns,
            'decompress_ns': time.perf_counter_ns() - start, 'round_trip_ok': True,
            'pyarrow_version': pa.__version__, 'arrow_cpp_version': pa.cpp_build_info.version}

def parquet_queries(path, reference, encoded_sha):
    import duckdb
    require(sha256_file(path) == encoded_sha, 'Parquet alterado antes da consulta')
    import pyarrow.parquet as pq
    require(pq.read_schema(path).metadata[b'source_member_sha256'].decode() == reference['source_member_sha256'], 'Parquet de outra origem')
    connection = duckdb.connect(config={'threads': '1', 'memory_limit': str(LIMITS['QUERY_MEMORY_BYTES']) + 'B'})
    q1 = connection.execute('''SELECT CD_CARGO_PERGUNTA, SG_UF, CD_MUNICIPIO, SUM(CAST(QT_VOTOS AS UBIGINT))
        FROM read_parquet(?) GROUP BY 1,2,3''', [str(path)]).fetchall()
    q1 = [{'key': list(row[:3]), 'votes': str(int(row[3]))} for row in sorted(q1)]
    contexts = '''SELECT CD_PLEITO, NR_TURNO, SG_UF, CD_MUNICIPIO, NR_ZONA, NR_SECAO,
        MIN(CAST(QT_APTOS AS UBIGINT)) a, MIN(CAST(QT_COMPARECIMENTO AS UBIGINT)) c,
        MIN(CAST(QT_ABSTENCOES AS UBIGINT)) ab, MAX(CAST(QT_APTOS AS UBIGINT)) amax,
        MAX(CAST(QT_COMPARECIMENTO AS UBIGINT)) cmax, MAX(CAST(QT_ABSTENCOES AS UBIGINT)) abmax
        FROM read_parquet(?) WHERE CD_CARGO_PERGUNTA='1' GROUP BY 1,2,3,4,5,6'''
    bad = connection.execute('SELECT COUNT(*) FROM (' + contexts + ') WHERE a!=amax OR c!=cmax OR ab!=abmax OR a!=c+ab', [str(path)]).fetchone()[0]
    require(bad == 0, 'contexto presidencial inconsistente')
    q2 = connection.execute('SELECT SG_UF,CD_MUNICIPIO,NR_ZONA,COUNT(*),SUM(a),SUM(c),SUM(ab) FROM (' + contexts + ') GROUP BY 1,2,3', [str(path)]).fetchall()
    q2 = [{'key': list(row[:3]), 'sections': int(row[3]), 'aptos': str(int(row[4])),
           'comparecimento': str(int(row[5])), 'abstencoes': str(int(row[6]))} for row in sorted(q2)]
    cols = [HEADER[i] for i in (5,7,10,11,13,14,16)]
    select = ','.join('"' + c + '"' for c in HEADER)
    localized = connection.execute('SELECT ' + select + ' FROM read_parquet(?,file_row_number=true) WHERE ' +
        ' AND '.join('"' + c + '"=?' for c in cols) + ' ORDER BY file_row_number', [str(path)] + reference['localized_key']).fetchall()
    localized_hash = hashlib.sha256(b''.join(encode_row(row) for row in localized)).hexdigest()
    result = dict(reference, q1=q1, q2_presidente=q2, localized_rows=len(localized), localized_sha256=localized_hash)
    require(result == reference, 'resultado de consultas Parquet diverge do Rust/CSV')
    connection.close()
    return result

def validate_parquet(path, expected_sha, expected_bytes, expected_rows, output=None):
    import pyarrow as pa
    import pyarrow.parquet as pq
    table=pq.ParquetFile(path)
    schema=table.schema_arrow
    metadata=schema.metadata
    require(schema.names==HEADER and all(pa.types.is_string(f.type) and not f.nullable for f in schema), 'schema Parquet incompatível')
    require(metadata=={b'urnapack_format':b'bweb-parquet-v1',b'source_member_sha256':expected_sha.encode(),
                      b'encoding':b'latin-1',b'lineterminator':b'CRLF',b'quoting_rule':b'tse-text-columns-v1'}, 'metadata Parquet incompatível')
    require(table.metadata.num_rows==expected_rows<=LIMITS['MAX_CSV_RECORDS'], 'contagem Parquet divergente')
    digest=hashlib.sha256()
    count=total=0
    temporary=None
    stream=None
    try:
        if output:
            target=Path(output)
            require(not os.path.lexists(target),'saída existente recusada')
            target.parent.mkdir(parents=True,exist_ok=True)
            stream=tempfile.NamedTemporaryFile(dir=target.parent,prefix='.urnapack-parquet-',delete=False)
            temporary=Path(stream.name)
        def emit(raw):
            nonlocal total
            total+=len(raw)
            require(total<=expected_bytes<=LIMITS['MAX_SOURCE_FILE_BYTES'],'limite/tamanho de restauração excedido')
            digest.update(raw)
            if stream: stream.write(raw)
        emit(encode_row(HEADER,header=True))
        for batch in table.iter_batches(batch_size=LIMITS['PARQUET_ROW_GROUP_SMALL'],use_threads=False):
            for row in zip(*(batch.column(i).to_pylist() for i in range(len(HEADER)))):
                emit(encode_row(row));count+=1
        require(count==expected_rows and total==expected_bytes and digest.hexdigest()==expected_sha,'SHA-256/contagem de restauração Parquet diverge')
        if stream:
            stream.close();stream=None
            os.link(temporary,output);temporary.unlink();temporary=None
    finally:
        if stream: stream.close()
        if temporary: temporary.unlink(missing_ok=True)
    return {'records':count,'bytes':total,'sha256':digest.hexdigest()}

VIEW_FIELDS={'artifact_kind','format_version','guarantee','kind','source','encoded','codec','dictionary','pack_manifest','decoded_stream'}

def view_filename(obj):
    require(isinstance(obj,dict) and set(obj)=={'file','bytes','sha256'},'campos de objeto inválidos')
    name=obj['file']
    require(isinstance(name,str) and name not in ('','.','..') and Path(name).name==name
            and '/' not in name and '\\' not in name and '\x00' not in name,'caminho de objeto inválido')
    require(type(obj['bytes']) is int and obj['bytes']>=0,'tamanho de objeto inválido')
    return name

def restore_view(descriptor,output,binary):
    descriptor=Path(descriptor)
    view=read_json(descriptor)
    require(set(view)==VIEW_FIELDS and view['artifact_kind']=='bweb_storage_view' and type(view['format_version']) is int and view['format_version']==1,'contrato de view incompatível')
    require(view['guarantee']=='exact-csv-member-bytes','garantia incompatível')
    root=descriptor.resolve().parent
    def checked(obj):
        path=root/view_filename(obj)
        require(not path.is_symlink() and path.is_file() and path.stat().st_size==obj['bytes'] and sha256_file(path)==obj['sha256'],'objeto de view divergente')
        return path
    payload=checked(view['encoded'])
    source=view['source']
    require(set(source)=={'bytes','sha256','records','zip_path','zip_sha256','member_name','member_ordinal'},'campos de proveniência incompatíveis')
    require(type(source['bytes']) is int and type(source['records']) is int and 0<=source['bytes']<=LIMITS['MAX_SOURCE_FILE_BYTES'] and 0<=source['records']<=LIMITS['MAX_CSV_RECORDS'],'limites/tipos da origem inválidos')
    require(isinstance(source['sha256'],str) and len(source['sha256'])==64 and all(c in '0123456789abcdef' for c in source['sha256']),'SHA-256 da origem inválido')
    require(not os.path.lexists(output),'saída existente recusada')
    if view['kind']=='parquet':
        validate_parquet(payload,source['sha256'],source['bytes'],source['records'],output)
    elif view['kind']=='csv-codec':
        command=[binary,'codec','decompress','--input',payload,'--output',output,'--method',view['codec'],
                 '--expected-sha',source['sha256'],'--expected-bytes',str(source['bytes'])]
        if view['dictionary']: command+=['--dictionary',checked(view['dictionary'])]
        subprocess.run([str(a) for a in command],check=True)
    elif view['kind']=='column-stream':
        metadata=checked(view['pack_manifest'])
        m=read_json(metadata)
        require(m['source_member_sha256']==source['sha256'] and m['rows']==source['records'],'proveniência colunar divergente')
        stream=view['decoded_stream']
        with tempfile.TemporaryDirectory(prefix='urnapack-view-') as scratch:
            scratch=Path(scratch)
            raw=scratch/'columns.raw'
            subprocess.run([str(a) for a in [binary,'codec','decompress','--input',payload,'--output',raw,
                '--method',view['codec'],'--expected-sha',stream['sha256'],'--expected-bytes',str(stream['bytes'])]],check=True)
            pack=scratch/'pack';(pack/'columns').mkdir(parents=True)
            shutil.copyfile(metadata,pack/'pack.json')
            with raw.open('rb') as source_file:
                for i,column in enumerate(m['columns']):
                    require(column['file']==f'columns/{i:02}.bin','caminho colunar inválido')
                    remaining=column['bytes']
                    with (pack/column['file']).open('xb') as target:
                        while remaining:
                            chunk=source_file.read(min(remaining,LIMITS['IO_BUFFER_BYTES']))
                            require(bool(chunk),'stream colunar truncado')
                            target.write(chunk);remaining-=len(chunk)
                require(not source_file.read(1),'resíduo no stream colunar')
            subprocess.run([str(a) for a in [binary,'unpack','--input',pack,'--output',output]],check=True,stdout=subprocess.DEVNULL)
    else: raise ValueError('representação de view desconhecida')
    require(Path(output).stat().st_size==source['bytes'] and sha256_file(output)==source['sha256'],'restauração final de view diverge')

def materialize_view(bundle_path,output,binary):
    """Regenera o cache CSV selecionado a partir dos ZIPs preservados no arquivo."""
    from fetch_source import check_rel
    bundle_path=Path(bundle_path).resolve()
    bundle=read_json(bundle_path)
    require(bundle['artifact_kind']=='urnapack_local_bundle' and bundle['format_version']==1,'bundle incompatível')
    root=bundle_path.parent
    def component(ref):
        require(check_rel(ref['relative_file']) is None,'referência de bundle inválida')
        path=root/ref['relative_file']
        require(path.stat().st_size==ref['bytes'] and sha256_file(path)==ref['sha256'],'referência de bundle divergente')
        return path
    descriptor=component(bundle['archive_descriptor'])
    recipe=component(bundle['bweb_view_recipe'])
    view=read_json(recipe)
    require(set(view)==VIEW_FIELDS and view['artifact_kind']=='bweb_storage_view' and type(view['format_version']) is int
            and view['format_version']==1 and view['guarantee']=='exact-csv-member-bytes' and view['kind']=='csv-codec',
            'esta materialização suporta o perfil CSV selecionado; outras representações exigem receita própria')
    view_filename(view['encoded'])
    if view['dictionary']:view_filename(view['dictionary'])
    require(check_rel(view['source']['zip_path']) is None,'caminho ZIP inválido')
    output=Path(output)
    require(not os.path.lexists(output),'materialização existente recusada')
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.urnapack-materialize-',dir=output.parent) as scratch:
        scratch=Path(scratch);raw=scratch/'raw'
        subprocess.run([str(a) for a in [binary,'restore','--dataset',descriptor.parent,'--output',raw]],check=True,stdout=subprocess.DEVNULL)
        zip_path=raw/view['source']['zip_path']
        require(sha256_file(zip_path)==view['source']['zip_sha256'],'ZIP de origem divergente')
        source=scratch/'source.csv'
        expected=view['source']['bytes']
        require(type(expected) is int and 0<=expected<=LIMITS['MAX_SOURCE_FILE_BYTES'],'tamanho de origem inválido')
        with zipfile.ZipFile(zip_path) as archive:
            ordinal=view['source']['member_ordinal']
            require(type(ordinal) is int and 0<=ordinal<len(archive.infolist()),'ordinal ZIP inválido')
            info=archive.infolist()[ordinal]
            require(info.filename==view['source']['member_name'] and info.file_size==expected,'membro ZIP incompatível')
            with archive.open(info) as src,source.open('xb') as dst:
                count=0
                while True:
                    chunk=src.read(min(LIMITS['IO_BUFFER_BYTES'],expected-count+1))
                    if not chunk:break
                    count+=len(chunk);require(count<=expected,'limite do membro ZIP excedido');dst.write(chunk)
        require(source.stat().st_size==expected and sha256_file(source)==view['source']['sha256'],'membro CSV não confere')
        target=scratch/'view';target.mkdir()
        command=[binary,'codec','compress','--input',source,'--output',target/view['encoded']['file'],'--method',view['codec']]
        if view['dictionary']:
            dictionary=root/view['dictionary']['file']
            require(sha256_file(dictionary)==view['dictionary']['sha256'],'dicionário divergente')
            shutil.copyfile(dictionary,target/view['dictionary']['file']);command+=['--dictionary',dictionary]
        subprocess.run([str(a) for a in command],check=True,stdout=subprocess.DEVNULL)
        require(sha256_file(target/view['encoded']['file'])==view['encoded']['sha256'],'encoder atual não reproduz o cache da receita; reavaliar e versionar a materialização')
        shutil.copyfile(recipe,target/'view.json')
        os.rename(target,output)

class Stage:
    def __init__(self, args):
        self.args = args
        self.root = Path(args.output).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.binary = Path(args.binary).resolve()
        self.source = Path(args.csv).resolve()
        self.source_hash = sha256_file(self.source)
        self.raw = Path(args.raw_root).resolve()
        require(not self.root.is_relative_to(self.raw), 'experimento dentro dos brutos recusado')
        self.manifest = Path(args.manifest).resolve()
        self.tar = self.root / 'raw-mt.tar'

    def codec_case(self, name, source, method, dictionary=None):
        folder = self.root / 'cases' / name
        folder.mkdir(parents=True, exist_ok=True)
        report = folder / 'result.json'
        payload = folder / 'payload.encoded'
        source_hash = sha256_file(source)
        if report.exists():
            result = read_json(report)
            require(result['measurement']['round_trip_ok'] is True, 'checkpoint sem round-trip aprovado')
            require(result['measurement']['source_sha256'] == source_hash and result['measurement']['codec'] == method, 'checkpoint de outra entrada/codec')
            require(payload.stat().st_size == result['measurement']['output_bytes'] and sha256_file(payload) == result['measurement']['encoded_sha256'], 'cache corrompido')
            require(result['measurement'].get('dictionary_sha256') == (sha256_file(dictionary) if dictionary else None), 'dicionário do cache diverge')
            command=[self.binary,'codec','check','--input',payload,'--method',method,'--expected-sha',source_hash,
                     '--expected-bytes',str(Path(source).stat().st_size)]
            if dictionary: command+=['--dictionary',dictionary]
            subprocess.run([str(arg) for arg in command],check=True,stdout=subprocess.DEVNULL)
            print('cache conferido:', name, flush=True)
            return result
        require(not payload.exists(), f'artefato órfão: {payload}')
        print('medindo:', name, flush=True)
        command = [self.binary, 'codec', 'compress', '--input', source, '--output', payload, '--method', method]
        if dictionary:
            command += ['--dictionary', dictionary]
        timing = measured(command, folder, 'codec')
        measurement = read_json(timing['stdout'])
        require(measurement['round_trip_ok'] and measurement['source_sha256'] == source_hash, 'conferência do codec incompleta')
        result = {'artifact_kind': 'compression_case', 'format_version': 1,
                  'measurement': measurement, 'process': timing, 'payload': str(payload),
                  'dictionary': str(dictionary) if dictionary else None}
        save(report, result)
        return result

    def raw_phase(self):
        if not self.tar.exists():
            measured([self.binary, 'archive', 'tar', '--input', self.raw, '--manifest', self.manifest, '--output', self.tar], self.root, 'raw-tar')
        results = []
        for method in RAW_SOLID_METHODS:
            results.append(self.codec_case('raw-solid-' + method, self.tar, method))
        per_file = []
        for index, entry in enumerate(read_json(self.manifest)['files']):
            candidates = []
            for method in ('zstd-3','xz-6'):
                candidates.append(self.codec_case(f'raw-file-{index:02}-{method}', self.raw / entry['path'], method))
            per_file.append({'source': entry, 'cases': [str(Path(c['payload']).parent / 'result.json') for c in candidates],
                             'best_payload_bytes': min([entry['size']] + [c['measurement']['output_bytes'] for c in candidates])})
        save(self.root / 'raw-comparison.json', {'format_version': 1, 'complete': True,
             'source_manifest': describe(self.manifest), 'tar': describe(self.tar), 'per_file': per_file,
             'per_file_payload_minimum_bytes': sum(p['best_payload_bytes'] for p in per_file),
             'solid_cases': [str(Path(c['payload']).parent / 'result.json') for c in results]})

    def bweb_phase(self):
        for method in BWEB_METHODS:
            self.codec_case('bweb-' + method, self.source, method)
        report=self.root/'pack-exhaustive.json'
        command=[self.binary,'benchmark','--input',self.args.pack,'--profile','exhaustive','--output',report]
        if report.exists():command+=['--resume']
        measured(command,self.root,'pack-exhaustive-recheck' if report.exists() else 'pack-exhaustive')
        stream=self.root/'columns.raw'
        manifest=read_json(Path(self.args.pack)/'pack.json')
        if not stream.exists():
            temporary=stream.with_name(stream.name+'.partial')
            with temporary.open('xb') as output:
                for column in manifest['columns']:
                    path=Path(self.args.pack)/column['file']
                    require(sha256_file(path)==column['sha256'],'coluna de origem corrompida')
                    with path.open('rb') as source:
                        shutil.copyfileobj(source,output,LIMITS['IO_BUFFER_BYTES'])
            os.rename(temporary,stream)
        for method in COLUMN_METHODS:
            self.codec_case('columns-solid-'+method,stream,method)

    def dictionary_phase(self):
        split = split_dictionary(self.source, self.root / 'dictionary')
        validation = split['parts']['validation']['path']
        test = split['parts']['test']['path']
        sizes = [LIMITS['MAX_DICTIONARY_BYTES'] // n for n in (8,2,1)]
        candidates = []
        for size in sizes:
            dictionary = self.root / 'dictionary' / f'dict-{size}.bin'
            if not dictionary.exists():
                measured([self.binary,'codec','train','--input',split['parts']['train']['path'],
                          '--output',dictionary,'--dictionary-size',str(size)], dictionary.parent, f'train-{size}')
            candidate = self.codec_case(f'dictionary-validation-{size}',validation,'zstd-10',dictionary)
            candidates.append(candidate)
        baseline = self.codec_case('dictionary-validation-baseline',validation,'zstd-10')
        chosen = min(candidates, key=lambda c:c['measurement']['output_bytes'] + c['measurement']['dictionary_bytes'])
        selected = chosen['dictionary']
        self.codec_case('dictionary-test-selected',test,'zstd-10',selected)
        self.codec_case('dictionary-test-baseline',test,'zstd-10')
        full = self.codec_case('bweb-dictionary-selected',self.source,'zstd-10',selected)
        save(self.root / 'dictionary-comparison.json', {'format_version':1,'complete':True,
             'split':split,'selection_metric':'validation encoded bytes + dictionary bytes; level fixed at 10',
             'chosen_dictionary':describe(selected),'validation_baseline':baseline,'validation_chosen':chosen,
             'full_case':str(Path(full['payload']).parent/'result.json'), 'test_used_for_selection':False})

    def parquet_phase(self):
        for group in (LIMITS['PARQUET_ROW_GROUP_SMALL'],LIMITS['PARQUET_ROW_GROUP_LARGE']):
            for level in (3,19):
                folder = self.root/'cases'/f'parquet-g{group}-z{level}'
                folder.mkdir(parents=True,exist_ok=True)
                report = folder/'result.json'
                if report.exists():
                    cached = read_json(report)
                    require(cached['measurement']['source_sha256']==self.source_hash and sha256_file(cached['payload'])==cached['measurement']['encoded_sha256'], 'Parquet cache divergente')
                    continue
                payload = folder/'payload.parquet'
                print('medindo Parquet:',folder.name,flush=True)
                timing = measured([sys.executable,__file__,'worker-parquet','--csv',self.source,'--output',payload,
                                   '--row-group',str(group),'--level',str(level)],folder,'parquet')
                measurement = read_json(timing['stdout'])
                save(report,{'artifact_kind':'compression_case','format_version':1,'measurement':measurement,
                             'process':timing,'payload':str(payload),'dictionary':None})

    def queries_phase(self):
        folder = self.root/'queries'
        folder.mkdir(exist_ok=True)
        reference_path = folder/'reference.json'
        if not reference_path.exists():
            measured([self.binary,'queries','--input',self.source,'--output',reference_path],folder,'reference')
        reference = read_json(reference_path)
        require(reference['source_member_sha256']==self.source_hash, 'consultas de outra origem')
        results = []
        for name, path in [('csv',self.source),('columns',Path(self.args.pack).resolve())]:
            trials = []
            for repetition in range(LIMITS['BENCH_REPETITIONS']):
                output = folder/f'{name}-{repetition}.json'
                if output.exists():
                    require(read_json(output)==reference, 'consultas nativas divergentes')
                    trials.append(read_json(folder/f'{name}-{repetition}.timing.json'))
                    continue
                timing = measured([self.binary,'queries','--input',path,'--output',output],folder,f'{name}-{repetition}')
                require(read_json(output)==reference, 'consultas nativas divergentes')
                save(folder/f'{name}-{repetition}.timing.json',timing)
                trials.append(timing)
            results.append({'representation':name,'trials':trials,'latency':stats([t['wall_ns'] for t in trials]),'equal_to_csv':True})
        for case in sorted((self.root/'cases').glob('parquet-*/result.json')):
            result = read_json(case)
            name = case.parent.name
            trials = []
            for repetition in range(LIMITS['BENCH_REPETITIONS']):
                report = folder/f'{name}-{repetition}.timing.json'
                if report.exists():
                    trials.append(read_json(report));continue
                timing = measured([sys.executable,__file__,'worker-queries','--input',result['payload'],
                        '--reference',reference_path,'--encoded-sha',result['measurement']['encoded_sha256']],folder,f'{name}-{repetition}')
                require(read_json(timing['stdout'])==reference,'consultas Parquet divergentes')
                save(report,timing);trials.append(timing)
            results.append({'representation':name,'trials':trials,'latency':stats([t['wall_ns'] for t in trials]),'equal_to_csv':True})
        save(self.root/'query-comparison.json',{'format_version':1,'complete':True,'reference':describe(reference_path),
             'q1':'QT_VOTOS por cargo/UF/município','q2':'aptos/comparecimento/abstenções por zona, Presidente; contexto igual verificado por seção e contado uma vez',
             'localized':'primeira chave real de seção/cargo; igualdade de todas as ocorrências em ordem',
             'cache_policy':'OS cache not evicted; process startup and integrity checks included', 'results':results})

    def view_candidates(self):
        mapping=read_json(self.args.map)
        profile=next(p for p in mapping['csv_profiles'] if p['family']=='bweb' and p['member_sha256']==self.source_hash)
        origins=read_json(self.manifest)['files']
        require(any(f['path']==profile['source'] and f['sha256']==profile['source_sha256'] for f in origins),'mapa BU não vincula um ZIP do manifesto de origem')
        source={'bytes':self.source.stat().st_size,'sha256':self.source_hash,'records':profile['records'],
                'zip_path':profile['source'],'zip_sha256':profile['source_sha256'],
                'member_name':profile['name'],'member_ordinal':profile['ordinal']}
        manifest_path=Path(self.args.pack)/'pack.json'
        columns=self.root/'columns.raw'
        require(columns.exists(),'falta experimento do fluxo de colunas')
        stream=describe(columns)
        result=[]
        def candidate(name,kind,path,method,measurement=None,dictionary=None):
            actual=describe(path)
            if measurement:
                require(actual['sha256']==measurement['encoded_sha256'] and actual['bytes']==measurement['output_bytes'],'candidato alterado')
            encoded={'file':'payload.parquet' if kind=='parquet' else 'payload.encoded','bytes':actual['bytes'],'sha256':actual['sha256']}
            dictionary_object=None
            if dictionary:
                d=describe(dictionary);dictionary_object={'file':'dictionary.bin','bytes':d['bytes'],'sha256':d['sha256']}
            pack=None
            if kind=='column-stream':
                p=describe(manifest_path);pack={'file':'pack.json','bytes':p['bytes'],'sha256':p['sha256']}
            view={'artifact_kind':'bweb_storage_view','format_version':1,'guarantee':'exact-csv-member-bytes',
                  'kind':kind,'source':source,'encoded':encoded,'codec':method,'dictionary':dictionary_object,
                  'pack_manifest':pack,'decoded_stream':{'bytes':stream['bytes'],'sha256':stream['sha256']} if pack else None}
            metadata_bytes=len((json.dumps(view,ensure_ascii=False,indent=2)+'\n').encode())
            require(metadata_bytes<=LIMITS['MAX_PACK_MANIFEST_BYTES'],'descritor de view excessivo')
            cost=encoded['bytes']+metadata_bytes+(dictionary_object['bytes'] if dictionary_object else 0)+(pack['bytes'] if pack else 0)
            result.append({'name':name,'kind':kind,'total_bytes':cost,'view_descriptor_bytes':metadata_bytes,
                           'view':view,'payload':str(path),'dictionary':dictionary,'measurement':measurement})
        candidate('csv-stored','csv-codec',self.source,'stored')
        for path in sorted((self.root/'cases').glob('*/result.json')):
            case=read_json(path);name=path.parent.name
            m=case['measurement']
            if name.startswith('bweb-'):
                require(m['source_sha256']==self.source_hash,'candidato BU de outra origem')
                candidate(name,'csv-codec',case['payload'],m['codec'],m,case.get('dictionary'))
            elif name.startswith('parquet-'):
                candidate(name,'parquet',case['payload'],None,m)
            elif name.startswith('columns-solid-'):
                require(m['source_sha256']==stream['sha256'],'candidato colunar de outra origem')
                candidate(name,'column-stream',case['payload'],m['codec'],m)
        report=read_json(self.root/'pack-exhaustive.json')
        require(report['complete'] and report['input_bytes']==source['bytes'],'baseline colunar incompleto')
        assets=self.root/'pack-exhaustive.json.assets'
        for m in report['cases']:
            if not m['compressed_file']:continue
            path=assets/m['compressed_file']
            require(sha256_file(path)==m['compressed_sha256'],'artefato colunar alterado')
            method=m['method'].split('zstd-')[-1]
            candidate(m['method'],'column-stream',path,'zstd-'+method)
        return sorted(result,key=lambda c:(c['total_bytes'],c['name']))

    def views_phase(self):
        require(all((self.root/'cases'/('bweb-'+method)/'result.json').exists() for method in BWEB_METHODS),'grid CSV incompleto')
        require(all((self.root/'cases'/f'parquet-g{g}-z{z}'/'result.json').exists() for g in
                    (LIMITS['PARQUET_ROW_GROUP_SMALL'],LIMITS['PARQUET_ROW_GROUP_LARGE']) for z in (3,19)), 'grid Parquet incompleto')
        require(all((self.root/'cases'/('columns-solid-'+method)/'result.json').exists() for method in COLUMN_METHODS), 'grid colunar incompleto')
        candidates=self.view_candidates()
        best=candidates[0]
        folder=self.root/('selected-bweb-'+best['view']['encoded']['sha256'][:16])
        folder.mkdir(exist_ok=True)
        view=best['view']
        for path,obj in [(best['payload'],view['encoded']), (best['dictionary'],view['dictionary']),
                         (Path(self.args.pack)/'pack.json',view['pack_manifest'])]:
            if not obj:continue
            target=folder/obj['file']
            if not target.exists():
                with open(path,'rb') as src,target.open('xb') as dst:shutil.copyfileobj(src,dst,LIMITS['IO_BUFFER_BYTES'])
            require(sha256_file(target)==obj['sha256'],'cópia de view divergente')
        descriptor=folder/'view.json'
        if descriptor.exists():require(read_json(descriptor)==view,'view existente incompatível')
        else:save(descriptor,view)
        require(disk_bytes(folder)==best['total_bytes'],'custo permanente de view incompleto')
        restored=self.root/('selected-view-restored-'+view['encoded']['sha256'][:16]+'.csv')
        if not restored.exists():
            measured([sys.executable,__file__,'restore-view','--input',descriptor,'--output',restored,
                      '--binary',self.binary],self.root/'view-verification','restore')
        require(describe(restored)['sha256']==self.source_hash,'view não recupera a origem')
        repetitions=[]
        for index in range(LIMITS['BENCH_REPETITIONS']):
            old_report=self.root/'view-repetitions'/str(index)/'result.json'
            if old_report.exists():
                old=read_json(old_report)
                if old['selected_encoded_sha256']==view['encoded']['sha256']:
                    repetitions.append(old);continue
            trial=self.root/'view-repetitions'/view['encoded']['sha256'][:16]/str(index)
            trial.mkdir(parents=True,exist_ok=True)
            report=trial/'result.json'
            if report.exists():
                cached=read_json(report)
                require(cached['selected_encoded_sha256']==view['encoded']['sha256'],'repetição de outra view')
                repetitions.append(cached);continue
            payload=trial/'payload.tmp'
            if view['kind']=='parquet':
                m=best['measurement']
                timing=measured([sys.executable,__file__,'worker-parquet','--csv',self.source,'--output',payload,
                    '--row-group',str(m['row_group_rows']),'--level',str(m['level'])],trial,'compress')
            else:
                source=self.source if view['kind']=='csv-codec' else self.root/'columns.raw'
                command=[self.binary,'codec','compress','--input',source,'--output',payload,'--method',view['codec']]
                if best['dictionary']:command+=['--dictionary',best['dictionary']]
                timing=measured(command,trial,'compress')
            measurement=read_json(timing['stdout'])
            require(measurement['round_trip_ok'] and measurement['encoded_sha256']==view['encoded']['sha256'],'repetição não reproduz os bytes selecionados')
            item={'selected_encoded_sha256':view['encoded']['sha256'],'measurement':measurement,'process':timing,'payload_retained':False}
            save(report,item);payload.unlink();repetitions.append(item)
        save(self.root/'view-comparison.json',{'format_version':1,'complete':True,'selection_metric':'payload + dictionary + pack metadata + exact serialized view descriptor bytes',
             'candidates':candidates,'selected':best,'descriptor':describe(descriptor),'restore':describe(restored),
             'repetitions':repetitions,'compression_variation':stats([r['measurement']['compress_ns'] for r in repetitions]),
             'scope':'exact CSV member; raw ZIP is separately retained in the forensic archive; lexical values, all rows and order preserved'})

    def final_phase(self):
        for name in ('raw-comparison.json','dictionary-comparison.json','query-comparison.json','view-comparison.json'):
            require(read_json(self.root/name)['complete'],f'fase incompleta: {name}')
        require(all((self.root/'cases'/('bweb-'+method)/'result.json').exists() for method in BWEB_METHODS),'grid CSV incompleto')
        require(all((self.root/'cases'/('raw-solid-'+method)/'result.json').exists() for method in RAW_SOLID_METHODS),'grid de originais incompleto')
        views=read_json(self.root/'view-comparison.json')
        current=self.view_candidates()
        require(views['selected']['view']==current[0]['view'] and {c['name'] for c in views['candidates']}=={c['name'] for c in current},'decisão de view desatualizada; reexecute views')
        raw=read_json(self.root/'raw-comparison.json')
        files=read_json(self.manifest)['files']
        selection=[]
        for item in raw['per_file']:
            entry=item['source']
            choices=[{'source_path':entry['path'],'codec':'stored','encoded_path':str(self.raw/entry['path']),'bytes':entry['size']}]
            for report in item['cases']:
                c=read_json(report);m=c['measurement']
                require(m['source_sha256']==entry['sha256'] and sha256_file(c['payload'])==m['encoded_sha256'],'candidato de fonte divergente')
                choices.append({'source_path':entry['path'],'codec':m['codec'],'encoded_path':c['payload'],'bytes':m['output_bytes']})
            selection.append(min(choices,key=lambda c:(c['bytes'],c['codec'])))
        selection_path=self.root/'raw-selection.json'
        save(selection_path,{'format_version':1,'source_manifest_sha256':sha256_file(self.manifest),
             'files':[{key:c[key] for key in ('source_path','codec','encoded_path')} for c in selection]})
        solid=[read_json(path) for path in raw['solid_cases']]
        solid_choice=min(solid,key=lambda c:c['measurement']['output_bytes'])
        options=[]
        for name,action,input_path,codec in [('per-file','individual',selection_path,None),
                 ('solid-tar','seal',solid_choice['payload'],solid_choice['measurement']['codec'])]:
            folder=self.root/('archive-candidate-'+name)
            if not folder.exists():
                command=[self.binary,'archive',action,'--input',input_path,'--manifest',self.manifest,'--output',folder]
                if codec:command+=['--codec',codec]
                measured(command,self.root/'archive-verification',name)
            subprocess.run([str(a) for a in [self.binary,'archive','verify','--input',folder]],check=True,stdout=subprocess.DEVNULL)
            options.append({'layout':name,'directory':str(folder),'bytes':disk_bytes(folder),'descriptor':describe(folder/'dataset.json')})
        best=min(options,key=lambda o:(o['bytes'],o['layout']))
        final=self.root/'final'
        final.mkdir(exist_ok=True)
        archive=final/'forensic-mt'
        if not archive.exists():shutil.copytree(best['directory'],archive)
        require(sha256_file(archive/'dataset.json')==best['descriptor']['sha256'],'arquivo final de outra seleção')
        recovered=self.root/'restored-raw-final'
        if not recovered.exists():measured([self.binary,'restore','--dataset',archive,'--output',recovered],self.root/'archive-verification','restore-all')
        measured([self.binary,'verify','--manifest',self.manifest,'--source',recovered],self.root/'archive-verification','restored-vs-origin')
        recovery_trials=[]
        for i in range(LIMITS['BENCH_REPETITIONS']):
            result=self.root/'archive-verification'/f'recovery-{i}.json'
            if result.exists():recovery_trials.append(read_json(result));continue
            timing=measured([self.binary,'archive','verify','--input',archive],self.root/'archive-verification',f'recovery-{i}')
            save(result,timing);recovery_trials.append(timing)
        view=read_json(self.root/'view-comparison.json')
        source_view=Path(view['descriptor']['path']).parent
        recipe=final/'bweb-view-recipe.json'
        if not recipe.exists():shutil.copyfile(source_view/'view.json',recipe)
        require(sha256_file(recipe)==view['descriptor']['sha256'],'receita final divergente')
        selected_view=view['selected']['view']
        if selected_view['dictionary']:
            dictionary=selected_view['dictionary']
            target=final/dictionary['file']
            if not target.exists():shutil.copyfile(source_view/dictionary['file'],target)
            require(sha256_file(target)==dictionary['sha256'],'dicionário da receita divergente')
        provenance=final/'provenance';provenance.mkdir(exist_ok=True)
        preserved=[]
        for name in ('map.json','members.jsonl','run.json'):
            source=Path(self.args.map).resolve().parent/name
            c=self.codec_case('provenance-'+name,source,'zstd-19')
            target=provenance/(name+'.zst')
            if not target.exists():shutil.copyfile(c['payload'],target)
            require(sha256_file(target)==c['measurement']['encoded_sha256'],'proveniência final divergente')
            preserved.append({'source':describe(source),'encoded':dict(describe(target),relative_file='provenance/'+target.name),'codec':'zstd-19'})
        source_bytes=sum(f['size'] for f in files)
        components={'forensic_archive_bytes':disk_bytes(archive),'bweb_view_recipe_bytes':recipe.stat().st_size,
                    'required_dictionary_bytes':selected_view['dictionary']['bytes'] if selected_view['dictionary'] else 0,
                    'provenance_encoded_bytes':disk_bytes(provenance)}
        bundle={'artifact_kind':'urnapack_local_bundle','format_version':1,'scope':read_json(self.args.map)['coverage']['requested'],
                'source_manifest':dict(describe(self.manifest),relative_file='forensic-mt/source-manifest.json'),'source_files':len(files),'original_download_bytes':source_bytes,
                'archive_descriptor':dict(describe(archive/'dataset.json'),relative_file='forensic-mt/dataset.json'),
                'bweb_view_recipe':dict(describe(recipe),relative_file='bweb-view-recipe.json'),
                'optional_materialized_view':{'descriptor':describe(source_view/'view.json'),'bytes':disk_bytes(source_view),'permanent_by_default':False},
                'provenance':preserved,'components':components,
                'guarantees':['all original file paths and bytes, including ZIPs and sidecars','exact BU web CSV member restoration','Q1/Q2/localized results compared with native CSV'],
                'limitations':['local MT corpus only; t2 coverage remains partial as mapped','no authenticity or electoral conclusion','no analytical models or national rollout performed','original downloads retained separately','materialized CSV view is a regenerable optional cache outside the minimum bundle']}
        save(final/'bundle.json',bundle)
        total=disk_bytes(final)
        report={'artifact_kind':'urnapack_compression_stage','format_version':1,'complete':True,
                'scope':bundle['scope'],'source_files':len(files),'source_bytes':source_bytes,'permanent_components':components,
                'final_bundle_bytes':total,'final_bundle':describe(final/'bundle.json'),
                'raw_archive_candidates':options,'selected_raw_archive':best,'selected_bweb':view['selected']['name'],
                'raw_archive_saved_pct':100*(1-components['forensic_archive_bytes']/source_bytes),
                'actual_originals_plus_final_bundle_bytes':source_bytes+total,
                'optional_materialized_view_bytes':disk_bytes(source_view),
                'actual_originals_plus_bundle_plus_optional_cache_bytes':source_bytes+total+disk_bytes(source_view),
                'experiment_retained_bytes_before_stage_report':disk_bytes(self.root),
                'final_bundle_saved_pct':100*(1-total/source_bytes),
                'raw_recovery_repetitions':recovery_trials,'raw_recovery_variation':stats([r['wall_ns'] for r in recovery_trials]),
                'resource_measurement':'RSS process-tree sum sampled at BENCH_POLL_MILLIS; case directory bytes sampled; source input and shared preserved artifacts reported separately; unrelated machine workloads not controlled',
                'experiment_policy':'bounded grid, full corpus per declared candidate; selected CSV compression repeated; archive recovery and Q1/Q2/localized queries repeated; best measured alternative, no absolute compression optimum claimed',
                'source_code_snapshot':{str(p.relative_to(REPO)):sha256_file(p) for p in sorted((REPO/'src').glob('*.rs'))},
                'cargo_lock_sha256':sha256_file(REPO/'Cargo.lock')}
        save(self.root/'stage-report.json',report)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',choices=['raw','bweb','dictionary','parquet','queries','views','final','all','worker-parquet','worker-queries','restore-view','materialize-view'])
    parser.add_argument('--binary',default=str(REPO/'target/release/tsepack'))
    parser.add_argument('--csv')
    parser.add_argument('--raw-root')
    parser.add_argument('--manifest')
    parser.add_argument('--pack')
    parser.add_argument('--map',default=str(REPO/'relatorios-locais/etapa-1/mt/map.json'))
    parser.add_argument('--output')
    parser.add_argument('--input')
    parser.add_argument('--row-group',type=int)
    parser.add_argument('--level',type=int)
    parser.add_argument('--reference')
    parser.add_argument('--encoded-sha')
    args=parser.parse_args()
    if args.phase=='restore-view':
        require(bool(args.output and args.input),'informe --input e --output')
        restore_view(args.input,args.output,args.binary)
        return
    if args.phase=='materialize-view':
        require(bool(args.output and args.input),'informe --input e --output')
        materialize_view(args.input,args.output,args.binary)
        return
    if args.phase=='worker-parquet':
        require(bool(args.output), '--output obrigatório')
        print(json.dumps(parquet_encode(args.csv,args.output,args.row_group,args.level)))
        return
    if args.phase=='worker-queries':
        print(json.dumps(parquet_queries(args.input,read_json(args.reference),args.encoded_sha)))
        return
    require(all((args.csv,args.raw_root,args.manifest,args.pack,args.output)), 'informe --csv --raw-root --manifest --pack --output')
    stage=Stage(args)
    for phase in ('raw','bweb','dictionary','parquet','queries','views','final'):
        if args.phase in (phase,'all'):
            getattr(stage,phase+'_phase')()

if __name__=='__main__':
    try:
        main()
    except (OSError,ValueError,KeyError,TypeError,csv.Error,subprocess.SubprocessError,ModuleNotFoundError) as error:
        print(f'compression_stage: FALHA: {error}',file=sys.stderr)
        sys.exit(1)
