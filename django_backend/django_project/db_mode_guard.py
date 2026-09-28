"""Fail closed when a Compose backend starts against a different data-directory mode."""

import os
from pathlib import Path


def verify_compose_db_mode(engine: str) -> None:
    mode = os.getenv("NASSAV_COMPOSE_DB_MODE")
    if not mode:
        return  # Host development is configured directly by config.yaml.
    if mode not in {"sqlite", "postgres"} or engine != mode:
        raise RuntimeError(
            "Compose database mode conflicts with DB_ENGINE; use the matching Compose files"
        )
    marker_name = os.getenv("NASSAV_DB_MODE_FILE")
    if not marker_name:
        raise RuntimeError("NASSAV_DB_MODE_FILE is required for Compose backends")
    marker = Path(marker_name)
    try:
        declared = marker.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(
            "Database mode declaration is missing or unreadable; run scripts/compose_stack.py init"
        ) from exc
    if declared not in {"sqlite", "postgres"} or declared != mode:
        raise RuntimeError(
            "Data directory database mode conflicts with Compose mode; use the declared mode"
        )
