"""
测试用户设置重启后不被覆盖的问题修复
"""

import tempfile
from pathlib import Path

from nassav.user_settings import UserSettingsManager


def test_empty_config_file_gets_defaults():
    """测试空配置文件会被填充默认值"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "test_settings.ini"

        # 创建一个空的配置文件
        config_path.touch()

        # 加载空配置文件应该成功，并填充默认值
        manager = UserSettingsManager(config_path)

        # 验证默认值被添加
        assert manager.get("enable_avatar") == "true"
        assert manager.get("display_title") == "source_title"
        assert manager.get("color_mode") == "dark"

        # 验证配置文件现在有内容
        assert config_path.read_text().strip() != ""


def test_config_persistence_after_restart():
    """测试配置在重启后不会被覆盖"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "test_settings.ini"

        # 第一次初始化：创建默认配置
        manager1 = UserSettingsManager(config_path)
        assert manager1.get("enable_avatar") == "true"
        assert manager1.get("display_title") == "source_title"

        # 修改配置
        manager1.set("enable_avatar", "false")
        manager1.set("display_title", "translated_title")
        manager1.set("color_mode", "light")

        # 验证修改成功
        assert manager1.get("enable_avatar") == "false"
        assert manager1.get("display_title") == "translated_title"
        assert manager1.get("color_mode") == "light"

        # 模拟服务重启：创建新的管理器实例
        manager2 = UserSettingsManager(config_path)

        # 验证配置没有被覆盖
        assert manager2.get("enable_avatar") == "false"
        assert manager2.get("display_title") == "translated_title"
        assert manager2.get("color_mode") == "light"

        # 再次修改配置
        manager2.set("enable_avatar", "true")

        # 再次模拟重启
        manager3 = UserSettingsManager(config_path)

        # 验证最新的配置被保留
        assert manager3.get("enable_avatar") == "true"
        assert manager3.get("display_title") == "translated_title"
        assert manager3.get("color_mode") == "light"
