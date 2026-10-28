#!/usr/bin/env python3
"""Aquisição gerenciada de arquivos oficiais (Etapa 2, sem transformação).

Lê um manifesto de origem (v1/v2) com `url` por arquivo e materializa a árvore
em `--out-dir`: metadados HTTP capturados, retomada via `Range` com checkpoint
(`.partial`), conclusão atômica (rename só após SHA-256 e tamanho conferidos) e
recibo de execução determinístico (`fetch-run.json`, conforme
`spec/execution.schema.json`).

Falha explícita (exit ≠ 0), sem promover parcial como íntegro: hash divergente,
tamanho divergente, HTTP de erro, versão de manifesto não suportada, arquivo sem
URL, limite excedido ou saída inválida. Limites em `scripts/limits.env`.
"""

import argparse
import hashlib
import json
import os
import ntpath
import re
import stat
import tempfile
import urllib.parse
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_LIMITS = os.path.join(HERE, "limits.env")
SCRIPT_VERSION = "fetch-source-v1"

REQUIRED_LIMITS = [
    "MAX_FETCH_BYTES",
    "MAX_FETCH_REDIRECTS",
    "FETCH_TIMEOUT_SECS",
    "IO_BUFFER_BYTES",
]


def fail(msg, errors):
    errors.append(msg)
    return errors


def load_limits(path):
    if not os.path.isfile(path):
        raise SystemExit(f"limites ausentes: {path}")
    vals = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip()
    missing = [k for k in REQUIRED_LIMITS if k not in vals]
    if missing:
        raise SystemExit(f"limite desconhecido/ausente em {path}: {', '.join(missing)}")
    out = {}
    for k in REQUIRED_LIMITS:
        try:
            out[k] = int(vals[k])
        except ValueError:
            raise SystemExit(f"limite inválido em {path}: {k}={vals[k]!r}")
        if out[k] <= 0:
            raise SystemExit(f"limite inválido em {path}: {k} deve ser > 0")
    return out


def check_rel(rel):
    if not isinstance(rel, str) or not rel or "\x00" in rel or rel.startswith("/") or "\\" in rel or ntpath.splitdrive(rel)[0]:
        return f"caminho inválido no manifesto: {rel!r}"
    for seg in rel.split("/"):
        if seg in ("", ".", ".."):
            return f"caminho não canônico no manifesto: {rel!r}"
    return None


from validate import sha256_file


def safe_destination(root, rel):
    problem = check_rel(rel)
    if problem:
        raise ValueError(problem)
    current = root
    parts = rel.split("/")
    for index, part in enumerate(parts):
        current = os.path.join(current, part)
        if os.path.lexists(current):
            meta = os.lstat(current)
            if stat.S_ISLNK(meta.st_mode):
                raise ValueError(f"symlink interno recusado: {rel}")
            if index < len(parts)-1 and not stat.S_ISDIR(meta.st_mode):
                raise ValueError(f"componente não diretório: {rel}")
            if index == len(parts)-1 and not stat.S_ISREG(meta.st_mode):
                raise ValueError(f"arquivo especial recusado: {rel}")
    return current


