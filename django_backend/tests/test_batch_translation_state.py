"""Offline batch selection and failure-state contract through registered task."""

import pytest
from nassav import tasks
from nassav.models import AVResource
from nassav.translator import translator_manager


@pytest.mark.django_db
def test_batch_selects_original_and_source_titles_and_skip_existing(
    resource_factory, monkeypatch
):
    first = resource_factory(
        avid="BT-001", original_title="Original", source_title="Fallback"
    )
    second = resource_factory(avid="BT-002", original_title="", source_title="Source")
    done = resource_factory(
        avid="BT-003",
        original_title="Done",
        translated_title="已有",
        translation_status="completed",
    )
    empty = resource_factory(avid="BT-004", original_title="", source_title="")
    seen = []

    def translate(texts):
        seen.extend(texts)
        return [f"译文:{text}" for text in texts]

    monkeypatch.setattr(translator_manager, "batch_translate", translate)
    result = tasks.batch_translate_titles_task.apply(
        args=([first.avid.lower(), second.avid, done.avid, empty.avid],)
    ).get()
    assert result == {
        "success": True,
        "total": 2,
        "translated": 2,
        "failed": 0,
        "skipped": 0,
    }
    assert set(seen) == {"Original", "Source"}
    done.refresh_from_db()
    assert done.translated_title == "已有"
    result = tasks.batch_translate_titles_task.apply(args=([done.avid], False)).get()
    assert result["translated"] == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    "outcome",
    [
        [],
        ["one"],
        ["one", "two", "extra"],
        None,
        RuntimeError("translator unavailable"),
    ],
)
def test_batch_failure_finishes_only_selected_inflight_rows(
    resource_factory, monkeypatch, outcome
):
    selected = [
        resource_factory(
            avid=f"BT-10{i}", original_title=f"Title {i}", translated_title="旧译文"
        )
        for i in range(2)
    ]
    unrelated = resource_factory(
        avid="BT-199", original_title="Other", translation_status="translating"
    )

    def translate(texts):
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(translator_manager, "batch_translate", translate)
    result = tasks.batch_translate_titles_task.apply(
        args=([row.avid for row in selected],)
    ).get()
    assert result["success"] is False and result["error"]
    for row in selected:
        row.refresh_from_db()
        assert row.translation_status == "failed" and row.translated_title == "旧译文"
    unrelated.refresh_from_db()
    assert unrelated.translation_status == "translating"


@pytest.mark.django_db
def test_batch_partial_save_failure_preserves_completed_row(
    resource_factory, monkeypatch
):
    resources = [
        resource_factory(avid=f"BT-20{i}", original_title=f"Title {i}")
        for i in range(2)
    ]
    monkeypatch.setattr(
        translator_manager, "batch_translate", lambda texts: ["译文"] * len(texts)
    )
    original_save = AVResource.save
    saved = []

    def save(row, *args, **kwargs):
        if saved:
            raise RuntimeError("second result save failed")
        saved.append(row.pk)
        return original_save(row, *args, **kwargs)

    monkeypatch.setattr(AVResource, "save", save)
    result = tasks.batch_translate_titles_task.apply(
        args=([row.avid for row in resources],)
    ).get()
    assert result["success"] is False
    states = list(
        AVResource.objects.filter(pk__in=[row.pk for row in resources]).values_list(
            "translation_status", flat=True
        )
    )
    assert sorted(states) == ["completed", "failed"]
