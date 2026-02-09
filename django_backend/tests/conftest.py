import tempfile
from pathlib import Path

import pytest
from nassav.models import Actor, AVResource


@pytest.fixture(scope="session", autouse=True)
def setup_test_user_settings():
    """
    为测试环境设置独立的用户配置文件路径
    使用临时目录，避免覆盖生产环境的配置
    """
    from django.conf import settings

    # 创建临时目录
    temp_dir = tempfile.mkdtemp(prefix="nassav_test_")
    temp_config_path = Path(temp_dir) / "user_settings.ini"

    # 保存原始路径
    original_path = getattr(settings, "USER_SETTINGS_PATH", None)

    # 设置测试路径
    settings.USER_SETTINGS_PATH = temp_config_path

    # 清除全局单例，强制重新初始化
    import nassav.user_settings

    nassav.user_settings._settings_manager = None

    yield temp_config_path

    # 测试结束后恢复原始路径
    if original_path is not None:
        settings.USER_SETTINGS_PATH = original_path

    # 清理临时目录
    import shutil

    try:
        shutil.rmtree(temp_dir)
    except Exception:
        pass


@pytest.fixture
def actor_factory(db):
    """返回一个可创建 Actor 的工厂函数"""

    def _create(**kwargs):
        defaults = {"name": "测试演员", "avatar_url": None, "avatar_filename": None}
        defaults.update(kwargs)
        return Actor.objects.create(**defaults)

    return _create


@pytest.fixture
def resource_factory(db):
    """返回一个可创建 AVResource 的工厂函数"""

    def _create(**kwargs):
        defaults = {"avid": "TEST-001", "original_title": "测试作品", "source": "test"}
        defaults.update(kwargs)
        res = AVResource.objects.create(**defaults)
        return res

    return _create


@pytest.fixture
def genre_factory(db):
    from nassav.models import Genre

    def _create(**kwargs):
        defaults = {"name": "测试类别"}
        defaults.update(kwargs)
        return Genre.objects.create(**defaults)

    return _create


@pytest.fixture
def api_client():
    """返回 DRF 的 APIClient 实例"""
    from rest_framework.test import APIClient

    return APIClient()


@pytest.fixture
def client(db):
    """返回 Django test client（用于渐进式迁移）"""
    from django.test import Client

    return Client()


@pytest.fixture
def assert_api_response():
    """验证 API 响应格式的辅助函数"""

    def _assert(response, expected_code=200):
        assert response.status_code == expected_code
        data = response.json()
        assert "code" in data
        assert data["code"] == expected_code
        return data

    return _assert


@pytest.fixture
def resource_with_actors(db, resource_factory, actor_factory):
    """创建一个带有演员的资源"""

    def _create(actor_names, **resource_kwargs):
        resource = resource_factory(**resource_kwargs)
        for name in actor_names:
            actor = actor_factory(name=name)
            resource.actors.add(actor)
        return resource

    return _create


@pytest.fixture
def resource_with_genres(db, resource_factory, genre_factory):
    """创建一个带有类别的资源"""

    def _create(genre_names, **resource_kwargs):
        resource = resource_factory(**resource_kwargs)
        for name in genre_names:
            genre = genre_factory(name=name)
            resource.genres.add(genre)
        return resource

    return _create


@pytest.fixture
def bulk_resources(resource_factory):
    """批量创建资源"""

    def _create(count, **defaults):
        resources = []
        for i in range(count):
            kwargs = defaults.copy()
            if "avid" not in kwargs:
                kwargs["avid"] = f"TEST-{i+1:03d}"
            if "original_title" not in kwargs:
                kwargs["original_title"] = f"测试作品{i+1}"
            resources.append(resource_factory(**kwargs))
        return resources

    return _create
