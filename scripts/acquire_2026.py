#!/usr/bin/env python3
"""Inventário CKAN e aquisição nacional de 2026, preservando bytes e recibos.

Automação, não análise eleitoral. Nenhum SHA local é tratado como assinatura.
Arquivos completos só são promovidos após tamanho, releitura SHA-256 e,
quando publicado no catálogo, confronto com sidecar SHA-512/SHA-1.
"""
import argparse
import fcntl
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import urllib.parse
import urllib.request

from fetch_source import load_limits, check_rel

API = "https://dadosabertos.tse.jus.br/api/3/action/package_search?q=2026&rows=100"
OFFICIAL_HOSTS = {"cdn.tse.jus.br", "dadosabertos.tse.jus.br", "resultados.tse.jus.br"}
EXTRA_LIMITS = ("MAX_AUDIT_FETCH_BYTES", "AUDIT_FETCH_WORKERS", "AUDIT_MIN_FREE_BYTES",
                "MAX_ZIP_MEMBER_BYTES", "MAX_ZIP_MEMBERS", "FETCH_MIN_SPEED_BYTES_PER_SEC")


def now():
    return datetime.now(timezone.utc).isoformat()


def limits_at(path):
    limits = load_limits(path)
    for line in Path(path).read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            if key in EXTRA_LIMITS:
                limits[key] = int(value)
    for key in EXTRA_LIMITS:
        if limits.get(key, 0) <= 0:
            raise ValueError(f"limite ausente/inválido: {key}")
    return limits


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    os.replace(tmp, path)


def hashes(path, buffer_size):
    sha256, sha512, sha1 = hashlib.sha256(), hashlib.sha512(), hashlib.sha1()
    size = 0
    with open(path, "rb") as stream:
        while chunk := stream.read(buffer_size):
            size += len(chunk)
            for digest in (sha256, sha512, sha1):
                digest.update(chunk)
    return {"bytes": size, "sha256": sha256.hexdigest(),
            "sha512": sha512.hexdigest(), "sha1": sha1.hexdigest()}


def relative_url(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in OFFICIAL_HOSTS or parsed.query or parsed.fragment:
        raise ValueError(f"URL fora do contrato de aquisição: {url}")
    rel = parsed.hostname + urllib.parse.unquote(parsed.path)
    error = check_rel(rel)
    if error:
        raise ValueError(error)
    return rel


def catalog_from_snapshot(raw):
    data = json.loads(raw)
    if data.get("success") is not True:
        raise ValueError("CKAN success != true")
    result = data["result"]
    if result["count"] != len(result["results"]):
        raise ValueError("resposta CKAN paginada/incompleta; não declarar inventário completo")
    items, excluded = {}, []
    for dataset in result["results"]:
        for resource in dataset["resources"]:
            url = resource.get("url", "")
            # Datasets gerais têm anos diferentes: preservar a exclusão explícita.
            if "2026" not in dataset["name"] and "2026" not in (url + " " + resource.get("name", "")):
                excluded.append({"dataset": dataset["name"], "resource": resource,
                                 "reason": "recurso de outro ano em dataset multianual"})
                continue
            reference = {"dataset": dataset["name"], "resource_id": resource["id"],
                         "name": resource.get("name"), "format": resource.get("format"),
                         "metadata_modified": dataset.get("metadata_modified")}
            # Uma cópia por URL; todas as referências originais são preservadas.
            if url not in items:
                items[url] = {"url": url, "references": []}
                try:
                    items[url]["path"] = relative_url(url)
                except ValueError as exc:
                    items[url]["unsupported"] = str(exc)
            items[url]["references"].append(reference)
    return {"format_version": 1, "source_url": API, "acquired_at_utc": now(),
            "snapshot_sha256": hashlib.sha256(raw).hexdigest(),
            "scope": "recursos de 2026 retornados pela busca CKAN q=2026; não todos os objetos internos de sistemas TSE",
            "datasets_returned": result["count"], "items": sorted(items.values(), key=lambda x: x["url"]),
            "excluded_other_years": excluded}


def official_digest(body, filename, algorithm):
    length = {"sha512": 128, "sha1": 40}[algorithm]
    lines = body.decode("ascii").splitlines()
    matches = []
    for line in lines:
        if not line.strip():
            continue
        match = re.fullmatch(r"([0-9a-fA-F]{%d})(?:\s+\*?(.+))?" % length, line.strip())
        if not match or (match[2] is not None and match[2] != filename):
            raise ValueError("sidecar inválido ou nome divergente")
        matches.append(match[1].lower())
    if len(matches) != 1:
        raise ValueError("sidecar deve conter exatamente um digest")
    return matches[0]


def safe_path(root, rel):
    if check_rel(rel):
        raise ValueError(f"caminho inválido: {rel}")
    path = root / rel
    current = root
    for part in Path(rel).parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f"symlink interno recusado: {current}")
    return path


