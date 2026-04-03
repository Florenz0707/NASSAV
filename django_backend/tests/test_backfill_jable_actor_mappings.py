import importlib.util
from pathlib import Path

import pytest

from nassav.models import ActorSourceMapping


def load_script_module():
    script_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "backfill_jable_actor_mappings.py"
    )
    spec = importlib.util.spec_from_file_location(
        "backfill_jable_actor_mappings",
        script_path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_jable_model_candidates_extracts_slug_and_name():
    module = load_script_module()

    html = """
    <div class="models">
        <a class="model" href="https://jable.tv/models/tsumugi-akari/">
            <img
                class="avatar rounded-circle"
                src="https://assets-cdn.jable.tv/contents/models/157/s1_akari_tumugi.jpg"
                width="24"
                height="24"
                data-original-title="明里つむぎ"
            >
        </a>
    </div>
    """

    candidates = module.parse_jable_model_candidates(html)

    assert len(candidates) == 1
    assert candidates[0].source_actor_name == "明里つむぎ"
    assert candidates[0].source_actor_slug == "tsumugi-akari"
    assert candidates[0].source_actor_url == "https://jable.tv/models/tsumugi-akari/"


def test_parse_jable_model_candidates_prefers_data_original_title_over_text():
    module = load_script_module()

    html = """
    <div class="models">
        <a class="model" href="https://jable.tv/models/tsumugi-akari/">
            明
            <span class="tooltip-target" data-original-title="明里つむぎ"></span>
        </a>
    </div>
    """

    candidates = module.parse_jable_model_candidates(html)

    assert len(candidates) == 1
    assert candidates[0].source_actor_name == "明里つむぎ"


def test_select_best_model_candidate_uses_actor_aliases():
    module = load_script_module()

    candidates = [
        module.JableModelCandidate(
            source_actor_name="藤浦めぐ",
            source_actor_slug="meguri-fujiura",
            source_actor_url="https://jable.tv/models/meguri-fujiura/",
        )
    ]

    selected, confidence, reason = module.select_best_model_candidate(
        actor_name="めぐり（藤浦めぐ）",
        candidates=candidates,
    )

    assert selected is not None
    assert selected.source_actor_slug == "meguri-fujiura"
    assert confidence == pytest.approx(1.0)
    assert reason == "exact_name"


@pytest.mark.django_db
def test_backfill_jable_actor_mappings_persists_mapping(
    monkeypatch, actor_factory, resource_factory
):
    module = load_script_module()

    actor = actor_factory(name="明里つむぎ")
    resource = resource_factory(avid="JAB-001", original_title="Demo", source="Jable")
    resource.actors.add(actor)

    html = """
    <div class="models">
        <a class="model" href="https://jable.tv/models/tsumugi-akari/">
            <img data-original-title="明里つむぎ">
        </a>
    </div>
    """

    monkeypatch.setattr(module.Jable, "load_cookie_from_db", lambda self: False)
    monkeypatch.setattr(module.Jable, "get_html", lambda self, avid: html)

    stats = module.backfill_jable_actor_mappings(dry_run=False, verbose=False)

    mapping = ActorSourceMapping.objects.get(actor=actor, source_name="jable")
    assert stats["saved"] == 1
    assert mapping.source_actor_name == "明里つむぎ"
    assert mapping.source_actor_slug == "tsumugi-akari"
    assert mapping.source_actor_url == "https://jable.tv/models/tsumugi-akari/"
    assert mapping.match_method == "imported"


@pytest.mark.django_db
def test_backfill_jable_actor_mappings_dry_run_does_not_persist(
    monkeypatch, actor_factory, resource_factory
):
    module = load_script_module()

    actor = actor_factory(name="明里つむぎ")
    resource = resource_factory(avid="JAB-002", original_title="Demo", source="Jable")
    resource.actors.add(actor)

    html = """
    <div class="models">
        <a class="model" href="https://jable.tv/models/tsumugi-akari/">
            <img data-original-title="明里つむぎ">
        </a>
    </div>
    """

    monkeypatch.setattr(module.Jable, "load_cookie_from_db", lambda self: False)
    monkeypatch.setattr(module.Jable, "get_html", lambda self, avid: html)

    stats = module.backfill_jable_actor_mappings(dry_run=True, verbose=False)

    assert stats["dry_run"] == 1
    assert not ActorSourceMapping.objects.filter(
        actor=actor, source_name="jable"
    ).exists()


@pytest.mark.django_db
def test_backfill_jable_actor_mappings_skip_existing_treats_conflict_as_skip(
    monkeypatch, actor_factory, resource_factory
):
    module = load_script_module()

    actor = actor_factory(name="明里つむぎ")
    other_actor = actor_factory(name="其他演员")
    resource = resource_factory(avid="JAB-003", original_title="Demo", source="Jable")
    resource.actors.add(actor)
    ActorSourceMapping.objects.create(
        actor=other_actor,
        source_name="jable",
        source_actor_name="明里つむぎ",
        source_actor_slug="tsumugi-akari",
        is_verified=True,
    )

    html = """
    <div class="models">
        <a class="model" href="https://jable.tv/models/tsumugi-akari/">
            <img data-original-title="明里つむぎ">
        </a>
    </div>
    """

    monkeypatch.setattr(module.Jable, "load_cookie_from_db", lambda self: False)
    monkeypatch.setattr(module.Jable, "get_html", lambda self, avid: html)

    stats = module.backfill_jable_actor_mappings(
        dry_run=False,
        verbose=False,
        skip_existing=True,
    )

    assert stats["saved"] == 0
    assert stats["conflict"] == 0
    assert stats["skipped"] >= 1
    assert not ActorSourceMapping.objects.filter(
        actor=actor,
        source_name="jable",
    ).exists()


@pytest.mark.django_db
def test_backfill_jable_actor_mappings_blocks_single_candidate_fallback_by_default(
    monkeypatch, actor_factory, resource_factory
):
    module = load_script_module()

    actor = actor_factory(name="愛里るい")
    resource = resource_factory(avid="JAB-004", original_title="Demo", source="Jable")
    resource.actors.add(actor)

    html = """
    <div class="models">
        <a class="model" href="https://jable.tv/models/tsumugi-akari/">
            <img data-original-title="明里つむぎ">
        </a>
    </div>
    """

    monkeypatch.setattr(module.Jable, "load_cookie_from_db", lambda self: False)
    monkeypatch.setattr(module.Jable, "get_html", lambda self, avid: html)

    stats = module.backfill_jable_actor_mappings(dry_run=False, verbose=False)

    assert stats["saved"] == 0
    assert stats["fallback_blocked"] == 1
    assert not ActorSourceMapping.objects.filter(
        actor=actor,
        source_name="jable",
    ).exists()


@pytest.mark.django_db
def test_backfill_jable_actor_mappings_allows_single_candidate_fallback_when_enabled(
    monkeypatch, actor_factory, resource_factory
):
    module = load_script_module()

    actor = actor_factory(name="愛里るい")
    resource = resource_factory(avid="JAB-005", original_title="Demo", source="Jable")
    resource.actors.add(actor)

    html = """
    <div class="models">
        <a class="model" href="https://jable.tv/models/tsumugi-akari/">
            <img data-original-title="明里つむぎ">
        </a>
    </div>
    """

    monkeypatch.setattr(module.Jable, "load_cookie_from_db", lambda self: False)
    monkeypatch.setattr(module.Jable, "get_html", lambda self, avid: html)

    stats = module.backfill_jable_actor_mappings(
        dry_run=False,
        verbose=False,
        allow_single_fallback=True,
    )

    mapping = ActorSourceMapping.objects.get(actor=actor, source_name="jable")
    assert stats["saved"] == 1
    assert stats["fallback_blocked"] == 0
    assert mapping.source_actor_slug == "tsumugi-akari"
