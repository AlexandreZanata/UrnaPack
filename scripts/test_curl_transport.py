#!/usr/bin/env python3
"""Testes do fluxo HTTP; corpo é a fixture sintética identificada no repo."""
import io
from pathlib import Path
import unittest
from unittest.mock import patch
import urllib.request

from acquire_2026 import limits_at
from curl_transport import CurlResponse

LIMITS = limits_at(Path(__file__).with_name("limits.env"))
BODY = (Path(__file__).resolve().parents[1] / "tests/fixtures/audit-2026/synthetic.csv").read_bytes()
REQUEST = urllib.request.Request("https://cdn.tse.jus.br/synthetic-fixture.csv")


class Process:
    def __init__(self, data, code=0):
        self.stdout = io.BytesIO(data)
        self.code = code

    def wait(self, timeout):
        return self.code

    def poll(self):
        return self.code


class CurlTests(unittest.TestCase):
    def test_status_headers_and_identical_body(self):
        payload = b"HTTP/2 206\r\ncontent-length: " + str(len(BODY)).encode() + b"\r\nETag: fixture\r\n\r\n" + BODY
        with patch("subprocess.Popen", return_value=Process(payload)):
            with CurlResponse(REQUEST, LIMITS, LIMITS["FETCH_TIMEOUT_SECS"]) as response:
                self.assertEqual(response.status, 206)
                self.assertEqual(int(response.headers["Content-Length"]), len(BODY))
                self.assertEqual(response.read(), BODY)
                self.assertEqual(response.read(), b"")

    def test_truncated_transfer_exit_is_error(self):
        payload = b"HTTP/2 200\r\ncontent-length: " + str(len(BODY)).encode() + b"\r\n\r\n"
        with patch("subprocess.Popen", return_value=Process(payload, 18)):
            with self.assertRaisesRegex(OSError, "curl exit 18"):
                with CurlResponse(REQUEST, LIMITS, LIMITS["FETCH_TIMEOUT_SECS"]) as response:
                    response.read()

    def test_invalid_header_cannot_be_accepted_as_payload(self):
        with patch("subprocess.Popen", return_value=Process(b"HTTP/2 200\r\nnot-a-header\r\n\r\n")):
            with self.assertRaisesRegex(ValueError, "cabeçalho inválida"):
                CurlResponse(REQUEST, LIMITS, LIMITS["FETCH_TIMEOUT_SECS"])


if __name__ == "__main__":
    unittest.main()
