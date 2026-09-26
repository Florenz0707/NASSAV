#!/bin/sh
set -eu

# The translator manager checks model availability once when each process starts.
if [ "${OLLAMA_URL:-}" = "http://ollama:11434" ]; then
    python manage.py ensure_ollama_model --check-only
fi

exec "$@"
