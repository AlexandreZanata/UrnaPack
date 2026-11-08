#!/usr/bin/env python3
"""Aquisição histórica MT via o mesmo adquiridor validado da auditoria nacional.

O destino v2 conserva host/caminho oficial e recibos individuais. Os arquivos
legados em brutos/ permanecem preservados; não são promovidos como verificados
só por já existirem. Sidecars são bytes originais, comparados antes da promoção.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from acquire_2026 import relative_url, write_json


def catalog(inventory, only_substr=None, skip_big=False, limit=0):
    if limit < 0:
        raise ValueError("limite negativo")
    data = [i for i in inventory["items"] if not i["url"].endswith((".sha512", ".sha1"))]
    if only_substr:
        data = [i for i in data if only_substr in i["url"]]
    if skip_big:
        data = [i for i in data if "arqurnatot" not in i["url"] and "logsgedai" not in i["url"]]
    urls = sorted({i["url"] for i in data})
    if limit:
        urls = urls[:limit]
    if not urls:
        raise ValueError("seleção vazia")
    selected = set(urls)
    for item in inventory["items"]:
        for suffix in (".sha512", ".sha1"):
            if item["url"].endswith(suffix) and item["url"][:-len(suffix)] in selected:
                selected.add(item["url"])
    rows = {}
    for item in inventory["items"]:
        if item["url"] in selected:
            row = rows.setdefault(item["url"], {"url": item["url"], "path": relative_url(item["url"]), "references": []})
            row["references"].append(item)
    return {"format_version": 1, "scope": "recorte explícito do inventário histórico MT; referências compartilhadas preservadas", "items": [rows[u] for u in sorted(rows)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=Path("scripts/inventory_mt_2000_2026.json"))
    parser.add_argument("--root", type=Path, default=Path("/data/urnapack/mt-historico-verificado/fontes"))
    parser.add_argument("--catalog-output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--only-substr")
    parser.add_argument("--skip-big", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--transport", choices=["curl", "urllib"], default="curl")
    args = parser.parse_args()
    if any(p.exists() or p.is_symlink() for p in (args.catalog_output, args.receipt)):
        raise ValueError("catálogo/recibo de saída já existe; preserve a tentativa anterior")
    raw = args.inventory.read_bytes()
    result = catalog(json.loads(raw), args.only_substr, args.skip_big, args.limit)
    result["source_inventory_sha256"] = hashlib.sha256(raw).hexdigest()
    write_json(args.catalog_output, result)
    return subprocess.run([sys.executable, str(Path(__file__).with_name("acquire_2026.py")), "fetch",
        "--catalog", str(args.catalog_output), "--root", str(args.root), "--receipt", str(args.receipt),
        "--transport", args.transport]).returncode


if __name__ == "__main__":
    sys.exit(main())