def check_pinned(item, measured):
    keys = {"expected_bytes", "expected_sha256"}
    present = keys.intersection(item)
    if not present:
        return
    if present != keys or type(item["expected_bytes"]) is not int or item["expected_bytes"] < 0 or not re.fullmatch(r"[0-9a-f]{64}", item["expected_sha256"]):
        raise ValueError("fixação de tamanho/hash inválida ou incompleta")
    if measured["bytes"] != item["expected_bytes"] or measured["sha256"] != item["expected_sha256"]:
        raise ValueError("bytes divergem do snapshot fixado; preservar e investigar")


def fetch(item, root, catalog_urls, limits, opener=urllib.request.urlopen):
    """Um bloqueio por destino impede escritores concorrentes, inclusive entre CLIs."""
    try:
        dest = safe_path(root, item["path"])
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest.with_name(dest.name + ".lock"), "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return _fetch_unlocked(item, root, catalog_urls, limits, opener)
    except Exception as exc:
        return {"url": item["url"], "path": item.get("path"), "status": "error",
                "error": f"{type(exc).__name__}: {exc}", "finished_at_utc": now()}


def _fetch_unlocked(item, root, catalog_urls, limits, opener=urllib.request.urlopen):
    entry = {"url": item["url"], "path": item.get("path"), "started_at_utc": now()}
    try:
        if "unsupported" in item:
            raise ValueError(item["unsupported"])
        dest = safe_path(root, item["path"])
        dest.parent.mkdir(parents=True, exist_ok=True)
        receipt_path = dest.with_name(dest.name + ".receipt.json")
        if dest.exists():
            if not receipt_path.is_file():
                raise ValueError("arquivo existente sem recibo; preservar e investigar")
            saved = json.loads(receipt_path.read_text())
            measured = hashes(dest, limits["IO_BUFFER_BYTES"])
            if measured["sha256"] != saved["sha256"] or measured["bytes"] != saved["bytes"]:
                raise ValueError("SHA-256/tamanho local divergente do recibo")
            check_pinned(item, measured)
            for algorithm in ("sha512", "sha1"):
                if item["url"] + "." + algorithm in catalog_urls:
                    side_path = dest.with_name(dest.name + "." + algorithm)
                    expected = official_digest(side_path.read_bytes(), dest.name, algorithm)
                    if measured[algorithm] != expected:
                        raise ValueError(f"{algorithm} local diverge do sidecar oficial")
            entry.update(saved, status="reverified_local", reverified_at_utc=now())
            return entry
        request = urllib.request.Request(item["url"], method="HEAD")
        with opener(request, timeout=limits["FETCH_TIMEOUT_SECS"]) as response:
            relative_url(response.geturl())
            headers = dict(response.headers.items())
            wanted = int(response.headers["Content-Length"]) if response.headers.get("Content-Length") else None
            etag = response.headers.get("ETag")
            modified = response.headers.get("Last-Modified")
        entry["http_head"] = headers
        if wanted is not None and (wanted < 0 or wanted > limits["MAX_AUDIT_FETCH_BYTES"]):
            raise ValueError(f"Content-Length excede limite: {wanted}")
        partial = dest.with_name(dest.name + ".partial")
        state_path = dest.with_name(dest.name + ".partial.json")
        state = {"url": item["url"], "bytes_expected": wanted, "etag": etag, "last_modified": modified}
        offset = 0
        if partial.exists():
            if partial.is_symlink() or partial.stat().st_nlink != 1:
                raise ValueError("parcial inseguro")
            if not state_path.is_file() or json.loads(state_path.read_text()) != state or not (etag or modified):
                raise ValueError("origem/parcial mudou ou não possui validador HTTP; bytes preservados")
            offset = partial.stat().st_size
            if wanted is None:
                raise ValueError("parcial sem tamanho HTTP conhecido; bytes preservados")
            if offset > wanted:
                raise ValueError("parcial maior que Content-Length")
        else:
            write_json(state_path, state)
        if shutil.disk_usage(root).free < (wanted or 0) - offset + limits["AUDIT_MIN_FREE_BYTES"]:
            raise ValueError("espaço livre insuficiente; aquisição interrompida")
        if offset != wanted or not partial.exists():
            req = urllib.request.Request(item["url"])
            if offset:
                req.add_header("Range", f"bytes={offset}-")
                req.add_header("If-Range", etag or modified)
            with opener(req, timeout=limits["FETCH_TIMEOUT_SECS"]) as response:
                relative_url(response.geturl())
                entry["http_get"] = dict(response.headers.items())
                entry["http_get_status"] = response.status
                entry["http_get_url"] = response.geturl()
                if hasattr(response, "http_status_line"):
                    entry["http_get_protocol"] = response.http_status_line
                if offset:
                    match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("Content-Range", ""))
                    if response.status != 206 or not match or tuple(map(int, match.groups())) != (offset, wanted - 1, wanted):
                        raise ValueError("servidor não confirmou Range; parcial preservado")
                elif response.status != 200:
                    raise ValueError(f"HTTP inesperado: {response.status}")
                get_length = response.headers.get("Content-Length")
                if wanted is not None and get_length is not None and int(get_length) != wanted - offset:
                    raise ValueError("Content-Length HEAD/GET divergente")
                if (etag and response.headers.get("ETag") != etag) or (modified and response.headers.get("Last-Modified") != modified):
                    raise ValueError("origem alterada entre HEAD e GET")
                with open(partial, "ab" if offset else "xb") as stream:
                    received = offset
                    while chunk := response.read(limits["IO_BUFFER_BYTES"]):
                        received += len(chunk)
                        if received > limits["MAX_AUDIT_FETCH_BYTES"] or (wanted is not None and received > wanted):
                            raise ValueError("resposta excede tamanho anunciado")
                        if shutil.disk_usage(root).free < len(chunk) + limits["AUDIT_MIN_FREE_BYTES"]:
                            raise ValueError("espaço livre insuficiente durante streaming")
                        stream.write(chunk)
        measured = hashes(partial, limits["IO_BUFFER_BYTES"])
        if wanted is not None and measured["bytes"] != wanted:
            raise ValueError("download truncado; parcial preservado")
        official = []
        check_pinned(item, measured)
        for algorithm in ("sha512", "sha1"):
            side_url = item["url"] + "." + algorithm
            if side_url in catalog_urls:
                side_path = safe_path(root, relative_url(side_url))
                expected = official_digest(side_path.read_bytes(), dest.name, algorithm)
                if measured[algorithm] != expected:
                    raise ValueError(f"{algorithm} diverge do sidecar oficial; parcial preservado")
                official.append({"algorithm": algorithm, "expected": expected, "verified": True,
                                 "sidecar_url": side_url, "sidecar_sha256": hashes(side_path, limits["IO_BUFFER_BYTES"])["sha256"]})
        entry.update(measured, status="downloaded", http_head=headers,
                     http_length_verification="matched" if wanted is not None else "HEAD sem Content-Length; tamanho local medido, sem confronto de tamanho remoto",
                     official_checks=official, finished_at_utc=now(),
                     integrity_scope="bytes e sidecar quando listado; assinatura digital não verificada")
        # Publicar recibo antes dos bytes: interrupção nunca cria final sem digest.
        write_json(receipt_path, entry)
        os.replace(partial, dest)
        return entry
    except Exception as exc:
        entry.update(status="error", error=f"{type(exc).__name__}: {exc}", finished_at_utc=now())
        return entry


