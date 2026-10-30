"""Respostas HEAD/GET por curl/HTTP2 para a mesma aquisição verificada.

Não segue redirecionamentos. HEAD e GET usam o mesmo transporte; Content-Length,
Content-Range, validadores e hashes continuam sendo conferidos pelo chamador.
"""
from email.message import Message
import subprocess
import tempfile


class CurlResponse:
    def __init__(self, request, limits, timeout):
        if request.get_method() not in ("HEAD", "GET"):
            raise ValueError("curl: método não permitido na aquisição somente leitura")
        self.url = request.full_url
        self.timeout = timeout
        self.error_stream = tempfile.TemporaryFile()
        command = ["curl", "--http2", "--include", "--suppress-connect-headers",
                   "--silent", "--show-error", "--fail", "--proto", "=https",
                   "--connect-timeout", str(timeout), "--speed-time", str(timeout),
                   "--speed-limit", str(limits["FETCH_MIN_SPEED_BYTES_PER_SEC"]) ]
        if request.get_method() == "HEAD":
            command.append("--head")
        for name, value in request.header_items():
            command.extend(["--header", f"{name}: {value}"])
        command.append(self.url)
        self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=self.error_stream)
        self.stream = self.process.stdout
        try:
            used = 0
            self.raw_http_headers = bytearray()
            while True:
                line = self.stream.readline(limits["IO_BUFFER_BYTES"] + 1)
                self.raw_http_headers.extend(line)
                used += len(line)
                if not line.startswith(b"HTTP/") or used > limits["IO_BUFFER_BYTES"]:
                    raise ValueError("curl: status HTTP ausente/inválido ou cabeçalho excessivo")
                self.status = int(line.split()[1])
                self.http_status_line = line.decode("ascii").strip()
                self.headers = Message()
                while True:
                    line = self.stream.readline(limits["IO_BUFFER_BYTES"] + 1)
                    self.raw_http_headers.extend(line)
                    used += len(line)
                    if used > limits["IO_BUFFER_BYTES"] or not line:
                        raise ValueError("curl: cabeçalho truncado/excessivo")
                    if line in (b"\r\n", b"\n"):
                        break
                    name, separator, value = line.partition(b":")
                    if not separator:
                        raise ValueError("curl: linha de cabeçalho inválida")
                    self.headers[name.decode("ascii")] = value.strip().decode("latin1")
                if not (100 <= self.status < 200):
                    break
        except Exception:
            self.close(terminate=True)
            raise

    def read(self, count=-1):
        data = self.stream.read(count)
        if not data:
            code = self.process.wait(timeout=self.timeout)
            if code:
                self.error_stream.seek(0)
                raise OSError(f"curl exit {code}: {self.error_stream.read().decode('utf-8', 'replace').strip()}")
        return data

    def geturl(self):
        return self.url

    def close(self, terminate=False):
        try:
            if terminate and self.process.poll() is None:
                self.process.terminate()
            self.stream.close()
            code = self.process.wait(timeout=self.timeout)
            if code and not terminate:
                self.error_stream.seek(0)
                raise OSError(f"curl exit {code}: {self.error_stream.read().decode('utf-8', 'replace').strip()}")
        finally:
            self.error_stream.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close(terminate=exc_type is not None)


class CurlOpener:
    def __init__(self, limits):
        self.limits = limits

    def __call__(self, request, timeout):
        return CurlResponse(request, self.limits, timeout)
