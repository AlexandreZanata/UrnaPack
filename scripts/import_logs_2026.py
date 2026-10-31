#!/usr/bin/env python3
"""Entrega logs originais ao analisador Rust por frames, sem expandir todo o SSD.

Cada corpo é o membro texto original, com tamanho e SHA-256 recalculados.
Índice de todos os membros externos e proveniência dos corpos ficam em gzip
determinístico (mtime=0). Não deduplica linhas, arquivos ou seções.
"""
import argparse
import csv
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile

from acquire_2026 import hashes, limits_at, safe_path, write_json

LOG_LIMIT_KEYS = ("MAX_AUDIT_LOG_OUTER_MEMBERS", "MAX_AUDIT_LOG_NESTING")
LOG_NAME = re.compile(r"^o03221([a-z]{2})(\d{5})(\d{4})(\d{4})-log(?:sa)?\.jez$", re.I)


def load_limits(path):
    result = limits_at(path)
    for line in Path(path).read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            if key in LOG_LIMIT_KEYS:
                result[key] = int(value)
    if any(result.get(key, 0) <= 0 for key in LOG_LIMIT_KEYS):
        raise ValueError("limites de log ausentes/inválidos")
    return result


def section_key(uf, municipality, zone, section):
    numbers = [int(municipality), int(zone), int(section)]
    if any(value < 0 for value in numbers):
        raise ValueError("identificador geográfico negativo")
    return f"{uf}/{numbers[0]:05d}/{numbers[1]:04d}/{numbers[2]:04d}"


def expected_sections(path, uf):
    expected = {}
    with path.open(newline="") as stream:
        for row in csv.DictReader(stream):
            if row["SG_UF"] != uf:
                continue
            key = section_key(uf, row["CD_MUNICIPIO"], row["NR_ZONA"], row["NR_SECAO"])
            if key in expected:
                raise ValueError("colisão de chave geográfica na exportação")
            expected[key] = int(row["QT_COMPARECIMENTO"])
    if not expected:
        raise ValueError("nenhuma seção presidencial para a UF solicitada")
    return expected


def shift(policy, uf, municipality):
    if policy["format_version"] != 1:
        raise ValueError("versão de política desconhecida")
    key = f"{uf}/{int(municipality):05d}"
    return policy["municipality_overrides"].get(key, policy["brt_shift_seconds_by_uf"][uf])


