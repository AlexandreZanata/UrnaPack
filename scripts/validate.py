#!/usr/bin/env python3
"""Validação offline do UrnaPack: limites, nomes, schemas, manifestos, índice, segredos.

Sem dependências obrigatórias (stdlib). Se `jsonschema`/`yaml` estiverem
instalados, a validação é total; sem eles, aplica-se um subconjunto manual
documentado (campos obrigatórios, tipos, enums, regex).
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

UFS = """AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR
SC SP SE TO BR""".split()

PKG_RE = re.compile(r"^urnapack-\d{4}-t[12]-[A-Z]{2}-[a-z]+-\d{4}\.upk\.zst$")
TAG_RE = re.compile(r"^data-\d{4}-t[12]-[A-Z]{2}-v\d+$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")

SECRET_RES = [
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA |ENCRYPTED )?PRIVATE KEY-----"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{36}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
]

try:
    import jsonschema  # type: ignore

    HAVE_JSONSCHEMA = True
except ImportError:
    HAVE_JSONSCHEMA = False


def fail(msg, errors):
    errors.append(msg)
    return errors


def load_limits(root):
    vals = {}
    with open(os.path.join(root, "scripts", "limits.env")) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip()
    return {k: int(v) for k, v in vals.items()}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def tracked_files(root):
    """Arquivos versionados + não-ignorados ainda não commitados.

    Usa `git ls-files` (rastreados) mais `--others --exclude-standard`
    (novos, respeitando .gitignore). Fora de repo git, varre o disco.
    Retorna também a contagem via variável global para relatório.
    """
    try:
        tracked = subprocess.run(
            ["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True
        ).stdout.split(b"\0")
        others = subprocess.run(
            ["git", "ls-files", "-z", "--others", "--exclude-standard"],
            cwd=root, capture_output=True, check=True,
        ).stdout.split(b"\0")
        paths = [os.path.join(root, p.decode()) for p in tracked + others if p]
        print(f" verificado(s) {len(paths)} arquivo(s) contra limites/segredos")
        return paths
    except Exception:
        found = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in (".git", "target")]
            found += [os.path.join(dirpath, f) for f in filenames]
        return found


def check_schema(doc, schema_path, errors, label):
    with open(schema_path) as f:
        schema = json.load(f)
    if HAVE_JSONSCHEMA:
        try:
            jsonschema.validate(doc, schema)
        except Exception as e:  # noqa: BLE001 - report as validation error
            fail(f"{label}: fora do schema: {e.message}", errors)
    else:
        # Subconjunto manual: obrigatórios, tipos e enums principais.
        for key in schema.get("required", []):
            if key not in doc:
                fail(f"{label}: campo obrigatório ausente: {key}", errors)


def validate_manifest_doc(m, errors, label="manifest"):
    if m.get("format_version") != 1:
        fail(f"{label}: format_version incompatível: {m.get('format_version')}", errors)
    if m.get("state") not in UFS:
        fail(f"{label}: UF inválida: {m.get('state')}", errors)
    pkgs = m.get("packages", [])
    hashes = m.get("package_hashes", [])
    if [p.get("sha256") for p in pkgs] != hashes:
        fail(f"{label}: package_hashes divergem de packages[]", errors)
    if sum(p.get("records", 0) for p in pkgs) != m.get("record_counts"):
        fail(f"{label}: record_counts != soma de packages[].records", errors)
    for p in pkgs:
        if not PKG_RE.match(p.get("name", "")):
            fail(f"{label}: nome de pacote fora do padrão: {p.get('name')}", errors)
    return errors


def cmd_manifest(args):
    errors = []
    with open(args.manifest) as f:
        m = json.load(f)
    check_schema(m, os.path.join(ROOT, "spec", "manifest.schema.json"), errors, "manifest")
    validate_manifest_doc(m, errors)
    if args.require_status and m.get("verification_status") != args.require_status:
        fail(
            f"manifest: verification_status={m.get('verification_status')!r}, "
            f"exigido {args.require_status!r}",
            errors,
        )
    if args.data_root:
        if len(m.get("packages", [])) > args.max_assets:
            fail(f"manifest: pacotes acima do limite ({args.max_assets})", errors)
        for p in m.get("packages", []):
            ap = os.path.join(args.data_root, p["name"])
            if not os.path.isfile(ap):
                fail(f"manifest: pacote declarado ausente: {p['name']}", errors)
                continue
            size = os.path.getsize(ap)
            if size != p["size_bytes"]:
                fail(
                    f"manifest: tamanho diverge em {p['name']} "
                    f"(manifesto {p['size_bytes']} x disco {size})",
                    errors,
                )
            if size > args.max_bytes:
                fail(f"manifest: {p['name']} acima do limite ({args.max_bytes})", errors)
            actual = sha256_file(ap)
            if actual != p["sha256"]:
                fail(f"manifest: SHA-256 diverge em {p['name']}", errors)
    return errors


def cmd_index(args):
    errors = []
    with open(args.index) as f:
        idx = json.load(f)
    check_schema(idx, os.path.join(ROOT, "spec", "index.schema.json"), errors, "index")
    seen = set()
    for d in idx.get("datasets", []):
        key = (d.get("election_year"), d.get("round"), d.get("state"),
               d.get("dataset_type"), d.get("version"))
        if key in seen:
            fail(f"index: entrada duplicada {key} (publicação duplicada?)", errors)
        seen.add(key)
        tag = d.get("release_tag", "")
        if not TAG_RE.match(tag):
            fail(f"index: release_tag fora do padrão: {tag}", errors)
        expect = f"data-{d.get('election_year')}-t{d.get('round')}-{d.get('state')}-{d.get('version')}"
        if tag != expect:
            fail(f"index: release_tag {tag} não confere com {expect}", errors)
    return errors


def cmd_repo(args):
    errors = []
    root = args.root
    limits = load_limits(root)
    for path in tracked_files(root):
        rel = os.path.relpath(path, root)
        if rel.endswith((".upk", ".upk.zst")):
            fail(f"repo: pacote binário versionado no Git (proibido): {rel}", errors)
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        if size > limits["MAX_GIT_FILE_BYTES"]:
            fail(f"repo: arquivo acima do limite Git ({limits['MAX_GIT_FILE_BYTES']}): {rel}", errors)
        if size < 1024 * 1024 and os.path.splitext(path)[1] not in (
            ".png", ".jpg", ".zst", ".upk", ".ico", ".pdf", ".bin",
        ):
            try:
                with open(path, "r", errors="strict") as f:
                    text = f.read()
            except (UnicodeDecodeError, OSError):
                continue
            for rx in SECRET_RES:
                if rx.search(text):
                    fail(f"repo: possível segredo em {rel}", errors)
                    break
    for name in ("manifest.schema.json", "index.schema.json"):
        try:
            json.load(open(os.path.join(root, "spec", name)))
        except Exception as e:  # noqa: BLE001
            fail(f"repo: schema inválido {name}: {e}", errors)
    idx_path = os.path.join(root, "data", "index.json")
    if os.path.isfile(idx_path):
        ns = argparse.Namespace(index=idx_path)
        errors = cmd_index(ns)
    else:
        fail("repo: data/index.json ausente", errors)
    return errors


def expect(ok, label, results):
    results.append((label, ok))
    print(("PASS " if ok else "FAIL ") + label)


def stage_fixture(tmp, manifest_src, data_src=None, trunc=None):
    """Copia a fixture para tmp com o nome canônico do pacote.

    O manifesto-good é um template: descreve bytes reais (hash/tamanho
    verdadeiros de bu-amostra.csv); o arquivo é materializado em tmp com
    o nome canônico exigido pela convenção de pacotes.
    """
    m = json.load(open(manifest_src))
    name = m["packages"][0]["name"]
    if data_src is not None:
        data = open(data_src, "rb").read()
        if trunc is not None:
            data = data[:trunc]
        with open(os.path.join(tmp, name), "wb") as f:
            f.write(data)
    mp = os.path.join(tmp, "m.json")
    with open(mp, "w") as f:
        json.dump(m, f)
    return mp, tmp


def cmd_self_test(_args):
    fx = os.path.join(ROOT, "tests", "fixtures")
    data = f"{fx}/data/bu-amostra.csv"
    results = []

    def run_manifest(manifest, data_root=None, **kw):
        ns = argparse.Namespace(
            manifest=manifest, data_root=data_root,
            max_bytes=kw.get("max_bytes", 10**12),
            max_assets=kw.get("max_assets", 1000),
            require_status=kw.get("require_status"),
        )
        return cmd_manifest(ns)

    # 1. Manifesto correto + bytes reais -> aprova.
    with tempfile.TemporaryDirectory() as tmp:
        mp, _ = stage_fixture(tmp, f"{fx}/manifest-good.json", data)
        errs = run_manifest(mp, data_root=tmp)
    expect(errs == [], "manifesto correto aprova", results)

    # 2. Hash incorreto -> reprova explicitamente.
    with tempfile.TemporaryDirectory() as tmp:
        mp, _ = stage_fixture(tmp, f"{fx}/manifest-bad-hash.json", data)
        errs = run_manifest(mp, data_root=tmp)
    expect(any("SHA-256 diverge" in e for e in errs), "hash incorreto reprova", results)

    # 3. Arquivo ausente -> reprova explicitamente.
    with tempfile.TemporaryDirectory() as tmp:
        mp, _ = stage_fixture(tmp, f"{fx}/manifest-missing.json", None)
        errs = run_manifest(mp, data_root=tmp)
    expect(any("ausente" in e for e in errs), "arquivo ausente reprova", results)

    # 4. Versão incompatível -> reprova explicitamente.
    with tempfile.TemporaryDirectory() as tmp:
        mp, _ = stage_fixture(tmp, f"{fx}/manifest-bad-version.json", data)
        errs = run_manifest(mp, data_root=tmp)
    expect(any("incompatível" in e for e in errs), "versão incompatível reprova", results)

    # 5. Pacote truncado (tamanho declarado > real) -> reprova.
    with tempfile.TemporaryDirectory() as tmp:
        full = os.path.getsize(data)
        mp, _ = stage_fixture(tmp, f"{fx}/manifest-good.json", data,
                              trunc=full // 2)
        errs = run_manifest(mp, data_root=tmp)
    expect(any("tamanho diverge" in e for e in errs), "pacote truncado reprova", results)

    # 6. Pacote acima do limite -> reprova.
    with tempfile.TemporaryDirectory() as tmp:
        mp, _ = stage_fixture(tmp, f"{fx}/manifest-good.json", data)
        errs = run_manifest(mp, data_root=tmp, max_bytes=16)
    expect(any("acima do limite" in e for e in errs), "acima do limite reprova", results)

    # 7. Índice com entrada duplicada -> reprova.
    ns = argparse.Namespace(index=f"{fx}/index-dup.json")
    errs = cmd_index(ns)
    expect(any("duplicada" in e for e in errs), "índice duplicado reprova", results)

    # 8. Nome fora do padrão -> rejeitado; nome canônico -> aceito.
    expect(not PKG_RE.match("urnapack-2026-2-MT-bu-1.upk.zst"), "nome inválido rejeitado", results)
    expect(bool(PKG_RE.match("urnapack-2026-t2-MT-bu-0001.upk.zst")),
           "nome válido aceito", results)

    failed = [label for label, ok in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} cenários OK")
    return ["self-test: " + f for f in failed]


def main():
    ap = argparse.ArgumentParser(description="Validação offline do UrnaPack")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_repo = sub.add_parser("repo", help="valida o repositório")
    p_repo.add_argument("--root", default=ROOT)
    p_man = sub.add_parser("manifest", help="valida um manifesto de dataset")
    p_man.add_argument("manifest")
    p_man.add_argument("--data-root", default=None)
    p_man.add_argument("--max-bytes", type=int, default=10**12)
    p_man.add_argument("--max-assets", type=int, default=1000)
    p_man.add_argument("--require-status", default=None)
    p_idx = sub.add_parser("index", help="valida data/index.json")
    p_idx.add_argument("index")
    sub.add_parser("self-test", help="cenários de falha com fixtures")
    args = ap.parse_args()

    errors = {"repo": cmd_repo, "manifest": cmd_manifest, "index": cmd_index,
              "self-test": cmd_self_test}[args.cmd](args)
    for e in errors:
        print("ERRO:", e)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
