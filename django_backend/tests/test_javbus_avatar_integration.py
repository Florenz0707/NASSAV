"""测试Javbus刮削器头像URL提取（集成测试）"""
import pytest


@pytest.mark.django_db
def test_javbus_scraper_returns_actor_avatars():
    """测试Javbus刮削器是否返回actor_avatars字典"""
    from nassav.scraper.Javbus import Javbus

    scraper = Javbus()
    # 使用一个真实AVID进行测试
    result = scraper.scrape("ABP-001")

    if result:
        # 验证返回数据结构
        assert "actors" in result
        assert "actor_avatars" in result
        assert isinstance(result["actor_avatars"], dict)

        # 如果有演员，应该有对应的头像URL
        if result["actors"]:
            for actor_name in result["actors"]:
                assert actor_name in result["actor_avatars"]
                avatar_url = result["actor_avatars"][actor_name]
                assert avatar_url.startswith("https://")
                assert "/pics/actress/" in avatar_url
                assert avatar_url.endswith(".jpg")
