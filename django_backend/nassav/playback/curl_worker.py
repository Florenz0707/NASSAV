"""Private one-request browser transport; bounded blocking pipe, no Django/DB."""

import json
import sys
from contextlib import closing
from curl_cffi import Curl
from curl_cffi.const import CurlOpt

ALLOWED_HEADERS = {
    "content-type",
    "content-length",
    "content-range",
    "content-encoding",
    "location",
}


def transfer(options, output):
    status, header_size, body_size = 0, 0, 0
    headers = {}
    emitted = False

    def header(data):
        nonlocal status, headers, header_size, emitted
        header_size += len(data)
        if header_size > 16384:
            return 0
        text = data.decode("latin-1").strip()
        if text.startswith("HTTP/"):
            status = int(text.split()[1])
            headers = {}
        elif not text and status >= 200:
            if emitted:
                return 0
            output.write(
                json.dumps({"status": status, "headers": headers}).encode() + b"\n"
            )
            output.flush()
            emitted = True
        elif ":" in text:
            name, value = text.split(":", 1)
            name = name.lower()
            if name in ALLOWED_HEADERS:
                if name in headers:
                    return 0
                headers[name] = value.strip()
        return len(data)

    def body(data):
        nonlocal body_size
        body_size += len(data)
        if not emitted or body_size > 16 * 1024 * 1024:
            return 0
        for start in range(0, len(data), 16384):
            output.write(data[start : start + 16384])
            output.flush()
        return len(data)

    with closing(Curl(cacert=options.get("cacert"))) as curl:
        if curl.impersonate(options["impersonate"], default_headers=False) != 0:
            raise ValueError("Unsupported impersonation profile")
        for option, value in [
            (CurlOpt.URL, options["url"]),
            (CurlOpt.PROXY, options["proxy"] or ""),
            (CurlOpt.NOPROXY, ""),
            (CurlOpt.FOLLOWLOCATION, 0),
            (CurlOpt.SUPPRESS_CONNECT_HEADERS, 1),
            (CurlOpt.CONNECTTIMEOUT_MS, 5000),
            (CurlOpt.TIMEOUT_MS, 45000),
            (CurlOpt.SSL_VERIFYPEER, 1),
            (CurlOpt.SSL_VERIFYHOST, 2),
        ]:
            curl.setopt(option, value)
        curl.setopt(
            CurlOpt.HTTPHEADER,
            [f"{k}: {v}".encode() for k, v in options["headers"].items()],
        )
        if options["method"] == "HEAD":
            curl.setopt(CurlOpt.NOBODY, 1)
        if not options["proxy"]:
            ip = options["ip"]
            ip = f"[{ip}]" if ":" in ip else ip
            curl.setopt(CurlOpt.RESOLVE, [f"{options['host']}:443:{ip}".encode()])
        if options.get("unix_socket_path"):
            curl.setopt(CurlOpt.UNIX_SOCKET_PATH, options["unix_socket_path"])
        curl.setopt(CurlOpt.HEADERFUNCTION, header)
        curl.setopt(CurlOpt.WRITEFUNCTION, body)
        curl.perform()
        if not emitted:
            raise ValueError("Missing response headers")


def main():
    try:
        raw = sys.stdin.buffer.read(32769)
        if len(raw) > 32768:
            return 1
        transfer(json.loads(raw), sys.stdout.buffer)
        return 0
    except Exception:
        # Secrets are stdin-only; never log URLs, proxy credentials or response body.
        return 1


if __name__ == "__main__":
    sys.exit(main())
