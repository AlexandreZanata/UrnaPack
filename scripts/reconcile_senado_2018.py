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
import argparse
import hashlib
import io
import json
import sys
import zipfile
from collections import Counter
from pathlib import Path
from validate import load_limits
from acquire_2026 import hashes

BU_2018 = "/data/urnapack/brutos/2018/MT/BWEB_1t_MT_101020181938.zip"
BU_2018_MEMBER = "bweb_1t_MT_101020182002.csv"
VOT_2018 = "/data/urnapack/brutos/2018/MT/votacao_secao_2018_MT.zip"


def sha256_file(path):
    limits = load_limits(Path(__file__).resolve().parents[1])
    return hashes(Path(path), limits["IO_BUFFER_BYTES"])["sha256"]


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
    limits = load_limits(Path(__file__).resolve().parents[1])
    if Path(zip_path).stat().st_size > limits["MAX_SOURCE_FILE_BYTES"]:
        raise ValueError("MAX_SOURCE_FILE_BYTES excedido")
    with zipfile.ZipFile(zip_path) as zf:
        selected = [i for i in zf.infolist() if i.filename == member]
        if len(selected) != 1 or selected[0].file_size > limits["MAX_ZIP_MEMBER_BYTES"]:
            raise ValueError("membro ausente/duplicado/excessivo")
        with zf.open(selected[0]) as f:
            text = io.TextIOWrapper(f, encoding="latin-1", newline="")
            reader = csv.DictReader(text, delimiter=";", strict=True)
            required = {"NR_TURNO", cargo_col, "CD_ELEICAO", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO", "NR_VOTAVEL", "QT_VOTOS"}
            if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)) or not required.issubset(reader.fieldnames):
                raise ValueError("cabeçalho insuficiente/duplicado na reconciliação")
            agg = Counter()
            seen = set()
            records = 0
            for row in reader:
                records += 1
                if records > limits["MAX_CSV_RECORDS"]:
                    raise ValueError("MAX_CSV_RECORDS excedido")
                if None in row or any(v is None for v in row.values()):
                    raise ValueError("registro com largura divergente")
                if row.get("NR_TURNO") != "1":
                    continue
                if row.get(cargo_col) != "5":
                    continue
                if row.get("CD_ELEICAO") != eleicao:
                    continue
                key = (row["CD_MUNICIPIO"], row["NR_ZONA"], row["NR_SECAO"])
                occurrence = (*key, row["NR_VOTAVEL"])
                if occurrence in seen:
                    raise ValueError("ocorrência duplicada na reconciliação")
                seen.add(occurrence)
                if len(seen) > limits["MAX_BWEB_OCCURRENCE_KEYS"]:
                    raise ValueError("MAX_BWEB_OCCURRENCE_KEYS excedido")
                votes = int(row["QT_VOTOS"])
                if votes < 0:
                    raise ValueError("QT_VOTOS negativo")
                agg[key] += votes
            return agg


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bu-zip",type=Path,default=Path(BU_2018))
    parser.add_argument("--bu-member",default=BU_2018_MEMBER)
    parser.add_argument("--vot-zip",type=Path,default=Path(VOT_2018))
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise ValueError("saída existente; preserve a reconciliação anterior")
    with zipfile.ZipFile(args.vot_zip) as zf:
        selected=[i for i in zf.infolist() if i.filename.endswith(".csv")]
        if len(selected)!=1:
            raise ValueError("CSV de votação ausente/ambíguo")
        vot_member=selected[0].filename
    bu = aggregate(args.bu_zip,args.bu_member,"CD_CARGO_PERGUNTA","297")
    vot = aggregate(args.vot_zip,vot_member,"CD_CARGO","297")
    vot_sup = aggregate(args.vot_zip,vot_member,"CD_CARGO","438")
    common = set(bu) & set(vot)
    only_bu = sorted(set(bu) - set(vot))
    only_vot = sorted(set(vot) - set(bu))
    divergentes = sorted(
        [(k, bu[k], vot[k], vot[k] - bu[k]) for k in common if bu[k] != vot[k]]
    )
    report = {
        "format_version": 2,
        "par_regular_297": {
            "bu_zip": str(args.bu_zip),
            "bu_zip_sha256": sha256_file(args.bu_zip),
            "bu_member": args.bu_member,
            "vot_zip": str(args.vot_zip),
            "vot_zip_sha256": sha256_file(args.vot_zip),
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
            "bu_status": "não conciliada nesta execução; ver inspeção documentada do BU 2020 em inspect_2020_bweb_quoting.py",
        },
        "exemplos_divergentes": [
            {"municipio": k[0], "zona": k[1], "secao": k[2], "bu": b, "vot": v, "diff": d}
            for k, b, v, d in divergentes[:20]
        ],
    }
    report["success"] = bool(bu) and bool(vot) and not divergentes and not only_bu and not only_vot
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, sort_keys=True, indent=2)
        fh.write("\n")
    print(f"regular 297: BU {sum(bu.values())} ({len(bu)} grupos) × "
          f"VOT {sum(vot.values())} ({len(vot)} grupos); "
          f"divergentes={len(divergentes)} sóBU={len(only_bu)} sóVOT={len(only_vot)}")
    print(f"suplementar 438 (só votação): {sum(vot_sup.values())} votos, {len(vot_sup)} grupos; BU bloqueada")
    return 0 if report["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
