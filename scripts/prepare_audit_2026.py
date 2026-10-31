#!/usr/bin/env python3
"""Extrai CSVs de BU t2 verificados, sem alterar ZIPs nem descartar membros."""
import argparse
import json
import os
from pathlib import Path
import re
import sys
import zipfile

from acquire_2026 import hashes, limits_at, official_digest, safe_path, write_json

UFS = set("AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO ZZ".split())


def prepare(catalog, root, destination, evidence, limits):
    inputs, members, ufs = [], [], set()
    selected = [item for item in catalog["items"] if "/buweb/bweb_2t_" in item["url"] and item["url"].endswith(".zip")]
    for item in selected:
        filename = item["url"].rsplit("/", 1)[-1]
        match = re.fullmatch(r"bweb_2t_([A-Z]{2})_\d+\.zip", filename)
        if not match or match[1] in ufs:
            raise ValueError("nome de ZIP/UF duplicada ou não reconhecida")
        uf = match[1]
        ufs.add(uf)
        path = safe_path(root, item["path"])
        receipt = json.loads(path.with_name(path.name + ".receipt.json").read_text())
        measured = hashes(path, limits["IO_BUFFER_BYTES"])
        if measured["sha256"] != receipt["sha256"] or measured["bytes"] != receipt["bytes"]:
            raise ValueError(f"SHA-256/tamanho do ZIP diverge: {filename}")
        sidecar = path.with_name(path.name + ".sha512")
        if measured["sha512"] != official_digest(sidecar.read_bytes(), filename, "sha512"):
            raise ValueError(f"SHA-512 oficial diverge: {filename}")
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > limits["MAX_ZIP_MEMBERS"] or any(info.file_size > limits["MAX_ZIP_MEMBER_BYTES"] for info in infos):
                raise ValueError("membros ZIP excedem os limites centralizados")
            if len({info.filename for info in infos}) != len(infos):
                raise ValueError("membros ZIP com nomes repetidos; não sobrescrever")
            csvs = [info for info in infos if info.filename.lower().endswith(".csv")]
            if len(csvs) != 1:
                raise ValueError(f"esperado um CSV por UF, observado {len(csvs)}: {filename}")
            members.append({"zip_url": item["url"], "zip_sha256": measured["sha256"],
                            "all_members": [{"name": info.filename, "bytes": info.file_size,
                                             "crc32": f"{info.CRC:08x}"} for info in infos]})
            info = csvs[0]
            target = destination / uf / Path(info.filename).name
            target.parent.mkdir(parents=True, exist_ok=True)
            partial = target.with_name(target.name + ".partial")
            # Não reutilizar CSV existente sem confrontar novamente com o ZIP.
            import hashlib
            digest = hashlib.sha256()
            count = 0
            with archive.open(info) as source, open(partial, "wb") as output:
                while chunk := source.read(limits["IO_BUFFER_BYTES"]):
                    count += len(chunk)
                    digest.update(chunk)
                    output.write(chunk)
            if count != info.file_size:
                raise ValueError("membro ZIP truncado")
            if target.exists():
                current = hashes(target, limits["IO_BUFFER_BYTES"])
                if current["sha256"] != digest.hexdigest():
                    raise ValueError("CSV existente diverge; preservar ambos")
                partial.unlink()
            else:
                os.replace(partial, target)
            inputs.append({"path": str(target), "sha256": digest.hexdigest(), "bytes": count,
                           "uf": uf, "zip_sha256": measured["sha256"], "zip_url": item["url"], "member": info.filename})
            # Dicionário oficial preservado como evidência, sem modificar seu PDF.
            for other in infos:
                if other.filename == "_leiame-boletimurnaweb.pdf":
                    body = archive.read(other)
                    doc = evidence / (hashlib.sha256(body).hexdigest() + "-leiame-boletimurnaweb.pdf")
                    if not doc.exists():
                        doc.write_bytes(body)
        print(f"preparado {uf}: {count} bytes CSV", flush=True)
    if ufs != UFS:
        raise ValueError(f"cobertura incompleta/não reconhecida: ausentes={sorted(UFS-ufs)} extras={sorted(ufs-UFS)}")
    write_json(evidence / "membros-buweb.json", members)
    return {"format_version": 1, "inputs": inputs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--limits", default=str(Path(__file__).with_name("limits.env")))
    args = parser.parse_args()
    args.evidence.mkdir(parents=True, exist_ok=True)
    result = prepare(json.loads(args.catalog.read_text()), args.root, args.destination, args.evidence, limits_at(args.limits))
    write_json(args.manifest, result)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"preparação reprovada: {exc}", file=sys.stderr)
        sys.exit(1)
