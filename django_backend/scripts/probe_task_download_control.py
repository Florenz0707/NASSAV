"""Exercise a fixed downloader against generated media on loopback only.

No Django settings, application database, external media or production files are used.
The workspace must be new. Exit 1 means the capability gate did not pass.
"""

import argparse
import hashlib
import http.server
import json
import os
import signal
import shutil
import subprocess
import threading
import time
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

EXPECTED_BINARY_SHA256 = (
    "d2fa5b4b79f243320c509a85835327a520d8c160c600d99921e764bfc519fec7"
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command, **kwargs):
    return subprocess.run(command, check=True, timeout=60, **kwargs)


def generate_media(directory, source="testsrc"):
    directory.mkdir()
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"{source}=size=160x90:rate=10",
            "-t",
            "24",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-g",
            "20",
            "-sc_threshold",
            "0",
            "-hls_time",
            "2",
            "-hls_playlist_type",
            "vod",
            "-hls_segment_filename",
            str(directory / "segment%03d.ts"),
            str(directory / "index.m3u8"),
        ]
    )


@contextmanager
def media_server(root):
    counts = Counter()
    lock = threading.Lock()

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path.endswith(".ts"):
                time.sleep(0.15)
                with lock:
                    counts[path] += 1
            try:
                super().do_GET()
            except (BrokenPipeError, ConnectionResetError):
                pass  # Expected when the downloader's process group is stopped.

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", counts
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def stop_group(process):
    """Mirror the production POSIX TERM/wait/KILL sequence, including descendants."""
    started = time.monotonic()
    try:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=2)
    except ProcessLookupError:
        process.wait(timeout=2)
    return round((time.monotonic() - started) * 1000)


def group_writers(pgid):
    """Linux process-group check; zombies cannot write and are reported separately."""
    writers = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            if int(fields[2]) == pgid and fields[0] != "Z":
                writers.append(int(entry.name))
        except (FileNotFoundError, ProcessLookupError):
            continue
    return writers


def wait_until(predicate, process, seconds=15):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        if process.poll() is not None:
            raise RuntimeError(f"CLI exited before checkpoint: {process.returncode}")
        time.sleep(0.02)
    raise TimeoutError("CLI did not reach the requested checkpoint")


def decoded_hash(path):
    result = run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-xerror",
            "-i",
            str(path),
            "-map",
            "0:v:0",
            "-f",
            "hash",
            "-hash",
            "sha256",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def snapshot(directory):
    return {
        str(file.relative_to(directory)): {
            "size": file.stat().st_size,
            "sha256": digest(file),
        }
        for file in directory.rglob("*")
        if file.is_file()
    }


class Probe:
    def __init__(self, binary, workspace, base_url, counts):
        self.binary, self.workspace = binary, workspace
        self.base_url, self.counts = base_url, counts
        self.env = {
            key: value
            for key, value in os.environ.items()
            if "proxy" not in key.lower()
        }
        # Spectre.Console can crash with a zero-width redirected console.
        self.env.update(COLUMNS="120", LINES="40", TERM="xterm")

    def command(self, directory, playlist="media/index.m3u8", ffmpeg=None):
        command = [
            str(self.binary),
            f"{self.base_url}/{playlist}",
            "--tmp-dir",
            str(directory / "temp"),
            "--save-dir",
            str(directory),
            "--save-name",
            "P0",
            "--thread-count",
            "1",
            "--download-retry-count",
            "0",
            "--auto-select",
            "--no-log",
            "--del-after-done",
            "--no-ansi-color",
            "--disable-update-check",
        ]
        if ffmpeg:
            command.extend(["--ffmpeg-binary-path", str(ffmpeg)])
        return command

    def complete(self, directory, playlist="media/index.m3u8", ffmpeg=None):
        directory.mkdir(exist_ok=True)
        before = self.counts.copy()
        with (directory / "complete.log").open("w") as log:
            result = subprocess.run(
                self.command(directory, playlist, ffmpeg),
                stdout=log,
                stderr=subprocess.STDOUT,
                env=self.env,
                timeout=45,
            )
        output = directory / "P0.mp4"
        output_hash = None
        decode_error = None
        if result.returncode == 0:
            try:
                output_hash = decoded_hash(output)
            except subprocess.CalledProcessError as error:
                decode_error = error.returncode
        return {
            "exit_code": result.returncode,
            "requests": dict(self.counts - before),
            "decoded_hash": output_hash,
            "decode_error": decode_error,
        }

    def interrupt(self, name, ffmpeg=None, marker=None):
        directory = self.workspace / name
        directory.mkdir()
        with (directory / "interrupted.log").open("w") as log:
            process = subprocess.Popen(
                self.command(directory, ffmpeg=ffmpeg),
                stdout=log,
                stderr=subprocess.STDOUT,
                env=self.env,
                start_new_session=True,
            )
            try:
                wait_until(
                    lambda: (
                        marker.exists()
                        if marker
                        else len(list(directory.glob("temp/P0/*/*.ts"))) >= 4
                    ),
                    process,
                )
            finally:
                stop_ms = stop_group(process)
        deadline = time.monotonic() + 3
        while group_writers(process.pid) and time.monotonic() < deadline:
            time.sleep(0.02)
        return directory, {
            "stop_ms": stop_ms,
            "writers_after_stop": group_writers(process.pid),
            "files_after_stop": snapshot(directory / "temp"),
        }


