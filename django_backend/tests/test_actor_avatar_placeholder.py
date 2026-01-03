"""
测试演员头像占位图过滤功能
验证后端正确过滤掉 Javbus 的占位图 URL
"""

import pytest
from nassav.constants import ACTOR_AVATAR_PLACEHOLDER_URLS
from nassav.models import Actor, AVResource


@pytest.mark.django_db
def test_actor_with_placeholder_avatar_returns_none(client):
    """测试有占位图的演员返回 None"""
    # 创建资源和演员
    resource = AVResource.objects.create(avid="TEST-001", title="Test")
    actor = Actor.objects.create(
        name="测试演员",
        avatar_url=ACTOR_AVATAR_PLACEHOLDER_URLS[0],  # nowprinting.gif
        avatar_filename="nowprinting.gif",
    )
    resource.actors.add(actor)

    response = client.get("/nassav/api/actors/")
    data = response.json()

    assert response.status_code == 200
    assert len(data["data"]) == 1

    actor_data = data["data"][0]
    assert actor_data["name"] == "测试演员"
    assert actor_data["avatar_url"] is None  # 占位图被过滤
    assert actor_data["avatar_filename"] is None  # 同时过滤文件名


@pytest.mark.django_db
def test_actor_with_valid_avatar_returns_url(client):
    """测试有真实头像的演员正常返回"""
    resource = AVResource.objects.create(avid="TEST-002", title="Test")
    actor = Actor.objects.create(
        name="真实演员",
        avatar_url="https://www.javbus.com/pics/actress/123_a.jpg",
        avatar_filename="123_a.jpg",
    )
    resource.actors.add(actor)

    response = client.get("/nassav/api/actors/")
    data = response.json()

    assert response.status_code == 200
    actor_data = data["data"][0]
    assert actor_data["avatar_url"] == "https://www.javbus.com/pics/actress/123_a.jpg"
    assert actor_data["avatar_filename"] == "123_a.jpg"


@pytest.mark.django_db
def test_actor_without_avatar_returns_none(client):
    """测试没有头像的演员返回 None"""
    resource = AVResource.objects.create(avid="TEST-003", title="Test")
    actor = Actor.objects.create(
        name="无头像演员",
        avatar_url=None,
        avatar_filename=None,
    )
    resource.actors.add(actor)

    response = client.get("/nassav/api/actors/")
    data = response.json()

    assert response.status_code == 200
    actor_data = data["data"][0]
    assert actor_data["avatar_url"] is None
    assert actor_data["avatar_filename"] is None


@pytest.mark.django_db
def test_mixed_actors_filters_correctly(client):
    """测试混合场景：占位图、真实头像、无头像"""
    resource = AVResource.objects.create(avid="TEST-004", title="Test")

    actor1 = Actor.objects.create(
        name="占位图演员",
        avatar_url="https://pics.dmm.co.jp/mono/actjpgs/nowprinting.gif",
        avatar_filename="nowprinting.gif",
    )
    actor2 = Actor.objects.create(
        name="真实头像演员",
        avatar_url="https://www.javbus.com/pics/actress/456_a.jpg",
        avatar_filename="456_a.jpg",
    )
    actor3 = Actor.objects.create(name="无头像演员", avatar_url=None, avatar_filename=None)

    resource.actors.add(actor1, actor2, actor3)

    response = client.get("/nassav/api/actors/?page_size=10&order_by=name&order=asc")
    data = response.json()

    assert response.status_code == 200
    assert len(data["data"]) == 3

    # 按名称排序验证
    actors_by_name = {a["name"]: a for a in data["data"]}

    # 占位图演员：avatar_url 应该被过滤为 None
    assert actors_by_name["占位图演员"]["avatar_url"] is None
    assert actors_by_name["占位图演员"]["avatar_filename"] is None

    # 真实头像演员：正常返回
    assert (
        actors_by_name["真实头像演员"]["avatar_url"]
        == "https://www.javbus.com/pics/actress/456_a.jpg"
    )
    assert actors_by_name["真实头像演员"]["avatar_filename"] == "456_a.jpg"

    # 无头像演员：返回 None
    assert actors_by_name["无头像演员"]["avatar_url"] is None
    assert actors_by_name["无头像演员"]["avatar_filename"] is None
