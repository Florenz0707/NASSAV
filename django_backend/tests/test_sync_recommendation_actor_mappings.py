import importlib.util
from pathlib import Path

import pytest

from nassav.models import ActorSourceMapping, RecommendationItem, RecommendationSnapshot


def load_script_module():
    script_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "sync_recommendation_actor_mappings.py"
    )
    spec = importlib.util.spec_from_file_location(
        "sync_recommendation_actor_mappings",
        script_path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.django_db
def test_collect_target_avids_deduplicates_and_prefers_recent():
    module = load_script_module()
    snapshot = RecommendationSnapshot.objects.create(
        recommender_id="jable_page_lookup",
        strategy_id="local_preference",
        request_payload={},
        seed_summary={},
    )
    RecommendationItem.objects.create(
        snapshot=snapshot,
        rank=1,
        avid="REC-OLD",
        title="Old",
        detail_url="https://jable.tv/videos/rec-old/",
        source="Jable",
    )
    RecommendationItem.objects.create(
        snapshot=snapshot,
        rank=2,
        avid="REC-NEW",
        title="New",
        detail_url="https://jable.tv/videos/rec-new/",
        source="Jable",
    )
    RecommendationItem.objects.create(
        snapshot=snapshot,
        rank=3,
        avid="REC-OLD",
        title="Old Again",
        detail_url="https://jable.tv/videos/rec-old/",
        source="Jable",
    )
    RecommendationItem.objects.create(
        snapshot=snapshot,
        rank=4,
        avid="MISS-001",
        title="Miss",
        detail_url="https://missav.ai/dm1",
        source="MissAV",
    )

    avids = module.collect_target_avids(limit=10)

    assert avids == ["REC-OLD", "REC-NEW"]


@pytest.mark.django_db
def test_sync_recommendation_actor_mappings_uses_recommendation_history(
    monkeypatch, actor_factory
):
    module = load_script_module()
    actor = actor_factory(name="めぐり（藤浦めぐ）")
    snapshot = RecommendationSnapshot.objects.create(
        recommender_id="jable_page_lookup",
        strategy_id="local_preference",
        request_payload={},
        seed_summary={},
    )
    RecommendationItem.objects.create(
        snapshot=snapshot,
        rank=1,
        avid="REC-LAZY-001",
        title="Lazy Mapping Hit",
        detail_url="https://jable.tv/videos/rec-lazy-001/",
        source="Jable",
    )

    from nassav.scraper import Javbus
    from nassav.source import Jable

    monkeypatch.setattr(Jable, "load_cookie_from_db", lambda self: False)
    monkeypatch.setattr(
        Javbus,
        "get_html",
        lambda self, avid: "<html></html>" if avid == "REC-LAZY-001" else None,
    )
    monkeypatch.setattr(
        Javbus,
        "parse_html",
        lambda self, html, avid: (
            {"actors": ["めぐり（藤浦めぐ）"]} if avid == "REC-LAZY-001" else None
        ),
    )
    monkeypatch.setattr(
        Jable,
        "get_html",
        lambda self, avid: (
            """
        <div class="models">
            <a class="model" href="https://jable.tv/models/meguri-fujiura/">
                <img data-original-title="藤浦めぐ">
            </a>
        </div>
        """
            if avid == "REC-LAZY-001"
            else None
        ),
    )

    stats = module.sync_recommendation_actor_mappings(limit=10, verbose=False)

    mapping = ActorSourceMapping.objects.get(actor=actor, source_name="jable")
    assert stats["target_avids"] == 1
    assert stats["saved"] == 1
    assert mapping.source_actor_name == "藤浦めぐ"
    assert mapping.source_actor_slug == "meguri-fujiura"
