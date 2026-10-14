"""Create or append a dedicated key without displaying key material."""

import base64
import json
import os
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from nassav.credential_crypto import CredentialKeyring, CredentialUnavailable


class Command(BaseCommand):
    help = "Create a private source keyring (never overwrites an existing file)."

    def add_arguments(self, parser):
        parser.add_argument("--output", required=True)
        parser.add_argument("--key-id", required=True)

    def handle(self, *args, **options):
        path = Path(options["output"])
        key_id = options["key_id"]
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", key_id):
            raise CommandError("Invalid key ID")
        payload = {
            "active_key_id": key_id,
            "keys": {key_id: base64.b64encode(os.urandom(32)).decode()},
        }
        descriptor = None
        created = False
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            created = True
            with os.fdopen(descriptor, "w") as stream:
                descriptor = None
                json.dump(payload, stream)
                stream.flush()
                os.fsync(stream.fileno())
            CredentialKeyring.from_file(path)
        except (OSError, CredentialUnavailable):
            if descriptor is not None:
                os.close(descriptor)
            if created:
                path.unlink(missing_ok=True)
            raise CommandError(
                "Keyring creation failed; existing files are preserved"
            ) from None
        self.stdout.write(
            "Private keyring created. Back it up securely before importing credentials."
        )
