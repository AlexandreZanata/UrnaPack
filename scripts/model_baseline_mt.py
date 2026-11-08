#!/usr/bin/env python3
"""Baseline binomial para comparecimento — MT 2026 t1, cargo 1 (Presidente).

Escopo A1-A4 prévio: bweb 2026 t1 validado por `tsepack analyze`
(perfil mt-2026-t1-bweb-v1). Modelo A5 mínimo:
- H0: cada seção i ~ Binomial(n_i=aptos, p), p global;
- p-valor bilateral por aproximação normal com correção de continuidade;
- controle FDR Benjamini-Hochberg q=0.05;
- casos sintéticos são testes separados; a saída v2 contém dados observados.

Saída v2: destino novo explícito, sem sobrescrever a execução histórica.
Nenhuma conclusão de fraude/autenticidade; atípicos exigem confronto.
"""
import csv
import argparse
import io
import json
import math
import sys
import zipfile
from pathlib import Path

from acquire_2026 import hashes
from analyze_check import CONTEXT_EQUALITY_FIELDS, U64_MAX
from validate import load_limits
from validate_bweb import HEADER

ZIP = "/data/urnapack/brutos/2026/t1/MT/bweb_1t_MT_051020261403.zip"
Q = 0.05


def phi(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def two_sided_p(k, n, p):
    if n == 0:
        return 1.0
    if p <= 0.0 or p >= 1.0:
        return 0.0 if k != p * n else 1.0
    mean = n * p
    var = n * p * (1.0 - p)
    if var == 0:
        return 0.0 if k != mean else 1.0
    z = (abs(k - mean) - 0.5) / math.sqrt(var)
    return max(0.0, min(1.0, 2.0 * (1.0 - phi(z))))


def bh_flags(pvalues, q=Q):
    order = sorted(range(len(pvalues)), key=lambda i: pvalues[i])
    flagged = [False] * len(pvalues)
    threshold = 0
    for rank, idx in enumerate(order, start=1):
        if pvalues[idx] <= rank / len(pvalues) * q:
            threshold = rank
    for rank, idx in enumerate(order, start=1):
        if rank <= threshold:
            flagged[idx] = True
    return flagged


def load_groups(zip_path, cargo="1", turno="1", eleicao="6257", expected_sha256=None, metadata=None):
    limits = load_limits(Path(__file__).resolve().parents[1])
    measured = hashes(Path(zip_path), limits["IO_BUFFER_BYTES"])
    if expected_sha256 is not None and measured["sha256"] != expected_sha256:
        raise ValueError("SHA-256 do ZIP divergente")
    if measured["bytes"] > limits["MAX_SOURCE_FILE_BYTES"]:
        raise ValueError("MAX_SOURCE_FILE_BYTES excedido")
    with zipfile.ZipFile(zip_path) as zf:
        infos = zf.infolist()
        selected = [i for i in infos if i.filename.endswith(".csv")]
        if len(selected) != 1 or len({i.filename for i in infos}) != len(infos) or len(infos) > limits["MAX_ZIP_MEMBERS"]:
            raise ValueError("índice ZIP inesperado/duplicado")
        if selected[0].file_size > limits["MAX_ZIP_MEMBER_BYTES"]:
            raise ValueError("MAX_ZIP_MEMBER_BYTES excedido")
        with zf.open(selected[0]) as f:
            text = io.TextIOWrapper(f, encoding="latin-1", newline="")
            reader = csv.DictReader(text, delimiter=";", strict=True)
            if reader.fieldnames != HEADER:
                raise ValueError("cabeçalho fora do perfil canônico")
            groups, contexts, occurrences = {}, {}, set()
            records = excluded = selected_records = 0
            for row in reader:
                records += 1
                if records > limits["MAX_CSV_RECORDS"] or None in row or any(v is None for v in row.values()):
                    raise ValueError("registro incompleto/excessivo")
                if row.get("NR_TURNO") != turno:
                    excluded += 1
                    continue
                if row.get("CD_CARGO_PERGUNTA") != cargo:
                    excluded += 1
                    continue
                if row.get("CD_ELEICAO") != eleicao:
                    excluded += 1
                    continue
                selected_records += 1
                if (row["SG_UF"], row["ANO_ELEICAO"], row["CD_PLEITO"]) != ("MT", "2026", "3220"):
                    raise ValueError("grupo fora do escopo MT/2026/pleito 3220")
                key = (row.get("CD_MUNICIPIO"), row.get("NR_ZONA"), row.get("NR_SECAO"))
                occurrence = (*key, row["NR_VOTAVEL"])
                if occurrence in occurrences:
                    raise ValueError("ocorrência duplicada; sem deduplicação")
                occurrences.add(occurrence)
                if len(occurrences) > limits["MAX_BWEB_OCCURRENCE_KEYS"]:
                    raise ValueError("MAX_BWEB_OCCURRENCE_KEYS excedido")
                context = tuple(row[c] for c in CONTEXT_EQUALITY_FIELDS)
                if key in contexts and contexts[key] != context:
                    raise ValueError("contexto divergente no grupo")
                contexts[key] = context
                n, k, abst = (int(row[c]) for c in ("QT_APTOS", "QT_COMPARECIMENTO", "QT_ABSTENCOES"))
                if min(n, k, abst) < 0 or max(n, k, abst) > U64_MAX or n != k + abst:
                    raise ValueError("aritmética de contexto inválida")
                groups[key] = (n, k)
            if metadata is not None:
                metadata.update(zip=measured, member=selected[0].filename, records=records,
                                selected_records=selected_records, excluded_by_scope=excluded,
                                repeated_context_rows=selected_records-len(groups))
            return groups


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, default=Path(ZIP))
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise ValueError("saída existente; preserve a execução anterior")
    source = {}
    groups = load_groups(args.zip, expected_sha256=args.expected_sha256, metadata=source)
    keys = sorted(groups)
    observed = [groups[k] for k in keys]
    total_n = sum(n for n, _ in observed)
    total_k = sum(k for _, k in observed)
    if not groups or total_n == 0:
        raise ValueError("população vazia ou denominador zero")
    p_hat = total_k / total_n
    pvalues = [two_sided_p(k, n, p_hat) for n, k in observed]
    flagged = bh_flags(pvalues)
    n_flagged = sum(flagged)

    out = {
        "format_version": 2,
        "source": source,
        "escopo": {"zip": str(args.zip), "cargo": "1", "turno": "1", "eleicao": "6257",
                   "grupos": len(observed), "aptos_total": total_n,
                   "comparecimento_total": total_k, "p_hat": p_hat},
        "metodo": "binomial H0 por seção, p bilateral normal com continuidade, BH q=0.05",
        "flags_observados": n_flagged,
        "exemplos": [
            {"municipio": k[0], "zona": k[1], "secao": k[2], "aptos": n, "comp": kk, "p": p}
            for (k, (n, kk), p, f) in zip(keys, observed, pvalues, flagged) if f][:20],
        "synthetic_checks": "Separados em scripts/test_model_baseline_mt.py; não são dados eleitorais observados.",
        "nota": "Atípicos sob baseline não concluem fraude/autenticidade.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, sort_keys=True, indent=2)
        fh.write("\n")
    print(f"grupos={len(observed)} p_hat={p_hat:.6f} flags={n_flagged}; diagnóstico do modelo, sem inferência de fraude")
    return 0


if __name__ == "__main__":
    sys.exit(main())
