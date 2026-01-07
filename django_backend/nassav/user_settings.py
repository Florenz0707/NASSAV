"""
用户设置管理模块
管理 config/user_settings.ini 文件
"""
import configparser
from pathlib import Path
from typing import Any, Dict

from loguru import logger


class UserSettingsManager:
    """用户设置管理器"""

    # 默认配置
    DEFAULT_SETTINGS = {
        "display": {
            "enable_avatar": "true",
            "display_title": "source_title",  # original_title | source_title | translated_title
        }
    }

    # 配置验证规则
    VALID_VALUES = {
        "enable_avatar": ["true", "false"],
        "display_title": ["original_title", "source_title", "translated_title"],
    }

    def __init__(self, config_path: Path = None):
        """初始化设置管理器"""
        if config_path is None:
            # 默认路径：django_backend/config/user_settings.ini
            base_dir = Path(__file__).resolve().parent.parent
            config_path = base_dir / "config" / "user_settings.ini"

        self.config_path = config_path
        self.config = configparser.ConfigParser()
        self._last_mtime = None  # 记录配置文件的最后修改时间
        self._ensure_config_exists()

    def _ensure_config_exists(self):
        """确保配置文件存在，不存在则创建默认配置"""
        if not self.config_path.exists():
            logger.info(f"用户配置文件不存在，创建默认配置: {self.config_path}")
            self._create_default_config()
        else:
            self._load_config()
            # 检查并补充缺失的配置项
            self._ensure_default_values()

    def _create_default_config(self):
        """创建默认配置文件"""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        for section, settings in self.DEFAULT_SETTINGS.items():
            self.config.add_section(section)
            for key, value in settings.items():
                self.config.set(section, key, value)

        self._save_config()
        logger.info("默认用户配置已创建")

    def _load_config(self):
        """加载配置文件"""
        try:
            self.config.read(self.config_path, encoding="utf-8")
            # 更新文件修改时间
            if self.config_path.exists():
                self._last_mtime = self.config_path.stat().st_mtime
        except Exception as e:
            logger.error(f"加载用户配置失败: {e}")
            raise

    def _save_config(self):
        """保存配置到文件"""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                self.config.write(f)
            # 更新文件修改时间
            if self.config_path.exists():
                self._last_mtime = self.config_path.stat().st_mtime
        except Exception as e:
            logger.error(f"保存用户配置失败: {e}")
            raise

    def _ensure_default_values(self):
        """确保所有默认配置项都存在"""
        changed = False
        for section, settings in self.DEFAULT_SETTINGS.items():
            if not self.config.has_section(section):
                self.config.add_section(section)
                changed = True

            for key, value in settings.items():
                if not self.config.has_option(section, key):
                    self.config.set(section, key, value)
                    changed = True
                    logger.info(f"添加缺失的配置项: [{section}] {key} = {value}")

        if changed:
            self._save_config()

    def _is_file_modified(self) -> bool:
        """检查配置文件是否被外部修改"""
        if not self.config_path.exists():
            return False

        current_mtime = self.config_path.stat().st_mtime
        return self._last_mtime is None or current_mtime != self._last_mtime

    def reload(self):
        """重新加载配置文件"""
        logger.info("重新加载用户配置")
        self._load_config()
        self._ensure_default_values()

    def get_all(self) -> Dict[str, Any]:
        """获取所有配置（扁平化结构）"""
        # 检查文件是否被外部修改，如果是则重新加载
        if self._is_file_modified():
            logger.info("检测到配置文件被修改，自动重新加载")
            self.reload()

        settings = {}
        for section in self.config.sections():
            for key, value in self.config.items(section):
                settings[key] = value
        return settings

    def get(self, key: str, default: Any = None) -> Any:
        """获取单个配置项"""
        for section in self.config.sections():
            if self.config.has_option(section, key):
                return self.config.get(section, key)
        return default

    def set(self, key: str, value: str) -> bool:
        """
        设置配置项
        返回是否成功
        """
        # 验证配置值
        if key in self.VALID_VALUES:
            if value not in self.VALID_VALUES[key]:
                logger.warning(f"无效的配置值: {key}={value}, 有效值: {self.VALID_VALUES[key]}")
                return False

        # 查找配置项所在的 section
        section_found = None
        for section in self.config.sections():
            if self.config.has_option(section, key):
                section_found = section
                break

        if not section_found:
            # 如果配置项不存在，添加到 display section
            section_found = "display"
            if not self.config.has_section(section_found):
                self.config.add_section(section_found)

        try:
            self.config.set(section_found, key, value)
            self._save_config()
            logger.info(f"配置已更新: {key} = {value}")
            return True
        except Exception as e:
            logger.error(f"更新配置失败: {e}")
            return False

    def update_batch(self, settings: Dict[str, str]) -> Dict[str, bool]:
        """
        批量更新配置
        返回每个配置项的更新结果
        """
        results = {}
        for key, value in settings.items():
            results[key] = self.set(key, value)
        return results

    def reset_to_default(self):
        """重置为默认配置"""
        logger.info("重置用户配置为默认值")
        self.config.clear()
        for section, settings in self.DEFAULT_SETTINGS.items():
            self.config.add_section(section)
            for key, value in settings.items():
                self.config.set(section, key, value)
        self._save_config()


# 全局单例
_settings_manager = None


def get_settings_manager() -> UserSettingsManager:
    """获取全局设置管理器实例"""
    global _settings_manager
    if _settings_manager is None:
        _settings_manager = UserSettingsManager()
    return _settings_manager
