"""A native CLI can exit zero after rejecting an incomplete segment set."""

import os
import subprocess

import pytest
from loguru import logger

from nassav.m3u8downloader.N_m3u8DL_RE import N_m3u8DL_RE


@pytest.mark.parametrize("existing_output", [False, True])
@pytest.mark.parametrize("controlled", [False, True])
def test_zero_exit_with_missing_segments_is_failure_and_reports_safe_facts(
    tmp_path, monkeypatch, existing_output, controlled
):
    secret = "do-not-log-this-credential"

    class Process:
        pid = 123
        stdout = iter(
            [
                f"Loading URL: https://cdn.invalid/secret?token={secret}\n",
                f"Cookie: session={secret}\n",
                f"User-Agent: {secret}\n",
                "WARN : Response status code does not indicate success: 428.\n",
                "ERROR: Segment count check not pass, total: 1437, downloaded: 1241.\n",
                "ERROR: Failed\n",
            ]
        )

        def wait(self):
            return 0

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: Process())
    monkeypatch.setattr(N_m3u8DL_RE, "_terminate_process", lambda *_: None)
    monkeypatch.setattr("nassav.task_processes.ensure_group_stopped", lambda *_: None)
    if existing_output:
        (tmp_path / "SAMPLE-1.mp4").write_bytes(b"older output is not success evidence")
    messages = []
    sink = logger.add(lambda message: messages.append(str(message)))
    try:
        arguments = dict(
            url="https://cdn.invalid/master.m3u8?secret=" + secret,
            output_dir=tmp_path,
            output_name="SAMPLE-1",
            referer="https://source.invalid/",
            user_agent=secret,
            process_started=(lambda _: None) if controlled else None,
        )
        if controlled:
            with pytest.raises(RuntimeError, match="428") as error:
                N_m3u8DL_RE().download(**arguments)
            messages.append(str(error.value))
        else:
            assert N_m3u8DL_RE().download(**arguments) is False
    finally:
        logger.remove(sink)
    report = "\n".join(messages)
    assert "428" in report and "1241/1437" in report
    assert secret not in report and "https://" not in report
    assert "Cookie" not in report and "User-Agent" not in report


@pytest.mark.skipif(
    not os.environ.get("NASSAV_LOCAL_DOWNLOAD_BINARY"),
    reason="Fixed local CLI integration opt-in",
)
def test_real_cli_reports_http_rejection_without_leaking_native_output(tmp_path):
    import os
    from functools import partial
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    from scripts.probe_task_download_control import generate_media

    media = tmp_path / "media"
    generate_media(media)

    class Handler(SimpleHTTPRequestHandler):
        def do_GET(self):
            if self.path.endswith("segment005.ts"):
                self.send_error(428)
            else:
                super().do_GET()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(Handler, directory=str(media))
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    downloader = N_m3u8DL_RE()
    downloader.tool_path = os.environ["NASSAV_LOCAL_DOWNLOAD_BINARY"]
    try:
        with pytest.raises(RuntimeError, match=r"退出码 0.*HTTP 428.*分片 11/12"):
            downloader.download(
                f"http://127.0.0.1:{server.server_port}/index.m3u8",
                tmp_path / "output",
                "REJECTED-1",
                referer="http://localhost/",
                user_agent="local-test",
                thread_count=1,
                retry_count=0,
                process_started=lambda _: None,
            )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.skipif(
    not os.environ.get("NASSAV_LOCAL_DOWNLOAD_BINARY"),
    reason="Fixed local CLI integration opt-in",
)
def test_default_concurrency_completes_with_four_request_upstream_limit(tmp_path):
    import time
    from functools import partial
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
    from threading import Lock, Thread

    from scripts.probe_task_download_control import generate_media

    media = tmp_path / "media"
    generate_media(media)
    active, maximum, rejected = 0, 0, 0
    lock = Lock()

    class Handler(SimpleHTTPRequestHandler):
        def do_GET(self):
            nonlocal active, maximum, rejected
            if not self.path.endswith(".ts"):
                return super().do_GET()
            with lock:
                active += 1
                current = active
                maximum = max(maximum, current)
            try:
                if current > 4:
                    with lock:
                        rejected += 1
                    self.send_error(428)
                else:
                    time.sleep(0.1)
                    super().do_GET()
            finally:
                with lock:
                    active -= 1

        def log_message(self, *args):
            pass

    class Server(ThreadingHTTPServer):
        request_queue_size = 128

    server = Server(("127.0.0.1", 0), partial(Handler, directory=str(media)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    downloader = N_m3u8DL_RE()
    downloader.tool_path = os.environ["NASSAV_LOCAL_DOWNLOAD_BINARY"]
    try:
        assert downloader.download(
            f"http://127.0.0.1:{server.server_port}/index.m3u8",
            tmp_path / "output",
            "BOUNDED-1",
            referer="http://localhost/",
            user_agent="local-test",
            retry_count=0,
            process_started=lambda _: None,
        )
        assert rejected == 0 and 1 < maximum <= 4
        assert (tmp_path / "output/BOUNDED-1.mp4").is_file()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
