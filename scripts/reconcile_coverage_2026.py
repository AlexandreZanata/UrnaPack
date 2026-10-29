#!/usr/bin/env python3
"""Concilia chaves/aptos/abstenções do BU presidencial e sentinelas do exterior."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

from acquire_2026 import write_json

GEO = ("SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO")


def key(row):
    # Junção semântica de identificadores: zeros da representação original
    # permanecem nos arquivos; colisões após normalização são erro.
    return (row["SG_UF"], *(str(int(row[field])) for field in GEO[1:]))


def reconcile(rows, sentinels, report, official):
    keys, aptos, turnout, abstentions = set(), 0, 0, 0
    for row in rows:
        geo = key(row)
        if geo in keys:
            raise ValueError("chave geográfica repetida na exportação presidencial")
        keys.add(geo)
        a, c, b = (int(row[field]) for field in ("QT_APTOS", "QT_COMPARECIMENTO", "QT_ABSTENCOES"))
        if min(a, c, b) < 0 or a != c + b:
            raise ValueError("aritmética da exportação inválida")
        aptos += a
        turnout += c
        abstentions += b
    if len(keys) != report["presidential"]["sections"] or turnout != report["presidential"]["turnout"]:
        raise ValueError("exportação diverge do relatório presidencial")
    additions = []
    for row in sentinels:
        geo = key(row)
        if geo in keys:
            raise ValueError("sentinela duplica chave presidencial/outra sentinela")
        if row["SG_UF"] != "ZZ" or row["CD_CARGO_PERGUNTA"] != "-1" or int(row["QT_COMPARECIMENTO"]) != 0 or int(row["QT_VOTOS"]) != 0:
            raise ValueError("registro externo ao cargo fora da definição aceita")
        a, b = int(row["QT_APTOS"]), int(row["QT_ABSTENCOES"])
        if a < 0 or a != b:
            raise ValueError("sentinela: aptos != abstenções")
        keys.add(geo)
        aptos += a
        abstentions += b
        additions.append({"key": geo, "municipality": row["NM_MUNICIPIO"], "aptos": a,
                          "turnout": 0, "source_cargo": "-1"})
    if len(keys) != int(official["s"]["si"]) or aptos != int(official["e"]["esi"]) or abstentions != int(official["e"]["a"]):
        raise ValueError("união do BU não confere com instaladas/aptos/abstenções da totalização")
    return {"format_version": 1, "status": "matched",
            "presidential_sections": report["presidential"]["sections"],
            "additional_zero_turnout_sections": additions,
            "union_geographic_sections": len(keys), "union_aptos": aptos,
            "union_turnout": turnout, "union_abstentions": abstentions,
            "official_not_installed_sections": int(official["s"]["sni"]),
            "scope": "BU presidencial + registros do exterior com cargo -1 e comparecimento zero; o campo si é seções instaladas no EA20. Identifica as duas chaves adicionais, sem atribuir motivo ao comparecimento zero."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sections", type=Path, required=True)
    parser.add_argument("--export-receipt", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--official", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export = json.loads(args.export_receipt.read_text())
    actual = hashlib.sha256(args.sections.read_bytes()).hexdigest()
    if actual != export["sha256"] or args.sections.stat().st_size != export["bytes"]:
        raise ValueError("SHA-256/tamanho da exportação diverge do recibo")
    manifest = json.loads(args.source_manifest.read_text())
    zz = [i for i in manifest["inputs"] if i["uf"] == "ZZ"]
    if len(zz) != 1:
        raise ValueError("membro ZZ ausente ou repetido")
    source = Path(zz[0]["path"])
    if hashlib.sha256(source.read_bytes()).hexdigest() != zz[0]["sha256"]:
        raise ValueError("SHA-256 da fonte ZZ divergente")
    with source.open(encoding="latin1", newline="") as stream:
        sentinels = [row for row in csv.DictReader(stream, delimiter=";") if row["CD_CARGO_PERGUNTA"] == "-1"]
    with args.sections.open(newline="") as stream:
        result = reconcile(csv.DictReader(stream), sentinels, json.loads(args.report.read_text()), json.loads(args.official.read_text()))
    result["inputs_sha256"] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.sections, args.export_receipt, args.source_manifest, args.report, args.official)}
    result["sentinel_source_member"] = zz[0]["member"]
    result["sentinels_all_fields"] = sentinels
    write_json(args.output, result)
    print("união das chaves, aptos, comparecimento e abstenções: confronto aprovado")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"cobertura reprovada: {exc}", file=sys.stderr)
        sys.exit(1)
