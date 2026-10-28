#!/usr/bin/env python3
"""Regressões da aquisição gerenciada (Etapa 2, sem rede externa).

Servidor HTTP local nos testes, com suporte a `Range` sob controle do teste.
Bytes servidos são sintéticos e identificados; hashes calculados dos bytes.
"""

import hashlib
import http.server
import io
import json
import os
import socketserver
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "fetch_source.py")

PAYLOAD = b"urna-pack-aquisicao-" * 4096  # ~82 KB sintéticos
PAYLOAD_SHA = hashlib.sha256(PAYLOAD).hexdigest()


class Handler(http.server.BaseHTTPRequestHandler):
    mode = "normal"  # normal | no_range | flaky | empty
    hits = 0

    def log_message(self, *a):
        pass

    def _send(self, code, body, extra=None):
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("ETag", '"teste-123"')
        self.send_header("Last-Modified", "Tue, 28 Oct 2026 00:00:00 GMT")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        type(self).hits += 1
        if self.mode == "flaky" and type(self).hits == 1:
            # Interrompe no meio do corpo na primeira tentativa.
            self.send_response(200)
            self.send_header("Content-Length", str(len(PAYLOAD)))
            self.end_headers()
            self.wfile.write(PAYLOAD[:1000])
            self.connection.close()
            return
        if self.mode == "no_range":
            self._send(200, PAYLOAD, {"Accept-Ranges": "none"})
            return
        rng = self.headers.get("Range")
        if rng and rng.startswith("bytes="):
            try:
                start = int(rng[len("bytes="):].split("-")[0])
            except ValueError:
                start = 0
            if start >= len(PAYLOAD):
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{len(PAYLOAD)}")
                self.end_headers()
                return
            body = PAYLOAD[start:]
            self._send(206, body, {"Accept-Ranges": "bytes",
                                   "Content-Range": f"bytes {start}-{len(PAYLOAD) - 1}/{len(PAYLOAD)}"})
            return
        self._send(200, PAYLOAD, {"Accept-Ranges": "bytes"})


class Server:
    def __init__(self, mode="normal"):
        Handler.mode = mode
        Handler.hits = 0
        self.srv = socketserver.TCPServer(("127.0.0.1", 0), Handler)
        self.port = self.srv.server_address[1]
        self.thread = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.thread.start()

    def url(self, name="arq.bin"):
        return f"http://127.0.0.1:{self.port}/{name}"

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


def run_fetch(manifest, out_dir, only=None, limits_file=None):
    env = dict(os.environ)
    if limits_file:
        env["URNAPACK_LIMITS_FILE"] = limits_file
    cmd = [sys.executable, SCRIPT, "--manifest", manifest, "--out-dir", out_dir]
    if only:
        cmd += ["--only"] + list(only)
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def write_manifest(path, files, version=1):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"format_version": version, "tool_version": "teste",
                   "source": "teste", "files": files}, f, sort_keys=True, indent=2)


def entry(path, url, size=None, sha=None):
    return {"path": path, "size": size if size is not None else len(PAYLOAD),
            "sha256": sha or PAYLOAD_SHA, "file_type": "bin", "url": url}


