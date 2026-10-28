#!/usr/bin/env python3
"""Mapeador estrutural dos dados brutos (Etapa 1, sem transformação eleitoral).

Inventaria arquivos físicos por varredura (sem lista fixa), cataloga membros
ZIP por fonte+ordinal+nome e perfila CSVs integralmente em streaming
(Latin-1, ';', parser csv real). Binários/PDFs ficam opacos, com amostra
limitada por família para formato mágico. Não extrai caminhos do ZIP, não
expande contêineres recursivamente e não infere tipo só pela extensão.

Limites operacionais vêm de scripts/limits.env (fonte única); limite ou
esquema desconhecido reprova. Saídas determinísticas (map.json, members.jsonl)
separadas de tempos de execução (run.json). Falha não deixa mapa final
marcado como completo; diagnóstico parcial é identificado.
"""

import argparse
from collections import Counter
import csv
import hashlib
import io
import json
import os
import ntpath
import shutil
import stat
import subprocess
import tempfile
import zlib
import platform
import sys
import time
import zipfile
from datetime import datetime, timezone

from validate import sha256_file

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_LIMITS = os.path.join(HERE, "limits.env")

REQUIRED_LIMITS = [
    "MAX_SOURCE_FILE_BYTES",
    "MAX_ZIP_MEMBERS",
    "MAX_ZIP_MEMBER_BYTES",
    "MAX_ZIP_EXPANSION_RATIO",
    "MAX_CSV_RECORDS",
    "MAX_CSV_FIELDS",
    "MAX_FIELD_BYTES",
    "MAX_RECORD_BYTES",
    "MAX_DISTINCT_VALUES_PER_COLUMN",
    "MAX_PROFILE_VALUE_BYTES",
    "MAX_SAMPLE_BYTES",
]

