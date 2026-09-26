"""Ensure the active Ollama translation model is present before workers start.

Usage:
    python manage.py ensure_ollama_model

The URL comes from OLLAMA_URL when set, otherwise Translator.<active>.url.
"""

import os

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Pull and verify the active Ollama translation model"

    def add_arguments(self, parser):
        parser.add_argument(
            "--check-only",
            action="store_true",
            help="Verify the configured model without downloading it",
        )

    def handle(self, *args, **options):
        active = settings.ACTIVE_TRANSLATOR
        config = settings.TRANSLATOR_CONFIG.get(active, {})
        if config.get("type") != "ollama":
            raise CommandError("The active translator must use Ollama")

        model = config.get("model")
        if not model:
            raise CommandError("The active Ollama translator has no model configured")
        url = (os.getenv("OLLAMA_URL") or config.get("url") or "").rstrip("/")
        if not url:
            raise CommandError("The active Ollama translator has no URL configured")

        try:
            response = requests.get(f"{url}/api/tags", timeout=10)
            response.raise_for_status()
            models = {item.get("name") for item in response.json().get("models", [])}
            if model not in models:
                if options["check_only"]:
                    raise CommandError(f"Ollama model {model} is not installed")
                self.stdout.write(f"Pulling Ollama model {model}...")
                response = requests.post(
                    f"{url}/api/pull",
                    json={"model": model, "stream": False},
                    timeout=(10, 3600),
                )
                response.raise_for_status()
                if response.json().get("status") != "success":
                    raise CommandError(f"Ollama did not finish pulling {model}")

            response = requests.get(f"{url}/api/tags", timeout=10)
            response.raise_for_status()
            if model not in {
                item.get("name") for item in response.json().get("models", [])
            }:
                raise CommandError(f"Ollama model {model} is unavailable after pull")
        except (requests.RequestException, ValueError) as exc:
            raise CommandError(
                f"Unable to prepare Ollama model {model}: {exc}"
            ) from exc

        self.stdout.write(self.style.SUCCESS(f"Ollama model ready: {model}"))
