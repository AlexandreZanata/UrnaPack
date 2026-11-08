#!/usr/bin/env python3
"""Inspeção reproduzível do erro de quoting no BU web 2020 t1 MT.

Não modifica bytes originais. Localiza o registro com NM_VOTAVEL
`ELIEL ROCHA " O GORDINHO"` (aspa simples não escapada como `""`),
informa ordinal, offset em bytes, SHA-256 do ZIP/membro e o trecho bruto.
Falha explicitamente (exit 1) se o padrão não for encontrado ou se o
layout divergir do esperado.
"""
import hashlib
import argparse
import csv
import io
import json
from pathlib import Path
import sys
import zipfile
from acquire_2026 import hashes
from validate import load_limits

ZIP = "/data/urnapack/brutos/2020/MT/bweb_1t_MT_181120201549.zip"
MEMBER = "bweb_1t_MT_181120201549.csv"
NEEDLE = b'ELIEL ROCHA " O GORDINHO""'


def locate(raw, needle=NEEDLE):
    """Retorna offset e índice de linha de dados por LF (não ordinal CSV)."""
    offset = raw.find(needle)
    if offset < 0:
        return None, None
    line_start = raw.rfind(b"\n", 0, offset) + 1
    ordinal = raw.count(b"\n", 0, line_start)
    return offset, ordinal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, default=Path(ZIP))
    parser.add_argument("--member", default=MEMBER)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output and (args.output.exists() or args.output.is_symlink()):
        raise ValueError("saída existente; preserve a inspeção anterior")
    limits = load_limits(Path(__file__).resolve().parents[1])
    measured = hashes(args.zip, limits["IO_BUFFER_BYTES"])
    if measured["bytes"] > limits["MAX_SOURCE_FILE_BYTES"]:
        raise ValueError("MAX_SOURCE_FILE_BYTES excedido")
    try:
        zf = zipfile.ZipFile(args.zip)
    except Exception as exc:
        print(f"ERRO: abrir {args.zip}: {exc}", file=sys.stderr)
        return 2
    with zf:
        try:
            selected = [i for i in zf.infolist() if i.filename == args.member]
            if len(selected) != 1:
                raise KeyError("membro ausente/duplicado")
            info = selected[0]
        except KeyError:
            print(f"ERRO: membro ausente/duplicado: {args.member}", file=sys.stderr)
            return 2
        if info.file_size > limits["MAX_ZIP_MEMBER_BYTES"]:
            raise ValueError("MAX_ZIP_MEMBER_BYTES excedido")
        raw = zf.read(info)
    member_sha = hashlib.sha256(raw).hexdigest()
    offset, ordinal = locate(raw)
    if offset is None:
        print("ERRO: padrão de quoting não encontrado; arquivo pode ter mudado", file=sys.stderr)
        return 1
    # ordinal: conta LF até o início da linha (arquivo usa LF)
    line_start = raw.rfind(b"\n", 0, offset) + 1
    reader = csv.reader(io.StringIO(raw.decode("latin1"), newline=""), delimiter=";", strict=True)
    accepted = 0
    error = None
    try:
        next(reader)
        for _ in reader:
            accepted += 1
    except csv.Error as exc:
        error = str(exc)
    if error is None:
        print("ERRO: padrão presente, mas parser estrito não reprovou; não afirmar erro de quoting", file=sys.stderr)
        return 1
    result = {"format_version": 1, "zip": str(args.zip), "source": measured,
        "member": args.member, "member_bytes": len(raw), "member_sha256": member_sha,
        "pattern_offset_bytes": offset, "pattern_physical_line": ordinal+1,
        "strict_records_accepted": accepted, "strict_error_next_record_ordinal": accepted+1,
        "strict_error_physical_line": reader.line_num, "strict_error": error,
        "raw_excerpt_hex": raw[line_start:line_start+600].hex(),
        "scope": "Inspeção de padrão específico e primeiro erro do parser; sem corrigir bytes originais."}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x",encoding="utf8") as out:
            json.dump(result,out,ensure_ascii=False,sort_keys=True,indent=2);out.write("\n")
    print(f"zip: {args.zip}")
    print(f"zip_sha256: {measured['sha256']}")
    print(f"zip_bytes: {measured['bytes']}")
    print(f"membro: {args.member} ({len(raw)} bytes, sha256={member_sha})")
    print(f"offset_bytes: {offset}")
    print(f"linha_fisica: {ordinal + 1} (header=1)")
    print(f"registro_ordinal_primeiro_erro: {accepted+1} (calculado pelo parser, exclui header)")
    print(f"trecho: {raw[line_start:line_start+600]!r}")
    print("diagnostico: NM_VOTAVEL contém aspa dupla isolada; parser estrito "
          f"reprova após {accepted} registros aceitos, erro={error!r}. "
          "Bytes preservados; nenhuma correção aplicada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