# Cabeçalhos conhecidos em ordem (observados em MT, docs/DADOS-BRUTOS.md).
# Comparação é pelo array completo; variante desconhecida reprova sem
# eliminar campos ou membros. Não usar contagem de campos sozinha.
KNOWN_LAYOUTS = {
    "bweb": [
        "DT_GERACAO", "HH_GERACAO", "ANO_ELEICAO", "CD_TIPO_ELEICAO",
        "NM_TIPO_ELEICAO", "CD_PLEITO", "DT_PLEITO", "NR_TURNO",
        "CD_ELEICAO", "DS_ELEICAO", "SG_UF", "CD_MUNICIPIO",
        "NM_MUNICIPIO", "NR_ZONA", "NR_SECAO", "NR_LOCAL_VOTACAO",
        "CD_CARGO_PERGUNTA", "DS_CARGO_PERGUNTA", "NR_PARTIDO",
        "SG_PARTIDO", "NM_PARTIDO", "DT_BU_RECEBIDO", "QT_APTOS",
        "QT_COMPARECIMENTO", "QT_ABSTENCOES", "CD_TIPO_URNA",
        "DS_TIPO_URNA", "CD_TIPO_VOTAVEL", "DS_TIPO_VOTAVEL",
        "NR_VOTAVEL", "NM_VOTAVEL", "QT_VOTOS", "NR_URNA_EFETIVADA",
        "CD_CARGA_1_URNA_EFETIVADA", "CD_CARGA_2_URNA_EFETIVADA",
        "CD_FLASHCARD_URNA_EFETIVADA", "DT_CARGA_URNA_EFETIVADA",
        "DS_CARGO_PERGUNTA_SECAO", "DS_SECOES_AGREGADAS",
        "DT_ABERTURA", "DT_ENCERRAMENTO",
        "QT_ELEI_BIOM_SEM_HABILITACAO", "DT_EMISSAO_BU",
        "NR_JUNTA_APURADORA", "NR_TURMA_APURADORA",
    ],
    "ceft": [
        "DT_GERACAO", "HH_GERACAO", "AA_ELEICAO", "DT_PLEITO",
        "CD_PLEITO", "SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO",
        "NR_ZONA", "NR_SECAO", "NR_LOCAL_VOTACAO",
        "SQ_CORRESPONDENCIA_ESPERADA", "NR_URNA_ESPERADA",
        "CD_CARGA_URNA_ESPERADA", "CD_CARGA_1_URNA_ESPERADA",
        "CD_CARGA_2_URNA_ESPERADA", "CD_FLASHCARD_URNA_ESPERADA",
        "DT_CARGA_URNA_ESPERADA", "DT_RECBTO_URNA_ESPERADA",
        "SQ_CORRESPONDENCIA_EFETIVADA", "NR_URNA_EFETIVADA",
        "CD_CARGA_URNA_EFETIVADA", "CD_CARGA_1_URNA_EFETIVADA",
        "CD_CARGA_2_URNA_EFETIVADA", "CD_FLASHCARD_URNA_EFETIVADA",
        "DT_CARGA_URNA_EFETIVADA", "DT_RECBTO_URNA_EFETIVADA",
        "CD_ORIGEM_VOTO", "DS_ORIGEM_VOTO", "TP_DIVERGENCIA",
        "NM_MAQUINA_GERACAO_MIDIA", "NR_SRI_TPM_GERACAO_MIDIA",
        "NR_SRI_INSTAL_GERACAO_MIDIA", "NM_MAQUINA_TRANSM_CORRESP",
        "NR_SRI_TPM_TRANSM_CORRESP", "NR_SRI_INSTAL_TRANSM_CORRESP",
    ],
    "csec": [
        "DT_GERACAO", "HH_GERACAO", "AA_ELEICAO", "CD_PLEITO",
        "SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA",
        "NR_SECAO", "NR_LOCAL_VOTACAO", "NR_URNA_ESPERADA",
        "CD_CARGA_URNA_ESPERADA", "CD_FLASHCARD_URNA_ESPERADA",
        "DT_CARGA_URNA_ESPERADA", "ST_CORRESP_ALTERADA",
        "NM_MAQUINA_GERACAO_MIDIA", "NR_SRI_TPM_GERACAO_MIDIA",
        "NR_SRI_INSTAL_GERACAO_MIDIA", "NM_MAQUINA_TRANSM_CORRESP",
        "NR_SRI_TPM_TRANSM_CORRESP", "NR_SRI_INSTAL_TRANSM_CORRESP",
    ],
    "ccont": [
        "DT_GERACAO", "HH_GERACAO", "AA_ELEICAO", "CD_PLEITO",
        "SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA",
        "NR_URNA_ESPERADA", "CD_CARGA_URNA_ESPERADA",
        "CD_FLASHCARD_URNA_ESPERADA", "DT_CARGA_URNA_ESPERADA",
        "ST_CORRESP_ALTERADA", "NM_MAQUINA_GERACAO_MIDIA",
        "NR_SRI_TPM_GERACAO_MIDIA", "NR_SRI_INSTAL_GERACAO_MIDIA",
        "NM_MAQUINA_TRANSM_CORRESP", "NR_SRI_TPM_TRANSM_CORRESP",
        "NR_SRI_INSTAL_TRANSM_CORRESP",
    ],
    "votacao": [
        "DT_GERACAO", "HH_GERACAO", "ANO_ELEICAO", "CD_TIPO_ELEICAO",
        "NM_TIPO_ELEICAO", "NR_TURNO", "CD_ELEICAO", "DS_ELEICAO",
        "DT_ELEICAO", "TP_ABRANGENCIA", "SG_UF", "SG_UE", "NM_UE",
        "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA", "NR_SECAO",
        "CD_CARGO", "DS_CARGO", "NR_VOTAVEL", "NM_VOTAVEL",
        "QT_VOTOS", "NR_LOCAL_VOTACAO", "SQ_CANDIDATO",
        "NM_LOCAL_VOTACAO", "DS_LOCAL_VOTACAO_ENDERECO",
    ],
}

# Colunas de escopo observadas quando presentes (sem inferir ausente).
SCOPE_COLUMNS = [
    "ANO_ELEICAO", "AA_ELEICAO", "NR_TURNO", "CD_ELEICAO",
    "DS_ELEICAO", "CD_PLEITO", "DT_PLEITO", "CD_TIPO_ELEICAO",
    "NM_TIPO_ELEICAO", "TP_ABRANGENCIA", "SG_UF", "SG_UE",
    "NM_UE", "CD_CARGO", "DS_CARGO", "CD_CARGO_PERGUNTA",
    "DS_CARGO_PERGUNTA",
]

# Sentinelas lexicais documentadas (preservadas, sem normalização).
SENTINELS = ["#NULO", "#NULO#", "#NE", "#NE#", "-1", "-3", ""]

METHOD_NAMES = {0: "stored", 8: "deflate"}


class MappingError(Exception):
    """Uma falha impede publicar o mapa; interrompe leituras adicionais."""


def fail(msg, errors):
    errors.append(msg)
    raise MappingError(msg)


def load_limits(path, extra=()):
    if not os.path.isfile(path):
        raise SystemExit(f"limites ausentes: {path}")
    vals = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip()
    required = list(dict.fromkeys([*REQUIRED_LIMITS, *extra]))
    missing = [k for k in required if k not in vals]
    if missing:
        raise SystemExit(f"limite desconhecido/ausente em {path}: {', '.join(missing)}")
    out = {}
    for k in required:
        try:
            out[k] = int(vals[k])
        except ValueError:
            raise SystemExit(f"limite inválido em {path}: {k}={vals[k]!r}")
        if out[k] <= 0:
            raise SystemExit(f"limite inválido em {path}: {k} deve ser > 0")
    return out


