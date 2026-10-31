#!/usr/bin/env python3
"""Confere SHA-256 e CRC de cada membro declarado dos ZIPs, por ordinal.

Sem extração e sem deduplicação. Um arquivo ZIP aninhado é opaco nesta etapa;
seus bytes são conferidos pelo CRC externo. Assinaturas não são verificadas.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import zipfile

from acquire_2026 import hashes, now, safe_path, write_json
from validate import load_limits


def check_zip(path, limits):
    if path.stat().st_size > limits["MAX_AUDIT_FETCH_BYTES"]:
        raise ValueError("arquivo físico excede limite centralizado")
    member_count = directories = duplicate_names = read_bytes = declared = 0
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) > limits["MAX_AUDIT_LOG_OUTER_MEMBERS"]:
            raise ValueError("quantidade de membros excede limite centralizado")
        declared = sum(member.file_size for member in members)
        if declared > limits["MAX_AUDIT_ZIP_EXPANDED_BYTES"] or declared > path.stat().st_size * limits["MAX_ZIP_EXPANSION_RATIO"]:
            raise ValueError("expansão ZIP excede limite centralizado")
        frequencies = Counter(member.filename for member in members)
        duplicate_names = sum(count-1 for count in frequencies.values())
        for ordinal, member in enumerate(members):
            count = 0
            try:
                # ZipInfo, não nome: nomes repetidos não podem ocultar membros.
                with archive.open(member) as stream:
                    while block := stream.read(limits["IO_BUFFER_BYTES"]):
                        count += len(block)
                        read_bytes += len(block)
                        if read_bytes > limits["MAX_AUDIT_ZIP_EXPANDED_BYTES"]:
                            raise ValueError("bytes expandidos excedem limite")
                if count != member.file_size:
                    raise ValueError("tamanho expandido diverge do índice")
            except Exception as exc:
                raise ValueError(f"membro ordinal {ordinal}, nome {member.filename!r}: {exc}") from exc
            member_count += 1
            directories += int(member.is_dir())
    return {"members_crc_checked": member_count, "directory_members": directories,
            "duplicate_name_occurrences_preserved": duplicate_names,
            "declared_expanded_bytes": declared, "member_bytes_read": read_bytes}


def verify_item(item, root, cache, limits, validation_key):
    result = {"url": item["url"], "path": item["path"], "observed_at_utc": now()}
    try:
        path = safe_path(root, item["path"])
        if not path.is_file():
            return dict(result, status="source_missing")
        saved = json.loads(path.with_name(path.name+".receipt.json").read_text())
        measured = hashes(path, limits["IO_BUFFER_BYTES"])
        if saved["url"] != item["url"] or measured["sha256"] != saved["sha256"] or measured["bytes"] != saved["bytes"]:
            raise ValueError("fonte diverge do recibo de aquisição")
        result.update(source_sha256=measured["sha256"], source_bytes=measured["bytes"], validation_key=validation_key)
        cache_path = cache / (hashlib.sha256(item["url"].encode()).hexdigest()+".json")
        if cache_path.exists():
            prior = json.loads(cache_path.read_text())
            if prior.get("status") == "verified" and all(prior.get(k) == result[k] for k in ("source_sha256", "source_bytes", "validation_key")):
                return dict(prior, status="reused_crc_after_source_rehash", observed_at_utc=now())
        result.update(check_zip(path, limits))
        result["status"] = "verified"
        write_json(cache_path, result)
    except Exception as exc:
        result.update(status="error", error=f"{type(exc).__name__}: {exc}")
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--catalog", type=Path, required=True)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        raise ValueError("recibo de saída já existe")
    limits = load_limits(Path(__file__).resolve().parents[1])
    keys = ["MAX_AUDIT_FETCH_BYTES", "MAX_AUDIT_LOG_OUTER_MEMBERS", "MAX_AUDIT_ZIP_EXPANDED_BYTES", "MAX_ZIP_EXPANSION_RATIO", "IO_BUFFER_BYTES"]
    if any(limits[key] <= 0 for key in keys+["AUDIT_ZIP_INTEGRITY_WORKERS"]):
        raise ValueError("limite inválido")
    script_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    validation_key = hashlib.sha256(json.dumps({"script_sha256": script_hash, "python": sys.version,
        "limits": {key: limits[key] for key in keys}}, sort_keys=True).encode()).hexdigest()
    raw = args.catalog.read_bytes()
    catalog = json.loads(raw)
    if catalog["format_version"] != 1:
        raise ValueError("catálogo incompatível")
    selected = [item for item in catalog["items"] if item["url"].lower().endswith(".zip")]
    if not selected or len({item["url"] for item in selected}) != len(selected):
        raise ValueError("seleção vazia ou com URL repetida")
    report = {"format_version": 1, "catalog_sha256": hashlib.sha256(raw).hexdigest(),
              "started_at_utc": now(), "selected_zip_resources": len(selected),
              "nonzip_resources_not_crc_checked": len(catalog["items"])-len(selected),
              "validation_key": validation_key, "items": [], "complete": False,
              "scope": "SHA-256 dos arquivos + CRC dos membros declarados dos ZIPs externos; opacos aninhados não decodificados aqui. Não verifica autenticidade/assinaturas."}
    args.cache.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=limits["AUDIT_ZIP_INTEGRITY_WORKERS"]) as pool:
        futures = [pool.submit(verify_item, item, args.root, args.cache, limits, validation_key) for item in selected]
        for future in as_completed(futures):
            result = future.result()
            report["items"].append(result)
            write_json(args.output, report)
            print(result["status"], result["url"].rsplit("/",1)[-1], result.get("error", ""), flush=True)
    report.update(finished_at_utc=now(), complete=all(item["status"] in ("verified", "reused_crc_after_source_rehash") for item in report["items"]))
    write_json(args.output, report)
    return 0 if report["complete"] else 1


if __name__ == "__main__":
    sys.exit(main())