def priority(item):
    url = item["url"]
    if url.endswith((".sha512", ".sha1")):
        return 0
    if "/buweb/" in url and "_2t_" in url:
        return 1
    if "/buweb/" in url:
        return 2
    if "/arqurnatot/" in url:
        return 3 if "_2026_2t_" in url else 5
    return 4


def scheduled_batches(selected):
    """Sidecars têm dependência; demais prioridades ordenam a fila, sem barreira."""
    return [batch for batch in ([item for item in selected if priority(item) == 0],
                                [item for item in selected if priority(item) != 0]) if batch]


def probe(item, limits):
    entry = {"url": item["url"], "observed_at_utc": now()}
    try:
        req = urllib.request.Request(item["url"], method="HEAD")
        with urllib.request.urlopen(req, timeout=limits["FETCH_TIMEOUT_SECS"]) as response:
            relative_url(response.geturl())
            entry.update(status="http_observed", final_url=response.geturl(), http_status=response.status,
                         http_headers=dict(response.headers.items()),
                         content_length=int(response.headers["Content-Length"]) if response.headers.get("Content-Length") else None)
    except Exception as exc:
        entry.update(status="error", error=f"{type(exc).__name__}: {exc}")
    return entry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["catalog", "fetch", "plan", "verify"])
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--match", default="")
    parser.add_argument("--exclude", default="")
    parser.add_argument("--transport", choices=["urllib", "curl"], default="urllib")
    parser.add_argument("--limits", default=str(Path(__file__).with_name("limits.env")))
    args = parser.parse_args()
    limits = limits_at(args.limits)
    if args.action == "catalog":
        if not args.snapshot:
            parser.error("--snapshot obrigatório (resposta completa package_search oficial)")
        catalog = catalog_from_snapshot(args.snapshot.read_bytes())
        write_json(args.catalog, catalog)
        print(f"catálogo: {len(catalog['items'])} URLs; referências preservadas")
        return 0
    if not args.receipt or (args.action != "plan" and not args.root):
        parser.error("exige --receipt; fetch/verify exigem também --root")
    if args.root:
        args.root.mkdir(parents=True, exist_ok=True)
    catalog = json.loads(args.catalog.read_text())
    if catalog["format_version"] != 1:
        raise ValueError("versão de catálogo desconhecida")
    urls = {item["url"] for item in catalog["items"]}
    selected = sorted([item for item in catalog["items"] if args.match in item["url"] and not (args.exclude and args.exclude in item["url"])], key=lambda i: (priority(i), i["url"]))
    if not selected:
        raise ValueError("filtro sem recursos; não declarar sucesso")
    report = {"format_version": 1, "started_at_utc": now(), "filter": args.match, "exclude": args.exclude,
              "transport_requested": args.transport,
              "catalog_sha256": hashlib.sha256(args.catalog.read_bytes()).hexdigest(), "items": []}
    if args.action == "plan":
        with ThreadPoolExecutor(max_workers=limits["AUDIT_FETCH_WORKERS"]) as executor:
            for result in executor.map(lambda item: probe(item, limits), selected):
                report["items"].append(result)
                write_json(args.receipt, report)
        report["known_content_length_sum"] = sum(i.get("content_length") or 0 for i in report["items"])
        report["unknown_content_length_count"] = sum(i.get("content_length") is None for i in report["items"])
        report["finished_at_utc"] = now()
        write_json(args.receipt, report)
        print(f"HEAD: {len(selected)} URLs, bytes conhecidos={report['known_content_length_sum']}; tamanhos ausentes={report['unknown_content_length_count']}")
        return int(any(i["status"] == "error" for i in report["items"]))

    def operation(item):
        if args.action == "verify" and not safe_path(args.root, item["path"]).is_file():
            return {"url": item["url"], "path": item["path"], "status": "error", "error": "arquivo final ausente; sem download no modo verify"}
        if args.transport == "curl":
            from curl_transport import CurlOpener
            return fetch(item, args.root, urls, limits, CurlOpener(limits))
        return fetch(item, args.root, urls, limits)
    # Só os sidecars dependem de barreira. Um ZIP grande não bloqueia a fila
    # de outros datasets enquanto há trabalhadores livres.
    for phase_items in scheduled_batches(selected):
        with ThreadPoolExecutor(max_workers=limits["AUDIT_FETCH_WORKERS"]) as executor:
            futures = [executor.submit(operation, item) for item in phase_items]
            for future in as_completed(futures):
                result = future.result()
                report["items"].append(result)
                write_json(args.receipt, report)
                print(f"{result['status']} {result['url'].rsplit('/', 1)[-1]} {result.get('bytes', '')} {result.get('error', '')}", flush=True)
    report["finished_at_utc"] = now()
    report["errors"] = sum(item["status"] == "error" for item in report["items"])
    write_json(args.receipt, report)
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
