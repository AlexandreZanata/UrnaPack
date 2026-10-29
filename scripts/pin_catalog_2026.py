#!/usr/bin/env python3
"""Fixa o catálogo com bytes/SHA-256 de uma verificação completa dos originais."""
import argparse
import hashlib
import json
from pathlib import Path

from acquire_2026 import check_pinned, write_json


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
