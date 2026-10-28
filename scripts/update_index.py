#!/usr/bin/env python3
"""Atualiza data/index.json com uma entrada de dataset publicado.

Recusa duplicatas (mesma tupla ano/turno/UF/tipo/versão) e grava o índice
ordenado de forma determinística. Usado por .github/workflows/publish-data.yml
somente após re-verificação dos assets publicados.
"""

import argparse
import datetime
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from validate import TAG_RE  # noqa: E402


def parse_asset(spec):
    name, url, sha256, size = spec.split(",", 3)
    return {"name": name, "url": url, "sha256": sha256,
            "size_bytes": int(size)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", required=True)
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--round", type=int, choices=[1, 2], required=True)
    ap.add_argument("--state", required=True)
    ap.add_argument("--type", dest="dtype", required=True,
                    choices=["bu", "rdv", "logs", "resultados", "metadata"])
    ap.add_argument("--version", required=True)
    ap.add_argument("--release-tag", required=True)
    ap.add_argument("--manifest-url", required=True)
    ap.add_argument("--manifest-sha256", required=True)
    ap.add_argument("--asset", action="append", default=[])
    ap.add_argument("--published-at", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not TAG_RE.match(args.release_tag):
        sys.exit(f"release_tag fora do padrão: {args.release_tag}")

    with open(args.index) as f:
        idx = json.load(f)

    key = (args.year, args.round, args.state, args.dtype, args.version)
    for d in idx.get("datasets", []):
        existing = (d["election_year"], d["round"], d["state"],
                    d["dataset_type"], d["version"])
        if existing == key:
            sys.exit(f"entrada duplicada recusada: {key} (nunca sobrescrever)")

    idx.setdefault("datasets", []).append({
        "election_year": args.year,
        "round": args.round,
        "state": args.state,
        "dataset_type": args.dtype,
        "version": args.version,
        "release_tag": args.release_tag,
        "assets": [parse_asset(a) for a in args.asset],
        "manifest_url": args.manifest_url,
        "manifest_sha256": args.manifest_sha256,
        "validation_state": "published",
        "published_at": args.published_at
        or datetime.datetime.now(datetime.timezone.utc).isoformat(),
    })
    idx["datasets"].sort(key=lambda d: (
        d["election_year"], d["round"], d["state"],
        d["dataset_type"], d["version"]))

    out = json.dumps(idx, indent=2, ensure_ascii=False) + "\n"
    if args.dry_run:
        print(out)
    else:
        with open(args.index, "w") as f:
            f.write(out)
        print(f"índice atualizado: {args.release_tag}")


if __name__ == "__main__":
    main()
