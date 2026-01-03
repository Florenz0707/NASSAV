"""
测试演员列表 API 过滤功能

功能：验证演员列表只返回有作品的演员

运行方法：
    uv run python manage.py test tests.test_actors_list_filter
"""
import pytest
from django.urls import reverse


@pytest.fixture
def setup_actors(actor_factory, resource_factory):
    # 创建有作品的演员
    actor_with_works = actor_factory(name="有作品的演员")
    res1 = resource_factory(avid="TEST-001", original_title="测试资源1")
    res1.actors.add(actor_with_works)

    # 创建有多个作品的演员
    actor_with_multiple_works = actor_factory(name="多作品演员")
    res2 = resource_factory(avid="TEST-002", original_title="测试资源2")
    res3 = resource_factory(avid="TEST-003", original_title="测试资源3")
    res2.actors.add(actor_with_multiple_works)
    res3.actors.add(actor_with_multiple_works)

    # 创建没有作品的演员
    actor_factory(name="めぐり（藤")
    actor_factory(name="ミュウ（夏")
    actor_factory(name="森沢かな（")


@pytest.mark.django_db
def test_actors_list_excludes_zero_count(client, setup_actors):
    url = reverse("nassav:actors-list")
    response = client.get(url)

    assert response.status_code == 200
    data = response.json()

    assert "code" in data
    assert "data" in data
    assert data["code"] == 200

    actors = data["data"]
    assert len(actors) == 2

    actor_names = [a["name"] for a in actors]
    assert "有作品的演员" in actor_names
    assert "多作品演员" in actor_names

    assert "めぐり（藤" not in actor_names
    assert "ミュウ（夏" not in actor_names
    assert "森沢かな（" not in actor_names

    for actor in actors:
        assert actor["resource_count"] > 0
        if actor["name"] == "有作品的演员":
            assert actor["resource_count"] == 1
        elif actor["name"] == "多作品演员":
            assert actor["resource_count"] == 2


@pytest.mark.django_db
def test_actors_list_with_search_excludes_zero_count(client, setup_actors):
    url = reverse("nassav:actors-list")
    response = client.get(url, {"search": "演员"})
    assert response.status_code == 200
    data = response.json()
    actors = data["data"]
    assert len(actors) == 2
    for actor in actors:
        assert actor["resource_count"] > 0


@pytest.mark.django_db
def test_actors_list_by_id_allows_zero_count(client, setup_actors):
    from nassav.models import Actor

    zero_actor = Actor.objects.filter(name__startswith="めぐり").first()
    url = reverse("nassav:actors-list")
    response = client.get(url, {"id": zero_actor.id})
    assert response.status_code == 200
    data = response.json()
    actors = data["data"]
    assert len(actors) == 1
    assert actors[0]["name"] == zero_actor.name
    assert actors[0]["resource_count"] == 0


@pytest.mark.django_db
def test_actors_list_pagination_excludes_zero_count(client, setup_actors):
    url = reverse("nassav:actors-list")
    response = client.get(url, {"page": 1, "page_size": 10})
    assert response.status_code == 200
    data = response.json()
    assert "pagination" in data
    pagination = data["pagination"]
    assert pagination["total"] == 2
    for actor in data["data"]:
        assert actor["resource_count"] > 0


@pytest.mark.django_db
def test_actors_list_order_by_count_excludes_zero(client, setup_actors):
    url = reverse("nassav:actors-list")
    response = client.get(url, {"order_by": "count", "order": "desc"})
    assert response.status_code == 200
    data = response.json()
    actors = data["data"]
    assert len(actors) == 2
    assert actors[0]["name"] == "多作品演员"
    assert actors[0]["resource_count"] == 2
    assert actors[1]["name"] == "有作品的演员"
    assert actors[1]["resource_count"] == 1


@pytest.mark.django_db
def test_database_has_zero_count_actors(setup_actors):
    from nassav.models import Actor

    zero_count_actors = Actor.objects.filter(resources__isnull=True)
    assert zero_count_actors.count() == 3
    zero_names = [a.name for a in zero_count_actors]
    assert "めぐり（藤" in zero_names
    assert "ミュウ（夏" in zero_names
    assert "森沢かな（" in zero_names
