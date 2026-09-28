"""Validate startup inputs before Django imports application modules."""

import os
import re
from pathlib import Path
from urllib.parse import urlsplit

import yaml


def load_yaml(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as stream:
            config = yaml.safe_load(stream)
    except (OSError, UnicodeError, yaml.YAMLError):
        raise RuntimeError(
            f"Configuration file cannot be read or parsed: {path}"
        ) from None
    if not isinstance(config, dict):
        raise RuntimeError(f"Configuration root must be a mapping: {path}")
    for key in (
        "Proxy",
        "Database",
        "BrowserFetch",
        "FlareSolverr",
        "Source",
        "Scraper",
        "Translator",
    ):
        if key == "Proxy" and key not in config:
            raise RuntimeError(f"Configuration key Proxy is required: {path}")
        if key in config and not isinstance(config[key], dict):
            raise RuntimeError(f"Configuration key {key} must be a mapping: {path}")
    return config


def load_env(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        raise RuntimeError(
            f"Development environment file cannot be read: {path}"
        ) from None
    values = {}
    for number, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise RuntimeError(f"Invalid .env assignment at {path}:{number}")
        key, value = (part.strip() for part in line.split("=", 1))
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise RuntimeError(f"Invalid .env key at {path}:{number}")
        if value.startswith(('"', "'")):
            if len(value) < 2 or value[-1] != value[0]:
                raise RuntimeError(f"Invalid .env quoting at {path}:{number}")
            value = value[1:-1]
        values[key] = value
    for key, value in values.items():
        os.environ.setdefault(key, value)


def boolean(value: object, key: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes"}:
            return True
        if lowered in {"0", "false", "no"}:
            return False
    raise RuntimeError(f"{key} must be a boolean")


def integer(value: object, key: str, minimum: int, maximum: int | None = None) -> int:
    try:
        if isinstance(value, bool) or not re.fullmatch(r"[0-9]+", str(value)):
            raise ValueError
        parsed = int(str(value))
    except (TypeError, ValueError):
        raise RuntimeError(f"{key} must be an integer") from None
    if parsed < minimum or (maximum is not None and parsed > maximum):
        raise RuntimeError(f"{key} is out of range")
    return parsed


def url(value: object, key: str, *, schemes=("http", "https")) -> str:
    if not isinstance(value, str):
        raise RuntimeError(f"{key} must be an absolute URL")
    try:
        parsed = urlsplit(value)
        valid = parsed.scheme in schemes and bool(parsed.hostname)
        port = parsed.port
    except ValueError:
        valid, port = False, None
    if not valid or (port is not None and port < 1):
        raise RuntimeError(f"{key} must be an absolute URL")
    return value


def _validate_yaml(config: dict, path: Path) -> None:
    proxy = config["Proxy"]
    if "Enable" not in proxy:
        raise RuntimeError(f"Configuration key Proxy.Enable is required: {path}")
    boolean(proxy["Enable"], "Proxy.Enable")
    for key in ("url", "download_url"):
        if key in proxy and proxy[key] is not None and not isinstance(proxy[key], str):
            raise RuntimeError(f"Proxy.{key} must be a string: {path}")
    if proxy["Enable"]:
        if not proxy.get("url"):
            raise RuntimeError(f"Configuration key Proxy.url is required: {path}")
        url(proxy["url"], "Proxy.url", schemes=("http", "https", "socks5", "socks5h"))
    elif proxy.get("url"):
        url(proxy["url"], "Proxy.url", schemes=("http", "https", "socks5", "socks5h"))
    if proxy.get("download_url"):
        url(
            proxy["download_url"],
            "Proxy.download_url",
            schemes=("http", "https", "socks5", "socks5h"),
        )
    database = config.get("Database", {})
    if "Engine" in database and (
        not isinstance(database["Engine"], str)
        or database["Engine"] not in {"sqlite", "postgres", "postgresql"}
    ):
        raise RuntimeError(f"Database.Engine must be sqlite or postgres: {path}")
    for key in ("Path", "Host", "Name", "User", "Password", "PasswordFile"):
        if (
            key in database
            and database[key] is not None
            and not isinstance(database[key], str)
        ):
            raise RuntimeError(f"Database.{key} must be a string: {path}")
    if "Port" in database:
        integer(database["Port"], "Database.Port", 1, 65535)
    if "ConnectionMaxAge" in database:
        integer(database["ConnectionMaxAge"], "Database.ConnectionMaxAge", 0)
    if "FlareSolverr" in config:
        legacy = config["FlareSolverr"]
        if "Enable" in legacy:
            boolean(legacy["Enable"], "FlareSolverr.Enable")
        if "timeout" in legacy:
            integer(legacy["timeout"], "FlareSolverr.timeout", 1000)
        if "url" in legacy:
            url(legacy["url"], "FlareSolverr.url")
    for key in ("Source", "Scraper"):
        for name, value in config.get(key, {}).items():
            if not isinstance(value, dict):
                raise RuntimeError(f"{key}.{name} must be a mapping: {path}")
    translator = config.get("Translator", {})
    active = translator.get("active")
    if active is not None:
        if not isinstance(active, str) or not isinstance(translator.get(active), dict):
            raise RuntimeError(
                f"Translator.active must name a configured translator: {path}"
            )
        for key in ("timeout", "max_retries"):
            if key in translator[active]:
                integer(
                    translator[active][key],
                    f"Translator.{active}.{key}",
                    1 if key == "timeout" else 0,
                )
        if "url" in translator[active]:
            url(translator[active]["url"], f"Translator.{active}.url")


def validate_yaml(config: dict, path: Path) -> None:
    """Attach the source path to every YAML validation error."""
    try:
        _validate_yaml(config, path)
    except RuntimeError as exc:
        message = str(exc)
        if str(path) not in message:
            message = f"{message}: {path}"
        raise RuntimeError(message) from None
