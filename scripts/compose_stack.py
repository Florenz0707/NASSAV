#!/usr/bin/env python3
"""Use the declared data-directory database mode for every Compose command."""

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

BACKEND_SERVICES = {
    "migrate",
    "api",
    "scrape-worker",
    "download-worker",
    "default-worker",
    "beat",
    "ollama-model",
}
ROOT = Path(__file__).resolve().parents[1]
MARKER = ".nassav-db-mode"


def run(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        command, cwd=ROOT, check=True, text=True, capture_output=capture
    )


def compose_command(
    mode: str, project: str, gpu: bool, profiles: list[str]
) -> list[str]:
    command = ["docker", "compose", "-p", project, "-f", "compose.yaml"]
    if mode == "postgres":
        command += ["-f", "compose.postgres.yaml"]
    if gpu:
        command += ["-f", "compose.gpu.yaml"]
    for profile in profiles:
        command += ["--profile", profile]
    return command


def rendered_backend(command: list[str], mode: str) -> tuple[Path, str, str]:
    config = json.loads(
        run(command + ["config", "--format", "json"], capture=True).stdout
    )
    for service in BACKEND_SERVICES & config["services"].keys():
        environment = config["services"][service]["environment"]
        if (
            environment.get("NASSAV_COMPOSE_DB_MODE") != mode
            or environment.get("NASSAV_DB_MODE_FILE") != "/app/data/db/.nassav-db-mode"
        ):
            raise RuntimeError(
                f"{service} has inconsistent database mode configuration"
            )
    if mode == "postgres":
        secret = config.get("secrets", {}).get("postgres_password", {}).get("file")
        if not secret or not Path(secret).is_file():
            raise RuntimeError(
                "PostgreSQL password secret file is missing or is not a file"
            )
    api = config["services"]["api"]
    environment = api["environment"]
    mounts = api["volumes"]
    database_mount = next(item for item in mounts if item["target"] == "/app/data/db")
    return (
        Path(database_mount["source"]),
        environment.get("DB_NAME", "sqlite"),
        environment.get("DB_SCHEMA", ""),
    )


def running_modes(project: str) -> set[str]:
    ids = run(
        [
            "docker",
            "ps",
            "-a",
            "--filter",
            f"label=com.docker.compose.project={project}",
            "--format",
            "{{.ID}}",
        ],
        capture=True,
    ).stdout.splitlines()
    if not ids:
        return set()
    labels = run(
        ["docker", "inspect", "--format", "{{json .Config.Labels}}", *ids], capture=True
    ).stdout.splitlines()
    modes = set()
    for line in labels:
        item = json.loads(line)
        if item.get("com.docker.compose.service") not in BACKEND_SERVICES:
            continue
        files = item.get("com.docker.compose.project.config_files")
        if not files:
            raise RuntimeError(
                "Running backend has no Compose file labels; inspect it manually"
            )
        modes.add("postgres" if "compose.postgres.yaml" in files else "sqlite")
    return modes


def read_mode(marker: Path) -> str | None:
    if not marker.exists():
        return None
    mode = marker.read_text(encoding="utf-8").strip()
    if mode not in {"sqlite", "postgres"}:
        raise RuntimeError(f"Invalid database mode declaration: {marker}")
    return mode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=("sqlite", "postgres"))
    parser.add_argument(
        "--project", default=os.getenv("COMPOSE_PROJECT_NAME", "nassav")
    )
    parser.add_argument("--gpu", action="store_true")
    parser.add_argument("--profile", action="append", default=[])
    parser.add_argument(
        "--adopt-existing",
        action="store_true",
        help="Declare an existing data directory after checking its running stack",
    )
    parser.add_argument(
        "command",
        choices=(
            "init",
            "up",
            "ps",
            "logs",
            "exec",
            "down",
            "config",
            "build",
            "restart",
        ),
    )
    parser.add_argument("args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = compose_command(args.mode, args.project, args.gpu, args.profile)
    db_dir, db_name, db_schema = rendered_backend(command, args.mode)
    marker = db_dir / MARKER
    existing = read_mode(marker)
    running = running_modes(args.project)
    if running and running != {args.mode}:
        raise RuntimeError(
            f"Running Compose backend mode {sorted(running)} differs from requested {args.mode}"
        )
    if args.command == "init":
        if existing and existing != args.mode:
            raise RuntimeError(
                f"Data directory declares {existing}; refusing {args.mode}"
            )
        if existing is None:
            if db_dir.exists() and any(db_dir.iterdir()) and not args.adopt_existing:
                raise RuntimeError(
                    "Existing database directory requires --adopt-existing after backup and mode check"
                )
            try:
                db_dir.mkdir(parents=True, exist_ok=True)
                with marker.open("x", encoding="utf-8") as handle:
                    handle.write(args.mode + "\n")
            except PermissionError as exc:
                repair = (
                    f"sudo install -d -m 0755 -o {os.getuid()} -g {os.getgid()} "
                    f"{shlex.quote(str(db_dir))}"
                )
                raise RuntimeError(
                    f"Cannot initialize database mode in {db_dir}: permission denied. "
                    f"After checking the data directory, run: {repair}; then retry init. "
                    "Do not change ownership of the whole data directory recursively."
                ) from exc
        print(f"project={args.project} mode={args.mode} data={db_dir} declared")
        return 0
    if existing != args.mode:
        raise RuntimeError(
            "Data directory mode is missing or different; run init with the intended mode"
        )
    print(
        f"project={args.project} mode={args.mode} database={db_name} schema={db_schema or '-'} "
        f"files={','.join(Path(f).name for f in command if f.endswith('.yaml'))}",
        flush=True,
    )
    return run(command + [args.command, *args.args]).returncode


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (
        OSError,
        ValueError,
        KeyError,
        subprocess.CalledProcessError,
        RuntimeError,
    ) as exc:
        print(f"Compose mode preflight failed: {exc}", file=sys.stderr)
        sys.exit(1)
