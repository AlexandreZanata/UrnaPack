#!/usr/bin/env python3
"""Reconciliação Senado 2018 MT — BU × votação por seção e eleição.

Compara soma de QT_VOTOS por (CD_MUNICIPIO, NR_ZONA, NR_SECAO) para
cargo 5 (Senador), turno 1, separando CD_ELEICAO:
- 297 regular (DT 07/10/2018): BU 2018 t1 × votação 2018 eleição 297;
- 438 suplementar (DT 15/11/2020): BU 2020 t1 é ilegível em parser estrito
  (quoting, ver inspect_2020_bweb_quoting.py) → comparação bloqueada;
  votação 438 reportada como observação.

Saída: relatorios-locais/mt-historico/reconcile-senado-2018.json + texto.
Nenhuma conclusão de fraude/autenticidade.
"""
import csv
import hashlib
import io
import json
import sys
import zipfile
from collections import Counter
from pathlib import Path

BU_2018 = "/data/urnapack/brutos/2018/MT/BWEB_1t_MT_101020181938.zip"
BU_2018_MEMBER = "bweb_1t_MT_101020182002.csv"
VOT_2018 = "/data/urnapack/brutos/2018/MT/votacao_secao_2018_MT.zip"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def compare(bu, vot):
    common = set(bu) & set(vot)
    divergentes = sorted((k, bu[k], vot[k], vot[k] - bu[k]) for k in common if bu[k] != vot[k])
    return {
        "comuns": len(common),
        "divergentes": len(divergentes),
        "so_bu": len(set(bu) - set(vot)),
        "so_vot": len(set(vot) - set(bu)),
    }


def aggregate(zip_path, member, cargo_col, eleicao):
    with zipfile.ZipFile(zip_path) as zf:
        with zf.open(member) as f:
            text = io.TextIOWrapper(f, encoding="latin-1", newline="")
            reader = csv.DictReader(text, delimiter=";")
            agg = Counter()
            for row in reader:
                if row.get("NR_TURNO") != "1":
                    continue
                if row.get(cargo_col) != "5":
                    continue
                if row.get("CD_ELEICAO") != eleicao:
                    continue
                key = (row.get("CD_MUNICIPIO"), row.get("NR_ZONA"), row.get("NR_SECAO"))
                agg[key] += int(row.get("QT_VOTOS", 0))
            return agg


def main():
    out_dir = Path("relatorios-locais/mt-historico")
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(VOT_2018) as zf:
        vot_member = [n for n in zf.namelist() if n.endswith(".csv")][0]
    bu = aggregate(BU_2018, BU_2018_MEMBER, "CD_CARGO_PERGUNTA", "297")
    vot = aggregate(VOT_2018, vot_member, "CD_CARGO", "297")
    vot_sup = aggregate(VOT_2018, vot_member, "CD_CARGO", "438")
    common = set(bu) & set(vot)
    only_bu = sorted(set(bu) - set(vot))
    only_vot = sorted(set(vot) - set(bu))
    divergentes = sorted(
        [(k, bu[k], vot[k], vot[k] - bu[k]) for k in common if bu[k] != vot[k]]
    )
    report = {
        "par_regular_297": {
            "bu_zip": BU_2018,
            "bu_zip_sha256": sha256_file(BU_2018),
            "bu_member": BU_2018_MEMBER,
            "vot_zip": VOT_2018,
            "vot_zip_sha256": sha256_file(VOT_2018),
            "vot_member": vot_member,
            "bu_grupos": len(bu),
            "vot_grupos": len(vot),
            "bu_votos": sum(bu.values()),
            "vot_votos": sum(vot.values()),
            "grupos_comuns": len(common),
            "grupos_divergentes": len(divergentes),
            "somente_bu": len(only_bu),
            "somente_vot": len(only_vot),
        },
        "suplementar_438_observacao": {
            "vot_grupos": len(vot_sup),
            "vot_votos": sum(vot_sup.values()),
            "bu_status": "bloqueada: bweb_1t_MT_181120201549.csv ilegível em parser estrito "
                         "(quoting registro 59083; ver inspect_2020_bweb_quoting.py)",
        },
        "exemplos_divergentes": [
            {"municipio": k[0], "zona": k[1], "secao": k[2], "bu": b, "vot": v, "diff": d}
            for k, b, v, d in divergentes[:20]
        ],
    }
    with open(out_dir / "reconcile-senado-2018.json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, sort_keys=True, indent=2)
        fh.write("\n")
    print(f"regular 297: BU {sum(bu.values())} ({len(bu)} grupos) × "
          f"VOT {sum(vot.values())} ({len(vot)} grupos); "
          f"divergentes={len(divergentes)} sóBU={len(only_bu)} sóVOT={len(only_vot)}")
    print(f"suplementar 438 (só votação): {sum(vot_sup.values())} votos, {len(vot_sup)} grupos; BU bloqueada")
    return 0 if (len(divergentes) == 0 and not only_bu and not only_vot) else 1


if __name__ == "__main__":
    sys.exit(main())
