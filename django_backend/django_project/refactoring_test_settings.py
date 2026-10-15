"""Isolated R0-R7 quality gate: uv run pytest tests/ --ds=django_project.refactoring_test_settings -v.

Use the credential-free template, temporary SQLite/resources, and in-memory cache
and Channels. Live tests are skipped and unexpected network use fails in conftest.
This module is only a test configuration, never a deployment configuration.
"""

import atexit
import os
from pathlib import Path
from tempfile import TemporaryDirectory

_sandbox = TemporaryDirectory(prefix="nassav-refactoring-")
atexit.register(_sandbox.cleanup)
_root = Path(_sandbox.name)
os.environ.update(
    DEBUG="false",
    SECRET_KEY="refactoring-tests-only",
    DB_ENGINE="sqlite",
    DATABASE_PATH=str(_root / "database.sqlite3"),
    NASSAV_CONFIG_PATH=str(
        Path(__file__).resolve().parents[1] / "config" / "config.example.yaml"
    ),
    NASSAV_ENV_PATH=str(_root / "absent.env"),
    NASSAV_RESOURCE_DIR=str(_root / "resource"),
    NASSAV_SECURE_COOKIES="false",
    NASSAV_SOURCE_CREDENTIAL_KEYRING_FILE="",
    NASSAV_SCOPED_SOURCE_CREDENTIALS="false",
    NASSAV_SHARED_LIBRARY_ENABLED="false",
    NASSAV_MULTI_USER_ENABLED="false",
    NASSAV_RESOURCE_GC_ENABLED="false",
    NASSAV_RESOURCE_GC_BATCH_SIZE="32",
)
os.environ.pop("NASSAV_COMPOSE_DB_MODE", None)
os.environ.pop("NASSAV_DB_MODE_FILE", None)

from django_project import settings as _production

for _name in dir(_production):
    if _name.isupper():
        globals()[_name] = getattr(_production, _name)

NASSAV_REFACTORING_OFFLINE = True
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
# The production manager probes availability at construction. Never probe Ollama
# during offline collection; dedicated adapter tests supply mocked transports.
ACTIVE_TRANSLATOR = None
