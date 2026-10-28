#!/usr/bin/env python3
"""Validador executável da BU web contra o esquema canônico v1 (Etapa 2).

Streaming (Latin-1, ';', parser csv real), sem transformar nem deduplicar:
cabeçalho exato em ordem, padrões lexicais, domínios MT-2026, consistências
cruzadas, regra aritmética do contexto, unicidade da chave de ocorrência
(duplicatas listadas com ordinal, nunca removidas) e sentinelas por coluna.
Divergência reprova com exit ≠ 0. Limites em scripts/limits.env.
"""

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from map_raw_data import KNOWN_LAYOUTS, HashingReader, CsvLines, MappingError  # noqa: E402 — cabeçalho canônico único

HEADER = KNOWN_LAYOUTS["bweb"]
FAMILY = "bweb"

REQUIRED_LIMITS = [
    "MAX_CSV_FIELDS",
    "MAX_FIELD_BYTES",
    "MAX_RECORD_BYTES",
    "MAX_CSV_RECORDS",
    "MAX_BWEB_OCCURRENCE_KEYS",
    "MAX_BWEB_DUPLICATE_EVIDENCE",
]

DATE_BR = re.compile(r"^\d{2}/\d{2}/\d{4}$")
TIME = re.compile(r"^\d{2}:\d{2}:\d{2}$")
DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
UINT = re.compile(r"^\d+$")
SINT = re.compile(r"^-?\d+$")
DOTTED = re.compile(r"^[\d.]+$")
HEXISH = re.compile(r"^[0-9A-Fa-f]+$")

# Regras por coluna: (padrão, ou None para texto livre).
PATTERNS = {c: None for c in HEADER}
for c in ("ANO_ELEICAO",):
    PATTERNS[c] = r"^\d{4}$"
PATTERNS["DT_GERACAO"] = DATE_BR.pattern
PATTERNS["HH_GERACAO"] = TIME.pattern
for c in ("DT_PLEITO", "DT_BU_RECEBIDO", "DT_CARGA_URNA_EFETIVADA",
          "DT_ABERTURA", "DT_ENCERRAMENTO", "DT_EMISSAO_BU"):
    PATTERNS[c] = DATETIME.pattern
for c in ("QT_APTOS", "QT_COMPARECIMENTO", "QT_ABSTENCOES", "QT_VOTOS",
          "QT_ELEI_BIOM_SEM_HABILITACAO"):
    PATTERNS[c] = UINT.pattern
for c in ("NR_ZONA", "NR_SECAO", "NR_LOCAL_VOTACAO", "NR_VOTAVEL",
          "NR_URNA_EFETIVADA", "NR_JUNTA_APURADORA", "NR_TURMA_APURADORA",
          "CD_MUNICIPIO", "NR_PARTIDO"):
    PATTERNS[c] = SINT.pattern
PATTERNS["CD_CARGA_1_URNA_EFETIVADA"] = DOTTED.pattern
PATTERNS["CD_CARGA_2_URNA_EFETIVADA"] = DOTTED.pattern
PATTERNS["CD_FLASHCARD_URNA_EFETIVADA"] = HEXISH.pattern
COMPILED = {c: (re.compile(p) if p else None) for c, p in PATTERNS.items()}

# Domínios MT-2026 (nível 2). None = sem restrição além do padrão.
DOMAINS = {c: None for c in HEADER}
DOMAINS.update({
    "DT_GERACAO": {"05/10/2026"},
    "HH_GERACAO": {"14:03:43"},
    "ANO_ELEICAO": {"2026"},
    "CD_TIPO_ELEICAO": {"0"},
    "NM_TIPO_ELEICAO": {"Eleição Ordinária"},
    "CD_PLEITO": {"3220"},
    "DT_PLEITO": {"2026-10-04 00:00:00"},
    "NR_TURNO": {"1"},
    "CD_ELEICAO": {"6257", "6259"},
    "SG_UF": {"MT"},
    "CD_CARGO_PERGUNTA": {"1", "3", "5", "6", "7"},
    "CD_TIPO_URNA": {"1"},
    "DS_TIPO_URNA": {"Apurada"},
    "CD_TIPO_VOTAVEL": {"1", "2", "3", "4"},
})
CONSISTENT = {
    "CD_ELEICAO": ("DS_ELEICAO", {"6257": "Eleição Geral Federal 2026",
                                  "6259": "Eleições Gerais Estaduais 2026"}),
    "CD_CARGO_PERGUNTA": ("DS_CARGO_PERGUNTA", {"1": "Presidente", "3": "Governador",
                                                "5": "Senador", "6": "Deputado Federal",
                                                "7": "Deputado Estadual"}),
    "CD_TIPO_VOTAVEL": ("DS_TIPO_VOTAVEL", {"1": "Nominal", "2": "Branco",
                                            "3": "Nulo", "4": "Legenda"}),
    "CD_TIPO_URNA": ("DS_TIPO_URNA", {"1": "Apurada"}),
}

