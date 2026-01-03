"""
测试视频时间排序时的过滤逻辑

功能：验证按 video_create_time 排序时，只返回已下载的视频

运行方法：
    uv run pytest tests/test_video_time_sort_filter.py -v
"""
import pytest
from django.utils import timezone
from nassav.services import list_resources


@pytest.fixture
def setup_video_resources(resource_factory):
    """创建测试数据：已下载和未下载的资源"""
    # 创建已下载的资源
    downloaded1 = resource_factory(
        avid="TEST-001",
        original_title="已下载资源1",
        file_exists=True,
        video_saved_at=timezone.now() - timezone.timedelta(days=2),
    )
    downloaded2 = resource_factory(
        avid="TEST-002",
        original_title="已下载资源2",
        file_exists=True,
        video_saved_at=timezone.now() - timezone.timedelta(days=1),
    )

    # 创建未下载的资源
    pending1 = resource_factory(
        avid="TEST-003",
        original_title="未下载资源1",
        file_exists=False,
        video_saved_at=None,
    )
    pending2 = resource_factory(
        avid="TEST-004",
        original_title="未下载资源2",
        file_exists=False,
        video_saved_at=None,
    )

    return {
        "downloaded": [downloaded1, downloaded2],
        "pending": [pending1, pending2],
    }


@pytest.mark.django_db
def test_video_create_time_sort_filters_undownloaded(setup_video_resources):
    """测试按视频创建时间排序时，只返回已下载的资源"""
    # 模拟前端请求参数：按 video_create_time 降序排序
    params = {"ordering": "-video_saved_at"}

    objects, pagination = list_resources(params)

    # 验证只返回已下载的资源
    assert len(objects) == 2
    avids = [obj.avid for obj in objects]
    assert "TEST-001" in avids
    assert "TEST-002" in avids
    assert "TEST-003" not in avids
    assert "TEST-004" not in avids

    # 验证排序顺序（降序：最新的在前）
    assert objects[0].avid == "TEST-002"
    assert objects[1].avid == "TEST-001"


@pytest.mark.django_db
def test_video_create_time_sort_asc(setup_video_resources):
    """测试按视频创建时间升序排序"""
    params = {"ordering": "video_saved_at"}

    objects, pagination = list_resources(params)

    # 验证只返回已下载的资源
    assert len(objects) == 2

    # 验证排序顺序（升序：最旧的在前）
    assert objects[0].avid == "TEST-001"
    assert objects[1].avid == "TEST-002"


@pytest.mark.django_db
def test_other_sort_includes_all(setup_video_resources):
    """测试按其他字段排序时，包含所有资源"""
    # 按 AVID 排序应该包含所有资源
    params = {"ordering": "avid"}

    objects, pagination = list_resources(params)

    # 验证返回所有资源
    assert len(objects) == 4


@pytest.mark.django_db
def test_status_filter_with_video_sort(setup_video_resources):
    """测试状态过滤与视频时间排序结合使用"""
    # 明确指定 status=pending 但按 video_saved_at 排序
    # 这种情况下，应该优先考虑排序过滤（只返回已下载）
    params = {"ordering": "-video_saved_at"}

    objects, pagination = list_resources(params)

    # 验证只返回已下载的资源
    assert len(objects) == 2
    for obj in objects:
        assert obj.file_exists
        assert obj.video_saved_at is not None


@pytest.mark.django_db
def test_pagination_with_video_sort(setup_video_resources):
    """测试分页与视频时间排序结合使用"""
    params = {"ordering": "-video_saved_at", "page": 1, "page_size": 1}

    objects, pagination = list_resources(params)

    # 验证分页信息
    assert pagination["total"] == 2
    assert pagination["page"] == 1
    assert pagination["page_size"] == 1
    assert pagination["pages"] == 2

    # 验证返回第一个结果
    assert len(objects) == 1
    assert objects[0].avid == "TEST-002"
