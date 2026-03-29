import re
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from django.utils import timezone

from nassav.models import Actor, ActorSourceMapping


@dataclass(frozen=True)
class JableModelCandidate:
    source_actor_name: str
    source_actor_slug: str
    source_actor_url: str


def extract_actor_aliases(raw_name: str) -> list[str]:
    name = str(raw_name or "").strip()
    if not name:
        return []

    variants: list[str] = []
    seen: set[str] = {name.casefold()}

    def add_variant(candidate: str) -> None:
        normalized = str(candidate or "").strip()
        if not normalized:
            return
        token = normalized.casefold()
        if token in seen:
            return
        seen.add(token)
        variants.append(normalized)

    fullwidth_match = re.match(r"^(.*?)（(.+?)）$", name)
    halfwidth_match = re.match(r"^(.*?)\((.+?)\)$", name)
    match = fullwidth_match or halfwidth_match
    if match:
        outer_name = match.group(1).strip()
        inner_aliases = match.group(2).strip()
        add_variant(outer_name)
        for part in re.split(r"[、,，/／|・]+", inner_aliases):
            add_variant(part)

    return variants


def normalize_person_name(raw_value: str) -> str:
    value = str(raw_value or "").strip()
    value = re.sub(r"[\s\u3000]+", "", value)
    return value.casefold()


def build_lookup_terms(actor_name: str) -> list[str]:
    terms = [str(actor_name or "").strip()]
    terms.extend(extract_actor_aliases(actor_name))
    return [term for term in terms if term]


def extract_model_display_name(anchor) -> str:
    for attr_name in ("data-original-title", "title"):
        value = str(anchor.get(attr_name) or "").strip()
        if value:
            return value

    for tag in anchor.find_all(True):
        for attr_name in ("data-original-title", "title"):
            value = str(tag.get(attr_name) or "").strip()
            if value:
                return value

    return str(anchor.get_text(" ", strip=True)).strip()


def parse_jable_model_candidates(
    html: str,
    *,
    base_url: str = "https://jable.tv/",
) -> list[JableModelCandidate]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[JableModelCandidate] = []
    seen_slugs: set[str] = set()

    for anchor in soup.select("div.models a.model[href]"):
        href = str(anchor.get("href") or "").strip()
        if not href:
            continue

        source_actor_url = urljoin(base_url, href)
        match = re.search(r"/models/([^/?#]+)/?", source_actor_url)
        if not match:
            continue

        source_actor_slug = match.group(1).strip().strip("/").lower()
        if not source_actor_slug or source_actor_slug in seen_slugs:
            continue

        seen_slugs.add(source_actor_slug)
        candidates.append(
            JableModelCandidate(
                source_actor_name=extract_model_display_name(anchor),
                source_actor_slug=source_actor_slug,
                source_actor_url=source_actor_url,
            )
        )

    return candidates


def select_best_model_candidate(
    *,
    actor_name: str,
    candidates: list[JableModelCandidate],
) -> tuple[JableModelCandidate | None, float, str]:
    if not candidates:
        return None, 0.0, "no_candidate"

    normalized_terms = {
        normalize_person_name(term)
        for term in build_lookup_terms(actor_name)
        if normalize_person_name(term)
    }
    if not normalized_terms:
        return None, 0.0, "empty_lookup_terms"

    exact_matches = [
        candidate
        for candidate in candidates
        if normalize_person_name(candidate.source_actor_name) in normalized_terms
    ]
    if len(exact_matches) == 1:
        return exact_matches[0], 1.0, "exact_name"
    if len(exact_matches) > 1:
        return None, 0.0, "ambiguous_exact_name"

    partial_matches = []
    for candidate in candidates:
        normalized_name = normalize_person_name(candidate.source_actor_name)
        if not normalized_name:
            continue
        if any(
            term in normalized_name or normalized_name in term
            for term in normalized_terms
        ):
            partial_matches.append(candidate)

    if len(partial_matches) == 1:
        return partial_matches[0], 0.9, "partial_name"
    if len(partial_matches) > 1:
        return None, 0.0, "ambiguous_partial_name"

    if len(candidates) == 1:
        return candidates[0], 0.7, "single_model_fallback"

    return None, 0.0, "no_match"


def persist_actor_source_mapping(
    *,
    actor: Actor,
    candidate: JableModelCandidate,
    confidence: float,
    match_method: str = "imported",
    is_verified: bool = False,
) -> tuple[bool, str]:
    conflict = (
        ActorSourceMapping.objects.filter(
            source_name="jable",
            source_actor_slug=candidate.source_actor_slug,
            is_active=True,
        )
        .exclude(actor_id=actor.pk)
        .first()
    )
    if conflict is not None:
        return (
            False,
            f"slug {candidate.source_actor_slug} 已绑定到演员 {conflict.actor.name}",
        )

    existing = ActorSourceMapping.objects.filter(
        actor=actor,
        source_name="jable",
    ).first()
    aliases = list(existing.aliases or []) if existing is not None else []

    ActorSourceMapping.objects.update_or_create(
        actor=actor,
        source_name="jable",
        defaults={
            "source_actor_name": candidate.source_actor_name,
            "source_actor_slug": candidate.source_actor_slug,
            "source_actor_url": candidate.source_actor_url,
            "aliases": aliases,
            "match_method": match_method,
            "confidence": confidence,
            "is_verified": is_verified,
            "is_active": True,
            "last_seen_at": timezone.now(),
        },
    )
    return True, "saved"


def sync_actor_source_mappings_from_jable_html(
    *,
    actors: Iterable[Actor],
    html: str,
    base_url: str,
    match_method: str = "imported",
) -> dict[str, int]:
    candidates = parse_jable_model_candidates(html, base_url=base_url)
    stats = {
        "parsed_candidates": len(candidates),
        "saved": 0,
        "unmatched": 0,
        "conflict": 0,
    }
    if not candidates:
        return stats

    for actor in actors:
        selected, confidence, _ = select_best_model_candidate(
            actor_name=actor.name,
            candidates=candidates,
        )
        if selected is None:
            stats["unmatched"] += 1
            continue

        ok, _ = persist_actor_source_mapping(
            actor=actor,
            candidate=selected,
            confidence=confidence,
            match_method=match_method,
        )
        if ok:
            stats["saved"] += 1
        else:
            stats["conflict"] += 1

    return stats
