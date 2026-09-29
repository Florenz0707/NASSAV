"""The deploy entry refuses mode mistakes without changing running containers."""

import importlib.util
import sys
from pathlib import Path

import pytest


@pytest.fixture
def stack_module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "compose_stack.py"
    spec = importlib.util.spec_from_file_location("compose_stack_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_init_writes_marker_once_and_rejects_different_mode(
    stack_module, tmp_path, monkeypatch
):
    directory = tmp_path / "db"
    monkeypatch.setattr(
        stack_module,
        "rendered_backend",
        lambda _command, _mode: (directory, "sqlite", ""),
    )
    monkeypatch.setattr(stack_module, "running_modes", lambda _: set())
    monkeypatch.setattr(sys, "argv", ["compose_stack.py", "--mode", "sqlite", "init"])
    assert stack_module.main() == 0
    assert (directory / ".nassav-db-mode").read_text() == "sqlite\n"
    assert stack_module.main() == 0
    monkeypatch.setattr(sys, "argv", ["compose_stack.py", "--mode", "postgres", "init"])
    with pytest.raises(RuntimeError, match="declares sqlite"):
        stack_module.main()


def test_up_rejects_running_mode_before_docker_mutation(
    stack_module, tmp_path, monkeypatch
):
    directory = tmp_path / "db"
    directory.mkdir()
    (directory / ".nassav-db-mode").write_text("postgres\n")
    monkeypatch.setattr(
        stack_module,
        "rendered_backend",
        lambda _command, _mode: (directory, "nassav", "app"),
    )
    monkeypatch.setattr(stack_module, "running_modes", lambda _: {"sqlite"})
    mutations = []
    monkeypatch.setattr(stack_module, "run", lambda command: mutations.append(command))
    monkeypatch.setattr(
        sys, "argv", ["compose_stack.py", "--mode", "postgres", "up", "-d"]
    )
    with pytest.raises(RuntimeError, match="Running Compose backend mode"):
        stack_module.main()
    assert mutations == []


def test_existing_directory_needs_explicit_adoption(
    stack_module, tmp_path, monkeypatch
):
    directory = tmp_path / "db"
    directory.mkdir()
    (directory / "db.sqlite3").write_text("existing")
    monkeypatch.setattr(
        stack_module,
        "rendered_backend",
        lambda _command, _mode: (directory, "sqlite", ""),
    )
    monkeypatch.setattr(stack_module, "running_modes", lambda _: set())
    monkeypatch.setattr(sys, "argv", ["compose_stack.py", "--mode", "sqlite", "init"])
    with pytest.raises(RuntimeError, match="--adopt-existing"):
        stack_module.main()
    monkeypatch.setattr(
        sys,
        "argv",
        ["compose_stack.py", "--mode", "sqlite", "--adopt-existing", "init"],
    )
    assert stack_module.main() == 0


def test_rendered_postgres_requires_secret_file(stack_module, tmp_path, monkeypatch):
    import json
    from subprocess import CompletedProcess

    environment = {
        "NASSAV_COMPOSE_DB_MODE": "postgres",
        "NASSAV_DB_MODE_FILE": "/app/data/db/.nassav-db-mode",
        "DB_NAME": "isolated",
    }
    config = {
        "services": {
            name: {
                "environment": environment,
                "volumes": [{"target": "/app/data/db", "source": str(tmp_path / "db")}],
            }
            for name in stack_module.BACKEND_SERVICES
        },
        "secrets": {"postgres_password": {"file": str(tmp_path / "missing")}},
    }
    monkeypatch.setattr(
        stack_module,
        "run",
        lambda command, capture: CompletedProcess(command, 0, json.dumps(config), ""),
    )
    with pytest.raises(RuntimeError, match="password secret file is missing"):
        stack_module.rendered_backend(["docker", "compose"], "postgres")
    (tmp_path / "missing").write_text("dummy-test-password")
    assert stack_module.rendered_backend(["docker", "compose"], "postgres") == (
        tmp_path / "db",
        "isolated",
        "",
    )


def test_init_unwritable_parent_explains_one_directory_repair(
    stack_module, tmp_path, monkeypatch
):
    parent = tmp_path / "deploy-data"
    parent.mkdir()
    directory = parent / "db"
    original_mkdir = Path.mkdir

    def deny_db_creation(path, *args, **kwargs):
        if path == directory:
            raise PermissionError(13, "Permission denied", str(path))
        return original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", deny_db_creation)
    monkeypatch.setattr(
        stack_module,
        "rendered_backend",
        lambda _command, _mode: (directory, "nassav", ""),
    )
    monkeypatch.setattr(stack_module, "running_modes", lambda _project: {"postgres"})
    monkeypatch.setattr(sys, "argv", ["compose_stack.py", "--mode", "postgres", "init"])
    with pytest.raises(RuntimeError, match="sudo install -d.*deploy-data/db"):
        stack_module.main()
    assert not directory.exists()
