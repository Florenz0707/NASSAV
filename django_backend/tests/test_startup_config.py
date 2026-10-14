"""Startup must reject malformed inputs before application work starts."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

BACKEND = Path(__file__).resolve().parents[1]
TEMPLATE = BACKEND / "config" / "config.example.yaml"


def startup(
    config_path: Path, env_path: Path, **overrides: str
) -> subprocess.CompletedProcess:
    environment = os.environ.copy()
    for key in (
        "DB_ENGINE",
        "DB_HOST",
        "DB_PORT",
        "DB_NAME",
        "DB_USER",
        "DB_PASSWORD",
        "DB_PASSWORD_FILE",
        "DB_CONN_MAX_AGE",
        "NASSAV_COMPOSE_DB_MODE",
        "DEBUG",
        "NASSAV_SECURE_COOKIES",
    ):
        environment.pop(key, None)
    environment.update(
        DJANGO_SETTINGS_MODULE="django_project.settings",
        NASSAV_CONFIG_PATH=str(config_path),
        NASSAV_ENV_PATH=str(env_path),
        NASSAV_RESOURCE_DIR=str(env_path.parent / "resource"),
        **overrides,
    )
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "import django; django.setup(); from django.conf import settings; print(settings.DEBUG)",
        ],
        cwd=BACKEND,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
    )


def write_config(path: Path, mutate=None) -> None:
    config = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
    if mutate:
        mutate(config)
    path.write_text(yaml.safe_dump(config), encoding="utf-8")


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("", "Configuration root must be a mapping"),
        ("[]", "Configuration root must be a mapping"),
        ("Database: {}", "Configuration key Proxy is required"),
        ("Proxy: []", "Configuration key Proxy must be a mapping"),
        ("Proxy: {}", "Configuration key Proxy.Enable is required"),
        ("Proxy:\n  Enable: false\n  url: []", "Proxy.url must be a string"),
        (
            "Proxy:\n  Enable: false\nDatabase:\n  Engine: []",
            "Database.Engine must be sqlite or postgres",
        ),
        ("Proxy:\n  Enable: maybe", "Proxy.Enable must be a boolean"),
        (
            "Proxy:\n  Enable: false\nDatabase:\n  Engine: mysql",
            "Database.Engine must be sqlite or postgres",
        ),
    ],
)
def test_invalid_yaml_fails_without_echoing_values(tmp_path, content, expected):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(content)
    result = startup(config_path, tmp_path / "absent.env")
    assert result.returncode != 0
    assert expected in result.stderr
    if "Configuration key" in expected:
        assert str(config_path) in result.stderr


def test_malformed_development_env_fails_without_secret_leak(tmp_path):
    config_path = tmp_path / "config.yaml"
    write_config(config_path)
    env_path = tmp_path / ".env"
    env_path.write_text("SECRET_KEY=private-test-value\nnot-an-assignment\n")
    result = startup(config_path, env_path)
    assert result.returncode != 0
    assert "Invalid .env assignment" in result.stderr
    assert "private-test-value" not in result.stderr


def test_unreadable_development_env_fails(tmp_path):
    config_path = tmp_path / "config.yaml"
    write_config(config_path)
    env_path = tmp_path / ".env"
    env_path.mkdir()
    result = startup(config_path, env_path)
    assert result.returncode != 0
    assert "Development environment file cannot be read" in result.stderr


def test_invalid_password_file_does_not_echo_secret(tmp_path):
    config_path = tmp_path / "config.yaml"
    write_config(config_path)
    result = startup(
        config_path,
        tmp_path / "absent.env",
        DB_ENGINE="postgres",
        DB_NAME="test",
        DB_USER="test",
        DB_HOST="localhost",
        DB_PASSWORD_FILE=str(tmp_path / "missing-secret"),
    )
    assert result.returncode != 0
    assert "Database.PasswordFile cannot be read" in result.stderr


def test_valid_config_starts_and_process_env_wins(tmp_path):
    config_path = tmp_path / "config.yaml"
    write_config(config_path)
    env_path = tmp_path / ".env"
    env_path.write_text("DEBUG=true\n")
    result = startup(config_path, env_path, DEBUG="false")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False"


@pytest.mark.parametrize("entrypoint", ["manage", "asgi", "worker"])
def test_entrypoints_report_same_invalid_config(tmp_path, entrypoint):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("Proxy: []\n")
    environment = os.environ.copy()
    environment.update(
        DJANGO_SETTINGS_MODULE="django_project.settings",
        NASSAV_CONFIG_PATH=str(config_path),
        NASSAV_ENV_PATH=str(tmp_path / "absent.env"),
        NASSAV_RESOURCE_DIR=str(tmp_path / "resource"),
        DEBUG="false",
    )
    commands = {
        "manage": [sys.executable, "manage.py", "check"],
        "asgi": [sys.executable, "-c", "import django_project.asgi"],
        "worker": [
            sys.executable,
            "-c",
            "from django_project.celery import app; app.conf.broker_url",
        ],
    }
    result = subprocess.run(
        commands[entrypoint],
        cwd=BACKEND,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode != 0
    assert "Configuration key Proxy must be a mapping" in result.stderr
    assert str(config_path) in result.stderr


def test_file_logging_is_idempotent(monkeypatch, tmp_path):
    import nassav.logging_setup as setup

    added = []
    monkeypatch.setattr(
        setup.logger, "add", lambda *args, **kwargs: added.append(args) or 123
    )
    monkeypatch.setattr(setup, "_configured_pid", None)
    monkeypatch.setattr(setup, "_sink_id", None)
    setup.configure_file_logging(tmp_path)
    setup.configure_file_logging(tmp_path)
    assert len(added) == 1


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("Port", "not-a-port", "Database.Port must be an integer"),
        ("ConnectionMaxAge", -1, "Database.ConnectionMaxAge must be an integer"),
        ("Host", [], "Database.Host must be a string"),
    ],
)
def test_invalid_database_fields_fail_at_startup(tmp_path, field, value, message):
    config_path = tmp_path / "config.yaml"
    write_config(config_path, lambda config: config["Database"].update({field: value}))
    result = startup(config_path, tmp_path / "absent.env")
    assert result.returncode != 0
    assert message in result.stderr


def test_conflicting_password_sources_fail_at_startup(tmp_path):
    config_path = tmp_path / "config.yaml"
    write_config(config_path)
    password_path = tmp_path / "password"
    password_path.write_text("test-password")
    result = startup(
        config_path,
        tmp_path / "absent.env",
        DB_ENGINE="postgres",
        DB_NAME="test",
        DB_USER="test",
        DB_HOST="localhost",
        DB_PASSWORD="other-test-password",
        DB_PASSWORD_FILE=str(password_path),
    )
    assert result.returncode != 0
    assert "DB_PASSWORD conflicts with DB_PASSWORD_FILE" in result.stderr
    assert "other-test-password" not in result.stderr


def test_signal_registration_is_stable_when_ready_runs_again():
    from django.apps import apps
    from nassav.signals import resource_added

    config = apps.get_app_config("nassav")
    before = len(resource_added.receivers)
    config.ready()
    config.ready()
    assert len(resource_added.receivers) == before


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda config: config["Proxy"].update({"Enable": True, "url": "http://"}),
            "Proxy.url must be an absolute URL",
        ),
        (
            lambda config: config["BrowserFetch"].update({"timeout_ms": 999}),
            "Browser fetch timeout_ms must be whole seconds",
        ),
    ],
)
def test_invalid_url_and_timeout_fail_at_startup(tmp_path, mutate, message):
    config_path = tmp_path / "config.yaml"
    write_config(config_path, mutate)
    result = startup(config_path, tmp_path / "absent.env")
    assert result.returncode != 0
    assert message in result.stderr
    assert str(config_path) in result.stderr


def test_forked_worker_installs_own_file_sink(tmp_path):
    code = """
