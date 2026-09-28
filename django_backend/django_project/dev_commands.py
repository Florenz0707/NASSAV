"""Convenient local-development entry points for the API and Celery services."""

import os
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent.parent


def _exec(module: str, arguments: list[str]) -> None:
    os.chdir(BACKEND_DIR)
    os.execv(
        sys.executable,
        [sys.executable, "-m", module, *arguments, *sys.argv[1:]],
    )


def _has_option(arguments: list[str], *options: str) -> bool:
    for argument in arguments:
        if argument in options:
            return True
        if argument.startswith("--") and any(
            argument.startswith(f"{option}=") for option in options
        ):
            return True
        if "-n" in options and argument.startswith("-n") and argument != "-n":
            return True
    return False


def _default_option(
    arguments: list[str],
    option: str,
    default: str,
    env_name: str,
    *aliases: str,
) -> list[str]:
    if _has_option(arguments, option, *aliases):
        return []
    return [option, os.environ.get(env_name, default)]


def run_api() -> None:
    """Run the Django ASGI app with configurable Uvicorn host and port."""
    user_arguments = sys.argv[1:]
    _exec(
        "uvicorn",
        [
            "django_project.asgi:application",
            *_default_option(user_arguments, "--host", "127.0.0.1", "NASSAV_API_HOST"),
            *_default_option(user_arguments, "--port", "9790", "NASSAV_API_PORT"),
            "--reload",
        ],
    )


def _run_worker(queue: str, default_name: str, env_name: str) -> None:
    user_arguments = sys.argv[1:]
    _exec(
        "celery",
        [
            "-A",
            "django_project",
            "worker",
            "-l",
            "INFO",
            "-Q",
            queue,
            "-c",
            "1",
            "--prefetch-multiplier=1",
            *_default_option(
                user_arguments,
                "--hostname",
                default_name,
                env_name,
                "-n",
            ),
        ],
    )


def run_default_worker() -> None:
    """Run the Celery worker for the default queue."""
    _run_worker("default", "default@%h", "NASSAV_WORKER_DEFAULT_NAME")


def run_scrape_worker() -> None:
    """Run the Celery worker for the scrape queue."""
    _run_worker("scrape", "scrape@%h", "NASSAV_WORKER_SCRAPE_NAME")


def run_download_worker() -> None:
    """Run the Celery worker for the download queue."""
    _run_worker("download", "download@%h", "NASSAV_WORKER_DOWNLOAD_NAME")


def run_beat() -> None:
    """Run the single local Celery Beat scheduler."""
    schedule_dir = BACKEND_DIR / "celery_beat"
    schedule_dir.mkdir(parents=True, exist_ok=True)
    _exec(
        "celery",
        [
            "-A",
            "django_project",
            "beat",
            "-l",
            "INFO",
            "-s",
            str(schedule_dir / "schedule"),
        ],
    )
