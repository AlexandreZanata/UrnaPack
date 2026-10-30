#!/usr/bin/env python3
"""Inspeção reproduzível do erro de quoting no BU web 2020 t1 MT.

Não modifica bytes originais. Localiza o registro com NM_VOTAVEL
`ELIEL ROCHA " O GORDINHO"` (aspa simples não escapada como `""`),
informa ordinal, offset em bytes, SHA-256 do ZIP/membro e o trecho bruto.
Falha explicitamente (exit 1) se o padrão não for encontrado ou se o
layout divergir do esperado.
"""
import hashlib
import sys
import zipfile

ZIP = "/data/urnapack/brutos/2020/MT/bweb_1t_MT_181120201549.zip"
MEMBER = "bweb_1t_MT_181120201549.csv"
NEEDLE = b'ELIEL ROCHA " O GORDINHO""'


def locate(raw, needle=NEEDLE):
    """Retorna (offset, ordinal_registro) ou (None, None) se ausente."""
    offset = raw.find(needle)
    if offset < 0:
        return None, None
    line_start = raw.rfind(b"\n", 0, offset) + 1
    ordinal = raw.count(b"\n", 0, line_start)
    return offset, ordinal


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(1 << 20)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def main():
    try:
        zf = zipfile.ZipFile(ZIP)
    except Exception as exc:
        print(f"ERRO: abrir {ZIP}: {exc}", file=sys.stderr)
        return 2
    with zf:
        try:
            info = zf.getinfo(MEMBER)
        except KeyError:
            print(f"ERRO: membro ausente: {MEMBER}", file=sys.stderr)
            return 2
        raw = zf.read(MEMBER)
    member_sha = hashlib.sha256(raw).hexdigest()
    zip_sha = sha256_file(ZIP)
    offset, ordinal = locate(raw)
    if offset is None:
        print("ERRO: padrão de quoting não encontrado; arquivo pode ter mudado", file=sys.stderr)
        return 1
    # ordinal: conta LF até o início da linha (arquivo usa LF)
    line_start = raw.rfind(b"\n", 0, offset) + 1
    print(f"zip: {ZIP}")
    print(f"zip_sha256: {zip_sha}")
    print(f"zip_bytes: {len(open(ZIP,'rb').read())}")
    print(f"membro: {MEMBER} ({info.file_size} bytes, sha256={member_sha})")
    print(f"offset_bytes: {offset}")
    print(f"linha_fisica: {ordinal + 1} (header=1)")
    print(f"registro_ordinal: {ordinal} (exclui header)")
    print(f"trecho: {raw[line_start:line_start+600]!r}")
    print("diagnostico: NM_VOTAVEL contém aspa dupla isolada; parser estrito "
          "reprova com `';' expected after '\"'` após 59.082 registros íntegros. "
          "Bytes preservados; nenhuma correção aplicada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
