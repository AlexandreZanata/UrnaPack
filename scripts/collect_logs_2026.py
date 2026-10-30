#!/usr/bin/env python3
"""Prepara manifesto explícito para consolidação Rust, sem somar resultados.

Passe os diretórios de importação escolhidos, um por UF. Duplicatas reprovam;
não escolhe silenciosamente uma tentativa mais recente. Diagnósticos podem
ser consolidados, mas a análise Rust impede classificá-los como sucesso.
"""
import argparse
import json
from pathlib import Path

from acquire_2026 import hashes, limits_at, write_json


def collect(directories, official, buffer):
    ufs, inputs = set(), []
    def reference(path):
        measured = hashes(path, buffer)
        return {"path": str(path.resolve()), "bytes": measured["bytes"], "sha256": measured["sha256"]}
    for directory in directories:
        receipt = json.loads((directory / "import-run.json").read_text())
        uf = receipt["uf"]
        if uf in ufs:
            raise ValueError("UF duplicada; escolha explicitamente uma tentativa")
        ufs.add(uf)
        if not receipt["stream_complete"]:
            raise ValueError("fluxo incompleto; não consolidar relatório inexistente")
        analysis = directory / "analysis.json"
        actual = reference(analysis)
        expected = receipt["outputs"]["analysis.json"]
        if actual["sha256"] != expected["sha256"] or actual["bytes"] != expected["bytes"]:
            raise ValueError("relatório diverge do recibo de importação")
        inputs.append(actual)
    return {"format_version": 1, "official": reference(official), "inputs": inputs}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--directories", nargs="+", type=Path, required=True)
    p.add_argument("--official", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        raise ValueError("manifesto de saída já existe")
    result = collect(args.directories, args.official, limits_at(Path(__file__).with_name("limits.env"))["IO_BUFFER_BYTES"])
    write_json(args.output, result)


if __name__ == "__main__":
    main()
