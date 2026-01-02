#!/usr/bin/env python
"""
生成 OpenAPI 文档脚本

功能：
    使用 drf-spectacular 生成 OpenAPI 3.0 规范的 API 文档 (openapi.yaml)

用法：
    # 生成 OpenAPI 文档到 doc/openapi.yaml
    uv run python scripts/generate_openapi.py

    # 或者使用 Django 管理命令
    uv run python manage.py spectacular --file doc/openapi.yaml

依赖：
    - drf-spectacular >= 0.27.0

输出：
    - doc/openapi.yaml: OpenAPI 3.0 规范文档

注意：
    - 需要在 Django 环境中运行
    - 确保 settings.py 中已配置 SPECTACULAR_SETTINGS
"""
import os
import sys
import django

# Ensure project root is on sys.path so Django project package is importable
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Ensure settings module is set
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_project.settings')
django.setup()

from django.core.management import call_command


def main():
    """Generate OpenAPI documentation using drf-spectacular."""
    try:
        call_command('spectacular', '--file', './doc/openapi.yaml')
        print('✅ 成功生成 OpenAPI 文档: doc/openapi.yaml')
        print('📝 可以使用 Swagger UI 或 Redoc 查看文档')
    except Exception as e:
        print(f'❌ 生成 OpenAPI 文档失败: {e}')
        sys.exit(1)


if __name__ == '__main__':
    main()
