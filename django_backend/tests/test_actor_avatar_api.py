"""测试演员头像功能完整流程（集成测试，使用 fixtures）"""
import pytest


@pytest.mark.django_db
def test_actor_avatar_full_flow(api_client, actor_factory, resource_factory):
    """测试演员头像从刮削到API获取的完整流程"""
    # 创建一个演员记录
    actor = actor_factory(
        name="测试演员",
        avatar_url="https://www.javbus.com/pics/actress/999_a.jpg",
        avatar_filename="999_a.jpg",
    )

    # 验证字段已保存
    assert actor.avatar_url == "https://www.javbus.com/pics/actress/999_a.jpg"
    assert actor.avatar_filename == "999_a.jpg"
    assert actor.updated_at is not None

    # 创建一个资源并关联演员
    resource = resource_factory(avid="TEST-001", original_title="测试作品")
    resource.actors.add(actor)

    # 测试API返回头像字段
    response = api_client.get("/nassav/api/actors/", {"page": 1, "page_size": 20})
    assert response.status_code == 200

    data = response.json()
    actors = data["data"]

    # 查找我们创建的演员
    test_actor = next((a for a in actors if a["name"] == "测试演员"), None)
    assert test_actor is not None
    assert test_actor["avatar_url"] == "https://www.javbus.com/pics/actress/999_a.jpg"
    assert test_actor["avatar_filename"] == "999_a.jpg"
    assert test_actor["resource_count"] == 1


@pytest.mark.django_db
def test_actor_without_avatar(api_client, actor_factory, resource_factory):
    """测试没有头像的演员也能正常返回"""
    # 创建没有头像的演员
    actor = actor_factory(name="无头像演员")
    resource = resource_factory(avid="TEST-002", original_title="测试作品2")
    resource.actors.add(actor)

    response = api_client.get("/nassav/api/actors/")
    assert response.status_code == 200

    data = response.json()
    actors = data["data"]

    test_actor = next((a for a in actors if a["name"] == "无头像演员"), None)
    assert test_actor is not None
    assert test_actor["avatar_url"] is None
    assert test_actor["avatar_filename"] is None
