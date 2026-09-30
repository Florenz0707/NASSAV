"""Regression coverage for download proxy selection and subprocess isolation.

Run: uv run pytest tests/test_download_proxy_isolation.py -q
"""

import importlib

import pytest
from django.test import override_settings

from nassav.m3u8downloader.N_m3u8DL_RE import N_m3u8DL_RE


@pytest.mark.parametrize(
    ("download_proxy", "expected"),
    [
        (None, None),
        ("", None),
        ("http://download-proxy:8080", "http://download-proxy:8080"),
    ],
)
def test_download_service_uses_only_explicit_proxy(download_proxy, expected):
    from nassav import services

    try:
        with override_settings(
            PROXY_ENABLED=True,
            PROXY_URL="http://scrape-proxy:8080",
            DOWNLOAD_PROXY_URL=download_proxy,
        ):
            importlib.reload(services)
            assert services.video_download_service.m3u8_downloader.proxy == expected
    finally:
        importlib.reload(services)


@pytest.mark.parametrize("proxy", [None, "http://download-proxy:8080"])
def test_downloader_does_not_inherit_system_proxy(monkeypatch, tmp_path, proxy):
    inherited_keys = (
        "http_proxy",
        "https_proxy",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "all_proxy",
    )
    for key in inherited_keys:
        monkeypatch.setenv(key, "http://system-proxy:8080")

    captured = {}

    class FakeProcess:
        stdout = []

        def wait(self):
            return 0

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs["env"]
        return FakeProcess()

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    output_file = tmp_path / "sample.mp4"
    output_file.write_bytes(b"video")
    downloader = N_m3u8DL_RE(proxy=proxy)
    monkeypatch.setattr(downloader, "get_output_file", lambda *_: output_file)

    assert downloader.download(
        url="https://example.com/video.m3u8",
        output_dir=tmp_path,
        output_name="sample",
        referer="https://example.com/",
        user_agent="test-agent",
    )
    expected = proxy or None
    for key in inherited_keys[:4]:
        assert captured["env"].get(key) == expected
    assert "ALL_PROXY" not in captured["env"]
    assert "all_proxy" not in captured["env"]


@pytest.mark.parametrize(
    ("override", "expected"),
    [
        (None, "http://config-download-proxy:8080"),
        ("", None),
        ("http://env-download-proxy:8080", "http://env-download-proxy:8080"),
    ],
)
def test_settings_reads_download_proxy_from_config_with_optional_override(
    tmp_path, override, expected
):
    import os
    import shutil
    import subprocess
    import sys
    from pathlib import Path

    backend_dir = Path(__file__).resolve().parents[1]
    project_dir = tmp_path / "django_project"
    project_dir.mkdir()
    shutil.copy2(
        backend_dir / "django_project" / "settings.py", project_dir / "settings.py"
    )
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config = (backend_dir / "config" / "config.example.yaml").read_text()
    config = config.replace(
        "  download_url: null",
        "  download_url: http://config-download-proxy:8080",
        1,
    )
    (config_dir / "config.yaml").write_text(config)
    env = os.environ.copy()
    env["NASSAV_CONFIG_PATH"] = str(config_dir / "config.yaml")
    env.pop("DOWNLOAD_PROXY_URL", None)
    if override is not None:
        env["DOWNLOAD_PROXY_URL"] = override
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import runpy,sys; print(repr(runpy.run_path(sys.argv[1])['DOWNLOAD_PROXY_URL']))",
            str(project_dir / "settings.py"),
        ],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == repr(expected)