class TestFetch(unittest.TestCase):
    def test_download_integral_com_recibo(self):
        srv = Server()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                mp = os.path.join(tmp, "m.json")
                out = os.path.join(tmp, "out")
                write_manifest(mp, [entry("a/arq.bin", srv.url())])
                r = run_fetch(mp, out)
                self.assertEqual(r.returncode, 0, msg=r.stderr)
                with open(os.path.join(out, "a", "arq.bin"), "rb") as f:
                    self.assertEqual(hashlib.sha256(f.read()).hexdigest(), PAYLOAD_SHA)
                receipt = json.load(open(os.path.join(out, "fetch-run.json"), encoding="utf-8"))
                self.assertEqual(receipt["artifact_kind"], "urnapack_execution")
                self.assertEqual(receipt["format_version"], 1)
                self.assertTrue(receipt["success"])
                self.assertEqual(receipt["files"][0]["status"], "fetched")
                self.assertEqual(receipt["files"][0]["http"]["etag"], '"teste-123"')
        finally:
            srv.close()

    def test_retomada_apos_parcial(self):
        srv = Server()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                mp = os.path.join(tmp, "m.json")
                out = os.path.join(tmp, "out")
                write_manifest(mp, [entry("arq.bin", srv.url())])
                os.makedirs(out)
                # Parcial com a primeira metade (checkpoint em disco).
                with open(os.path.join(out, "arq.bin.partial"), "wb") as f:
                    f.write(PAYLOAD[:len(PAYLOAD) // 2])
                r = run_fetch(mp, out)
                self.assertEqual(r.returncode, 0, msg=r.stderr)
                with open(os.path.join(out, "arq.bin"), "rb") as f:
                    self.assertEqual(f.read(), PAYLOAD)
                receipt = json.load(open(os.path.join(out, "fetch-run.json"), encoding="utf-8"))
                self.assertEqual(receipt["files"][0]["status"], "resumed")
                self.assertTrue(receipt["files"][0]["resumed"])
        finally:
            srv.close()

    def test_servidor_sem_range_recomeca_registrado(self):
        srv = Server(mode="no_range")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                mp = os.path.join(tmp, "m.json")
                out = os.path.join(tmp, "out")
                write_manifest(mp, [entry("arq.bin", srv.url())])
                os.makedirs(out)
                with open(os.path.join(out, "arq.bin.partial"), "wb") as f:
                    f.write(b"lixo-antigo")
                r = run_fetch(mp, out)
                self.assertEqual(r.returncode, 0, msg=r.stderr)
                with open(os.path.join(out, "arq.bin"), "rb") as f:
                    self.assertEqual(f.read(), PAYLOAD)
                receipt = json.load(open(os.path.join(out, "fetch-run.json"), encoding="utf-8"))
                self.assertTrue(receipt["files"][0]["range_ignored"])
        finally:
            srv.close()

    def test_interrupcao_preserva_parcial_e_retoma(self):
        srv = Server(mode="flaky")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                mp = os.path.join(tmp, "m.json")
                out = os.path.join(tmp, "out")
                write_manifest(mp, [entry("arq.bin", srv.url())])
                r1 = run_fetch(mp, out)
                self.assertNotEqual(r1.returncode, 0)
                self.assertTrue(os.path.isfile(os.path.join(out, "arq.bin.partial")))
                self.assertFalse(os.path.isfile(os.path.join(out, "arq.bin")))
                r2 = run_fetch(mp, out)
                self.assertEqual(r2.returncode, 0, msg=r2.stderr)
                with open(os.path.join(out, "arq.bin"), "rb") as f:
                    self.assertEqual(f.read(), PAYLOAD)
        finally:
            srv.close()

    def test_hash_divergente_reprova_sem_final(self):
        srv = Server()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                mp = os.path.join(tmp, "m.json")
                out = os.path.join(tmp, "out")
                write_manifest(mp, [entry("arq.bin", srv.url(), sha="0" * 64)])
                r = run_fetch(mp, out)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("SHA-256 diverge", r.stderr)
                self.assertFalse(os.path.isfile(os.path.join(out, "arq.bin")))
        finally:
            srv.close()

    def test_sem_url_reprova_explicito(self):
        with tempfile.TemporaryDirectory() as tmp:
            mp = os.path.join(tmp, "m.json")
            out = os.path.join(tmp, "out")
            write_manifest(mp, [{"path": "a.bin", "size": 3, "sha256": "x" * 64,
                                 "file_type": "bin"}])
            r = run_fetch(mp, out)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("sem URL", r.stderr)

    def test_versao_incompativel_reprova(self):
        with tempfile.TemporaryDirectory() as tmp:
            mp = os.path.join(tmp, "m.json")
            out = os.path.join(tmp, "out")
            write_manifest(mp, [], version=999)
            r = run_fetch(mp, out)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("não suportado", r.stderr)

    def test_ja_valido_nao_baixa(self):
        srv = Server()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                mp = os.path.join(tmp, "m.json")
                out = os.path.join(tmp, "out")
                os.makedirs(out)
                with open(os.path.join(out, "arq.bin"), "wb") as f:
                    f.write(PAYLOAD)
                write_manifest(mp, [entry("arq.bin", srv.url())])
                Handler.hits = 0
                r = run_fetch(mp, out)
                self.assertEqual(r.returncode, 0, msg=r.stderr)
                receipt = json.load(open(os.path.join(out, "fetch-run.json"), encoding="utf-8"))
                self.assertEqual(receipt["files"][0]["status"], "already_valid")
                self.assertEqual(Handler.hits, 0)
        finally:
            srv.close()

    def test_caminho_duplicado_reprova(self):
        srv = Server()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                mp = os.path.join(tmp, "m.json")
                out = os.path.join(tmp, "out")
                write_manifest(mp, [entry("a.bin", srv.url()), entry("a.bin", srv.url())])
                r = run_fetch(mp, out)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("duplicado", r.stderr)
        finally:
            srv.close()

    def test_limite_excedido_reprova(self):
        with open(os.path.join(ROOT, "scripts", "limits.env"), encoding="utf-8") as f:
            base = f.read()
        srv = Server()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                custom = os.path.join(tmp, "limits.env")
                with open(custom, "w", encoding="utf-8") as f:
                    f.write(base.replace("MAX_FETCH_BYTES=4294967296", "MAX_FETCH_BYTES=10"))
                mp = os.path.join(tmp, "m.json")
                out = os.path.join(tmp, "out")
                write_manifest(mp, [entry("a.bin", srv.url())])
                r = run_fetch(mp, out, limits_file=custom)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("MAX_FETCH_BYTES", r.stderr)
        finally:
            srv.close()


if __name__ == "__main__":
    unittest.main()