def resolve_root(path):
    if os.path.islink(path) or os.path.exists(path):
        pass
    else:
        raise SystemExit(f"raiz inexistente: {path}")
    real = os.path.realpath(path)
    if not os.path.isdir(real):
        raise SystemExit(f"raiz não é diretório: {path}")
    return real


def rel_posix(root_real, abs_path):
    rel = os.path.relpath(abs_path, root_real)
    if rel == ".." or rel.startswith(".." + os.sep):
        raise SystemExit(f"caminho fora da raiz: {abs_path}")
    return rel.replace(os.sep, "/")


def collect_files(root_real, errors):
    found = []

    def onerror(error):
        fail(f"erro de travessia em {error.filename!r}: {error}", errors)

    for dirpath, dirnames, filenames in os.walk(root_real, followlinks=False, onerror=onerror):
        for name in sorted(dirnames + filenames):
            full = os.path.join(dirpath, name)
            rel = rel_posix(root_real, full)
            try:
                rel.encode("utf-8", errors="strict")
            except UnicodeError:
                fail(f"nome não representável sem perda: {rel!r}", errors)
            if validate_zip_name(rel):
                fail(f"caminho físico não canônico: {rel!r}", errors)
            try:
                meta = os.lstat(full)
            except OSError as e:
                fail(f"erro de metadata em {rel}: {e}", errors)
            if stat.S_ISLNK(meta.st_mode):
                fail(f"symlink interno rejeitado: {rel}", errors)
            if stat.S_ISDIR(meta.st_mode):
                continue
            if not stat.S_ISREG(meta.st_mode):
                fail(f"arquivo especial rejeitado: {rel}", errors)
            found.append((full, rel))
        dirnames.sort()
    found.sort(key=lambda t: t[1])
    return found


