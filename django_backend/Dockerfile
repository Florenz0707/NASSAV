FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libicu72 ca-certificates ffmpeg && rm -rf /var/lib/apt/lists/*
RUN python -m pip install --no-cache-dir uv==0.9.24
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# Fixed upstream x86-64 release; fail the build if the downloaded archive differs.
ARG TARGETARCH
RUN test "$TARGETARCH" = amd64
RUN python - <<'PY'
import hashlib
import io
import tarfile
import urllib.request
from pathlib import Path

url = 'https://github.com/nilaoda/N_m3u8DL-RE/releases/download/v0.5.1-beta/N_m3u8DL-RE_v0.5.1-beta_linux-x64_20251029.tar.gz'
expected = '2acce91b64af3ee676a32d1002e1382840d81f430e1b7f8d5b151ce1eb6fb590'
data = urllib.request.urlopen(url, timeout=120).read()
assert hashlib.sha256(data).hexdigest() == expected, 'N_m3u8DL-RE archive checksum mismatch'
with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
    binary = archive.extractfile('N_m3u8DL-RE').read()
target = Path('/app/tools/N_m3u8DL-RE')
target.parent.mkdir(parents=True, exist_ok=True)
target.write_bytes(binary)
target.chmod(0o755)
PY

COPY django_project ./django_project
COPY nassav ./nassav
COPY manage.py log_config.py ./
RUN N_m3u8DL_RE_VERSION=$(/app/tools/N_m3u8DL-RE --version) && test -n "$N_m3u8DL_RE_VERSION"

EXPOSE 9790
CMD ["uvicorn", "django_project.asgi:application", "--host", "0.0.0.0", "--port", "9790"]
