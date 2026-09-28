from django.apps import AppConfig
from django.conf import settings


class NassavConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "nassav"
    verbose_name = "NASSAV Backend"

    def ready(self):
        """Register process-local logging and application signals."""
        from nassav.logging_setup import configure_file_logging

        configure_file_logging(settings.LOG_DIR)
        import nassav.receivers  # noqa: F401
