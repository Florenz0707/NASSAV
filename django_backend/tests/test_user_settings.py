"""
测试用户设置 API
"""

import pytest


@pytest.mark.django_db
def test_get_user_settings(client):
    """测试获取用户设置"""
    response = client.get("/nassav/api/setting")
    assert response.status_code == 200

    data = response.json()
    assert data["code"] == 200
    assert data["message"] == "success"
    assert "data" in data

    # 验证默认配置存在
    settings = data["data"]
    assert "enable_avatar" in settings
    assert "display_title" in settings
    assert "font_family" in settings
    assert "color_mode" in settings
    assert "search_result_display_style" in settings

    # 验证默认值
    assert settings["enable_avatar"] in ["true", "false"]
    assert settings["display_title"] in [
        "original_title",
        "source_title",
        "translated_title",
    ]
    assert settings["color_mode"] in ["light", "dark"]
    assert settings["search_result_display_style"] in ["grid", "masonry"]


@pytest.mark.django_db
def test_update_user_settings(client):
    """测试更新用户设置"""
    # 更新设置
    response = client.put(
        "/nassav/api/setting",
        data={
            "enable_avatar": "false",
            "display_title": "translated_title",
            "font_family": "ZenKakuGothicNew",
            "color_mode": "light",
            "search_result_display_style": "masonry",
        },
        content_type="application/json",
    )
    assert response.status_code == 200

    data = response.json()
    assert data["code"] == 200
    assert data["message"] == "设置已更新"

    # 验证更新后的值
    settings = data["data"]
    assert settings["enable_avatar"] == "false"
    assert settings["display_title"] == "translated_title"
    assert settings["font_family"] == "ZenKakuGothicNew"
    assert settings["color_mode"] == "light"
    assert settings["search_result_display_style"] == "masonry"

    # 再次获取验证持久化
    response = client.get("/nassav/api/setting")
    data = response.json()
    settings = data["data"]
    assert settings["enable_avatar"] == "false"
    assert settings["display_title"] == "translated_title"
    assert settings["font_family"] == "ZenKakuGothicNew"
    assert settings["color_mode"] == "light"
    assert settings["search_result_display_style"] == "masonry"


@pytest.mark.django_db
def test_update_partial_settings(client):
    """测试部分更新用户设置"""
    # 只更新一个字段
    response = client.put(
        "/nassav/api/setting",
        data={"display_title": "original_title"},
        content_type="application/json",
    )
    assert response.status_code == 200

    data = response.json()
    settings = data["data"]
    assert settings["display_title"] == "original_title"
    # enable_avatar 应该保持原值
    assert "enable_avatar" in settings


@pytest.mark.django_db
def test_update_invalid_enable_avatar(client):
    """测试更新无效的 enable_avatar 值"""
    response = client.put(
        "/nassav/api/setting",
        data={"enable_avatar": "invalid_value"},
        content_type="application/json",
    )
    assert response.status_code == 400

    data = response.json()
    assert data["code"] == 400
    assert "enable_avatar" in data["data"]


@pytest.mark.django_db
def test_update_invalid_display_title(client):
    """测试更新无效的 display_title 值"""
    response = client.put(
        "/nassav/api/setting",
        data={"display_title": "invalid_title"},
        content_type="application/json",
    )
    assert response.status_code == 400

    data = response.json()
    assert data["code"] == 400
    assert "display_title" in data["data"]


@pytest.mark.django_db
def test_update_invalid_color_mode(client):
    """测试更新无效的 color_mode 值"""
    response = client.put(
        "/nassav/api/setting",
        data={"color_mode": "invalid_mode"},
        content_type="application/json",
    )
    assert response.status_code == 400

    data = response.json()
    assert data["code"] == 400
    assert "color_mode" in data["data"]


@pytest.mark.django_db
def test_update_invalid_search_result_display_style(client):
    """测试更新无效的 search_result_display_style 值"""
    response = client.put(
        "/nassav/api/setting",
        data={"search_result_display_style": "invalid_mode"},
        content_type="application/json",
    )
    assert response.status_code == 400

    data = response.json()
    assert data["code"] == 400
    assert "search_result_display_style" in data["data"]


@pytest.mark.django_db
def test_default_search_source_persists_and_rejects_unknown(client):
    assert (
        client.put(
            "/nassav/api/setting",
            data={"default_external_search_source": "missav"},
            content_type="application/json",
        ).status_code
        == 200
    )
    assert (
        client.get("/nassav/api/setting").json()["data"][
            "default_external_search_source"
        ]
        == "missav"
    )
    assert (
        client.put(
            "/nassav/api/setting",
            data={"default_external_search_source": "unknown"},
            content_type="application/json",
        ).status_code
        == 400
    )