def assess(report):
    cases = report["cases"]
    expected = cases["baseline"]["decoded_hash"]
    return {
        "baseline_outputs_valid": bool(expected)
        and bool(cases["changed_baseline"]["decoded_hash"]),
        "fixed_binary": report["binary_sha256"] == EXPECTED_BINARY_SHA256,
        "negative_cases_detect_unsafe_native_reuse": cases["native_corrupt"][
            "decoded_hash"
        ]
        != expected
        and cases["native_changed"]["decoded_hash"]
        != cases["changed_baseline"]["decoded_hash"],
        "all_process_groups_stopped": all(
            not case.get("writers_after_stop") for case in cases.values()
        ),
        "warm_resume_reuses_valid_segments": cases["resume"]["reused_segments"] >= 4
        and cases["resume"]["decoded_hash"] == expected,
        "changed_url_same_content": cases["signed_url"]["decoded_hash"] == expected
        and cases["signed_url"]["reused_segments"] >= 4,
        "corrupt_cache_repaired": cases["repair_corrupt"]["decoded_hash"] == expected,
        "changed_content_restarted": cases["changed_content"]["decoded_hash"]
        == cases["changed_baseline"]["decoded_hash"],
        "merge_restart": cases["merge"]["discarded_partial_output"]
        and cases["merge"]["decoded_hash"] == expected,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument(
        "--workspace",
        type=Path,
        required=True,
        help="New directory for fixture, logs and report",
    )
    args = parser.parse_args()
    binary = args.binary.resolve(strict=True)
    if digest(binary) != EXPECTED_BINARY_SHA256:
        parser.error("Binary does not match the fixed v0.5.1-beta capability baseline")
    workspace = args.workspace.resolve()
    if workspace.exists():
        parser.error("Workspace must be new; existing files will not be modified")
    workspace.mkdir()  # Refuse to modify an existing directory.
    generate_media(workspace / "media")
    generate_media(workspace / "variant", "testsrc2")
    report = {"binary_sha256": digest(binary), "cases": {}}
    with media_server(workspace) as (base_url, counts):
        probe = Probe(binary, workspace, base_url, counts)
        cases = report["cases"]
        cases["baseline"] = probe.complete(workspace / "baseline")
        cases["changed_baseline"] = probe.complete(
            workspace / "changed-baseline", "variant/index.m3u8"
        )
        for name, playlist in (
            ("resume", "media/index.m3u8"),
            ("signed_url", "media/index.m3u8?token=renewed"),
        ):
            directory, stopped = probe.interrupt(name)
            cache = list(directory.glob("temp/P0/*/*.ts"))
            result = probe.complete(directory, playlist)
            requested = result["requests"]
            reused = sum(
                requested.get(f"/media/segment{int(file.stem):03d}.ts", 0) == 0
                for file in cache
            )
            cases[name] = {**stopped, **result, "reused_segments": reused}

        # Demonstrate and repair invalid cache by a recorded checksum, not by filename.
        directory, stopped = probe.interrupt("repair_corrupt")
        native_directory = workspace / "native-corrupt"
        shutil.copytree(directory, native_directory)
        native_file = next(native_directory.glob("temp/P0/*/*.ts"))
        native_file.write_bytes(b"corrupt")
        cases["native_corrupt"] = probe.complete(native_directory)
        file = next(directory.glob("temp/P0/*/*.ts"))
        expected_hash = digest(file)
        file.write_bytes(b"corrupt")
        detected = digest(file) != expected_hash
        if detected:
            file.unlink()
        cases["repair_corrupt"] = {
            **stopped,
            "checksum_mismatch_detected": detected,
            **probe.complete(directory),
        }

        # A changed manifest must use a fresh cache/output directory.
        directory, stopped = probe.interrupt("changed_content")
        native_directory = workspace / "native-changed"
        shutil.copytree(directory, native_directory)
        cases["native_changed"] = probe.complete(native_directory, "variant/index.m3u8")
        old_manifest = digest(workspace / "media/index.m3u8")
        new_manifest = digest(workspace / "variant/index.m3u8")
        # Playlist text can be identical even though segment contents differ.
        old_segment = digest(workspace / "media/segment000.ts")
        new_segment = digest(workspace / "variant/segment000.ts")
        cases["changed_content"] = {
            **stopped,
            "playlist_text_identical": old_manifest == new_manifest,
            "segment_identity_changed": old_segment != new_segment,
            **probe.complete(directory / "new-content", "variant/index.m3u8"),
        }

        marker = workspace / "merge.started"
        once = workspace / "merge.once"
        once.touch()
        wrapper = workspace / "slow-ffmpeg"
        wrapper.write_text(
            "#!/usr/bin/env python3\nimport os,sys,time\nfrom pathlib import Path\n"
            f"flag=Path({str(once)!r})\n"
            "if flag.exists() and Path(sys.argv[-1]).suffix == '.mp4':\n"
            " flag.unlink()\n"
            f" Path({str(marker)!r}).write_text(str(os.getpid()))\n"
            ' Path(sys.argv[-1]).write_bytes(b"partial-video")\n'
            " time.sleep(30)\n"
            "os.execvp('ffmpeg', ['ffmpeg', *sys.argv[1:]])\n"
        )
        wrapper.chmod(0o755)
        directory, stopped = probe.interrupt("merge", ffmpeg=wrapper, marker=marker)
        partial = directory / "P0.mp4"
        discarded_partial_output = partial.exists()
        if discarded_partial_output:
            partial.unlink()
        cases["merge"] = {
            **stopped,
            "discarded_partial_output": discarded_partial_output,
            **probe.complete(directory, ffmpeg=wrapper),
        }
    report["checks"] = assess(report)
    report["passed"] = all(report["checks"].values())
    (workspace / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {"report": str(workspace / "report.json"), "checks": report["checks"]},
            indent=2,
        )
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
