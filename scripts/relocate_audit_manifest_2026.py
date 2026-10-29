#!/usr/bin/env python3
"""Vincula um novo manifesto aos CSVs restaurados, após reler tamanho e SHA-256.

Preserva todos os campos da entrada; altera apenas path e grava recibo separado.
Não verifica novamente o contêiner ZIP do TSE, que não está no pacote tratado.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from acquire_2026 import hashes, limits_at, safe_path, write_json
from prepare_audit_2026 import UFS


def relocate(manifest, restored, buffer):
    if manifest["format_version"] != 1 or not manifest["inputs"]:
        raise ValueError("manifesto incompatível/vazio")
    result = deepcopy(manifest)
    seen = set()
    for item in result["inputs"]:
        uf, member = item["uf"], item["member"]
        if uf not in UFS or Path(member).name != member or "/" in member or "\\" in member:
            raise ValueError("UF/nome do membro inválido")
        relative = f"{uf}/{member}"
        if relative in seen:
            raise ValueError("membro repetido; não deduplicar")
        seen.add(relative)
        if type(item["bytes"]) is not int or item["bytes"] < 0 or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]):
            raise ValueError("compromisso de tamanho/hash inválido")
        path = safe_path(restored, relative)
        measured = hashes(path, buffer)
        if measured["bytes"] != item["bytes"] or measured["sha256"] != item["sha256"]:
            raise ValueError("CSV restaurado diverge do manifesto analítico")
        item["path"] = str(path.resolve())
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--restored", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    receipt = args.output.with_name(args.output.name+".receipt.json")
    if args.output.exists() or receipt.exists():
        raise ValueError("saída existente; preservar manifesto anterior")
    raw = args.manifest.read_bytes()
    result = relocate(json.loads(raw), args.restored, limits_at(Path(__file__).with_name("limits.env"))["IO_BUFFER_BYTES"])
    write_json(args.output, result)
    write_json(receipt, {"format_version": 1, "success": True,
        "source_manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "relocated_manifest_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
        "verified_csv_files": len(result["inputs"]),
        "scope": "Somente paths alterados; tamanho e SHA-256 de cada CSV restaurado conferidos com o manifesto anterior."})


if __name__ == "__main__":
    main()