def text_members(blob, limits, prefix="", depth=0):
    if depth > limits["MAX_AUDIT_LOG_NESTING"]:
        raise ValueError("limite de aninhamento de logs excedido")
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        infos = archive.infolist()
        if len(infos) > limits["MAX_ZIP_MEMBERS"] or len({info.filename for info in infos}) != len(infos):
            raise ValueError("índice interno excessivo ou com nomes duplicados")
        for info in sorted(infos, key=lambda info: info.filename):
            if info.is_dir():
                continue
            if info.file_size > limits["MAX_ZIP_MEMBER_BYTES"]:
                raise ValueError("membro interno de log excede limite")
            name = prefix + info.filename
            body = archive.read(info)  # zipfile confere CRC e término do membro.
            if len(body) != info.file_size:
                raise ValueError("membro interno truncado")
            if info.filename.lower().endswith((".jez", ".zip")):
                yield from text_members(body, limits, name + "!", depth + 1)
            elif info.filename.lower().endswith(("logd.dat", ".log")):
                yield name, body
            else:
                raise ValueError(f"membro interno de log desconhecido, sem descarte: {name}")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--uf", required=True)
    p.add_argument("--root", required=True, type=Path)
    p.add_argument("--catalog", required=True, type=Path)
    p.add_argument("--sections", required=True, type=Path)
    p.add_argument("--export-receipt", required=True, type=Path)
    p.add_argument("--policy", required=True, type=Path)
    p.add_argument("--out-dir", required=True, type=Path)
    p.add_argument("--binary", default="target/release/audit_logs_2026", type=Path)
    p.add_argument("--zero-sections", type=Path)
    p.add_argument("--limits", default=str(Path(__file__).with_name("limits.env")))
    args = p.parse_args()
    limits = load_limits(args.limits)
    catalog = json.loads(args.catalog.read_text())
    items = [item for item in catalog["items"] if item["url"].endswith(f"/bu_imgbu_logjez_rdv_vscmr_2026_2t_{args.uf}.zip")]
    if len(items) != 1:
        raise ValueError("recurso oficial da UF ausente ou ambíguo")
    item = items[0]
    source = safe_path(args.root, item["path"])
    saved = json.loads(source.with_name(source.name + ".receipt.json").read_text())
    actual = hashes(source, limits["IO_BUFFER_BYTES"])
    if actual["sha256"] != saved["sha256"] or actual["bytes"] != saved["bytes"]:
        raise ValueError("SHA-256/tamanho do ZIP oficial diverge do recibo")
    export = json.loads(args.export_receipt.read_text())
    sections_hash = hashes(args.sections, limits["IO_BUFFER_BYTES"])["sha256"]
    if sections_hash != export["sha256"] or args.sections.stat().st_size != export["bytes"]:
        raise ValueError("SHA-256/tamanho da exportação de seções diverge")
    expected = expected_sections(args.sections, args.uf)
    if args.zero_sections:
        for row in json.loads(args.zero_sections.read_text())["rows"]:
            if row["SG_UF"] != args.uf:
                continue
            if row["CD_CARGO_PERGUNTA"] != "-1" or int(row["QT_COMPARECIMENTO"]) != 0 or int(row["QT_VOTOS"]) != 0:
                raise ValueError("seção adicional não é sentinela sem votantes")
            key = section_key(args.uf, row["CD_MUNICIPIO"], row["NR_ZONA"], row["NR_SECAO"])
            if key in expected:
                raise ValueError("sentinela duplica seção já esperada")
            expected[key] = 0
    policy_raw = args.policy.read_bytes()
    policy = json.loads(policy_raw)
    policy_hash = hashlib.sha256(policy_raw).hexdigest()
    args.out_dir.mkdir(parents=True, exist_ok=False)
    output = args.out_dir / "analysis.json"
    section_output = args.out_dir / "sections.csv"
    metadata_partial = args.out_dir / "members.jsonl.gz.partial"
    metadata_final = args.out_dir / "members.jsonl.gz"
    command = [str(args.binary.resolve()), "--output", str(output), "--sections-output", str(section_output)]
    receipt = {"format_version": 1, "source_url": item["url"], "source_zip_sha256": actual["sha256"],
               "source_zip_bytes": actual["bytes"], "policy_sha256": policy_hash,
               "sections_export_sha256": sections_hash, "command": command, "uf": args.uf,
               "signature_verified": False, "success": False, "stream_complete": False,
               "inputs_sha256": {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in
                                 [args.catalog, args.export_receipt, args.policy] + ([args.zero_sections] if args.zero_sections else [])}}
    receipt["binary"] = {"path": str(args.binary.resolve()), **hashes(args.binary, limits["IO_BUFFER_BYTES"])}
    receipt["python_version"] = sys.version
    receipt["implementation_sha256"] = {
        str(path.relative_to(Path(__file__).resolve().parents[1])): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in [Path(__file__).resolve(), Path(__file__).with_name("acquire_2026.py"),
                     Path(__file__).resolve().parents[1] / "src/bin/audit_logs_2026.rs",
                     Path(__file__).resolve().parents[1] / "src/audit_io.rs",
                     Path(args.limits).resolve()]}
    count, wire_bytes, wire_hash = 0, 0, hashlib.sha256()
    process = None
    try:
        with open(args.out_dir / "parser.stderr.txt", "wb") as errors, open(metadata_partial, "xb") as raw_metadata:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=errors)
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw_metadata, mtime=0) as metadata:
                def index_record(record):
                    metadata.write((json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode())

                def emit(record, body=b""):
                    nonlocal wire_bytes
                    header = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode()
                    for block in (header, body):
                        process.stdin.write(block)
                        wire_hash.update(block)
                        wire_bytes += len(block)

                with zipfile.ZipFile(source) as archive:
                    infos = archive.infolist()
                    if len(infos) > limits["MAX_AUDIT_LOG_OUTER_MEMBERS"] or len({info.filename for info in infos}) != len(infos):
                        raise ValueError("índice externo excessivo ou com nomes duplicados")
                    logs = []
                    for ordinal, info in enumerate(infos):
                        index_record({"kind": "outer_member", "ordinal": ordinal, "name": info.filename,
                                      "bytes": info.file_size, "crc32": f"{info.CRC:08x}"})
                        if info.filename.lower().endswith(("-log.jez", "-logsa.jez")):
                            match = LOG_NAME.fullmatch(Path(info.filename).name)
                            if not match or match[1].upper() != args.uf:
                                raise ValueError(f"nome/UF/pleito de log não reconhecido: {info.filename}")
                            key = section_key(args.uf, match[2], match[3], match[4])
                            logs.append((key, ordinal, info, match[2]))
                    if not logs:
                        raise ValueError("ZIP sem logs reconhecidos; não declarar sucesso")
                    receipt["outer_members"] = len(infos)
                    receipt["selected_log_containers"] = len(logs)
                    receipt["nonlog_members_indexed_not_interpreted"] = len(infos)-len(logs)
                    actual_keys = {entry[0] for entry in logs}
                    missing = sorted(set(expected)-actual_keys)
                    receipt["expected_sections"] = len(expected)
                    receipt["missing_expected_log_sections"] = missing
                    receipt["unexpected_log_sections"] = sorted(actual_keys-set(expected))
                    for key in missing:
                        index_record({"kind": "missing_expected_section", "section_key": key, "expected_turnout": expected[key]})
                    for key, ordinal, info, municipality in sorted(logs, key=lambda entry: (entry[0], entry[2].filename)):
                        if info.file_size > limits["MAX_ZIP_MEMBER_BYTES"]:
                            raise ValueError("pacote de log excede limite")
                        blob = archive.read(info)
                        for nested, body in text_members(blob, limits):
                            header = {"kind": "log", "format_version": 1, "section_key": key, "uf": args.uf,
                                      "expected_turnout": expected.get(key), "brt_shift_seconds": shift(policy, args.uf, municipality),
                                      "source_zip_url": item["url"], "source_zip_sha256": actual["sha256"],
                                      "source_member": info.filename, "nested_member": nested,
                                      "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
                            index_record(dict(header, source_member_ordinal=ordinal))
                            emit(header, body)
                            count += 1
                        if count and count % 100 == 0:
                            print(f"{args.uf}: {count} corpos texto enviados", flush=True)
                emit({"kind": "end", "format_version": 1, "files": count,
                      "expected_sections": len(expected),
                      "expected_section_keys_sha256": hashlib.sha256("".join(key+"\n" for key in sorted(expected)).encode()).hexdigest(),
                      "policy_sha256": policy_hash, "sections_export_sha256": sections_hash})
            process.stdin.close()
            code = process.wait()
            receipt.update(parser_exit_code=code, stream_complete=True, frames_sent=count,
                           wire_sha256=wire_hash.hexdigest(), wire_bytes=wire_bytes)
            if output.is_file():
                parsed = json.loads(output.read_text())
                if parsed["wire_sha256"] != wire_hash.hexdigest() or parsed["wire_bytes"] != wire_bytes:
                    raise ValueError("hash/tamanho do fluxo Python x Rust diverge")
                receipt["success"] = code == 0 and parsed["success"] is True
            os.rename(metadata_partial, metadata_final)
            receipt["members_manifest"] = {"file": metadata_final.name, **hashes(metadata_final, limits["IO_BUFFER_BYTES"])}
            receipt["outputs"] = {path.name: hashes(path, limits["IO_BUFFER_BYTES"])
                                  for path in (output, section_output) if path.is_file()}
    except Exception as exc:
        receipt["error"] = f"{type(exc).__name__}: {exc}"
        if process is not None:
            try:
                process.stdin.close()
            except (BrokenPipeError, OSError):
                pass
            process.wait(timeout=limits["FETCH_TIMEOUT_SECS"])
    write_json(args.out_dir / "import-run.json", receipt)
    print(f"{args.uf}: success={receipt['success']} frames={count} {receipt.get('error', '')}", flush=True)
    return 0 if receipt["success"] else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"importação reprovada: {exc}", file=sys.stderr)
        sys.exit(1)
