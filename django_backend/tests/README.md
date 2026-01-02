# 测试套件总览

本文档提供 NASSAV 后端测试套件的完整概览和使用指南。

## 测试文件分类

### 单元测试（Unit Tests）

#### 1. test_serializers.py
- **功能**: 测试序列化器的数据转换和验证
- **覆盖**: ResourceSummarySerializer, ResourceSerializer
- **运行**: `python manage.py test tests.test_serializers`

### API 测试（API Tests）

#### 2. test_actors_api.py
- **功能**: 测试演员相关 API
- **端点**: `/api/resources/?actor=...`, `/api/actors/`
- **运行**: `python manage.py test tests.test_actors_api`

#### 3. test_genres_api.py
- **功能**: 测试类别/标签相关 API
- **端点**: `/api/resources/?genre=...`, `/api/genres/`
- **运行**: `python manage.py test tests.test_genres_api`

#### 4. test_resources_list.py
- **功能**: 测试资源列表和过滤功能
- **端点**: `/api/resources/`
- **运行**: `python manage.py test tests.test_resources_list`

#### 5. test_views_resource.py
- **功能**: 测试资源相关视图和文件操作
- **端点**: `/api/downloads/list`, `/api/resource/metadata`, `/api/downloads/abspath`
- **运行**: `python manage.py test tests.test_views_resource`

### 集成测试（Integration Tests）

#### 6. test_ws.py
- **功能**: 测试 WebSocket 实时通信
- **端点**: `/ws/tasks/`
- **运行**: `python manage.py test tests.test_ws`
- **依赖**: Redis 服务

#### 7. test_translator.py
- **功能**: 测试 Ollama 翻译器功能
- **运行**: `python tests/test_translator.py --batch --count 10`
- **依赖**: Ollama 服务

#### 8. test_translator_manager.py
- **功能**: 测试翻译管理器和重试机制
- **运行**: `python tests/test_translator_manager.py`
- **依赖**: Ollama 服务

#### 9. test_translation_cleaning.py
- **功能**: 测试翻译结果后处理清理功能
- **运行**: `uv run tests/test_translation_cleaning.py`
- **说明**: 验证翻译结果中多余说明文字的清理效果

### Shell 脚本测试（Shell Script Tests）

#### 10. test_api.sh
- **功能**: 综合 API 测试脚本
- **运行**: `./tests/test_api.sh --verbose`
- **依赖**: curl, jq (可选)

#### 11. test_mock_download.sh
- **功能**: 模拟下载任务批处理测试
- **运行**: `./tests/test_mock_download.sh --duration 30`
- **依赖**: curl, jq (可选)

#### 12. test_websocket.sh
- **功能**: WebSocket 实时监听测试
- **运行**: `./tests/test_websocket.sh`
- **依赖**: wscat 或 websocket-client (Python)

---

## 快速开始

### 运行所有单元测试
```bash
cd django_backend
python manage.py test tests/
```

### 运行所有 pytest 测试
```bash
cd django_backend
pytest tests/ -v
```

### 运行特定测试
```bash
# 单个测试文件
python manage.py test tests.test_actors_api

# 单个测试类
python manage.py test tests.test_actors_api.ActorsAPITest

# 单个测试方法
python manage.py test tests.test_actors_api.ActorsAPITest.test_actor_filter_by_name
```

### 运行 Shell 脚本测试
```bash
cd django_backend/tests

# 赋予执行权限
chmod +x *.sh

# 综合 API 测试
./test_api.sh --verbose

# 模拟下载测试
./test_mock_download.sh

# WebSocket 测试
./test_websocket.sh
```

---

## 测试环境设置

### 必需服务

1. **Redis** (用于 Celery 和 Channels)
   ```bash
   redis-server
   ```

2. **Django 服务器** (用于 Shell 脚本测试)
   ```bash
   uv run python manage.py runserver
   ```

3. **Celery Worker** (用于任务队列测试)
   ```bash
   uv run celery -A django_project worker -l info
   ```

4. **Ollama 服务** (用于翻译测试，可选)
   ```bash
   ollama serve
   ```

### 环境变量

创建 `.env` 文件用于测试：
```bash
# 测试环境配置
DEBUG=True
SECRET_KEY=test-secret-key
ALLOWED_HOSTS=localhost,127.0.0.1
```

---

## 测试覆盖率

### 生成覆盖率报告
```bash
# 安装 coverage
pip install coverage

# 运行测试并收集覆盖率
coverage run --source='.' manage.py test tests/

# 生成报告
coverage report

# 生成 HTML 报告
coverage html
# 在浏览器中打开 htmlcov/index.html
```

---

## 持续集成 (CI/CD)

### GitHub Actions 示例

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      redis:
        image: redis:latest
        ports:
          - 6379:6379

    steps:
      - uses: actions/checkout@v2

      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: |
          cd django_backend
          pip install uv
          uv sync

      - name: Run migrations
        run: |
          cd django_backend
          uv run python manage.py migrate

      - name: Run unit tests
        run: |
          cd django_backend
          uv run python manage.py test tests/

      - name: Run shell script tests
        run: |
          cd django_backend/tests
          chmod +x test_api.sh
          ./test_api.sh
```

---

## 常见问题

### Q: 测试时出现数据库错误
**A:** Django 测试使用独立的测试数据库，每次测试后自动清理。如果遇到问题，手动删除测试数据库：
```bash
rm db.sqlite3
python manage.py migrate
```

### Q: WebSocket 测试失败
**A:** 确保：
1. Redis 服务正在运行
2. 已安装 channels 和 channels-redis
3. settings.py 中正确配置了 CHANNEL_LAYERS

### Q: 翻译测试失败
**A:** 确保：
1. Ollama 服务正在运行（`ollama serve`）
2. 已下载所需模型（`ollama pull qwen2.5:7b`）
3. config.yaml 中正确配置了翻译器

### Q: Shell 脚本测试返回 403
**A:** 在 `.env` 中设置 `DEBUG=True` 以启用调试接口

---

## 测试编写指南

### 编写新的单元测试

```python
#!/usr/bin/env python
\"\"\"
新测试文件说明

功能：
1. 描述测试功能点1
2. 描述测试功能点2

运行方式：
    python manage.py test tests.test_new_feature
\"\"\"

from django.test import TestCase

class NewFeatureTest(TestCase):
    def setUp(self):
        # 设置测试数据
        pass

    def test_feature(self):
        # 测试逻辑
        self.assertEqual(1, 1)
```

### 编写新的 Shell 测试

```bash
#!/bin/bash
# 新测试脚本说明
# 功能：描述脚本功能
# 用法：./test_new_feature.sh [选项]

# 实现测试逻辑
```

---

## 测试最佳实践

1. **独立性**: 每个测试应独立运行，不依赖其他测试的执行顺序
2. **可重复性**: 测试结果应该可重复，避免随机性
3. **清晰性**: 测试名称应清楚描述测试内容
4. **完整性**: 测试应覆盖正常流程和异常情况
5. **速度**: 保持测试运行速度，避免长时间等待

---

**最后更新**: 2026-01-02
"""

if __name__ == '__main__':
    print(__doc__)
