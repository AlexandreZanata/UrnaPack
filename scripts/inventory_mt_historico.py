#!/usr/bin/env python3
"""Inventário MT 2000-2026 (somente leitura da API CKAN, sem download).

Gera scripts/inventory_mt_2000_2026.json com todos os recursos cujo URL ou
nome contém _MT_ / 'MT -', para os datasets resultados-YYYY* de 2000 a 2026.
Não inventa tamanho/hash: registra URL, dataset, resource_id, nome, formato
e turno_hint extraído do nome/URL. Tamanhos/hashes oficiais vêm dos sidecars
.sha512/.sha1 quando houver; SHA-256 local só após download.
"""
import json
import re
import sys
import urllib.request

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
    out = {"source": "dadosabertos.tse.jus.br CKAN", "years": YEARS, "items": []}
    seen_urls = set()
    for ds in DATASETS:
        try:
            with urllib.request.urlopen(BASE + ds, timeout=30) as resp:
                data = json.load(resp)
        except Exception as exc:  # dataset inexistente p/ ano: registra e segue
            print(f"{ds}: ausente ({exc})", file=sys.stderr)
            continue
        resources = data["result"]["resources"]
        for res in resources:
            url = res.get("url") or ""
            name = res.get("name") or ""
            if "_MT_" not in url and not name.startswith("MT "):
                continue
            if url in seen_urls:
                continue
            seen_urls.add(url)
            out["items"].append({
                "dataset": ds,
                "resource_id": res.get("id"),
                "name": name,
                "url": url,
                "format": res.get("format"),
                "turno_hint": turno_hint(name, url),
            })
    out["items"].sort(key=lambda item: item["url"])
    with open("scripts/inventory_mt_2000_2026.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, sort_keys=True, indent=2)
        fh.write("\n")
    print(f"inventário: {len(out['items'])} recursos MT")


if __name__ == "__main__":
    sys.exit(main())
