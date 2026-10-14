import json

from django.core.management.base import BaseCommand, CommandError

from nassav.composition import build_credential_records
from nassav.credential_crypto import CredentialUnavailable
from nassav.credential_rotation import rotate_credentials
from nassav.source_credentials import CredentialConflict


class Command(BaseCommand):
    help = "Preview or re-encrypt a bounded batch using the keyring's active key."

    def add_arguments(self, parser):
        parser.add_argument("--actor-id", type=int, required=True)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--batch-size", type=int, default=100)

    def handle(self, *args, **options):
        try:
            result = rotate_credentials(
                build_credential_records(),
                options["actor_id"],
                apply=options["apply"],
                batch_size=options["batch_size"],
            )
        except (ValueError, PermissionError, CredentialUnavailable, CredentialConflict):
            raise CommandError(
                "Credential rotation failed; preserve all old keys and retry"
            ) from None
        self.stdout.write(json.dumps(result))
