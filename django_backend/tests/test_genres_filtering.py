#!/usr/bin/env python
"""
测试类别 API 过滤功能

验证 GET /api/genres/ 接口是否正确过滤掉未使用的类别
"""

import os
import sys
from pathlib import Path

# 设置 Django 环境
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")

import django
django.setup()

from django.test import RequestFactory
from rest_framework.request import Request
from django.db.models import Count
from nassav.views import GenresListView
from nassav.models import Genre


def test_genres_filtering():
    """测试类别 API 是否过滤掉未使用的类别"""

    print("\n" + "=" * 60)
    print("测试类别 API 过滤功能")
    print("=" * 60)

    # 获取数据库统计
    total_genres = Genre.objects.count()
    used_genres = Genre.objects.annotate(
        resource_count=Count('resources')
    ).filter(resource_count__gt=0).count()
    unused_genres = Genre.objects.annotate(
        resource_count=Count('resources')
    ).filter(resource_count=0).count()

    print(f"\n数据库统计:")
    print(f"  总类别数:     {total_genres}")
    print(f"  使用中:       {used_genres}")
    print(f"  未使用:       {unused_genres}")

    # 测试 API 响应
    factory = RequestFactory()
    django_request = factory.get('/api/genres/', {'page_size': 1000})
    request = Request(django_request)

    view = GenresListView()
    response = view.get(request)

    api_total = response.data['pagination']['total']
    api_genres = response.data['data']

    print(f"\nAPI 响应:")
    print(f"  返回类别数:   {api_total}")
    print(f"  实际记录数:   {len(api_genres)}")

    # 检查是否有 resource_count = 0 的类别
    unused_in_api = [g for g in api_genres if g['resource_count'] == 0]

    print(f"\nAPI 中的未使用类别: {len(unused_in_api)}")

    # 验证结果
    print("\n" + "=" * 60)
    print("验证结果:")
    print("=" * 60)

    success = True

    # 验证 1: API 返回的数量应该等于使用中的类别数
    if api_total == used_genres:
        print("✅ API 返回数量正确")
    else:
        print(f"❌ API 返回数量错误: 期望 {used_genres}, 实际 {api_total}")
        success = False

    # 验证 2: API 响应中不应该有未使用的类别
    if len(unused_in_api) == 0:
        print("✅ API 已过滤未使用的类别")
    else:
        print(f"❌ API 中仍有 {len(unused_in_api)} 个未使用的类别:")
        for g in unused_in_api:
            print(f"   - {g['name']} (ID: {g['id']})")
        success = False

    # 验证 3: 使用 ID 查询应该能返回未使用的类别
    if unused_genres > 0:
        unused_genre = Genre.objects.annotate(
            resource_count=Count('resources')
        ).filter(resource_count=0).first()

        django_request_with_id = factory.get(
            '/api/genres/',
            {'id': unused_genre.id, 'page_size': 10}
        )
        request_with_id = Request(django_request_with_id)
        response_with_id = view.get(request_with_id)

        if response_with_id.data['pagination']['total'] == 1:
            print("✅ 使用 ID 查询可以返回未使用的类别")
        else:
            print("❌ 使用 ID 查询失败")
            success = False

    print("=" * 60)

    if success:
        print("\n🎉 所有测试通过!")
        return 0
    else:
        print("\n❌ 部分测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(test_genres_filtering())
