import json

from django.core.management.base import BaseCommand, CommandError

from nassav.composition import build_credential_records
from nassav.credential_crypto import CredentialUnavailable
from nassav.credential_import import import_legacy_credentials


class Command(BaseCommand):
    help = (
        "Preview or import legacy source cookies; unclassified cookies are quarantined."
    )

    def add_arguments(self, parser):
        parser.add_argument("--actor-id", type=int, required=True)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        try:
            plan = import_legacy_credentials(
                build_credential_records(), options["actor_id"], apply=options["apply"]
            )
        except (ValueError, PermissionError, CredentialUnavailable):
            raise CommandError(
                "Credential import failed; check admin, origins and keyring"
            ) from None
        self.stdout.write(json.dumps({"apply": options["apply"], "plan": plan}))
