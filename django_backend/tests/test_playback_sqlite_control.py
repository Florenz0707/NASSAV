from pathlib import Path
import subprocess
import sys


def test_control_during_concurrent_media_heartbeat_uses_file_wal_database():
    backend = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(backend / "tests/helpers/playback_sqlite_race.py")],
        cwd=backend,
        capture_output=True,
        text=True,
        timeout=40,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "WAL control race passed" in result.stdout
