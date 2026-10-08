"""Shared facts lookup: freshness and single flight behind one interface."""

import hashlib
import json
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import timedelta
from uuid import UUID, uuid4


@dataclass(frozen=True)
class CacheKey:
    avid: str
    provider_kind: str
    provider_name: str
    scope_key: str
    variant_key: str

    @classmethod
    def create(cls, avid, kind, provider, *, scope, variant="default"):
        avid = str(avid).strip().upper()
        if not avid or len(avid) > 50 or kind not in {"source", "scraper"}:
            raise ValueError("Invalid provider cache identity")
        return cls(
            avid,
            kind,
            str(provider).lower(),
            hashlib.sha256(str(scope).encode()).hexdigest(),
            hashlib.sha256(str(variant).encode()).hexdigest(),
        )


@dataclass(frozen=True)
class CachePolicy:
    parser_version: str
    required_fields: frozenset[str]
    ttl: timedelta


@dataclass(frozen=True)
class CacheClaim:
    key: CacheKey
    owner: UUID
    generation: int
    playback: bool


@dataclass(frozen=True)
class CachedFacts:
    payload: dict
    hit: bool


class CachePublicationLost(RuntimeError):
    pass


class ProviderFactsStore(ABC):
    @abstractmethod
    def read_many(self, keys, policy, now, *, playback=False) -> dict: ...
    @abstractmethod
    def claim(self, key, owner, now, until, *, playback=False) -> CacheClaim | None: ...
    @abstractmethod
    def publish(self, claim, payload, policy, now) -> bool: ...
    @abstractmethod
    def release(self, claim) -> None: ...


class ProviderFactsCache:
    def __init__(
        self,
        store: ProviderFactsStore,
        *,
        now: Callable,
        clock=time.monotonic,
        wait=time.sleep,
    ):
        self.store, self.now, self.clock, self.wait = store, now, clock, wait

    def read_many(self, keys, policy, *, playback=False):
        return self.store.read_many(keys, policy, self.now(), playback=playback)

    def resolve(
        self,
        key,
        policy,
        fetch,
        *,
        check=lambda: None,
        fence=None,
        force=False,
        playback=False,
    ):
        if policy.ttl.total_seconds() <= 0:
            raise ValueError("Cache TTL must be positive")
        started = self.clock()
        while True:
            check()
            if not force:
                cached = self.read_many([key], policy, playback=playback)
                if key in cached:
                    return CachedFacts(cached[key], True)
            now = self.now()
            claim = self.store.claim(
                key, uuid4(), now, now + timedelta(seconds=240), playback=playback
            )
            if claim is not None:
                break
            if self.clock() - started >= 60:
                raise TimeoutError("Provider cache update is busy")
            self.wait(0.1)
        try:
            payload = fetch()
            check()
            if not isinstance(payload, dict) or not payload:
                return CachedFacts({}, False)
            if not policy.required_fields.issubset(payload):
                raise ValueError("Provider result lacks validated fields")
            encoded = json.dumps(payload, ensure_ascii=False)
            if len(encoded.encode()) > 2 * 1024 * 1024:
                raise ValueError("Provider cache payload exceeds limit")
            parsed = json.loads(encoded)

            def publish():
                check()
                if not self.store.publish(claim, parsed, policy, self.now()):
                    raise CachePublicationLost("Provider cache update ownership lost")

            if fence is None:
                publish()
            else:
                fence(publish)
            return CachedFacts(parsed, False)
        finally:
            self.store.release(claim)


class DjangoProviderFactsStore(ProviderFactsStore):
    """Short conditional writes; never performs network or file work."""

    @staticmethod
    def model(playback):
        from nassav.resource_cache_models import (
            ResourceMetadataCache,
            ResourcePlaybackCache,
        )

        return ResourcePlaybackCache if playback else ResourceMetadataCache

    def read_many(self, keys, policy, now, *, playback=False):
        from django.db.models import Q

        if not keys:
            return {}
        query = Q(pk__in=[])
        for key in set(keys):
            query |= Q(**asdict(key))
        output = {}
        model = self.model(playback)
        for record in model.objects.filter(
            query, fresh_until__gt=now, parser_version=policy.parser_version
        ):
            if record.payload and policy.required_fields.issubset(
                record.validated_fields
            ):
                key = CacheKey(
                    *(getattr(record, name) for name in CacheKey.__dataclass_fields__)
                )
                output[key] = json.loads(json.dumps(record.payload))
        model.objects.filter(query, last_used_at__lt=now - timedelta(hours=6)).update(
            last_used_at=now
        )
        return output

    def claim(self, key, owner, now, until, *, playback=False):
        from django.db.models import F, Q

        model = self.model(playback)
        row, _ = model.objects.get_or_create(**asdict(key))
        updated = (
            model.objects.filter(pk=row.pk)
            .filter(Q(fetch_owner__isnull=True) | Q(fetch_lease_until__lte=now))
            .update(
                fetch_owner=owner,
                fetch_lease_until=until,
                generation=F("generation") + 1,
            )
        )
        if not updated:
            return None
        generation = (
            model.objects.filter(pk=row.pk, fetch_owner=owner)
            .values_list("generation", flat=True)
            .first()
        )
        if generation is None:
            return None
        return CacheClaim(key, owner, generation, playback)

    def publish(self, claim, payload, policy, now):
        return bool(
            self.model(claim.playback)
            .objects.filter(
                **asdict(claim.key),
                fetch_owner=claim.owner,
                generation=claim.generation,
                fetch_lease_until__gt=now,
            )
            .update(
                payload=payload,
                validated_fields=sorted(policy.required_fields),
                parser_version=policy.parser_version,
                fetched_at=now,
                fresh_until=now + policy.ttl,
                last_used_at=now,
            )
        )

    def release(self, claim):
        self.model(claim.playback).objects.filter(
            **asdict(claim.key), fetch_owner=claim.owner, generation=claim.generation
        ).update(fetch_owner=None, fetch_lease_until=None)

    def invalidate(self, key, *, playback=False):
        from django.db.models import F

        self.model(playback).objects.filter(**asdict(key)).update(
            fresh_until=None,
            generation=F("generation") + 1,
            fetch_owner=None,
            fetch_lease_until=None,
        )