class _RedirectCounter(urllib.request.HTTPRedirectHandler):
    def __init__(self, limit):
        self.limit = limit
        self.count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.count += 1
        if self.count > self.limit:
            raise urllib.error.HTTPError(newurl, code, "redirecionamentos acima do limite", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def build_opener(limits, timeout):
    counter = _RedirectCounter(limits["MAX_FETCH_REDIRECTS"])
    opener = urllib.request.build_opener(counter)
    opener.addheaders = [("User-Agent", "UrnaPack-fetch/1")]
    return opener, counter, timeout


def fetch_one(opener_counter_timeout, url, dest_final, expected_sha, expected_size, limits, errors):
    opener, counter, timeout = opener_counter_timeout
    entry = {"url": url, "status": None, "resumed": False, "range_ignored": False,
             "bytes": 0, "sha256": None, "http": {}}
    if expected_size < 0 or expected_size > limits["MAX_FETCH_BYTES"]:
        fail("tamanho esperado fora de MAX_FETCH_BYTES", errors)
        return entry, errors
    # Arquivo final já válido: não baixar de novo.
    if os.path.isfile(dest_final):
        try:
            if os.path.getsize(dest_final) == expected_size and sha256_file(dest_final) == expected_sha:
                entry.update({"status": "already_valid", "bytes": expected_size, "sha256": expected_sha})
                return entry, []
        except OSError as e:
            fail(f"erro de leitura em {dest_final}: {e}", errors)
            return entry, errors
        fail(f"destino existente divergente; bytes preservados: {dest_final}", errors)
        entry["status"] = "existing_mismatch"
        return entry, errors
    partial = dest_final + ".partial"
    offset = 0
    if os.path.isfile(partial):
        try:
            offset = os.path.getsize(partial)
        except OSError as e:
            fail(f"erro de leitura em {partial}: {e}", errors)
            return entry, errors
    if os.path.lexists(partial):
        meta = os.lstat(partial)
        if not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1 or offset > expected_size:
            fail("parcial inseguro ou maior que a origem esperada", errors)
            return entry, errors
    if offset == expected_size and os.path.isfile(partial):
        if sha256_file(partial) != expected_sha:
            fail("parcial completo divergente; bytes preservados", errors)
            return entry, errors
        os.replace(partial, dest_final)
        entry.update(status="resumed", resumed=True, bytes=offset, sha256=expected_sha)
        return entry, []
    req = urllib.request.Request(url)
    if offset > 0:
        req.add_header("Range", f"bytes={offset}-")
        entry["resumed"] = True
    try:
        resp = opener.open(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code == 416 and offset > 0:
            fail("HTTP 416: checkpoint não corresponde à origem; parcial preservado", errors)
            entry["status"] = "range_mismatch"
            return entry, errors
        else:
            fail(f"HTTP {e.code} em {url}: {e.reason}", errors)
            entry["status"] = "http_error"
            return entry, errors
    except Exception as e:  # noqa: BLE001 - erro de rede explícito
        fail(f"erro de rede em {url}: {e}", errors)
        entry["status"] = "network_error"
        return entry, errors
    with resp:
        status = resp.getcode()
        headers = {k.lower(): v for k, v in resp.getheaders()}
        entry["http"] = {k: headers[k] for k in ("content-length", "etag", "last-modified", "accept-ranges", "content-range") if k in headers}
        entry["final_url"] = resp.geturl()
        if offset > 0 and status == 200:
            # Servidor ignorou o intervalo: recomeçar, registrado (nunca anexar).
            entry["range_ignored"] = True
            try:
                os.remove(partial)
            except OSError:
                pass
            offset = 0
        elif offset > 0 and status != 206:
            fail(f"resposta inesperada {status} ao retomar {url}", errors)
            entry["status"] = "http_error"
            return entry, errors
        if status not in (200, 206):
            fail(f"resposta inesperada {status} em {url}", errors)
            entry["status"] = "http_error"
            return entry, errors
        if status == 206:
            match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", headers.get("content-range", ""))
            if not match:
                fail("Content-Range ausente ou inválido", errors)
                return entry, errors
            start, end, total = map(int, match.groups())
            if start != offset or end < start or end >= total or total != expected_size:
                fail("Content-Range não corresponde ao checkpoint/origem", errors)
                return entry, errors
        else:
            total = expected_size
        if total > limits["MAX_FETCH_BYTES"]:
            fail("MAX_FETCH_BYTES excedido", errors)
            return entry, errors
        if "content-length" in headers:
            length = int(headers["content-length"])
            wanted_length = end-start+1 if status == 206 else expected_size
            if length != wanted_length:
                fail("Content-Length diverge do tamanho esperado", errors)
                return entry, errors
        os.makedirs(os.path.dirname(dest_final), exist_ok=True)
        h = hashlib.sha256()
        if offset > 0:
            # Recomputa o hash do prefixo já em disco (não confia em checkpoint).
            try:
                with open(partial, "rb") as f:
                    for chunk in iter(lambda: f.read(1024 * 1024), b""):
                        h.update(chunk)
            except OSError as e:
                fail(f"erro de leitura em {partial}: {e}", errors)
                entry["status"] = "read_error"
                return entry, errors
        mode = "ab" if offset > 0 else "wb"
        try:
            with open(partial, mode) as f:
                while True:
                    chunk = resp.read(min(limits["IO_BUFFER_BYTES"], expected_size-offset+1))
                    if not chunk:
                        break
                    if offset + len(chunk) > expected_size:
                        fail("resposta excede o tamanho esperado", errors)
                        return entry, errors
                    h.update(chunk)
                    f.write(chunk)
                    offset += len(chunk)
                    if offset > limits["MAX_FETCH_BYTES"]:
                        fail(f"limite excedido durante {url} (> MAX_FETCH_BYTES)", errors)
                        entry["status"] = "limit_exceeded"
                        return entry, errors
        except Exception as e:  # noqa: BLE001 - interrupção preserva parcial p/ retomada
            fail(f"interrompido {url} em {offset} bytes: {e} (parcial preservado)", errors)
            entry["status"] = "interrupted"
            entry["bytes"] = offset
            return entry, errors
        digest = h.hexdigest()
        entry["bytes"] = offset
        entry["sha256"] = digest
        if offset != expected_size:
            fail(f"tamanho diverge em {url}: esperado {expected_size}, obtido {offset}", errors)
            entry["status"] = "size_mismatch"
            return entry, errors
        if digest != expected_sha:
            # Nunca promover bytes íntegros-duvidosos: remove parcial e final ausente.
            try:
                os.remove(partial)
            except OSError:
                pass
            fail(f"SHA-256 diverge em {url}", errors)
            entry["status"] = "hash_mismatch"
            entry["sha256"] = digest
            return entry, errors
        try:
            os.replace(partial, dest_final)
        except OSError as e:
            fail(f"falha atômica ao concluir {url}: {e}", errors)
            entry["status"] = "finalize_error"
            return entry, errors
        entry["status"] = "fetched" if not entry["resumed"] or entry["range_ignored"] else "resumed"
        return entry, []


def main(argv=None):
    t_start = time.time()
    ap = argparse.ArgumentParser(description="Aquisição gerenciada de arquivos oficiais.")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--only", nargs="+", default=None)
    args = ap.parse_args(argv)

    limits_path = os.environ.get("URNAPACK_LIMITS_FILE", DEFAULT_LIMITS)
    limits = load_limits(limits_path)
    errors = []

    try:
        with open(args.manifest, "rb") as f:
            manifest_bytes = f.read()
        manifest = json.loads(manifest_bytes)
        manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
        if not isinstance(manifest, dict):
            raise ValueError("manifesto deve ser objeto")
    except (OSError, ValueError) as e:
        print(f"ERRO: ler manifesto {args.manifest}: {e}", file=sys.stderr)
        return 2
    if manifest.get("format_version") not in (1, 2):
        print(f"ERRO: format_version não suportado em {args.manifest}: "
              f"{manifest.get('format_version')!r} (suportados: 1, 2)", file=sys.stderr)
        return 2
    files = manifest.get("files", [])
    if not isinstance(files, list):
        print(f"ERRO: campo files inválido em {args.manifest}", file=sys.stderr)
        return 2

    out_abs = os.path.realpath(args.out_dir)
    try:
        os.makedirs(out_abs, exist_ok=True)
    except OSError as e:
        print(f"ERRO: criar saída {out_abs}: {e}", file=sys.stderr)
        return 2

    wanted = set(args.only) if args.only else None
    try:
        if not isinstance(manifest, dict) or set(manifest) - {"format_version", "tool_version", "source", "files"}:
            raise ValueError("campos desconhecidos no manifesto")
        names = []
        for item in files:
            if not isinstance(item, dict) or set(item) - {"path","size","sha256","file_type","url"}:
                raise ValueError("campos desconhecidos na entrada")
            rel = item.get("path")
            if check_rel(rel):
                raise ValueError(check_rel(rel))
            if rel in names:
                raise ValueError(f"caminho duplicado: {rel}")
            if type(item.get("size")) is not int or item["size"] < 0:
                raise ValueError("tamanho inválido")
            if item.get("url") is not None and not isinstance(item["url"], str):
                raise ValueError("URL deve ser string")
            if not isinstance(item.get("sha256"), str):
                raise ValueError("SHA-256 deve ser string")
            names.append(rel)
        if wanted is not None and not wanted.issubset(set(names)):
            raise ValueError("--only contém arquivo ausente no manifesto")
        if not names:
            raise ValueError("nenhum arquivo para adquirir")
        reserved = {"fetch-run.json"} | {n+".partial" for n in names}
        if set(names) & reserved:
            raise ValueError("colisão entre arquivos e nomes reservados de checkpoint/recibo")
        for name in names:
            destination = safe_destination(out_abs, name)
            safe_destination(out_abs, name+".partial")
            if os.path.realpath(destination) == os.path.realpath(args.manifest):
                raise ValueError("destino sobrepõe manifesto de entrada")
        safe_destination(out_abs, "fetch-run.json")
    except (ValueError, OSError) as error:
        print(f"ERRO: {error}", file=sys.stderr)
        return 2
    entries = {}
    seen = set()
    for item in files:
        rel = item.get("path", "")
        bad = check_rel(rel)
        if bad:
            fail(bad, errors)
            continue
        if rel in seen:
            fail(f"caminho duplicado no manifesto: {rel}", errors)
            continue
        seen.add(rel)
        if wanted is not None and rel not in wanted:
            continue
        url = item.get("url")
        if not url:
            fail(f"sem URL para aquisição: {rel}", errors)
            continue
        parsed_url = urllib.parse.urlsplit(url)
        if parsed_url.scheme not in ("http", "https") or not parsed_url.hostname or parsed_url.username or parsed_url.password:
            fail(f"URL HTTP(S) pública inválida para {rel}", errors)
            continue
        try:
            expected_size = int(item.get("size", -1))
        except (TypeError, ValueError):
            fail(f"tamanho inválido no manifesto: {rel}", errors)
            continue
        expected_sha = item.get("sha256", "")
        if len(expected_sha) != 64 or any(c not in "0123456789abcdef" for c in expected_sha):
            fail(f"SHA-256 inválido no manifesto: {rel}", errors)
            continue
        dest = os.path.join(out_abs, *rel.split("/"))
        try:
            entry, _ = fetch_one(build_opener(limits, limits["FETCH_TIMEOUT_SECS"]),
                                 url, dest, expected_sha, expected_size, limits, errors)
        except (OSError, ValueError) as error:
            fail(f"erro na aquisição {rel}: {error}", errors)
            entry = {"status": "failed", "url": url}
        entry["path"] = rel
        entry["expected_sha256"] = expected_sha
        entry["expected_size"] = expected_size
        entries[rel] = entry

    outputs = sorted([
        {"path": rel, "sha256": e.get("sha256"), "size_bytes": e.get("bytes")}
        for rel, e in entries.items() if e.get("status") in ("fetched", "resumed", "already_valid")
    ], key=lambda o: o["path"])
    receipt = {
        "artifact_kind": "urnapack_execution",
        "format_version": 1,
        "tool": SCRIPT_VERSION,
        "command": [sys.executable, "scripts/fetch_source.py", "--manifest", args.manifest,
                    "--out-dir", args.out_dir] + (["--only"] + list(args.only) if args.only else []),
        "params": {"manifest": args.manifest},
        "inputs": [{"path": args.manifest, "sha256": manifest_sha}],
        "outputs": outputs,
        "files": [entries[k] for k in sorted(entries)],
        "started_at": datetime.fromtimestamp(t_start, tz=timezone.utc).isoformat(),
        "finished_at": datetime.now(tz=timezone.utc).isoformat(),
        "elapsed_ms": int((time.time() - t_start) * 1000),
        "success": not errors,
        "errors": errors,
    }
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=out_abs, delete=False) as stream:
            temporary = stream.name
            json.dump(receipt, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
        os.replace(temporary, os.path.join(out_abs, "fetch-run.json"))
    except OSError as e:
        print(f"ERRO: escrever recibo: {e}", file=sys.stderr)
        return 2
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)

    if errors:
        print(f"fetch_source: {len(errors)} erro(s); recibo em fetch-run.json", file=sys.stderr)
        for e in errors[:20]:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print(f"fetch_source: OK ({len(outputs)} arquivo(s) íntegros)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
