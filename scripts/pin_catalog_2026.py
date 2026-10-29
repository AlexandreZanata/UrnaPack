#!/usr/bin/env python3
"""Fixa o catálogo com bytes/SHA-256 de uma verificação completa dos originais."""
import argparse
import hashlib
import json
from pathlib import Path

from acquire_2026 import check_pinned, write_json


def validate_fixed(source_raw, fixed):
    """Valida vínculo e cobertura do catálogo antes de qualquer aquisição."""
    source = json.loads(source_raw)
    if source.get("format_version") != 1 or fixed.get("format_version") != 1:
        raise ValueError("versão de catálogo incompatível")
    if fixed.get("source_catalog_sha256") != hashlib.sha256(source_raw).hexdigest():
        raise ValueError("catálogo fixado não corresponde ao catálogo de descoberta")
    original = {row["url"]: row for row in source["items"]}
    rows = fixed["items"]
    if (not original or len(original) != len(source["items"]) or
            len(rows) != len(original) or {row["url"] for row in rows} != set(original)):
        raise ValueError("cobertura do catálogo fixado incompleta ou duplicada")
    for row in rows:
        prior = original[row["url"]]
        if any(row.get(k) != value for k, value in prior.items()):
            raise ValueError("metadados de descoberta alterados no catálogo fixado")
        if not {"expected_bytes", "expected_sha256"}.issubset(row):
            raise ValueError("recurso sem fixação de tamanho/SHA-256")
        if set(row) - set(prior) - {"expected_bytes", "expected_sha256", "metadata_method"}:
            raise ValueError("campo de fixação desconhecido")
        if row.get("metadata_method", "head") not in ("head", "range"):
            raise ValueError("método de metadados inválido")
        check_pinned(row, {"bytes": row["expected_bytes"], "sha256": row["expected_sha256"]})


def pin(catalog, report, catalog_hash):
    if report.get("errors") != 0 or not report.get("finished_at_utc") or report["catalog_sha256"] != catalog_hash:
        raise ValueError("verificação incompleta, com erros ou de outro catálogo")
    records = {}
    for row in report["items"]:
        if row["url"] in records or row["status"] != "reverified_local":
            raise ValueError("recursos repetidos ou sem releitura de verificação")
        records[row["url"]] = row
    urls = [item["url"] for item in catalog["items"]]
    if len(set(urls)) != len(urls) or set(urls) != set(records):
        raise ValueError("cobertura da verificação difere do catálogo")
    result = dict(catalog, source_catalog_sha256=catalog_hash, items=[])
    for item in catalog["items"]:
        row = records[item["url"]]
        if row["path"] != item["path"]:
            raise ValueError("caminho diverge entre catálogo e verificação")
        fixed = dict(item, expected_bytes=row["bytes"], expected_sha256=row["sha256"])
        if "metadata_method" in row:
            if row["metadata_method"] not in ("head", "range"):
                raise ValueError("método de metadados não reconhecido no recibo")
            fixed["metadata_method"] = row["metadata_method"]
        check_pinned(fixed, row)
        result["items"].append(fixed)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--catalog", required=True, type=Path)
    p.add_argument("--verification", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    if args.output.exists():
        raise ValueError("catálogo fixado de saída já existe")
    raw = args.catalog.read_bytes()
    result = pin(json.loads(raw), json.loads(args.verification.read_bytes()), hashlib.sha256(raw).hexdigest())
    result["verification_sha256"] = hashlib.sha256(args.verification.read_bytes()).hexdigest()
    write_json(args.output, result)


if __name__ == "__main__":
    main()
