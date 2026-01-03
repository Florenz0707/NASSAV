from django.apps import AppConfig


class NassavConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "nassav"
    verbose_name = "NASSAV Backend"

    def ready(self):
        """Django 应用启动时执行"""
        # 初始化用户设置（确保配置文件存在）
        try:
            from nassav.user_settings import get_settings_manager

            settings_manager = get_settings_manager()
            # 配置文件会在初始化时自动创建
        except Exception as e:
            print(f"初始化用户设置失败: {e}")
