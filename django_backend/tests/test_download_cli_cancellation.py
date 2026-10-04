"""Cancel a local downloader whose child ignores SIGTERM and retains stdout."""

import os
import signal
import subprocess
import sys
import time
from threading import Event, Timer

import pytest


@pytest.mark.skipif(os.name != "posix", reason="POSIX process group contract")
def test_cancel_terminates_cli_descendant_with_inherited_stdout(monkeypatch, tmp_path):
    from nassav.m3u8downloader.N_m3u8DL_RE import N_m3u8DL_RE

    original = subprocess.Popen
    processes = []
    child = "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print('child ready', flush=True); time.sleep(60)"
    parent = f"import subprocess,sys,time; subprocess.Popen([sys.executable,'-u','-c',{child!r}]); time.sleep(60)"

    def local_popen(command, **kwargs):
        process = original([sys.executable, "-u", "-c", parent], **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(subprocess, "Popen", local_popen)
    lost = Event()
    cancel = Timer(0.3, lost.set)

    def force_cleanup():
        for process in processes:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    fallback = Timer(4, force_cleanup)
    cancel.start()
    fallback.start()
    started = time.monotonic()
    try:
        assert not N_m3u8DL_RE().download(
            "https://offline.invalid/video.m3u8",
            tmp_path,
            "CHILD-001",
            referer="https://offline.invalid/",
            user_agent="test",
            cancelled=lost.is_set,
        )
    finally:
        cancel.cancel()
        fallback.cancel()
        force_cleanup()
        for process in processes:
            process.wait(timeout=2)
    assert time.monotonic() - started < 2, (
        "CLI descendant retained the pipe after cancellation"
    )
