#!/usr/bin/env python3
"""Testes offline; bytes sintéticos identificados em tests/fixtures/audit-2026."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from email.message import Message
from unittest.mock import patch
import fcntl

from acquire_2026 import catalog_from_snapshot, fetch, limits_at, official_digest, probe, relative_url, write_json
from pin_catalog_2026 import pin
from acquire_2026 import scheduled_batches

FIXTURE = Path(__file__).resolve().parents[1] / "tests/fixtures/audit-2026/synthetic.csv"
LIMITS = limits_at(Path(__file__).with_name("limits.env"))
URL = "https://cdn.tse.jus.br/synthetic.csv"


class Response(io.BytesIO):
    def __init__(self, body, headers, status=200):
        super().__init__(body)
        self.headers = Message()
        for key, value in headers.items():
            self.headers[key] = str(value)
        self.status = status

    def geturl(self):
        return URL


class AcquisitionTests(unittest.TestCase):
    def test_sidecar_barrier_preserves_every_resource_without_barrier_for_large_files(self):
        items = [{"url": URL+".sha512"}, {"url": URL},
                 {"url": "https://cdn.tse.jus.br/arqurnatot/synthetic_2026_1t_MT.zip"}]
        batches = scheduled_batches(items)
        self.assertEqual(batches, [items[:1], items[1:]])
        self.assertEqual([item for batch in batches for item in batch], items)
        self.assertEqual(scheduled_batches([]), [])

    def test_pinned_catalog_requires_full_verified_coverage_and_checks_actual_bytes(self):
        body = FIXTURE.read_bytes()
        item = {"url": URL, "path": relative_url(URL)}
        catalog = {"format_version": 1, "items": [item]}
        raw = json.dumps(catalog).encode()
        digest = hashlib.sha256(raw).hexdigest()
        row = dict(item, status="reverified_local", bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
        report = {"errors": 0, "finished_at_utc": "synthetic-test", "catalog_sha256": digest, "items": [row]}
        fixed = pin(catalog, report, digest)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = fetch(fixed["items"][0], root, {URL}, LIMITS, self.opener(body))
            self.assertEqual(result["status"], "downloaded")
            wrong = dict(fixed["items"][0], expected_bytes=len(body)+1)
            result = fetch(wrong, root, {URL}, LIMITS, self.opener(body))
            self.assertEqual(result["status"], "error")
            self.assertIn("snapshot fixado", result["error"])
            self.assertEqual((root/item["path"]).read_bytes(), body)
            fresh = root / "fresh"
            result = fetch(wrong, fresh, {URL}, LIMITS, self.opener(body))
            self.assertEqual(result["status"], "error")
            self.assertFalse((fresh/item["path"]).exists())
            self.assertEqual((fresh/(item["path"]+".partial")).read_bytes(), body)
        with self.assertRaisesRegex(ValueError, "cobertura"):
            pin(catalog, dict(report, items=[]), digest)
        with self.assertRaisesRegex(ValueError, "repetidos"):
            pin(catalog, dict(report, items=[row,row]), digest)

    def test_fixture_hashes_are_recomputed(self):
        metadata = json.loads((FIXTURE.parent / "hashes.json").read_text())
        for name, expected in metadata.items():
            body = (FIXTURE.parent / name).read_bytes()
            self.assertEqual(len(body), expected["bytes"])
            self.assertEqual(hashlib.sha256(body).hexdigest(), expected["sha256"])

    def opener(self, body, unknown=False):
        def open_response(request, timeout):
            headers = {"ETag": '"fixture"'}
            if not unknown:
                headers["Content-Length"] = len(body)
            return Response(b"" if request.get_method() == "HEAD" else body, headers)
        return open_response

    def test_local_hash_and_tamper_failure(self):
        body = FIXTURE.read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            item = {"url": URL, "path": relative_url(URL)}
            result = fetch(item, root, {URL}, LIMITS, self.opener(body))
            self.assertEqual(result["status"], "downloaded")
            self.assertEqual(result["sha256"], hashlib.sha256(body).hexdigest())
            path = root / item["path"]
            path.write_bytes(body + b"alteracao de teste\n")
            failed = fetch(item, root, {URL}, LIMITS, self.opener(body))
            self.assertEqual(failed["status"], "error")
            self.assertIn("divergente", failed["error"])

    def test_official_sidecar_mismatch_preserves_partial(self):
        body = FIXTURE.read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            item = {"url": URL, "path": relative_url(URL)}
            side = root / relative_url(URL + ".sha512")
            side.parent.mkdir(parents=True)
            # Digest real de bytes diferentes: teste negativo, não hash inventado.
            side.write_text(hashlib.sha512(body + b"diferente").hexdigest() + "  synthetic.csv\n")
            result = fetch(item, root, {URL, URL + ".sha512"}, LIMITS, self.opener(body))
            self.assertEqual(result["status"], "error")
            self.assertFalse((root / item["path"]).exists())
            self.assertTrue((root / (item["path"] + ".partial")).exists())

    def test_resume_range(self):
        body = FIXTURE.read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            item = {"url": URL, "path": relative_url(URL)}
            path = root / item["path"]
            path.parent.mkdir(parents=True)
            path.with_name(path.name + ".partial").write_bytes(body[:7])
            write_json(path.with_name(path.name + ".partial.json"), {
                "url": URL, "bytes_expected": len(body), "etag": '"fixture"', "last_modified": None})
            def opener(request, timeout):
                headers = {"ETag": '"fixture"', "Content-Length": len(body)}
                if request.get_method() == "HEAD":
                    return Response(b"", headers)
                self.assertEqual(request.get_header("Range"), "bytes=7-")
                headers.update({"Content-Length": len(body)-7, "Content-Range": f"bytes 7-{len(body)-1}/{len(body)}"})
                return Response(body[7:], headers, status=206)
            result = fetch(item, root, {URL}, LIMITS, opener)
            self.assertEqual(result["status"], "downloaded")
            self.assertEqual(path.read_bytes(), body)

    def test_unknown_http_length_is_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = fetch({"url": URL, "path": relative_url(URL)}, Path(tmp), {URL}, LIMITS,
                           self.opener(FIXTURE.read_bytes(), unknown=True))
            self.assertEqual(result["status"], "downloaded")
            self.assertIn("sem Content-Length", result["http_length_verification"])

    def test_catalog_preserves_aliases_and_rejects_truncation(self):
        resource = {"id": "synthetic-resource", "url": URL, "name": "2026"}
        response = {"success": True, "result": {"count": 1, "results": [{"name": "synthetic-2026", "resources": [resource, resource]}]}}
        catalog = catalog_from_snapshot(json.dumps(response).encode())
        self.assertEqual(len(catalog["items"]), 1)
        self.assertEqual(len(catalog["items"][0]["references"]), 2)
        response["result"]["count"] = 2
        with self.assertRaises(ValueError):
            catalog_from_snapshot(json.dumps(response).encode())

    def test_sidecar_filename_and_url_traversal(self):
        actual = hashlib.sha512(FIXTURE.read_bytes()).hexdigest()
        self.assertEqual(official_digest((actual + "  synthetic.csv\n").encode(), "synthetic.csv", "sha512"), actual)
        with self.assertRaises(ValueError):
            official_digest((actual + "  other.csv\n").encode(), "synthetic.csv", "sha512")
        with self.assertRaises(ValueError):
            relative_url("https://cdn.tse.jus.br/%2e%2e/escape")

    def test_concurrent_destination_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            item = {"url": URL, "path": relative_url(URL)}
            path = root / item["path"]
            path.parent.mkdir(parents=True)
            with open(path.with_name(path.name + ".lock"), "a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                result = fetch(item, root, {URL}, LIMITS, self.opener(FIXTURE.read_bytes()))
            self.assertEqual(result["status"], "error")
            self.assertIn("BlockingIOError", result["error"])
            self.assertFalse(path.exists())

    def test_truncated_body_does_not_become_final(self):
        body = FIXTURE.read_bytes()
        def opener(request, timeout):
            return Response(b"" if request.get_method() == "HEAD" else body[:-1],
                            {"Content-Length": len(body), "ETag": '"fixture"'})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            item = {"url": URL, "path": relative_url(URL)}
            result = fetch(item, root, {URL}, LIMITS, opener)
            self.assertEqual(result["status"], "error")
            self.assertIn("truncado", result["error"])
            self.assertFalse((root / item["path"]).exists())

    def test_probe_does_not_invent_missing_size(self):
        with patch("urllib.request.urlopen", self.opener(FIXTURE.read_bytes(), unknown=True)):
            result = probe({"url": URL}, LIMITS)
        self.assertEqual(result["status"], "http_observed")
        self.assertIsNone(result["content_length"])


if __name__ == "__main__":
    unittest.main()
