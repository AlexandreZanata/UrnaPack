#!/usr/bin/env python3
"""Concilia chaves/aptos/abstenções do BU presidencial e sentinelas do exterior."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
import io
import zipfile

from acquire_2026 import write_json, hashes, limits_at, official_digest

GEO = ("SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO")


def key(row):
    # Junção semântica de identificadores: zeros da representação original
    # permanecem nos arquivos; colisões após normalização são erro.
    return (row["SG_UF"], *(str(int(row[field])) for field in GEO[1:]))


def reconcile_origins(ceft, presidential, sentinels):
    expected = {}
    missing_closing = set()
    for row in presidential:
        if row["SG_UF"] != "ZZ":
            continue
        identity = key(row)
        if identity in expected:
            raise ValueError("chave ZZ duplicada na projeção")
        expected[identity] = int(row["QT_COMPARECIMENTO"])
        if row["DT_ENCERRAMENTO"] in ("", "#NULO#", "#NE#"):
            missing_closing.add(identity)
    for row in sentinels:
        identity = key(row)
        if identity in expected or row["SG_UF"] != "ZZ" or int(row["QT_COMPARECIMENTO"]) != 0:
            raise ValueError("sentinela de origem inválida")
        expected[identity] = 0
    seen, groups, system_rows, nonzero_system = set(), {}, [], set()
    for row in ceft:
        if None in row or any(value is None for value in row.values()):
            raise ValueError("CEFT: largura de registro divergente")
        identity = key(row)
        if identity in seen or identity not in expected:
            raise ValueError("CEFT: chave duplicada ou fora do universo ZZ")
        if row["SG_UF"] != "ZZ" or row["AA_ELEICAO"] != "2026" or row["CD_PLEITO"] != "3221":
            raise ValueError("CEFT: UF/ano/pleito inesperado")
        seen.add(identity)
        code, label = row["CD_ORIGEM_VOTO"], row["DS_ORIGEM_VOTO"]
        if not code or not label:
            raise ValueError("CEFT: origem vazia")
        group = groups.setdefault(code, {"labels": set(), "sections": 0, "turnout": 0})
        group["labels"].add(label)
        group["sections"] += 1
        group["turnout"] += expected[identity]
        if code == "C":
            if label != "Sistema de apuração":
                raise ValueError("CEFT: significado de C diferente do documentado")
            system_rows.append({"key": identity, "turnout": expected[identity], "ceft_row_all_fields": row})
            if expected[identity] > 0:
                nonzero_system.add(identity)
    if seen != set(expected):
        raise ValueError("CEFT: cobertura ZZ incompleta")
    if nonzero_system != missing_closing:
        raise ValueError("CEFT C com votantes difere das chaves sem encerramento")
    for group in groups.values():
        group["labels"] = sorted(group["labels"])
    return {"format_version": 1, "status": "matched", "scope": "Junção semântica por chave ZZ; origens preservam código/descrição oficial, sem inferir horário dos votos.",
            "by_origin": groups, "system_of_counting_rows": system_rows,
            "nonzero_system_keys_equal_missing_closing": True,
            "nonzero_system_sections": len(nonzero_system)}


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
    parser.add_argument("--correspondence-zip", type=Path)
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
    if args.correspondence_zip:
        path = args.correspondence_zip
        limits = limits_at(Path(__file__).with_name("limits.env"))
        measured = hashes(path, limits["IO_BUFFER_BYTES"])
        saved = json.loads(path.with_name(path.name+".receipt.json").read_text())
        if measured["sha256"] != saved["sha256"] or measured["bytes"] != saved["bytes"]:
            raise ValueError("CEFT: ZIP diverge do recibo")
        side = path.with_name(path.name+".sha512")
        if measured["sha512"] != official_digest(side.read_bytes(), path.name, "sha512"):
            raise ValueError("CEFT: SHA-512 diverge do sidecar oficial")
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            selected = [member for member in members if member.filename.endswith('.csv')]
            if len(selected) != 1 or len(members) > limits["MAX_ZIP_MEMBERS"] or selected[0].file_size > limits["MAX_ZIP_MEMBER_BYTES"] or len({m.filename for m in members}) != len(members):
                raise ValueError("CEFT: índice/tamanho inesperado")
            with archive.open(selected[0]) as body, io.TextIOWrapper(body, encoding="latin1", newline="") as text, args.sections.open(newline="") as sections:
                reader = csv.DictReader(text, delimiter=";")
                if len(reader.fieldnames) != len(set(reader.fieldnames)):
                    raise ValueError("CEFT: colunas duplicadas")
                origins = reconcile_origins(reader, csv.DictReader(sections), sentinels)
            origins["source"] = {"path": str(path), "member": selected[0].filename, **measured}
            result["exterior_origins"] = origins
    write_json(args.output, result)
    print("união das chaves, aptos, comparecimento e abstenções: confronto aprovado")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"cobertura reprovada: {exc}", file=sys.stderr)
        sys.exit(1)
