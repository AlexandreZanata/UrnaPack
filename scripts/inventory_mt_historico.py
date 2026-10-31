#!/usr/bin/env python3
"""Inventário MT 2000-2026 (somente leitura da API CKAN, sem download).

Gera scripts/inventory_mt_2000_2026.json com todos os recursos cujo URL ou
nome contém _MT_ / 'MT -', para os datasets resultados-YYYY* de 2000 a 2026.
Não inventa tamanho/hash: registra URL, dataset, resource_id, nome, formato
e turno_hint extraído do nome/URL. Tamanhos/hashes oficiais vêm dos sidecars
.sha512/.sha1 quando houver; SHA-256 local só após download.
"""
import json
import argparse
import hashlib
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path
from validate import load_limits

YEARS = list(range(2000, 2027, 2))
BASE = "https://dadosabertos.tse.jus.br/api/3/action/package_show?id="

DATASETS = []
for year in YEARS:
    DATASETS.append(f"resultados-{year}")
    DATASETS.append(f"resultados-{year}-boletim-de-urna")
    DATASETS.append(f"resultados-{year}-boletim-de-urna-1-turno")
    DATASETS.append(f"resultados-{year}-correspondencias-esperadas-e-efetivadas-1-turno")
    DATASETS.append(f"resultados-{year}-correspondencias-esperadas-efetivadas-1-turno")
    DATASETS.append(f"resultados-{year}-correspondencias-esperadas-e-efetivadas-2-turno")
    DATASETS.append(f"resultados-{year}-arquivos-transmitidos-para-totalizacao")
    DATASETS.append(f"resultados-{year}-logs-do-sistema-de-preparacao-das-urnas-eletronicas-gedai-1-turno")
    DATASETS.append(f"resultados-{year}-logs-do-sistema-de-preparacao-das-urnas-eletronicas-gedai-2-turno")


def turno_hint(name, url):
    blob = f"{name} {url}"
    if re.search(r"2t|segundo|2_turno|2-turno", blob, re.I):
        return "2"
    if re.search(r"1t|primeiro|1_turno|1-turno", blob, re.I):
        return "1"
    return ""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    snapshots = args.output.with_name(args.output.stem+"-ckan")
    if args.output.exists() or args.output.is_symlink() or snapshots.exists():
        raise ValueError("saída existente; preserve o inventário anterior")
    snapshots.mkdir(parents=True)
    limits = load_limits(Path(__file__).resolve().parents[1])
    out = {"format_version": 2, "source": "dadosabertos.tse.jus.br CKAN", "years": YEARS, "items": [], "errors": [], "unavailable": [], "responses": []}
    for ds in DATASETS:
        try:
            with urllib.request.urlopen(BASE + ds, timeout=limits["FETCH_TIMEOUT_SECS"]) as resp:
                raw = resp.read(limits["MAX_ARCHIVE_MANIFEST_BYTES"]+1)
            if len(raw) > limits["MAX_ARCHIVE_MANIFEST_BYTES"]:
                raise ValueError("resposta CKAN excede o limite central")
            (snapshots/(ds+".json")).write_bytes(raw)
            out["responses"].append({"dataset": ds, "file": ds+".json", "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
            data = json.loads(raw)
            if data.get("success") is not True:
                raise ValueError("CKAN retornou success diferente de true")
        except urllib.error.HTTPError as exc:
            target = "unavailable" if exc.code == 404 else "errors"
            out[target].append({"dataset": ds, "http_status": exc.code, "error": str(exc)})
            continue
        except Exception as exc:
            out["errors"].append({"dataset": ds, "error": str(exc)})
            continue
        resources = data["result"]["resources"]
        for res in resources:
            url = res.get("url") or ""
            name = res.get("name") or ""
            if "_MT_" not in url and not name.startswith("MT "):
                continue
            out["items"].append({
                "dataset": ds,
                "resource_id": res.get("id"),
                "name": name,
                "url": url,
                "format": res.get("format"),
                "turno_hint": turno_hint(name, url),
            })
    out["items"].sort(key=lambda item: item["url"])
    if not out["items"]:
        out["errors"].append({"error": "nenhum recurso MT encontrado; não aprovar inventário vazio"})
    with args.output.open("x", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, sort_keys=True, indent=2)
        fh.write("\n")
    print(f"inventário: {len(out['items'])} referências MT, erros={len(out['errors'])}")
    return 1 if out["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
