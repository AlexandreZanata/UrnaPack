#!/usr/bin/env python3
"""Comprime somente os CSVs selecionados; verifica TAR, restauração e ZIP externo.

Todos os codecs, selos e verificações de restauração usam o núcleo Rust já
existente. ZIP externo é um invólucro padrão, com payload interno comprimido;
não é um novo formato UPK. Os ZIPs originais do TSE não são incluídos.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

from acquire_2026 import hashes, write_json
from validate import load_limits


def check_selection(actual, expected, root):
    if expected["format_version"] != 1 or not expected["inputs"]:
        raise ValueError("manifesto analítico incompatível/vazio")
    if any(row["file_type"] != "csv" for row in actual["files"]):
        raise ValueError("a seleção BU web deve conter somente CSVs")
    wanted = {}
    for row in expected["inputs"]:
        path = Path(row["path"]).resolve()
        relative = path.relative_to(root.resolve()).as_posix()
        if relative in wanted:
            raise ValueError("seleção contém caminho duplicado")
        wanted[relative] = (row["bytes"], row["sha256"])
    measured = {row["path"]: (row["size"], row["sha256"]) for row in actual["files"]}
    if len(measured) != len(actual["files"]) or measured != wanted:
        raise ValueError("inventário/tamanho/SHA-256 difere dos CSVs selecionados; sem descartar extras")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--expected-manifest", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--binary", type=Path, default=Path("target/release/tsepack"))
    p.add_argument("--method", choices=["zstd-3", "zstd-9", "zstd-19"], default="zstd-19")
    args = p.parse_args()
    limits = load_limits(Path(__file__).resolve().parents[1])
    if min(limits["IO_BUFFER_BYTES"], limits["MAX_RELEASE_ASSET_BYTES"]) <= 0:
        raise ValueError("limites de buffer/asset inválidos")
    args.output.mkdir(parents=True, exist_ok=False)
    commands = []
    receipt = {"format_version": 1, "success": False, "commands": commands,
               "scope": "CSVs selecionados do BU web, comprimidos com restauração dos bytes; não inclui os ZIPs originais do TSE.",
               "binary": {"path": str(args.binary.resolve()), **hashes(args.binary, limits["IO_BUFFER_BYTES"])},
               "expected_manifest_sha256": hashes(args.expected_manifest, limits["IO_BUFFER_BYTES"])["sha256"]}
    try:
        def run(*arguments):
            command = [str(args.binary.resolve()), *map(str, arguments)]
            index = len(commands)
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            log = args.output / f"command-{index:02d}.txt"
            log.write_text(result.stdout)
            commands.append({"argv": command, "exit_code": result.returncode, "log": log.name,
                             "log_sha256": hashes(log, limits["IO_BUFFER_BYTES"])["sha256"]})
            if result.returncode:
                raise ValueError(f"comando Rust reprovado: {arguments[0]}; consulte {log}")

        original = args.output / "audit-input.json"
        shutil.copyfile(args.expected_manifest, original)
        source = args.output / "source-manifest.json"
        run("inspect", "--input", args.input, "--manifest", source, "--source", args.source)
        selected = json.loads(source.read_text())
        check_selection(selected, json.loads(original.read_text()), args.input)
        tar = args.output / "csvs.tar"
        encoded = args.output / "csvs.tar.zst"
        archive = args.output / "archive"
        restored = args.output / "restored"
        run("archive", "tar", "--input", args.input, "--manifest", source, "--output", tar)
        run("codec", "compress", "--input", tar, "--output", encoded, "--method", args.method)
        run("archive", "seal", "--input", encoded, "--codec", args.method, "--manifest", source, "--output", archive)
        run("archive", "verify", "--input", archive)
        run("restore", "--dataset", archive, "--output", restored)
        run("verify", "--manifest", source, "--source", restored)
        # Verificação adicional realmente lê cada arquivo restaurado nesta automação.
        restored_records = []
        for row in selected["files"]:
            measured = hashes(restored / row["path"], limits["IO_BUFFER_BYTES"])
            if (measured["bytes"], measured["sha256"]) != (row["size"], row["sha256"]):
                raise ValueError("arquivo restaurado diverge do manifesto de origem")
            restored_records.append({"path": row["path"], "bytes": measured["bytes"], "sha256": measured["sha256"]})
        members = {"audit-input.json": original}
        for path in sorted(archive.iterdir()):
            if not path.is_file() or path.is_symlink():
                raise ValueError("arquivo selado contém membro não regular")
            members["archive/" + path.name] = path
        partial = args.output / "buweb-csv-comprimido.zip.partial"
        with zipfile.ZipFile(partial, "x", compression=zipfile.ZIP_STORED) as bundle:
            for name, path in members.items():
                bundle.write(path, name)
        bundle_records = {}
        with zipfile.ZipFile(partial) as bundle:
            names = bundle.namelist()
            if len(set(names)) != len(names) or set(names) != set(members):
                raise ValueError("inventário do ZIP externo diverge")
            for name, path in members.items():
                h, count = hashlib.sha256(), 0
                with bundle.open(name) as stream:
                    while block := stream.read(limits["IO_BUFFER_BYTES"]):
                        h.update(block)
                        count += len(block)
                measured = hashes(path, limits["IO_BUFFER_BYTES"])
                if (count, h.hexdigest()) != (measured["bytes"], measured["sha256"]):
                    raise ValueError("membro do ZIP externo diverge dos bytes selados")
                bundle_records[name] = {"bytes": count, "sha256": h.hexdigest()}
        output = args.output / "buweb-csv-comprimido.zip"
        if partial.stat().st_size > limits["MAX_RELEASE_ASSET_BYTES"]:
            raise ValueError("asset excede o limite centralizado; invólucro parcial preservado")
        partial.rename(output)
        receipt.update(success=True, selected_files=len(selected["files"]),
                       selected_csv_bytes=sum(row["size"] for row in selected["files"]),
                       restored_files=restored_records, bundle_members=bundle_records,
                       payload=hashes(archive / "payload.tar.encoded", limits["IO_BUFFER_BYTES"]),
                       release_asset={"file": output.name, **hashes(output, limits["IO_BUFFER_BYTES"])},
                       codec=args.method, guarantee="relative-paths-and-file-bytes",
                       limitations=["O invólucro ZIP contém um arquivo UrnaPack v2 com payload comprimido e proveniência; não inclui o acervo de ZIPs originais.",
                                    "A identidade se refere aos CSVs selecionados, não aos contêineres ZIP ou à autenticidade eleitoral.",
                                    "Recibos/caminhos/tempos podem variar entre ambientes; não há promessa de hash idêntico para todo o invólucro."])
    except Exception as exc:
        receipt["error"] = f"{type(exc).__name__}: {exc}"
    write_json(args.output / "package-run.json", receipt)
    print(json.dumps({key: receipt.get(key) for key in ["success", "selected_files", "selected_csv_bytes", "release_asset", "error"]}, ensure_ascii=False))
    return 0 if receipt["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
