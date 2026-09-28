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


def run_api() -> None:
    """Run the Django ASGI app with Uvicorn autoreload on port 8000."""
    _exec(
        "uvicorn",
        [
            "django_project.asgi:application",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
            "--reload",
        ],
    )


def _run_worker(queue: str) -> None:
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
        ],
    )


def run_default_worker() -> None:
    """Run the Celery worker for the default queue."""
    _run_worker("default")


def run_scrape_worker() -> None:
    """Run the Celery worker for the scrape queue."""
    _run_worker("scrape")


def run_download_worker() -> None:
    """Run the Celery worker for the download queue."""
    _run_worker("download")


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
