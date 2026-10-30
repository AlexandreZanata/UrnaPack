#!/usr/bin/env python3
"""Empacota uma seleção explícita de artefatos, sem incluir fontes implicitamente."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

from acquire_2026 import hashes, safe_path, write_json
from validate import load_limits

INVENTORY = "_inventory.json"


def verify_bundle(path, records, buffer):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or set(names) != set(records):
            raise ValueError("inventário do ZIP diverge da seleção")
        for name, expected in records.items():
            digest, count = hashlib.sha256(), 0
            with archive.open(name) as stream:
                while block := stream.read(buffer):
                    count += len(block)
                    digest.update(block)
            if count != expected["bytes"] or digest.hexdigest() != expected["sha256"]:
                raise ValueError("bytes/SHA-256 de membro divergentes: " + name)


def package(root, output, include, scope, limits):
    if output.resolve().is_relative_to(root.resolve()):
        raise ValueError("saída dentro da origem recusada")
    if not include or len(include) != len(set(include)):
        raise ValueError("seleção vazia ou repetida")
    selected = {}
    for relative in include:
        path = safe_path(root, relative)
        if not path.exists():
            raise ValueError("seleção ausente: " + relative)
        paths = sorted(path.rglob("*")) if path.is_dir() else [path]
        for item in paths:
            name = item.relative_to(root).as_posix()
            safe_path(root, name)
            if item.is_dir():
                continue
            if not item.is_file() or name in selected or name == INVENTORY:
                raise ValueError("membro não regular, reservado ou selecionado duas vezes")
            selected[name] = item
    if not selected:
        raise ValueError("seleção sem arquivos")
    output.mkdir(parents=True, exist_ok=False)
    receipt = {"format_version": 1, "success": False, "scope": scope,
               "include": include, "guarantee": "relative-paths-and-file-bytes",
               "python_version": sys.version,
               "implementation_sha256": {str(p.name): hashes(p, limits["IO_BUFFER_BYTES"])["sha256"] for p in
                   (Path(__file__).resolve(), Path(__file__).with_name("acquire_2026.py"),
                    Path(__file__).with_name("validate.py"), Path(__file__).with_name("limits.env"))},
               "limitations": "Os arquivos selecionados são artefatos derivados; empacotá-los sem perdas não restaura os dados originais dos quais foram calculados. Diretórios vazios e metadados do sistema de arquivos não são preservados."}
    try:
        records = {name: {k: v for k, v in hashes(path, limits["IO_BUFFER_BYTES"]).items()
                          if k in ("bytes", "sha256")} for name, path in selected.items()}
        inventory = json.dumps(dict({k: v for k, v in receipt.items() if k != "success"}, files=records), ensure_ascii=False, sort_keys=True, indent=2).encode()+b"\n"
        partial = output/"resultados-auditoria-2026.zip.partial"
        with zipfile.ZipFile(partial, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, path in sorted(selected.items()):
                archive.write(path, name)
            archive.writestr(INVENTORY, inventory)
        verify_bundle(partial, dict(records, **{INVENTORY: {"bytes": len(inventory), "sha256": hashlib.sha256(inventory).hexdigest()}}), limits["IO_BUFFER_BYTES"])
        if partial.stat().st_size > limits["MAX_RELEASE_ASSET_BYTES"]:
            raise ValueError("asset excede limite centralizado; parcial preservado")
        final = output/"resultados-auditoria-2026.zip"
        partial.rename(final)
        receipt.update(success=True, files=records, release_asset=hashes(final, limits["IO_BUFFER_BYTES"]))
    except Exception as exc:
        receipt["error"] = f"{type(exc).__name__}: {exc}"
    write_json(output/"package-results.json", receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include", nargs="+", required=True)
    parser.add_argument("--scope", required=True)
    args = parser.parse_args()
    report = package(args.input, args.output, args.include, args.scope, load_limits(Path(__file__).resolve().parents[1]))
    print(json.dumps({k: report.get(k) for k in ("success", "release_asset", "error")}, ensure_ascii=False))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
