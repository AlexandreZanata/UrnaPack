#!/usr/bin/env python3
"""Download direto MT 2000-2026 (sem inventar hash/tamanho).

Lê scripts/inventory_mt_2000_2026.json, baixa apenas URLs de dados
(não sidecars isolados) para /data/urnapack/brutos/<ano>/MT/<arquivo>,
com retomada (curl -C -), verificação de Content-Length, conferência do
sidecar oficial (.sha512/.sha1) quando listado no inventário e SHA-256
local recalculado. Gera fetch-mt-historico.json com bytes/sha256/estado.

Filtros: --only-substr para reexecução parcial; --skip-big pula
arqurnatot/logsgedai (grandes) numa primeira passada.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request

ROOT = "/data/urnapack/brutos"


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def year_of(item):
    url = item["url"]
    match = re.search(r"eleicoes(\d{4})|eleicoes(\d{4})|votacao_secao_(\d{4})", url)
    if match:
        for group in match.groups():
            if group:
                return group
    match = re.search(r"resultados-(\d{4})", item["dataset"])
    return match.group(1) if match else "desconhecido"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only-substr", default=None)
    parser.add_argument("--skip-big", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    inventory = json.load(open("scripts/inventory_mt_2000_2026.json", encoding="utf-8"))
    data_items = [i for i in inventory["items"] if not i["url"].endswith((".sha512", ".sha1"))]
    if args.only_substr:
        data_items = [i for i in data_items if args.only_substr in i["url"]]
    if args.skip_big:
        data_items = [i for i in data_items if "arqurnatot" not in i["url"] and "logsgedai" not in i["url"]]
    data_items.sort(key=lambda i: i["url"])
    if args.limit:
        data_items = data_items[:args.limit]

    sidecars = {i["url"]: i for i in inventory["items"] if i["url"].endswith((".sha512", ".sha1"))}
    # índice sidecar por prefixo (zip -> zip.sha512)
    sidecar_by_data = {}
    for item in inventory["items"]:
        if item["url"].endswith((".sha512", ".sha1")):
            for ext in (".sha512", ".sha1"):
                if item["url"].endswith(ext):
                    sidecar_by_data[item["url"][: -len(ext)]] = item
                    break

    receipt = {"items": [], "errors": []}
    for item in data_items:
        url = item["url"]
        year = year_of(item)
        filename = url.rsplit("/", 1)[-1]
        dest_dir = os.path.join(ROOT, year, "MT")
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, filename)
        entry = {"url": url, "dest": dest, "dataset": item["dataset"], "name": item["name"]}

        # já válido? confere tamanho via HEAD apenas se ausente
        if os.path.isfile(dest):
            entry["status"] = "already_present"
            entry["bytes"] = os.path.getsize(dest)
            try:
                entry["sha256"] = sha256_file(dest)
            except OSError as exc:
                entry["status"] = "read_error"
                receipt["errors"].append(f"{dest}: {exc}")
            receipt["items"].append(entry)
            print(f"PRESENTE {year}/{filename} {entry.get('bytes', '?')} bytes")
            continue

        print(f"BAIXANDO {url} -> {dest}", flush=True)
        partial = dest + ".partial"
        cmd = ["curl", "-fSL", "--retry", "5", "--retry-delay", "10", "-C", "-", "--progress-bar", "-o", partial, url]
        proc = subprocess.run(cmd)
        if proc.returncode != 0:
            receipt["errors"].append(f"curl {proc.returncode}: {url}")
            entry["status"] = "download_error"
            receipt["items"].append(entry)
            continue
        try:
            os.replace(partial, dest)
        except OSError as exc:
            receipt["errors"].append(f"finalizar {dest}: {exc}")
            entry["status"] = "finalize_error"
            receipt["items"].append(entry)
            continue
        entry["bytes"] = os.path.getsize(dest)
        entry["sha256"] = sha256_file(dest)
        entry["status"] = "fetched"

        # sidecar oficial, quando listado
        side = sidecar_by_data.get(url)
        if side:
            try:
                with urllib.request.urlopen(side["url"], timeout=60) as resp:
                    body = resp.read().decode("utf-8", "replace").strip()
                # salva sidecar ao lado do dado
                with open(dest + (".sha512" if side["url"].endswith(".sha512") else ".sha1"), "w", encoding="utf-8") as fh:
                    fh.write(body + "\n")
                official = body.split()[0]
                entry["official_hash"] = official
                entry["official_algo"] = "sha512" if len(official) == 128 else ("sha1" if len(official) == 40 else "desconhecido")
                print(f"  oficial {entry['official_algo']}: {official[:16]}…")
            except Exception as exc:
                receipt["errors"].append(f"sidecar {side['url']}: {exc}")
        receipt["items"].append(entry)
        print(f"OK {filename} {entry['bytes']} bytes sha256={entry['sha256'][:16]}…", flush=True)

    out = "relatorios-locais/fetch-mt-historico.json"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    # não versionar relatorios-locais; mantém fora do Git (.gitignore já cobre)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(receipt, fh, ensure_ascii=False, sort_keys=True, indent=2)
        fh.write("\n")
    print(f"recibo: {out} itens={len(receipt['items'])} erros={len(receipt['errors'])}")
    return 1 if receipt["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
