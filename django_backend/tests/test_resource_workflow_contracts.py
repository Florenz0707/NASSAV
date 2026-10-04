"""R3: uv run pytest tests/test_resource_workflow_contracts.py -v."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from nassav.resource_contracts import (
    AssetResult,
    ResourceAssets,
    ResourceEvents,
    ResourceReader,
    TranslationSubmitter,
)
from nassav.resource_persistence import DjangoResourcePersistence
from nassav.resource_contracts import ResourcePersistence, ResourceSaveInput
from nassav.resource_workflow import ResourceAlreadyExistsError, ResourceService
from nassav.scraper import AVDownloadInfo
from nassav.source.Jable import Jable
from nassav.resource_contracts import SourceRelations
from nassav.source.jable_actor_mapping import JableModelCandidate


class MemoryResourceStore(ResourceReader, ResourcePersistence):
    def __init__(self, calls):
        self.calls = calls
        self.resource = None
        self.saved = []

    def get(self, avid):
        self.calls.append("read")
        return self.resource

    def save(self, data):
        self.calls.append("save")
        self.saved.append(data)
        self.resource = SimpleNamespace(
            avid=data.avid,
            original_title="Scraped title",
            source_title=data.info.source_title,
            translated_title=None,
            translation_status="pending",
            source=data.source_name,
            release_date="",
            duration=0,
            m3u8=data.info.m3u8,
            cover_filename=data.avid + ".jpg",
            file_exists=False,
            file_size=0,
            metadata_created_at=None,
            metadata_updated_at=None,
            video_saved_at=None,
            created_at=None,
            actors=Mock(),
            genres=Mock(),
            metadata={"avid": data.avid, "m3u8": data.info.m3u8},
        )
        self.resource.actors.all.return_value = []
        self.resource.genres.all.return_value = []
        return self.resource


class MemoryAssets(ResourceAssets):
    def __init__(self, calls, path):
        self.calls, self.path = calls, path

    def save_page(self, avid, html):
        self.calls.append("page")
        return AssetResult(self.path, True)

    def save_cover(self, avid, scraped_data, scraped_by, source_inst, html):
        self.calls.append("cover")
        return True

    def save_avatars(self, scraped_data):
        self.calls.append("avatars")


class MemoryTranslations(TranslationSubmitter):
    def __init__(self, calls):
        self.calls = calls

    def submit(self, avid):
        self.calls.append("translation")
        return "test-task"


class MemoryEvents(ResourceEvents):
    def __init__(self, calls):
        self.calls = calls

    def publish(self, event, sender, avid, result):
        self.calls.append(event)


def test_add_refresh_and_duplicate_use_injected_dependencies_without_database(tmp_path):
    calls = []
    store = MemoryResourceStore(calls)
    source = Mock()
    source.get_source_name.return_value = "test-source"
    source.parse_relations.return_value = SourceRelations()
    sources = Mock()
    info = AVDownloadInfo(
        avid="TEST-001", source_title="Source title", m3u8="test-playlist"
    )
    sources.get_info_from_any_source.return_value = (info, source, "page", {})
    sources.get_info_from_source.return_value = (info, source, "page", {})
    metadata = Mock()
    metadata.scrape_with_source.side_effect = lambda avid: (
        calls.append("metadata") or {"title": "Scraped title"},
        "test-scraper",
    )
    service = ResourceService(
        sources,
        metadata,
        reader=store,
        persistence=store,
        assets=MemoryAssets(calls, tmp_path / "page"),
        translations=MemoryTranslations(calls),
        events=MemoryEvents(calls),
    )
    result = service.add_resource("test-001")
    assert calls == [
        "read",
        "page",
        "metadata",
        "cover",
        "save",
        "avatars",
        "translation",
        "added",
    ]
    assert (
        result["resource"]["avid"] == "TEST-001"
        and result["translate_task_id"] == "test-task"
    )
    assert store.saved[0].source_name == "test-source"
    calls.clear()
    with pytest.raises(ResourceAlreadyExistsError):
        service.add_resource("test-001")
    assert calls == ["read"]
    calls.clear()
    assert service.refresh_resource("test-001")["m3u8_updated"]
    assert calls == [
        "read",
        "page",
        "metadata",
        "cover",
        "save",
        "avatars",
        "refreshed",
    ]


@pytest.mark.django_db
def test_parsed_persistence_does_not_mutate_inputs_and_supports_other_source():
    from nassav.models import ActorSourceMapping

    info = AVDownloadInfo(avid="TEST-002", source_title="Source", m3u8="test-playlist")
    scraped = {"title": "Original", "actors": [], "genres": ["Example"]}
    original_info, original_scraped = deepcopy(info), deepcopy(scraped)
    relations = SourceRelations(
        ("Actor",),
        (
            JableModelCandidate(
                "Actor", "actor", "https://source.test/actor", "test-source"
            ),
        ),
    )
    resource = DjangoResourcePersistence().save(
        ResourceSaveInput("TEST-002", info, "test-source", scraped, relations)
    )
    assert info == original_info and scraped == original_scraped
    assert resource.metadata["actors"] == ["Actor"]
    mapping = ActorSourceMapping.objects.get(source_name="test-source")
    assert mapping.source_actor_slug == "actor"


def test_source_relation_parser_needs_no_database():
    source = Jable()
    relations = source.parse_relations(
        '<div class="models"><a class="model" href="/models/actor/" title="Actor">A</a></div>'
    )
    assert relations.actor_names == ("Actor",)
    assert relations.actor_candidates[0].source_actor_slug == "actor"