KEY_COLS = ["CD_PLEITO", "NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NR_ZONA",
            "NR_SECAO", "CD_CARGO_PERGUNTA", "NR_VOTAVEL"]
SENTINELS = {"#NULO", "#NULO#", "#NE", "#NE#", "-1", "-3", ""}


def fail(msg, errors):
    errors.append(msg)
    return errors


def load_limits(path):
    vals = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip()
    missing = [k for k in REQUIRED_LIMITS if k not in vals]
    if missing:
        raise SystemExit(f"limite desconhecido/ausente em {path}: {', '.join(missing)}")
    out = {}
    for k in REQUIRED_LIMITS:
        try:
            out[k] = int(vals[k])
        except ValueError:
            raise SystemExit(f"limite inválido em {path}: {k}={vals[k]!r}")
        if out[k] <= 0:
            raise SystemExit(f"limite inválido em {path}: {k} deve ser > 0")
    return out


def open_text(source_zip, member, source_csv):
    if source_zip:
        zf = zipfile.ZipFile(source_zip, "r")
        try:
            info = zf.getinfo(member)
        except KeyError:
            zf.close()
            raise ValueError(f"membro ausente no ZIP: {member}")
        if sum(i.filename == member for i in zf.infolist()) != 1:
            zf.close()
            raise ValueError("nome duplicado no ZIP")
        raw = zf.open(info, "r")
        return raw, zf, member
    raw = open(source_csv, "rb")
    return raw, None, source_csv


class BoundedEvidence(list):
    def __init__(self, maximum):
        super().__init__()
        self.maximum = maximum
        self.total = 0
    def append(self, item):
        self.total += 1
        if super().__len__() < self.maximum:
            super().append(item)
    def __len__(self):
        return self.total


def logical_rows(reader, lines):
    while True:
        lines.start_record()
        row = next(reader, None)
        if row is None:
            return
        yield row