def fingerprint_header(header):
    blob = json.dumps(header, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def match_family(header):
    hits = [fam for fam, known in KNOWN_LAYOUTS.items() if known == header]
    if len(hits) == 1:
        return hits[0], None
    if len(hits) > 1:
        return None, f"cabeçalho ambíguo entre famílias: {', '.join(sorted(hits))}"
    return None, "cabeçalho desconhecido (variante não documentada)"


def validate_zip_name(name):
    if not name or "\x00" in name:
        return "nome vazio ou NUL no diretório central"
    if name.startswith(("/", "\\")) or ntpath.splitdrive(name)[0]:
        return f"caminho absoluto no ZIP: {name}"
    if "\\" in name:
        return f"separador inválido no ZIP: {name}"
    parts = name[:-1].split("/") if name.endswith("/") else name.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return f"travessia ou caminho não canônico no ZIP: {name}"
    return None


class HashingReader(io.RawIOBase):
    """Proxy binário que acumula SHA-256 de todos os bytes lidos."""

    def __init__(self, raw):
        self._raw = raw
        self._hash = hashlib.sha256()
        self.total = 0

    def readable(self):
        return True

    def readinto(self, b):
        data = self._raw.read(len(b))
        n = len(data) if data else 0
        if n:
            b[:n] = data
            self._hash.update(data)
            self.total += n
        return n

    def hexdigest(self):
        return self._hash.hexdigest()


def opaque_sample_kind(name):
    low = name.lower()
    if low.endswith(".pdf"):
        return "pdf"
    if low.endswith(".jez"):
        return "jez"
    if low.endswith(".vsc"):
        return "vsc"
    if low.endswith(".dat"):
        if "-bu.dat" in low or low.endswith("_bu.dat") or "-bu." in low:
            return "bu_dat"
        if "-rdv.dat" in low:
            return "rdv_dat"
        if "imgbu" in low:
            return "imgbu_dat"
        return "dat"
    return "outro"


OUTPUT_FILES = ("map.json", "members.jsonl", "report.md", "run.json", "diagnostic.partial.json")


def main(argv=None):
    t_start = time.time()
    ap = argparse.ArgumentParser(description="Mapa estrutural dos brutos (Etapa 1).")
    ap.add_argument("--source", required=True)
    ap.add_argument("--year", required=True, type=int)
    ap.add_argument("--scope", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args(argv)
    limits_path = os.environ.get("URNAPACK_LIMITS_FILE", DEFAULT_LIMITS)
    source_real = os.path.realpath(args.source)
    out_real = os.path.realpath(args.output)
    staging = None
    output_ready = False
    try:
        # Resolve aliases antes de qualquer escrita; ambas as árvores devem ser separadas.
        common = os.path.commonpath((source_real, out_real))
        if common in (source_real, out_real):
            raise MappingError("fonte e saída devem ser árvores separadas (saída dentro da fonte recusada)")
        os.makedirs(out_real, exist_ok=True)
        for filename in OUTPUT_FILES:
            target = os.path.join(out_real, filename)
            if os.path.lexists(target) and (os.path.islink(target) or not os.path.isfile(target)):
                raise MappingError(f"destino de artefato não é arquivo regular: {filename}")
        # Preserva a geração anterior e retira primeiro seu marcador de conclusão.
        existing = [fn for fn in OUTPUT_FILES if os.path.exists(os.path.join(out_real, fn))]
        if existing:
            previous = tempfile.mkdtemp(prefix=".previous-", dir=out_real)
            for filename in existing:
                os.replace(os.path.join(out_real, filename), os.path.join(previous, filename))
        output_ready = True
        try:
            root_real = resolve_root(args.source)
            limits = load_limits(limits_path)
        except SystemExit as e:
            raise MappingError(str(e)) from e
        staging = tempfile.mkdtemp(prefix=".staging-", dir=out_real)
        map_obj = build_map(args, limits, root_real, staging, limits_path)
        write_json(os.path.join(staging, "map.json"), map_obj)
        with open(os.path.join(staging, "report.md"), "w", encoding="utf-8", newline="\n") as stream:
            stream.write(build_report(map_obj))
        # O recibo também deve ter sido escrito com sucesso antes da publicação.
        write_run(staging, args, t_start, True, 0)
        for filename in ("members.jsonl", "report.md", "run.json", "map.json"):
            # map.json é publicado por último, como marcador da geração completa.
            os.replace(os.path.join(staging, filename), os.path.join(out_real, filename))
        print(f"map_raw_data: OK ({len(map_obj['sources'])} arquivos, "
              f"{map_obj['coverage']['members_cataloged']} membros, "
              f"{len(map_obj['csv_profiles'])} CSVs)")
        return 0
    except (MappingError, OSError, ValueError, RuntimeError, EOFError,
            zipfile.BadZipFile, NotImplementedError, zlib.error) as e:
        print(f"ERRO: {e}", file=sys.stderr)
        if output_ready:
            # Nunca deixar um mapa completo da tentativa que falhou.
            try:
                os.unlink(os.path.join(out_real, "map.json"))
            except FileNotFoundError:
                pass
            except OSError as cleanup_error:
                print(f"ERRO: invalidar mapa: {cleanup_error}", file=sys.stderr)
            try:
                write_json(os.path.join(out_real, "diagnostic.partial.json"), {
                    "artifact_kind": "raw_structure_map", "format_version": 1,
                    "status": "incomplete", "errors": [str(e)],
                })
                write_run(out_real, args, t_start, False, 1)
            except OSError as write_error:
                print(f"ERRO: escrever diagnóstico/recibo: {write_error}", file=sys.stderr)
        return 1
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)


def write_json(path, value):
    with open(path, "w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")


def build_map(args, limits, root_real, staging, limits_path):
    errors = []
    files = collect_files(root_real, errors)

    # Inventário físico.
    sources = []
    zip_targets = []  # (full, rel, sha, size)
    for full, rel in files:
        try:
            size = os.path.getsize(full)
        except OSError as e:
            fail(f"erro de metadata em {rel}: {e}", errors)
            continue
        if size > limits["MAX_SOURCE_FILE_BYTES"]:
            fail(f"limite excedido: {rel} com {size} bytes > MAX_SOURCE_FILE_BYTES", errors)
            continue
        try:
            sha = sha256_file(full)
        except OSError as e:
            fail(f"erro de leitura em {rel}: {e}", errors)
            continue
        try:
            with open(full, "rb") as f:
                magic = f.read(4)
        except OSError as e:
            fail(f"erro de leitura em {rel}: {e}", errors)
            continue
        magic_hex = magic.hex()
        is_zip_ext = rel.lower().endswith(".zip")
        is_zip_magic = magic in (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
        if is_zip_ext and not is_zip_magic:
            # Arquivo .zip sem assinatura ZIP: diagnóstico e reprovação.
            # Amostra de .jez com assinatura ZIP é tratada no membro, não aqui.
            fail(f"assinatura incompatível com extensão .zip: {rel} (magia {magic_hex})", errors)
        kind = "zip" if (is_zip_magic) else (
            "sidecar" if rel.lower().endswith(".sha512") else "outro")
        sources.append({
            "path": rel, "size": size, "sha256": sha,
            "magic_hex": magic_hex, "kind": kind,
        })
        if kind == "zip":
            zip_targets.append((full, rel, sha, size))
    sources.sort(key=lambda s: s["path"])

    members_path_staged = os.path.join(staging, "members.jsonl")
    with open(members_path_staged, "w", encoding="utf-8", newline="\n") as members_f:
        members_count = 0
        csv_profiles = []
        opaque_samples = {}  # kind -> sample info
        opaque_counts = 0
        dir_counts = 0
        scope_overall = {}
        scope_value_bytes = 0
        families_seen = set()
    
        def write_member(obj):
            nonlocal members_count
            line = json.dumps(obj, ensure_ascii=False, sort_keys=True)
            members_f.write(line + "\n")
            members_count += 1
    
        for full, rel, src_sha, src_size in sorted(zip_targets, key=lambda t: t[1]):
            try:
                zf = zipfile.ZipFile(full, "r")
            except zipfile.BadZipFile as e:
                fail(f"ZIP inválido: {rel}: {e}", errors)
                continue
            except OSError as e:
                fail(f"erro de leitura em {rel}: {e}", errors)
                continue
            with zf:
                try:
                    infos = zf.infolist()
                except (zipfile.BadZipFile, RuntimeError, OSError) as e:
                    fail(f"erro no diretório central de {rel}: {e}", errors)
                    continue
                if len(infos) > limits["MAX_ZIP_MEMBERS"]:
                    fail(f"limite excedido: {rel} com {len(infos)} membros > MAX_ZIP_MEMBERS", errors)
                    # Ainda cataloga metadados até o limite? Não: registra diagnóstico
                    # e segue sem leitura integral para não mascarar o excesso.
                    continue
                # Soma de expansão.
                try:
                    declared_sum = sum(i.file_size for i in infos)
                except Exception as e:  # noqa: BLE001
                    fail(f"erro em tamanhos declarados de {rel}: {e}", errors)
                    continue
                if src_size > 0 and declared_sum > src_size * limits["MAX_ZIP_EXPANSION_RATIO"]:
                    fail(f"limite excedido: expansão em {rel} ({declared_sum}/{src_size})", errors)
                seen_names = set()
                for ordinal, info in enumerate(infos):
                    name = info.filename
                    if info.orig_filename != name:
                        fail(f"nome de membro truncado em {rel} ordinal {ordinal}: {info.orig_filename!r}", errors)
                    unsafe = validate_zip_name(name)
                    if unsafe:
                        fail(f"caminho inseguro em {rel} ordinal {ordinal}: {unsafe}", errors)
                    if name in seen_names:
                        fail(f"nome duplicado em {rel}: {name!r} (ordinal {ordinal})", errors)
                        # Preserva a ocorrência: cataloga mesmo assim, sem escolher.
                    else:
                        seen_names.add(name)
                    is_dir = name.endswith("/")
                    ext = ""
                    if not is_dir and "." in name.rsplit("/", 1)[-1]:
                        ext = "." + name.rsplit(".", 1)[-1].lower()
                    method = METHOD_NAMES.get(info.compress_type, f"m{info.compress_type}")
                    base = {
                        "source": rel,
                        "source_sha256": src_sha,
                        "ordinal": ordinal,
                        "name": name,
                        "method": method,
                        "compress_type": info.compress_type,
                        "flag_bits": info.flag_bits,
                        "declared_size": info.file_size,
                        "declared_compress_size": info.compress_size,
                        "declared_crc": f"{info.CRC & 0xffffffff:08x}",
                        "extension": ext,
                    }
                    if is_dir:
                        dir_counts += 1
                        base.update({"observed_kind": "dir", "read_level": "metadata_only",
                                     "member_sha256": None})
                        # Erro inseguro já registrado acima, se houver.
                        write_member(base)
                        continue
                    if info.file_size > limits["MAX_ZIP_MEMBER_BYTES"]:
                        fail(f"limite excedido: {rel}#{ordinal} {name} "
                             f"({info.file_size} bytes > MAX_ZIP_MEMBER_BYTES)", errors)
                        base.update({"observed_kind": "opaque_grande",
                                     "read_level": "metadata_only", "member_sha256": None})
                        write_member(base)
                        continue
                    if ext == ".csv":
                        profile = profile_csv_member(zf, info, ordinal, rel, src_sha, limits, errors)
                        base.update({
                            "observed_kind": "csv",
                            "read_level": profile["read_level"],
                            "member_sha256": profile["member_sha256"],
                        })
                        write_member(base)
                        csv_profiles.append(profile)
                        families_seen.add(profile.get("family") or "unknown")
                        # Escopos agregados por família (documental, sem descartar misto).
                        for k, detail in profile.get("scopes", {}).items():
                            values = scope_overall.setdefault(k, set())
                            for value in detail.get("values", []):
                                if value not in values:
                                    scope_value_bytes += len(value.encode("utf-8"))
                                    if scope_value_bytes > limits["MAX_PROFILE_VALUE_BYTES"]:
                                        fail("limite excedido: escopos agregados > MAX_PROFILE_VALUE_BYTES", errors)
                                    values.add(value)
                            if len(scope_overall[k]) > limits["MAX_DISTINCT_VALUES_PER_COLUMN"]:
                                fail(f"limite excedido: escopos agregados de {k} > MAX_DISTINCT_VALUES_PER_COLUMN", errors)
                        continue
                    # Opaco: amostra determinística por família, demais só metadados.
                    kind = opaque_sample_kind(name)
                    opaque_counts += 1
                    if kind not in opaque_samples:
                        # Amostra limitada para formato mágico.
                        try:
                            with zf.open(info, "r") as mf:
                                sample = mf.read(limits["MAX_SAMPLE_BYTES"])
                            truncated = info.file_size > len(sample)
                            magic_hex = sample[:4].hex() if sample else ""
                            observed = "desconhecido"
                            if magic_hex.startswith("25504446"):
                                observed = "pdf (%PDF)"
                            elif sample[:4] == b"PK\x03\x04":
                                observed = "zip-aninhado (não expandido; pendência)"
                            elif magic_hex:
                                observed = f"opaco (magia {magic_hex})"
                            opaque_samples[kind] = {
                                "kind": kind, "source": rel, "ordinal": ordinal,
                                "name": name, "sample_bytes": len(sample),
                                "truncated_sample": truncated,
                                "magic_hex": magic_hex, "observed": observed,
                            }
                            base.update({"observed_kind": opaque_kind_label(name, observed),
                                         "read_level": "sampled", "member_sha256": None,
                                         "sample_bytes": len(sample), "magic_hex": magic_hex})
                        except (zipfile.BadZipFile, RuntimeError, OSError) as e:
                            fail(f"erro de leitura em {rel}#{ordinal} {name}: {e}", errors)
                            base.update({"observed_kind": "opaque",
                                         "read_level": "metadata_only", "member_sha256": None})
                    else:
                        base.update({"observed_kind": "opaque",
                                     "read_level": "metadata_only", "member_sha256": None})
                    write_member(base)
    # Hash do catálogo finalizado, sem buffering pendente.
    members_sha = sha256_file(members_path_staged)

    # Normaliza escopos para listas ordenadas (determinístico).
    scopes_sorted = {k: sorted(v) for k, v in sorted(scope_overall.items())}

    limitations = [
        "Observação: mapa estrutural, sem transformação eleitoral e sem equivalência semântica.",
        "Documentação: leia-mes declaram Latin-1 e ';'; prevalece o contrato por fonte.",
        "Hipótese: segmentação de <identificacao> em arquivos da urna não validada.",
        "Verificação: SHA-256 dos arquivos físicos recomputado; CRC do ZIP não substitui SHA-256.",
        "Pasta/turno no nome não prova o turno de cada membro (ex.: PDFs de T2 sob pasta t1).",
        "Ausência de sidecar/hash oficial é limitação, não prova de ausência ou autoria.",
    ]
    if "jez" in opaque_samples:
        limitations.append("Amostra .jez: " + opaque_samples["jez"]["observed"] +
                           "; conteúdo interno não examinado nesta execução.")
    # Divergência de recorte solicitado: documentar, sem descartar.
    req_year = str(args.year)
    years_seen = set(scopes_sorted.get("ANO_ELEICAO", []) + scopes_sorted.get("AA_ELEICAO", []))
    if years_seen and years_seen != {req_year}:
        limitations.append(
            f"Observação: ano solicitado {args.year} diverge dos anos observados {sorted(years_seen)}; "
            "conteúdo mantido, sem descarte para forçar concordância.")
    scopes_uf = set(scopes_sorted.get("SG_UF", []))
    if scopes_uf and scopes_uf != {args.scope}:
        limitations.append(
            f"Observação: escopo solicitado {args.scope} diverge dos SG_UF observados {sorted(scopes_uf)}; "
            "conteúdo mantido.")

    status = "complete" if not errors else "incomplete"
    map_obj = {
        "artifact_kind": "raw_structure_map",
        "format_version": 1,
        "status": status,
        "params": {
            "source": args.source,
            "year": args.year,
            "scope": args.scope,
            "limits_file": os.path.basename(limits_path),
            "limits": limits,
        },
        "sources": sources,
        "csv_profiles": csv_profiles,
        "opaque_samples": [opaque_samples[k] for k in sorted(opaque_samples)],
        "coverage": {
            "requested": {"year": args.year, "scope": args.scope},
            "files_found": len(files),
            "files_read": len(sources),
            "zip_sources": len(zip_targets),
            "members_cataloged": members_count,
            "csv_members": len(csv_profiles),
            "opaque_members": opaque_counts,
            "dir_entries": dir_counts,
            "families_seen": sorted(families_seen),
            "scopes_observed": scopes_sorted,
        },
        "limitations": limitations,
        "diagnostics": errors,
        "members_file": "members.jsonl",
        "members_sha256": members_sha,
    }

    return map_obj


def opaque_kind_label(name, observed):
    low = name.lower()
    if low.endswith(".pdf"):
        return "pdf_opaco"
    if low.endswith(".jez"):
        return "jez_opaco"
    if low.endswith(".vsc"):
        return "assinatura_opaca"
    if low.endswith(".dat"):
        return "binario_opaco"
    return "opaco"


class CsvLines:
    """Limita os bytes lexicais de um registro antes de construir a linha CSV."""

    def __init__(self, text, maximum):
        self.text = text
        self.maximum = maximum
        self.record_bytes = 0
        self.endings = Counter()

    def __iter__(self):
        return self

    def __next__(self):
        line = self.text.readline(self.maximum - self.record_bytes + 1)
        if not line:
            raise StopIteration
        self.record_bytes += len(line)  # Latin-1: um caractere por byte original.
        if self.record_bytes > self.maximum:
            raise MappingError("limite excedido: registro lexical > MAX_RECORD_BYTES")
        ending = ("CRLF" if line.endswith("\r\n") else "LF" if line.endswith("\n")
                  else "CR" if line.endswith("\r") else "unterminated")
        self.endings[ending] += 1
        return line

    def start_record(self):
        self.record_bytes = 0


def profile_csv_member(zf, info, ordinal, source_rel, source_sha, limits, errors):
    location = f"{source_rel}#{ordinal} {info.filename}"
    old_field_limit = csv.field_size_limit()
    try:
        csv.field_size_limit(limits["MAX_FIELD_BYTES"])
        with zf.open(info, "r") as raw:
            hashing = HashingReader(raw)
            with io.TextIOWrapper(io.BufferedReader(hashing), encoding="latin-1", newline="") as text:
                lines = CsvLines(text, limits["MAX_RECORD_BYTES"])
                reader = csv.reader(lines, delimiter=";", quotechar='"', doublequote=True, strict=True)
                try:
                    header = next(reader)
                except StopIteration:
                    fail(f"CSV vazio em {location}", errors)
                if len(header) > limits["MAX_CSV_FIELDS"]:
                    fail(f"limite excedido: {location} > MAX_CSV_FIELDS", errors)
                if len(set(header)) != len(header):
                    fail(f"cabeçalho duplicado em {location}", errors)
                family, family_error = match_family(header)
                if family_error:
                    fail(f"{family_error} em {location}: {header}", errors)
                scope_idx = {col: header.index(col) for col in SCOPE_COLUMNS if col in header}
                scope_counts = {col: Counter() for col in scope_idx}
                sentinel_counts = {col: Counter() for col in header}
                sentinel_set = set(SENTINELS)
                records = 0
                scope_value_bytes = 0
                while True:
                    lines.start_record()
                    try:
                        row = next(reader)
                    except StopIteration:
                        break
                    records += 1
                    if records > limits["MAX_CSV_RECORDS"]:
                        fail(f"limite excedido: {location} > MAX_CSV_RECORDS", errors)
                    if len(row) != len(header):
                        fail(f"divergência de campos em {location} registro {records} "
                             f"linha {reader.line_num}: {len(row)} vs {len(header)}", errors)
                    for col, idx in scope_idx.items():
                        val = row[idx]
                        counts = scope_counts[col]
                        if val not in counts and len(counts) >= limits["MAX_DISTINCT_VALUES_PER_COLUMN"]:
                            fail(f"limite excedido: distintos de {col} em {location} > MAX_DISTINCT_VALUES_PER_COLUMN", errors)
                        if val not in counts:
                            scope_value_bytes += len(val.encode("utf-8"))
                            if scope_value_bytes > limits["MAX_PROFILE_VALUE_BYTES"]:
                                fail(f"limite excedido: escopos de {location} > MAX_PROFILE_VALUE_BYTES", errors)
                        counts[val] += 1
                    for col, val in zip(header, row):
                        if val in sentinel_set:
                            sentinel_counts[col][val] += 1
                # O parser chegou ao EOF sem erro; o ZipExtFile verificou seu CRC.
                if hashing.total != info.file_size:
                    fail(f"tamanho lido diverge do declarado em {location}", errors)
                return {
                    "source": source_rel, "source_sha256": source_sha,
                    "ordinal": ordinal, "name": info.filename, "family": family,
                    "header": header, "header_fields": len(header),
                    "header_fingerprint": fingerprint_header(header),
                    "records": records, "field_divergences": [], "field_divergence_count": 0,
                    "scopes": {col: {"distinct": len(counts), "values": sorted(counts),
                                     "counts": dict(sorted(counts.items())), "truncated": False}
                               for col, counts in scope_counts.items()},
                    "sentinels": {col: dict(sorted(counts.items()))
                                  for col, counts in sentinel_counts.items() if counts},
                    "member_sha256": hashing.hexdigest(), "member_bytes_read": hashing.total,
                    "line_endings": dict(sorted(lines.endings.items())),
                    "read_level": "fully_read",
                }
    except MappingError as e:
        raise MappingError(f"{location}: {e}") from e
    except (csv.Error, OSError, EOFError, zipfile.BadZipFile, RuntimeError, zlib.error) as e:
        fail(f"erro de CSV/leitura em {location}: {e}", errors)
    finally:
        csv.field_size_limit(old_field_limit)


def build_report(m):
    cov = m["coverage"]
    lines = []
    lines.append("# Mapa estrutural — dados brutos\n")
    lines.append(f"Recorte solicitado: ano={cov['requested']['year']} escopo={cov['requested']['scope']}.")
    lines.append(f"Estado: {m['status']}. Formato do mapa: {m['artifact_kind']} v{m['format_version']}.")
    lines.append("")
    lines.append("## Observações (verificadas nesta execução)")
    lines.append(f"- Arquivos físicos lidos: {cov['files_read']} (encontrados: {cov['files_found']}).")
    lines.append(f"- Fontes ZIP: {cov['zip_sources']}; membros catalogados: {cov['members_cataloged']} "
                 f"(CSV: {cov['csv_members']}, opacos: {cov['opaque_members']}, dirs: {cov['dir_entries']}).")
    lines.append(f"- Famílias CSV vistas: {', '.join(cov['families_seen']) or 'nenhuma'}.")
    lines.append("- SHA-256 dos arquivos físicos recomputado dos bytes; "
                 "CRC do ZIP não substitui SHA-256 nem prova autoria.")
    lines.append("")
    lines.append("## Layouts CSV (cabeçalhos em ordem, fingerprints)")
    for p in m["csv_profiles"]:
        lines.append(f"- `{p['name']}` (fonte `{p['source']}` #{p['ordinal']}): "
                     f"família={p['family'] or 'unknown'}, "
                     f"campos={p['header_fields']}, registros={p['records']}, "
                     f"fingerprint={p['header_fingerprint'][:16]}…, "
                     f"sha_membro={ (p['member_sha256'] or 'null')[:16]}…")
    lines.append("")
    lines.append("## Escopos observados (conteúdo misto documentado, sem descarte)")
    for k, vals in cov["scopes_observed"].items():
        shown = ", ".join(vals[:20]) + ("…" if len(vals) > 20 else "")
        lines.append(f"- {k}: {len(vals)} distinto(s): {shown}")
    lines.append("")
    lines.append("## Amostras opacas (formato mágico, sem decoder novo)")
    for s in m["opaque_samples"]:
        lines.append(f"- {s['kind']} `{s['name']}` ({s['source']} #{s['ordinal']}): "
                     f"{s['observed']}, bytes lidos={s['sample_bytes']}")
    lines.append("")
    lines.append("## Documentação (contratos por fonte)")
    lines.append("- CSVs: Latin-1, ';', parser csv real com aspas; strings preservadas, sem cast.")
    lines.append("- Leia-mes internos vinculam layout à versão; capa de PDF indica turno do relatório, "
                 "não dos BUs/RDVs/logs por seção.")
    lines.append("")
    lines.append("## Hipóteses (não verificadas)")
    lines.append("- Segmentação de <identificacao> em arquivos da urna segue hipótese, sem confronto.")
    lines.append("- Gerações CESP/CEFT são snapshots preservados; concatenação como série exige prova.")
    lines.append("")
    lines.append("## Limitações e pendências")
    for lim in m["limitations"]:
        lines.append(f"- {lim}")
    if m["diagnostics"]:
        lines.append("")
        lines.append("## Diagnóstico (falhas explícitas)")
        for e in m["diagnostics"][:50]:
            lines.append(f"- {e}")
    lines.append("")
    lines.append(f"Membros: `members.jsonl` (SHA-256 {m['members_sha256']}). "
                 "Tempos e ambiente em `run.json`.")
    lines.append("")
    return "\n".join(lines)


def write_run(out_abs, args, t_start, ok, n_errors):
    run = {
        "command": [sys.executable, "scripts/map_raw_data.py", "--source", args.source,
                    "--year", str(args.year), "--scope", args.scope, "--output", args.output],
        "python": platform.python_version(),
        "platform": platform.platform(),
        "started_at": datetime.fromtimestamp(t_start, tz=timezone.utc).isoformat(),
        "finished_at": datetime.now(tz=timezone.utc).isoformat(),
        "elapsed_ms": int((time.time() - t_start) * 1000),
        "success": ok,
        "errors": n_errors,
    }
    run["script_sha256"] = sha256_file(__file__)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE, capture_output=True, text=True)
    run["git_commit"] = commit.stdout.strip() if commit.returncode == 0 else None
    write_json(os.path.join(out_abs, "run.json"), run)


if __name__ == "__main__":
    sys.exit(main())
