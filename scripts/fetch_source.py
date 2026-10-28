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
    if not rel or rel.startswith("/") or "\\" in rel:
        return f"caminho inválido no manifesto: {rel!r}"
    for seg in rel.split("/"):
        if seg in ("", ".", ".."):
            return f"caminho não canônico no manifesto: {rel!r}"
    return None


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


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
    # Arquivo final já válido: não baixar de novo.
    if os.path.isfile(dest_final):
        try:
            if os.path.getsize(dest_final) == expected_size and sha256_file(dest_final) == expected_sha:
                entry.update({"status": "already_valid", "bytes": expected_size, "sha256": expected_sha})
                return entry, []
        except OSError as e:
            fail(f"erro de leitura em {dest_final}: {e}", errors)
            return entry, errors
    partial = dest_final + ".partial"
    offset = 0
    if os.path.isfile(partial):
        try:
            offset = os.path.getsize(partial)
        except OSError as e:
            fail(f"erro de leitura em {partial}: {e}", errors)
            return entry, errors
    req = urllib.request.Request(url)
    if offset > 0:
        req.add_header("Range", f"bytes={offset}-")
        entry["resumed"] = True
    try:
        resp = opener.open(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code == 416 and offset > 0:
            # Parcial além do remoto: recomeçar do zero, registrado.
            try:
                os.remove(partial)
            except OSError:
                pass
            entry["resumed"] = False
            req = urllib.request.Request(url)
            try:
                resp = opener.open(req, timeout=timeout)
            except Exception as e2:  # noqa: BLE001
                fail(f"HTTP {getattr(e2, 'code', '?')} em {url}: {e2}", errors)
                entry["status"] = "http_error"
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
        # Teto por arquivo a partir do total conhecido.
        total = None
        if "content-range" in headers:
            try:
                total = int(headers["content-range"].rsplit("/", 1)[-1])
            except ValueError:
                total = None
        elif "content-length" in headers and status == 200:
            try:
                total = int(headers["content-length"])
            except ValueError:
                total = None
        if total is not None and offset + total > limits["MAX_FETCH_BYTES"]:
            fail(f"limite excedido: {url} ({offset + total} bytes > MAX_FETCH_BYTES)", errors)
            entry["status"] = "limit_exceeded"
            return entry, errors
        if expected_size > limits["MAX_FETCH_BYTES"]:
            fail(f"limite excedido: tamanho esperado ({expected_size} bytes > MAX_FETCH_BYTES)", errors)
            entry["status"] = "limit_exceeded"
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
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
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
    ap.add_argument("--only", nargs="*", default=None)
    args = ap.parse_args(argv)

    limits_path = os.environ.get("URNAPACK_LIMITS_FILE", DEFAULT_LIMITS)
    limits = load_limits(limits_path)
    errors = []

    try:
        with open(args.manifest, "r", encoding="utf-8") as f:
            manifest = json.load(f)
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

    out_abs = os.path.abspath(args.out_dir)
    try:
        os.makedirs(out_abs, exist_ok=True)
    except OSError as e:
        print(f"ERRO: criar saída {out_abs}: {e}", file=sys.stderr)
        return 2

    wanted = set(args.only) if args.only else None
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
        entry, _ = fetch_one(build_opener(limits, limits["FETCH_TIMEOUT_SECS"]),
                             url, dest, expected_sha, expected_size, limits, errors)
        entry["path"] = rel
        entry["expected_sha256"] = expected_sha
        entry["expected_size"] = expected_size
        entries[rel] = entry

    try:
        manifest_sha = sha256_file(args.manifest)
    except OSError:
        manifest_sha = None
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
    try:
        with open(os.path.join(out_abs, "fetch-run.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(receipt, f, ensure_ascii=False, sort_keys=True, indent=2)
            f.write("\n")
    except OSError as e:
        print(f"ERRO: escrever recibo: {e}", file=sys.stderr)
        return 2

    if errors:
        print(f"fetch_source: {len(errors)} erro(s); recibo em fetch-run.json", file=sys.stderr)
        for e in errors[:20]:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print(f"fetch_source: OK ({len(outputs)} arquivo(s) íntegros)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
