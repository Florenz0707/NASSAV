#!/usr/bin/env python3
"""Loopback-only real curl probe: partial timeout, retry and stop during resume IO."""

import hashlib
import json
import sys
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from curl_cffi import requests  # noqa: E402
from nassav.download_resume import HLSResumeGuard  # noqa: E402
from nassav.task_control_rules import TaskPauseRequested  # noqa: E402


def main():
    payload = b"fixture-segment" * 1024
    calls, budgets = [], []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append(self.path)
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            try:
                self.wfile.write(payload[:128])
                self.wfile.flush()
                if len(calls) == 1:
                    time.sleep(0.4)
                self.wfile.write(payload[128:])
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/segment.ts"
    original = requests.Session.get

    def get(session, requested_url, **kwargs):
        assert requested_url == url
        budgets.append(kwargs["timeout"])
        # Scale only the injected first network failure; production passes 60s.
        kwargs["timeout"] = (0.1, 0.15) if len(budgets) == 1 else (1, 2)
        return original(session, requested_url, **kwargs)

    try:
        with tempfile.TemporaryDirectory(prefix="nassav-hls-validation-") as root:
            workspace = Path(root)
            relative = "temp/DL-1/track/0.ts"
            cached = workspace / relative
            cached.parent.mkdir(parents=True)
            cached.write_bytes(payload)
            manifest = {
                "identity": "fixture",
                "safe": True,
                "urls": [url],
                "keys": [None],
            }
            checkpoint = {
                "manifest": manifest,
                "segments": {relative: hashlib.sha256(payload).hexdigest()},
            }
            with patch.object(requests.Session, "get", get):
                assert HLSResumeGuard()._fetch(url, {}, lambda: None) == payload
                HLSResumeGuard().prepare(
                    workspace, "DL-1", manifest, checkpoint, {}, lambda: None
                )
                assert calls == ["/segment.ts", "/segment.ts"]
                assert cached.read_bytes() == payload
                assert budgets == [(5, 55), (5, 55)]
                checks = []

                def stop():
                    checks.append(True)
                    if len(checks) >= 2:
                        raise TaskPauseRequested("fixture pause")

                try:
                    HLSResumeGuard()._fetch(url, {}, stop)
                except TaskPauseRequested:
                    pass
                else:
                    raise AssertionError("pause callback was swallowed")
                assert len(budgets) == 3
        print(
            json.dumps(
                {
                    "status": "passed",
                    "network": "loopback only",
                    "partial_timeout_retry": True,
                    "cache_preserved": True,
                    "pause_priority": True,
                    "request_budget_seconds": 60,
                    "maximum_attempts": 2,
                    "injected_timeout_seconds": 0.25,
                }
            )
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


if __name__ == "__main__":
    main()