import os
from pathlib import Path
from nassav import logging_setup as setup
setup.configure_file_logging(Path(os.environ['TEST_LOG_DIR']))
parent_pid = setup._configured_pid
read_fd, write_fd = os.pipe()
child = os.fork()
if child == 0:
    os.close(read_fd)
    payload = f'{setup._configured_pid}:{os.getpid()}:{setup._sink_id}'
    os.write(write_fd, payload.encode())
    os._exit(0)
os.close(write_fd)
payload = os.read(read_fd, 100).decode()
os.waitpid(child, 0)
child_configured_pid, child_pid, child_sink = payload.split(':')
assert int(child_configured_pid) == int(child_pid)
assert int(child_pid) != parent_pid
assert int(child_sink) != setup._sink_id
print('fork-log-ok')
"""
    environment = os.environ.copy()
    environment["TEST_LOG_DIR"] = str(tmp_path)
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "fork-log-ok"


@pytest.mark.parametrize("value", [0, True, 3601, "bad"])
def test_invalid_resource_playback_cache_ttl_fails_startup(tmp_path, value):
    config_path = tmp_path / "config.yaml"
    env_path = tmp_path / ".env"
    write_config(
        config_path,
        lambda config: config.update(ResourceCache={"PlaybackTTLSeconds": value}),
    )
    result = startup(config_path, env_path)
    assert result.returncode != 0
    assert "ResourceCache.PlaybackTTLSeconds" in result.stderr


@pytest.mark.parametrize("value", [-1, True, 86401, "bad"])
def test_invalid_external_search_result_ttl_fails_startup(tmp_path, value):
    config_path = tmp_path / "config.yaml"
    write_config(
        config_path,
        lambda config: config.update(ExternalSearch={"ResultTTLSeconds": value}),
    )
    result = startup(config_path, tmp_path / "absent.env")
    assert result.returncode != 0
    assert "ExternalSearch.ResultTTLSeconds" in result.stderr


@pytest.mark.parametrize(
    "key,value",
    [
        ("AggregateTTLSeconds", 0),
        ("AggregateTTLSeconds", True),
        ("AggregateTTLSeconds", 86401),
        ("CacheEnabled", "invalid"),
    ],
)
def test_invalid_external_aggregate_cache_config_fails_startup(tmp_path, key, value):
    config_path = tmp_path / "config.yaml"
    write_config(config_path, lambda config: config.update(ExternalSearch={key: value}))
    result = startup(config_path, tmp_path / "absent.env")
    assert result.returncode != 0
    assert f"ExternalSearch.{key}" in result.stderr


def test_shared_library_requires_scoped_source_mode(tmp_path):
    config = tmp_path / "config.yaml"
    write_config(config)
    env = tmp_path / "empty.env"
    env.write_text("")
    result = startup(
        config,
        env,
        NASSAV_SHARED_LIBRARY_ENABLED="true",
        NASSAV_SCOPED_SOURCE_CREDENTIALS="false",
    )
    assert (
        result.returncode != 0
        and "Shared library requires scoped source credentials" in result.stderr
    )


def test_shared_library_rejects_invalid_boolean(tmp_path):
    config = tmp_path / "config.yaml"
    write_config(config)
    env = tmp_path / "empty.env"
    env.write_text("")
    result = startup(config, env, NASSAV_SHARED_LIBRARY_ENABLED="maybe")
    assert result.returncode != 0 and "NASSAV_SHARED_LIBRARY_ENABLED" in result.stderr
