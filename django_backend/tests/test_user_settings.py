"""
测试用户设置 API
"""

import tempfile
from pathlib import Path

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

    # 验证默认值
    assert settings["enable_avatar"] in ["true", "false"]
    assert settings["display_title"] in [
        "original_title",
        "source_title",
        "translated_title",
    ]
    assert settings["color_mode"] in ["light", "dark"]


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

    # 再次获取验证持久化
    response = client.get("/nassav/api/setting")
    data = response.json()
    settings = data["data"]
    assert settings["enable_avatar"] == "false"
    assert settings["display_title"] == "translated_title"
    assert settings["font_family"] == "ZenKakuGothicNew"
    assert settings["color_mode"] == "light"


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


def test_settings_manager_default_creation():
    """测试设置管理器创建默认配置"""
    from nassav.user_settings import UserSettingsManager

    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "test_settings.ini"
        manager = UserSettingsManager(config_path)

        # 验证配置文件已创建
        assert config_path.exists()

        # 验证默认值
        settings = manager.get_all()
        assert settings["enable_avatar"] == "true"
        assert settings["display_title"] == "source_title"
        assert settings["font_family"] == "Mplus2"
        assert settings["color_mode"] == "dark"


def test_settings_manager_validation():
    """测试设置管理器的值验证"""
    from nassav.user_settings import UserSettingsManager

    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "test_settings.ini"
        manager = UserSettingsManager(config_path)

        # 测试有效值
        assert manager.set("enable_avatar", "true") is True
        assert manager.set("enable_avatar", "false") is True
        assert manager.set("display_title", "original_title") is True
        assert manager.set("display_title", "source_title") is True
        assert manager.set("display_title", "translated_title") is True
        assert manager.set("color_mode", "light") is True
        assert manager.set("color_mode", "dark") is True

        # 测试无效值
        assert manager.set("enable_avatar", "invalid") is False
        assert manager.set("display_title", "invalid") is False
        assert manager.set("color_mode", "invalid") is False


def test_settings_manager_persistence():
    """测试设置管理器的持久化"""
    from nassav.user_settings import UserSettingsManager

    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "test_settings.ini"

        # 创建并设置
        manager1 = UserSettingsManager(config_path)
        manager1.set("enable_avatar", "false")
        manager1.set("display_title", "translated_title")
        manager1.set("color_mode", "light")

        # 重新加载验证持久化
        manager2 = UserSettingsManager(config_path)
        assert manager2.get("enable_avatar") == "false"
        assert manager2.get("display_title") == "translated_title"
        assert manager2.get("color_mode") == "light"


def test_get_settings_manager_is_path_scoped_cache():
    from nassav.user_settings import (
        clear_settings_manager_cache,
        get_settings_manager,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        path_a = Path(tmpdir) / "settings-a.ini"
        path_b = Path(tmpdir) / "settings-b.ini"

        clear_settings_manager_cache()
        manager_a1 = get_settings_manager(path_a)
        manager_a2 = get_settings_manager(path_a)
        manager_b = get_settings_manager(path_b)

        assert manager_a1 is manager_a2
        assert manager_a1 is not manager_b


def test_clear_settings_manager_cache_recreates_instance():
    from nassav.user_settings import (
        clear_settings_manager_cache,
        get_settings_manager,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "settings.ini"

        clear_settings_manager_cache()
        manager1 = get_settings_manager(config_path)
        clear_settings_manager_cache(config_path)
        manager2 = get_settings_manager(config_path)

        assert manager1 is not manager2
