"""Opaque credential binding for source playback; private media waits for P5."""

from django.db.models import F
from django.utils import timezone

from nassav.credential_models import SourceCredential
from nassav.playback.models import PlaybackSession


def capture_source_binding(records, source_name):
    ref = records.resolve(source_name)  # Formal shared media uses system scope only.
    return {
        "source_name": source_name,
        "origin_host": records.origins[source_name],
        "credential_id": str(ref.id) if ref else None,
        "credential_version": ref.version if ref else None,
    }


def binding_current(binding, source_name):
    from nassav.source_registry import configured_source_origins
    from django.conf import settings

    if not isinstance(binding, dict) or set(binding) != {
        "source_name",
        "origin_host",
        "credential_id",
        "credential_version",
    }:
        return False
    if binding["source_name"] != source_name or binding[
        "origin_host"
    ] != configured_source_origins(settings.SOURCE_CONFIG).get(source_name):
        return False
    if binding["credential_id"] is None:
        return (
            binding["credential_version"] is None
            and not SourceCredential.objects.filter(
                source_name=source_name, scope="system"
            ).exists()
        )
    if (
        type(binding["credential_version"]) is not int
        or binding["credential_version"] < 1
    ):
        return False
    try:
        return SourceCredential.objects.filter(
            pk=binding["credential_id"],
            source_name=source_name,
            scope="system",
            state="active",
            version=binding["credential_version"],
            origin_host=binding["origin_host"],
        ).exists()
    except (ValueError, TypeError):
        return False


def close_bound_playback(credential_id):
    return (
        PlaybackSession.objects.filter(
            media_kind="source",
            library_grant__source_auth__credential_id=str(credential_id),
        )
        .exclude(state="closed")
        .update(
            state="closed",
            descriptor={},
            lease_until=None,
            generation=F("generation") + 1,
            version=F("version") + 1,
            updated_at=timezone.now(),
        )
    )