def main(argv=None):
    ap = argparse.ArgumentParser(description="Validador canônico da BU web v1.")
    ap.add_argument("--zip", default=None)
    ap.add_argument("--member", default=None)
    ap.add_argument("--csv", default=None)
    ap.add_argument("--output", default=None)
    args = ap.parse_args(argv)
    if bool(args.zip) != bool(args.member):
        print("ERRO: --zip e --member andam juntos (ou use --csv)", file=sys.stderr)
        return 2
    if not args.zip and not args.csv:
        print("ERRO: informe --zip+--member ou --csv", file=sys.stderr)
        return 2

    limits_path = os.environ.get("URNAPACK_LIMITS_FILE", os.path.join(HERE, "limits.env"))
    limits = load_limits(limits_path)
    errors = BoundedEvidence(limits["MAX_BWEB_DUPLICATE_EVIDENCE"])
    if args.zip and args.csv:
        print("ERRO: --zip e --csv são mutuamente exclusivos", file=sys.stderr)
        return 2
    if args.output and os.path.lexists(args.output):
        print("ERRO: saída existente recusada (origem preservada)", file=sys.stderr)
        return 2
    old_field_limit = csv.field_size_limit(limits["MAX_FIELD_BYTES"])

    label = args.member or args.csv
    try:
        raw, zf, _ = open_text(args.zip, args.member, args.csv)
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print(f"ERRO: {error}", file=sys.stderr)
        csv.field_size_limit(old_field_limit)
        return 2
    hashed = HashingReader(raw)
    complete = False
    idx = {c: i for i, c in enumerate(HEADER)}
    key_idx = [idx[c] for c in KEY_COLS]
    records = divergences = dup_total = 0
    dup_evidence = []
    domain_bad = BoundedEvidence(limits["MAX_BWEB_DUPLICATE_EVIDENCE"])
    pattern_bad = BoundedEvidence(limits["MAX_BWEB_DUPLICATE_EVIDENCE"])
    arith_bad = BoundedEvidence(limits["MAX_BWEB_DUPLICATE_EVIDENCE"])
    key_set = set()
    sentinel_counts = {}
    key_limit_hit = False
    try:
        text = io.TextIOWrapper(io.BufferedReader(hashed), encoding="latin-1", newline="")
        lines = CsvLines(text, limits["MAX_RECORD_BYTES"])
        reader = csv.reader(lines, delimiter=";", quotechar='"', doublequote=True, strict=True)
        try:
            header = next(reader)
        except StopIteration:
            print("ERRO: CSV vazio", file=sys.stderr)
            return 2
        if header != HEADER:
            print(f"ERRO: cabeçalho diverge do canônico v1 em {label}", file=sys.stderr)
            for i, (a, b) in enumerate(zip(header, HEADER)):
                if a != b:
                    print(f"  coluna {i}: lido {a!r} x canônico {b!r}", file=sys.stderr)
                    break
            if len(header) != len(HEADER):
                print(f"  {len(header)} colunas lidas x {len(HEADER)} canônicas", file=sys.stderr)
            return 2
        if len(header) > limits["MAX_CSV_FIELDS"]:
            fail(f"limite excedido: {len(header)} colunas > MAX_CSV_FIELDS", errors)
        for row in logical_rows(reader, lines):
            records += 1
            if records > limits["MAX_CSV_RECORDS"]:
                fail(f"limite excedido: > MAX_CSV_RECORDS", errors)
                raise MappingError("MAX_CSV_RECORDS excedido")
            if len(row) != len(HEADER):
                divergences += 1
                fail(f"divergência de campos no registro {records} (linha {reader.line_num}): "
                     f"{len(row)} x {len(HEADER)}", errors)
                continue
            if any(len(v) > limits["MAX_FIELD_BYTES"] for v in row):
                raise MappingError("MAX_FIELD_BYTES excedido")
            for col, rx in COMPILED.items():
                if rx is None:
                    continue
                if not rx.match(row[idx[col]]):
                    pattern_bad.append((records, col, row[idx[col]]))
                    fail(f"padrão lexical diverge no registro {records}, coluna {col}: "
                         f"{row[idx[col]]!r}", errors)
                    break
            for col, dom in DOMAINS.items():
                if dom is None:
                    continue
                if row[idx[col]] not in dom:
                    domain_bad.append((records, col, row[idx[col]]))
                    fail(f"domínio diverge no registro {records}, coluna {col}: "
                         f"{row[idx[col]]!r}", errors)
                    break
            for code_col, (desc_col, mapping) in CONSISTENT.items():
                code, desc = row[idx[code_col]], row[idx[desc_col]]
                if code in mapping and mapping[code] != desc:
                    fail(f"inconsistência no registro {records}: {code_col}={code!r} "
                         f"com {desc_col}={desc!r}", errors)
                    break
            try:
                a, c, ab = int(row[idx["QT_APTOS"]]), int(row[idx["QT_COMPARECIMENTO"]]), int(row[idx["QT_ABSTENCOES"]])
                if a - c != ab or c > a:
                    arith_bad.append(records)
                    fail(f"regra aritmética diverge no registro {records}: "
                         f"aptos={a} comp={c} abst={ab}", errors)
            except ValueError:
                fail(f"QT não numérico no registro {records}", errors)
            election, cargo = row[idx["CD_ELEICAO"]], row[idx["CD_CARGO_PERGUNTA"]]
            if (election == "6257" and cargo != "1") or (election == "6259" and cargo == "1"):
                fail(f"inconsistência eleição/cargo no registro {records}", errors)
            key = tuple(row[i] for i in key_idx)
            if key in key_set:
                dup_total += 1
                if len(dup_evidence) < limits["MAX_BWEB_DUPLICATE_EVIDENCE"]:
                    dup_evidence.append({"record": records, "line": reader.line_num, "key": list(key)})
                fail(f"chave de ocorrência duplicada no registro {records} (linha {reader.line_num})", errors)
            elif not key_limit_hit:
                if len(key_set) >= limits["MAX_BWEB_OCCURRENCE_KEYS"]:
                    key_limit_hit = True
                    raise MappingError("limite excedido: chaves de ocorrência > MAX_BWEB_OCCURRENCE_KEYS")
                else:
                    key_set.add(key)
            for col_i, val in enumerate(row):
                if val in SENTINELS:
                    d = sentinel_counts.setdefault(HEADER[col_i], {})
                    d[val] = d.get(val, 0) + 1
        complete = True
    except (csv.Error, MappingError, OSError, EOFError, zipfile.BadZipFile) as e:
        fail(f"erro de CSV/leitura: {e}", errors)
    finally:
        csv.field_size_limit(old_field_limit)
        try:
            raw.close()
        except Exception:  # noqa: BLE001
            pass
        if zf is not None:
            zf.close()

    report = {
        "artifact_kind": "bweb_canonical_validation",
        "format_version": 1,
        "family": FAMILY,
        "source": label,
        "records": records,
        "complete": complete,
        "source_sha256": hashed.hexdigest() if complete else None,
        "field_divergences": divergences,
        "distinct_keys": len(key_set),
        "duplicate_keys": dup_total,
        "duplicate_evidence": dup_evidence,
        "pattern_divergences": len(pattern_bad),
        "domain_divergences": len(domain_bad),
        "arithmetic_divergences": len(arith_bad),
        "sentinels": {c: dict(sorted(d.items())) for c, d in sorted(sentinel_counts.items())},
        "success": not errors,
        "errors": list(errors),
        "error_count": len(errors),
    }
    out_json = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        with open(args.output, "x", encoding="utf-8", newline="\n") as f:
            f.write(out_json)
    else:
        print(out_json)
    if errors:
        print(f"validate_bweb: {len(errors)} erro(s) em {label}", file=sys.stderr)
        return 1
    print(f"validate_bweb: OK ({records} registros, {len(key_set)} chaves distintas)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
