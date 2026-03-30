import pytest
from django.db import IntegrityError

from nassav.models import GenreSourceMapping


@pytest.mark.django_db
def test_genre_source_mapping_normalizes_jable_fields(genre_factory):
    genre = genre_factory(name="中文字幕")

    mapping = GenreSourceMapping.objects.create(
        genre=genre,
        source_name=" JABLE ",
        source_genre_name=" 中文字幕 ",
        source_genre_url="https://jable.tv/categories/chinese-subtitle/",
        aliases=None,
    )

    mapping.refresh_from_db()

    assert mapping.source_name == "jable"
    assert mapping.source_genre_name == "中文字幕"
    assert mapping.source_genre_slug == "chinese-subtitle"
    assert mapping.aliases == []


@pytest.mark.django_db
def test_genre_source_mapping_uses_explicit_slug(genre_factory):
    genre = genre_factory(name="OL")

    mapping = GenreSourceMapping.objects.create(
        genre=genre,
        source_name="jable",
        source_genre_name="OL",
        source_genre_slug="ol",
        source_genre_url="https://jable.tv/tags/ol/",
    )

    assert mapping.source_genre_slug == "ol"


@pytest.mark.django_db
def test_genre_source_mapping_enforces_unique_source_per_genre(genre_factory):
    genre = genre_factory(name="巨乳")

    GenreSourceMapping.objects.create(
        genre=genre,
        source_name="jable",
        source_genre_name="巨乳",
        source_genre_slug="big-tits",
    )

    with pytest.raises(IntegrityError):
        GenreSourceMapping.objects.create(
            genre=genre,
            source_name="jable",
            source_genre_name="超乳",
            source_genre_slug="huge-tits",
        )


@pytest.mark.django_db
def test_genre_source_mapping_allows_shared_source_slug(genre_factory):
    genre_one = genre_factory(name="制服")
    genre_two = genre_factory(name="校服")

    GenreSourceMapping.objects.create(
        genre=genre_one,
        source_name="jable",
        source_genre_name="制服誘惑",
        source_genre_slug="uniform",
    )

    second = GenreSourceMapping.objects.create(
        genre=genre_two,
        source_name="jable",
        source_genre_name="校服",
        source_genre_slug="uniform",
    )

    assert second.source_genre_slug == "uniform"
