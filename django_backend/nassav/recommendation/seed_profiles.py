from .seed_policy import normalize_seed_value
from collections.abc import Iterable

from django.db.models import F
from django.utils import timezone

from nassav.models import Actor, ActorSourceMapping, Genre, GenreSourceMapping
from nassav.models import RecommendationItem, RecommendationSeedProfile

from .entities import RecommendationSeed


class RecommendationSeedProfileRepository:
    def has_blocked_profiles(self) -> bool:
        return RecommendationSeedProfile.objects.filter(
            seed_type__in=["actor", "genre"],
            is_blocked=True,
        ).exists()

    def build_blocked_seed_keys(
        self,
    ) -> tuple[set[tuple[str, str]], set[tuple[str, str, str]]]:
        blocked_profiles = list(
            RecommendationSeedProfile.objects.filter(
                seed_type__in=["actor", "genre"],
                is_blocked=True,
            ).only(
                "seed_type",
                "value",
                "normalized_value",
                "source_name",
                "source_identifier",
            )
        )
        if not blocked_profiles:
            return set(), set()

        blocked_name_keys: set[tuple[str, str]] = {
            (
                str(profile.seed_type or "").strip().lower(),
                str(profile.normalized_value or "").strip(),
            )
            for profile in blocked_profiles
            if str(profile.normalized_value or "").strip()
        }
        blocked_source_keys: set[tuple[str, str, str]] = {
            (
                str(profile.seed_type or "").strip().lower(),
                str(profile.source_name or "").strip().lower(),
                str(profile.source_identifier or "").strip().lower(),
            )
            for profile in blocked_profiles
            if str(profile.source_name or "").strip()
            and str(profile.source_identifier or "").strip()
        }

        blocked_actor_values = [
            str(profile.value or "").strip()
            for profile in blocked_profiles
            if str(profile.seed_type or "").strip().lower() == "actor"
            and not str(profile.source_name or "").strip()
            and not str(profile.source_identifier or "").strip()
            and str(profile.value or "").strip()
        ]
        blocked_genre_values = [
            str(profile.value or "").strip()
            for profile in blocked_profiles
            if str(profile.seed_type or "").strip().lower() == "genre"
            and not str(profile.source_name or "").strip()
            and not str(profile.source_identifier or "").strip()
            and str(profile.value or "").strip()
        ]

        if blocked_actor_values:
            actor_mappings = ActorSourceMapping.objects.filter(
                actor__name__in=blocked_actor_values,
                is_active=True,
            ).only("source_name", "source_actor_slug")
            blocked_source_keys.update(
                (
                    "actor",
                    str(mapping.source_name or "").strip().lower(),
                    str(mapping.source_actor_slug or "").strip().lower(),
                )
                for mapping in actor_mappings
                if str(mapping.source_name or "").strip()
                and str(mapping.source_actor_slug or "").strip()
            )

        if blocked_genre_values:
            genre_mappings = GenreSourceMapping.objects.filter(
                genre__name__in=blocked_genre_values,
                is_active=True,
            ).only("source_name", "source_genre_slug")
            blocked_source_keys.update(
                (
                    "genre",
                    str(mapping.source_name or "").strip().lower(),
                    str(mapping.source_genre_slug or "").strip().lower(),
                )
                for mapping in genre_mappings
                if str(mapping.source_name or "").strip()
                and str(mapping.source_genre_slug or "").strip()
            )

        return blocked_name_keys, blocked_source_keys

    def get_blocked_normalized_values(
        self,
        *,
        seed_type: str,
        values: Iterable[str],
    ) -> set[str]:
        normalized_values = {
            self.normalize_value(value)
            for value in values
            if self.normalize_value(value)
        }
        if not normalized_values:
            return set()

        return set(
            RecommendationSeedProfile.objects.filter(
                seed_type=str(seed_type or "").strip().lower(),
                is_blocked=True,
                normalized_value__in=normalized_values,
            ).values_list("normalized_value", flat=True)
        )

    def get_blocked_source_identifiers(
        self,
        *,
        seed_type: str,
        source_name: str,
        identifiers: Iterable[str],
    ) -> set[str]:
        normalized_source_name = str(source_name or "").strip().lower()
        normalized_identifiers = {
            str(identifier or "").strip().lower()
            for identifier in identifiers
            if str(identifier or "").strip()
        }
        if not normalized_source_name or not normalized_identifiers:
            return set()

        return set(
            RecommendationSeedProfile.objects.filter(
                seed_type=str(seed_type or "").strip().lower(),
                is_blocked=True,
                source_name=normalized_source_name,
                source_identifier__in=normalized_identifiers,
            ).values_list("source_identifier", flat=True)
        )

    def filter_allowed_seeds(
        self,
        seeds: list[RecommendationSeed],
    ) -> list[RecommendationSeed]:
        if not seeds:
            return []

        blocked_name_keys, blocked_source_keys = self.build_blocked_seed_keys()
        if not blocked_name_keys and not blocked_source_keys:
            return seeds

        allowed: list[RecommendationSeed] = []
        for seed in seeds:
            normalized_value = self.normalize_value(seed.value)
            lookup_payload = dict(seed.lookup_payload or {})
            source_name = str(lookup_payload.get("source_name", "")).strip().lower()
            source_identifier = self._source_identifier_for_seed(seed)

            if (seed.seed_type, normalized_value) in blocked_name_keys:
                continue
            if source_name and source_identifier:
                if (
                    seed.seed_type,
                    source_name,
                    source_identifier,
                ) in blocked_source_keys:
                    continue
            allowed.append(seed)
        return allowed

    def sync_seed_profiles(
        self,
        *,
        items: Iterable[RecommendationItem],
        timestamp=None,
    ) -> None:
        timestamp = timestamp or timezone.now()
        grouped: dict[tuple[str, str, str, str], dict] = {}
        for item in items:
            seed_rows = getattr(item, "item_seeds").all()
            for seed_row in seed_rows:
                identity = (
                    seed_row.seed_type,
                    seed_row.normalized_value,
                    seed_row.source_name,
                    seed_row.source_identifier,
                )
                payload = grouped.setdefault(
                    identity,
                    {
                        "seed_type": seed_row.seed_type,
                        "value": seed_row.seed_value,
                        "source_name": seed_row.source_name,
                        "source_identifier": seed_row.source_identifier,
                        "aliases": list(seed_row.aliases or []),
                        "recommended_count": 0,
                    },
                )
                payload["recommended_count"] += 1
                if not payload["value"] and seed_row.seed_value:
                    payload["value"] = seed_row.seed_value
                payload["aliases"] = self._merge_aliases(
                    payload["aliases"],
                    list(seed_row.aliases or []),
                )

        for identity, payload in grouped.items():
            profile, created = RecommendationSeedProfile.objects.get_or_create(
                seed_type=identity[0],
                normalized_value=identity[1],
                source_name=identity[2],
                source_identifier=identity[3],
                defaults={
                    "value": payload["value"],
                    "aliases": payload["aliases"],
                    "recommended_count": payload["recommended_count"],
                    "last_recommended_at": timestamp,
                },
            )
            if created:
                continue

            profile.value = profile.value or payload["value"]
            profile.aliases = self._merge_aliases(
                list(profile.aliases or []),
                payload["aliases"],
            )
            profile.last_recommended_at = timestamp
            RecommendationSeedProfile.objects.filter(pk=profile.pk).update(
                value=profile.value,
                aliases=profile.aliases,
                last_recommended_at=timestamp,
                recommended_count=F("recommended_count") + payload["recommended_count"],
                updated_at=timestamp,
            )

    def build_seed_score_map(self) -> dict[str, float]:
        profiles = RecommendationSeedProfile.objects.filter(
            recommended_count__gt=0
        ).only(
            "seed_type",
            "value",
            "accepted_count",
            "disliked_count",
            "recommended_count",
        )
        output: dict[str, float] = {}
        for profile in profiles:
            recommended_count = max(int(profile.recommended_count or 0), 1)
            net = int(profile.accepted_count or 0) - int(profile.disliked_count or 0)
            if net == 0:
                continue
            output[f"{profile.seed_type}:{profile.value}"] = round(
                net / recommended_count, 4
            )
        return output

    def block_actor(
        self,
        *,
        actor: Actor,
        reason: str = "manual",
    ) -> RecommendationSeedProfile:
        profile = self._set_manual_block(
            seed_type="actor",
            value=actor.name,
            reason=reason,
        )
        self._set_actor_source_blocks(actor=actor, value=actor.name, reason=reason)
        return profile

    def unblock_actor(self, *, actor: Actor) -> RecommendationSeedProfile | None:
        profile = self._clear_manual_block(
            seed_type="actor",
            value=actor.name,
        )
        self._clear_actor_source_blocks(actor=actor, value=actor.name)
        return profile

    def block_genre(
        self,
        *,
        genre: Genre,
        reason: str = "manual",
    ) -> RecommendationSeedProfile:
        profile = self._set_manual_block(
            seed_type="genre",
            value=genre.name,
            reason=reason,
        )
        self._set_genre_source_blocks(genre=genre, value=genre.name, reason=reason)
        return profile

    def unblock_genre(self, *, genre: Genre) -> RecommendationSeedProfile | None:
        profile = self._clear_manual_block(
            seed_type="genre",
            value=genre.name,
        )
        self._clear_genre_source_blocks(genre=genre, value=genre.name)
        return profile

    def _set_actor_source_blocks(
        self, *, actor: Actor, value: str, reason: str
    ) -> None:
        actor_id = getattr(actor, "pk", None)
        if actor_id is None:
            return
        mappings = ActorSourceMapping.objects.filter(
            actor_id=actor_id,
            is_active=True,
        )
        for mapping in mappings:
            source_name = str(getattr(mapping, "source_name", "") or "").strip().lower()
            source_identifier = (
                str(getattr(mapping, "source_actor_slug", "") or "").strip().lower()
            )
            self._set_manual_source_block(
                seed_type="actor",
                value=value,
                source_name=source_name,
                source_identifier=source_identifier,
                reason=reason,
            )

    def _clear_actor_source_blocks(self, *, actor: Actor, value: str) -> None:
        actor_id = getattr(actor, "pk", None)
        if actor_id is None:
            return
        mappings = ActorSourceMapping.objects.filter(
            actor_id=actor_id,
            is_active=True,
        )
        for mapping in mappings:
            source_name = str(getattr(mapping, "source_name", "") or "").strip().lower()
            source_identifier = (
                str(getattr(mapping, "source_actor_slug", "") or "").strip().lower()
            )
            self._clear_manual_source_block(
                seed_type="actor",
                value=value,
                source_name=source_name,
                source_identifier=source_identifier,
            )

    def _set_genre_source_blocks(
        self, *, genre: Genre, value: str, reason: str
    ) -> None:
        genre_id = getattr(genre, "pk", None)
        if genre_id is None:
            return
        mappings = GenreSourceMapping.objects.filter(
            genre_id=genre_id,
            is_active=True,
        )
        for mapping in mappings:
            source_name = str(getattr(mapping, "source_name", "") or "").strip().lower()
            source_identifier = (
                str(getattr(mapping, "source_genre_slug", "") or "").strip().lower()
            )
            self._set_manual_source_block(
                seed_type="genre",
                value=value,
                source_name=source_name,
                source_identifier=source_identifier,
                reason=reason,
            )

    def _clear_genre_source_blocks(self, *, genre: Genre, value: str) -> None:
        genre_id = getattr(genre, "pk", None)
        if genre_id is None:
            return
        mappings = GenreSourceMapping.objects.filter(
            genre_id=genre_id,
            is_active=True,
        )
        for mapping in mappings:
            source_name = str(getattr(mapping, "source_name", "") or "").strip().lower()
            source_identifier = (
                str(getattr(mapping, "source_genre_slug", "") or "").strip().lower()
            )
            self._clear_manual_source_block(
                seed_type="genre",
                value=value,
                source_name=source_name,
                source_identifier=source_identifier,
            )

    def _set_manual_source_block(
        self,
        *,
        seed_type: str,
        value: str,
        source_name: str,
        source_identifier: str,
        reason: str,
    ) -> None:
        normalized_source_name = str(source_name or "").strip().lower()
        normalized_source_identifier = str(source_identifier or "").strip().lower()
        if not normalized_source_name or not normalized_source_identifier:
            return

        normalized_value = self.normalize_value(value)
        profile, _ = RecommendationSeedProfile.objects.get_or_create(
            seed_type=seed_type,
            normalized_value=normalized_value,
            source_name=normalized_source_name,
            source_identifier=normalized_source_identifier,
            defaults={
                "value": str(value or "").strip(),
            },
        )
        profile.value = profile.value or str(value or "").strip()
        profile.is_blocked = True
        profile.block_reason = str(reason or "").strip() or "manual"
        profile.save()

    def _clear_manual_source_block(
        self,
        *,
        seed_type: str,
        value: str,
        source_name: str,
        source_identifier: str,
    ) -> None:
        normalized_source_name = str(source_name or "").strip().lower()
        normalized_source_identifier = str(source_identifier or "").strip().lower()
        if not normalized_source_name or not normalized_source_identifier:
            return

        normalized_value = self.normalize_value(value)
        profile = (
            RecommendationSeedProfile.objects.filter(
                seed_type=seed_type,
                normalized_value=normalized_value,
                source_name=normalized_source_name,
                source_identifier=normalized_source_identifier,
            )
            .order_by("id")
            .first()
        )
        if profile is None:
            return

        profile.is_blocked = False
        profile.block_reason = ""
        profile.save()

    def increment_dislike_counts_for_item(self, item: RecommendationItem) -> None:
        self.adjust_feedback_counts_for_item(
            item, old_feedback="", new_feedback="dislike"
        )

    def adjust_feedback_counts_for_item(
        self,
        item: RecommendationItem,
        *,
        old_feedback: str = "",
        new_feedback: str = "",
    ) -> None:
        old_feedback = str(old_feedback or "").strip().lower()
        new_feedback = str(new_feedback or "").strip().lower()
        if old_feedback == new_feedback:
            return

        accepted_delta = self._feedback_delta(
            old_feedback=old_feedback,
            new_feedback=new_feedback,
            target="like",
        )
        disliked_delta = self._feedback_delta(
            old_feedback=old_feedback,
            new_feedback=new_feedback,
            target="dislike",
        )
        if accepted_delta == 0 and disliked_delta == 0:
            return

        seen_profiles: set[tuple[str, str, str, str]] = set()
        seed_rows = getattr(item, "item_seeds").all()
        for seed_row in seed_rows:
            identity = (
                seed_row.seed_type,
                seed_row.normalized_value,
                seed_row.source_name,
                seed_row.source_identifier,
            )
            if identity in seen_profiles:
                continue
            seen_profiles.add(identity)

            profile, _ = RecommendationSeedProfile.objects.get_or_create(
                seed_type=identity[0],
                normalized_value=identity[1],
                source_name=identity[2],
                source_identifier=identity[3],
                defaults={
                    "value": seed_row.seed_value,
                    "aliases": list(seed_row.aliases or []),
                },
            )
            update_payload = {
                "value": profile.value or seed_row.seed_value,
                "aliases": self._merge_aliases(
                    list(profile.aliases or []),
                    list(seed_row.aliases or []),
                ),
                "updated_at": timezone.now(),
            }
            if accepted_delta:
                update_payload["accepted_count"] = F("accepted_count") + accepted_delta
            if disliked_delta:
                update_payload["disliked_count"] = F("disliked_count") + disliked_delta
            RecommendationSeedProfile.objects.filter(pk=profile.pk).update(
                **update_payload
            )

    def _feedback_delta(
        self,
        *,
        old_feedback: str,
        new_feedback: str,
        target: str,
    ) -> int:
        delta = 0
        if new_feedback == target:
            delta += 1
        if old_feedback == target:
            delta -= 1
        return delta

    def _source_identifier_for_seed(self, seed: RecommendationSeed) -> str:
        payload = dict(seed.lookup_payload or {})
        if seed.seed_type == "actor":
            return str(payload.get("model_slug", "")).strip().lower()
        if seed.seed_type == "genre":
            return str(payload.get("genre_slug", "")).strip().lower()
        return ""

    def _merge_aliases(self, base: list[str], extra: list[str]) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for item in [*(base or []), *(extra or [])]:
            normalized = str(item or "").strip()
            if not normalized:
                continue
            token = normalized.casefold()
            if token in seen:
                continue
            seen.add(token)
            merged.append(normalized)
        return merged

    @staticmethod
    def normalize_value(value: str) -> str:
        return normalize_seed_value(value)

    def _set_manual_block(
        self,
        *,
        seed_type: str,
        value: str,
        reason: str,
    ) -> RecommendationSeedProfile:
        normalized_value = self.normalize_value(value)
        profile, _ = RecommendationSeedProfile.objects.get_or_create(
            seed_type=seed_type,
            normalized_value=normalized_value,
            source_name="",
            source_identifier="",
            defaults={
                "value": str(value or "").strip(),
            },
        )
        profile.value = profile.value or str(value or "").strip()
        profile.is_blocked = True
        profile.block_reason = str(reason or "").strip() or "manual"
        profile.save()
        return profile

    def _clear_manual_block(
        self,
        *,
        seed_type: str,
        value: str,
    ) -> RecommendationSeedProfile | None:
        normalized_value = self.normalize_value(value)
        profile = (
            RecommendationSeedProfile.objects.filter(
                seed_type=seed_type,
                normalized_value=normalized_value,
                source_name="",
                source_identifier="",
            )
            .order_by("id")
            .first()
        )
        if profile is None:
            return None

        profile.is_blocked = False
        profile.block_reason = ""
        profile.save()
        return profile


recommendation_seed_profile_repository = RecommendationSeedProfileRepository()
