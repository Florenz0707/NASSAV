"""Dedicated rotatable AEAD keyring; no Django signing-key or plaintext fallback."""

import base64
import json
import os
import re
import stat
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class CredentialUnavailable(RuntimeError):
    """A safe public error: never includes secrets or ciphertext."""


class CredentialKeyring:
    def __init__(self, active_id, keys):
        if not isinstance(active_id, str) or active_id not in keys:
            raise CredentialUnavailable("Credential active key is unavailable")
        if not keys or any(
            not isinstance(key_id, str)
            or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", key_id)
            or not isinstance(key, bytes)
            or len(key) != 32
            for key_id, key in keys.items()
        ):
            raise CredentialUnavailable("Invalid credential keyring")
        self.active_id = active_id
        self._keys = dict(keys)

    @classmethod
    def from_file(cls, path):
        try:
            with Path(path).open("rb") as stream:
                metadata = os.fstat(stream.fileno())
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077:
                    raise CredentialUnavailable("Credential keyring must be private")
                raw = stream.read(65537)
            if len(raw) > 65536:
                raise ValueError
            value = json.loads(raw)
            if set(value) != {"active_key_id", "keys"}:
                raise ValueError
            keys = {
                key_id: base64.b64decode(key, validate=True)
                for key_id, key in value["keys"].items()
            }
            return cls(value["active_key_id"], keys)
        except CredentialUnavailable:
            raise
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            raise CredentialUnavailable("Credential keyring cannot be loaded") from None

    def encrypt(self, payload, *, context):
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        if len(raw) > 65536:
            raise ValueError("Credential payload is too large")
        nonce = os.urandom(12)
        cipher = AESGCM(self._keys[self.active_id]).encrypt(
            nonce, raw, context.encode()
        )
        return self.active_id, base64.b64encode(nonce + cipher).decode()

    def decrypt(self, key_id, ciphertext, *, context):
        try:
            key = self._keys[key_id]
            raw = base64.b64decode(ciphertext, validate=True)
            value = AESGCM(key).decrypt(raw[:12], raw[12:], context.encode())
            payload = json.loads(value)
            if not isinstance(payload, dict):
                raise ValueError
            return payload
        except (KeyError, ValueError, TypeError, InvalidTag):
            raise CredentialUnavailable("Credential cannot be decrypted") from None
