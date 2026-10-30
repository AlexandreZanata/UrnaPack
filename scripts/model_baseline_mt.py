#!/usr/bin/env python3
"""Baseline binomial para comparecimento — MT 2026 t1, cargo 1 (Presidente).

Escopo A1-A4 prévio: bweb 2026 t1 validado por `tsepack analyze`
(perfil mt-2026-t1-bweb-v1). Modelo A5 mínimo:
- H0: cada seção i ~ Binomial(n_i=aptos, p), p global;
- p-valor bilateral por aproximação normal com correção de continuidade;
- controle FDR Benjamini-Hochberg q=0.05;
- calibração: sintético nulo (mesmos n_i, p_hat) deve gerar ~0 flags;
- falsificação: sintético com 10 grupos p+0.15 deve ser detectado em parte.

Saída: relatorios-locais/mt-historico/model-comparecimento-2026t1.json.
Nenhuma conclusão de fraude/autenticidade; atípicos exigem confronto.
"""
import csv
import io
import json
import math
import random
import sys
import zipfile
from pathlib import Path

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


def load_groups(zip_path, cargo="1", turno="1", eleicao="6257"):
    with zipfile.ZipFile(zip_path) as zf:
        name = [n for n in zf.namelist() if n.endswith(".csv")][0]
        with zf.open(name) as f:
            text = io.TextIOWrapper(f, encoding="latin-1", newline="")
            reader = csv.DictReader(text, delimiter=";")
            groups = {}
            for row in reader:
                if row.get("NR_TURNO") != turno:
                    continue
                if row.get("CD_CARGO_PERGUNTA") != cargo:
                    continue
                if row.get("CD_ELEICAO") != eleicao:
                    continue
                key = (row.get("CD_MUNICIPIO"), row.get("NR_ZONA"), row.get("NR_SECAO"))
                if key in groups:
                    continue
                groups[key] = (int(row["QT_APTOS"]), int(row["QT_COMPARECIMENTO"]))
            return groups


def main():
    groups = load_groups(ZIP)
    keys = sorted(groups)
    observed = [groups[k] for k in keys]
    total_n = sum(n for n, _ in observed)
    total_k = sum(k for _, k in observed)
    p_hat = total_k / total_n
    pvalues = [two_sided_p(k, n, p_hat) for n, k in observed]
    flagged = bh_flags(pvalues)
    n_flagged = sum(flagged)

    # calibração: sintético nulo determinístico
    rng = random.Random(0)
    synth_null = []
    for n, _ in observed:
        k = sum(1 for _ in range(n) if rng.random() < p_hat)
        synth_null.append((n, k))
    p_null = [two_sided_p(k, n, p_hat) for n, k in synth_null]
    flags_null = sum(bh_flags(p_null))

    # falsificação: 10 grupos com p+0.15
    rng2 = random.Random(1)
    synth_alt = []
    for i, (n, _) in enumerate(observed):
        p = p_hat + 0.15 if i < 10 else p_hat
        p = min(p, 0.99)
        k = sum(1 for _ in range(n) if rng2.random() < p)
        synth_alt.append((n, k))
    p_alt = [two_sided_p(k, n, p_hat) for n, k in synth_alt]
    flags_alt = bh_flags(p_alt)
    detected_injected = sum(flags_alt[:10])

    out = {
        "escopo": {"zip": ZIP, "cargo": "1", "turno": "1", "eleicao": "6257",
                   "grupos": len(observed), "aptos_total": total_n,
                   "comparecimento_total": total_k, "p_hat": p_hat},
        "metodo": "binomial H0 por seção, p bilateral normal com continuidade, BH q=0.05",
        "flags_observados": n_flagged,
        "exemplos": [
            {"municipio": k[0], "zona": k[1], "secao": k[2], "aptos": n, "comp": kk, "p": p}
            for (k, (n, kk), p, f) in zip(keys, observed, pvalues, flagged) if f][:20],
        "calibracao_nulo": {"flags_sintetico": flags_null, "criterio": "flags==0 esperado sob H0 global com BH"},
        "falsificacao_injetada": {"injetados": 10, "detectados": detected_injected,
                                  "criterio": "detectar ao menos 1 dos 10 com p+0.15"},
        "nota": "Atípicos sob baseline não concluem fraude/autenticidade.",
    }
    out_dir = Path("relatorios-locais/mt-historico")
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "model-comparecimento-2026t1.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, sort_keys=True, indent=2)
        fh.write("\n")
    print(f"grupos={len(observed)} p_hat={p_hat:.6f} flags={n_flagged} "
          f"calib_null={flags_null} falsif={detected_injected}/10")
    ok = flags_null == 0 and detected_injected >= 1
    if not ok:
        print("modelo: calibração/falsificação fora do critério", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
