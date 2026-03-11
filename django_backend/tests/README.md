# 测试套件总览

本文档提供 NASSAV 后端测试套件的完整概览和使用指南。

## 测试架构说明

本项目测试已迁移至 **pytest** 框架，使用 fixtures 进行测试数据管理。所有新测试和重构的测试都应遵循 pytest 规范。

### 通用 Fixtures（conftest.py）

项目提供以下可复用的 fixtures：

- `actor_factory`: 创建演员对象的工厂函数
- `resource_factory`: 创建资源对象的工厂函数
- `genre_factory`: 创建类别对象的工厂函数
- `api_client`: DRF APIClient 实例
- `client`: Django test client 实例
- `assert_api_response`: API 响应验证辅助函数
- `resource_with_actors`: 创建带演员的资源
- `resource_with_genres`: 创建带类别的资源
- `bulk_resources`: 批量创建资源

## 测试文件分类

### ✅ 已重构为 pytest 的测试

#### 1. test_actors_api.py

- **功能**: 测试演员相关 API
- **端点**: `/api/resources/?actor=...`, `/api/actors/`
- **运行**: `uv run pytest tests/test_actors_api.py -v`
- **fixtures**: `setup_actors_with_resources`, `api_client`

#### 2. test_genres_api.py

- **功能**: 测试类别/标签相关 API
- **端点**: `/api/resources/?genre=...`, `/api/genres/`
- **运行**: `uv run pytest tests/test_genres_api.py -v`
- **fixtures**: `setup_genres_with_resources`, `api_client`

#### 3. test_resources_list.py

- **功能**: 测试资源列表和过滤功能
- **端点**: `/api/resources/`
- **运行**: `uv run pytest tests/test_resources_list.py -v`
- **fixtures**: `setup_resources`, `api_client`

#### 4. test_views_resource.py

- **功能**: 测试资源相关视图和文件操作
- **端点**: `/api/resource/metadata`, `/api/downloads/abspath`
- **运行**: `uv run pytest tests/test_views_resource.py -v`
- **fixtures**: `api_client`, `resource_factory`, `tmp_path`, `settings`

#### 5. test_serializers.py

- **功能**: 测试序列化器的数据转换和验证
- **覆盖**: ResourceSummarySerializer, ResourceSerializer
- **运行**: `uv run pytest tests/test_serializers.py -v`
- **fixtures**: `resource_with_relations`

#### 6. test_actor_avatar_api.py

- **功能**: 测试演员头像功能完整流程
- **运行**: `uv run pytest tests/test_actor_avatar_api.py -v`
- **fixtures**: `actor_factory`, `resource_factory`, `api_client`

#### 7. test_actors_list_filter.py

- **功能**: 测试演员列表 API 过滤功能
- **覆盖**: 验证演员列表只返回有作品的演员
- **运行**: `uv run pytest tests/test_actors_list_filter.py -v`
- **fixtures**: `setup_actors`, `client`

### 其他测试文件

#### 8. test_video_time_sort_filter.py

- **功能**: 测试视频时间排序时的过滤逻辑
- **覆盖**: 按 video_create_time 排序时只返回已下载资源
- **运行**: `uv run pytest tests/test_video_time_sort_filter.py -v`
- **fixtures**: `setup_video_resources`, `resource_factory`

#### 9. test_javbus_actor_parsing.py

- **功能**: 测试 Javbus 女优名解析（防止括号内容被截断）
- **覆盖**: 从 img title 属性提取完整女优名
- **运行**: `uv run pytest tests/test_javbus_actor_parsing.py -v`
- **fixtures**: `javbus_html_content`, `javbus_scraper`

#### 10. test_fix_actor_names.py

- **功能**: 测试演员名称正常性判断逻辑
- **覆盖**: 判断演员名是否被截断（括号匹配检测）
- **运行**: `uv run pytest tests/test_fix_actor_names.py -v`

#### 11. test_actor_avatar_extraction.py

- **功能**: 测试演员头像 URL 提取
- **类型**: 纯单元测试，不依赖数据库
- **运行**: `uv run pytest tests/test_actor_avatar_extraction.py -v`

#### 12. test_user_settings.py

- **功能**: 测试用户设置 API
- **端点**: `/api/setting`
- **运行**: `uv run pytest tests/test_user_settings.py -v`

#### 13. test_resource_samples.py

- **功能**: 测试资源样例的完整流程和数据有效性
- **覆盖**:
  - 不存在的资源（TEST-001, TEST-002, TEST-003）- 预期失败
  - 真实存在的资源（MIMK-054, VEMA-208, OVG-206）- 预期成功
  - 主要使用 Jable 作为 Source
  - 验证数据库数据的有效性和一致性
- **运行**:
  - 全部测试: `uv run pytest tests/test_resource_samples.py -v`
  - 不存在资源: `uv run pytest tests/test_resource_samples.py::test_nonexistent_resources -v`
  - 真实资源: `uv run pytest tests/test_resource_samples.py::test_real_resources -v`

### 集成测试（Integration Tests）

#### 14. test_ws.py

- **功能**: 测试 WebSocket 实时通信
- **端点**: `/ws/tasks/`
- **运行**: `uv run pytest tests/test_ws.py -v`
- **依赖**: Redis 服务

#### 15. test_translator.py

- **功能**: 测试 Ollama 翻译器功能
- **运行**: `uv run python tests/test_translator.py --batch --count 10`
- **依赖**: Ollama 服务

#### 16. test_translator_manager.py

- **功能**: 测试翻译管理器和重试机制
- **运行**: `uv run python tests/test_translator_manager.py`
- **依赖**: Ollama 服务

#### 17. test_translation_cleaning.py

- **功能**: 测试翻译结果后处理清理功能
- **运行**: `uv run python tests/test_translation_cleaning.py`
- **说明**: 验证翻译结果中多余说明文字的清理效果

### Shell 脚本测试（Shell Script Tests）

#### 18. test_api.sh

- **功能**: 综合 API 测试脚本
- **运行**: `./tests/test_api.sh --verbose`
- **依赖**: curl, jq (可选)

#### 19. test_mock_download.sh

- **功能**: 模拟下载任务批处理测试
- **运行**: `./tests/test_mock_download.sh --duration 30`
- **依赖**: curl, jq (可选)

#### 20. test_websocket.sh

- **功能**: WebSocket 实时监听测试
- **运行**: `./tests/test_websocket.sh`
- **依赖**: wscat 或 websocket-client (Python)

---

## 快速开始

### 运行所有 pytest 测试

```bash
cd django_backend
uv run pytest tests/ -v
```

### 运行已重构的核心 API 测试

```bash
cd django_backend
uv run pytest tests/test_actors_api.py tests/test_genres_api.py tests/test_resources_list.py tests/test_views_resource.py tests/test_serializers.py -v
```

### 运行特定测试

```bash
# 单个测试文件
uv run pytest tests/test_actors_api.py -v

# 单个测试函数
uv run pytest tests/test_actors_api.py::test_actor_filter_by_name -v

# 带标记的测试
uv run pytest tests/ -v -m django_db
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

### 编写新的 pytest 测试（推荐）

```python
#!/usr/bin/env python
"""
新测试文件说明

功能：
1. 描述测试功能点1
2. 描述测试功能点2

运行方式：
    uv run pytest tests/test_new_feature.py -v
"""

import pytest


@pytest.fixture
def setup_test_data(resource_factory, actor_factory):
    """创建测试数据的 fixture"""
    resource = resource_factory(avid="TEST-001", original_title="测试")
    actor = actor_factory(name="测试演员")
    resource.actors.add(actor)
    return {"resource": resource, "actor": actor}


@pytest.mark.django_db
def test_feature(api_client, setup_test_data):
    """测试功能描述"""
    response = api_client.get("/nassav/api/endpoint/")
    assert response.status_code == 200

    data = response.json()
    assert data["code"] == 200
```

### 使用通用 Fixtures

项目提供的通用 fixtures 可以直接使用：

```python
@pytest.mark.django_db
def test_with_factories(actor_factory, resource_factory, genre_factory):
    """使用工厂 fixtures 创建测试数据"""
    actor = actor_factory(name="演员A")
    resource = resource_factory(avid="TEST-001")
    genre = genre_factory(name="类别A")

    resource.actors.add(actor)
    resource.genres.add(genre)

    assert resource.actors.count() == 1


@pytest.mark.django_db
def test_with_api_client(api_client):
    """使用 API client 测试端点"""
    response = api_client.get("/nassav/api/resources/")
    assert response.status_code == 200
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

1. **使用 pytest + fixtures**: 所有新测试应使用 pytest 框架和 fixtures
2. **独立性**: 每个测试应独立运行，不依赖其他测试的执行顺序
3. **可重复性**: 测试结果应该可重复，避免随机性
4. **清晰性**: 测试名称应清楚描述测试内容（使用 `test_` 前缀）
5. **完整性**: 测试应覆盖正常流程和异常情况
6. **速度**: 保持测试运行速度，避免长时间等待
7. **使用工厂 fixtures**: 优先使用 conftest.py 中定义的工厂函数创建测试数据
8. **标记数据库测试**: 使用 `@pytest.mark.django_db` 标记需要数据库的测试

## 重构说明

本项目测试代码已进行系统性重构（2026-01-03），主要改进：

### Phase 1: 基础设施

- ✅ 增强 conftest.py 提供通用 fixtures
- ✅ 添加 assert_api_response, resource_with_actors 等辅助函数

### Phase 2: 核心 API 测试重构（5个文件）

- ✅ test_actors_api.py - 演员 API
- ✅ test_genres_api.py - 类别 API
- ✅ test_resources_list.py - 资源列表
- ✅ test_views_resource.py - 资源视图
- ✅ test_serializers.py - 序列化器

### Phase 3: 业务逻辑测试重构（3个文件）

- ✅ test_video_time_sort_filter.py - 视频时间排序过滤
- ✅ test_javbus_actor_parsing.py - Javbus 演员解析
- ✅ test_fix_actor_names.py - 演员名称修复判断

### 清理工作

- 🗑️ 删除 demo_javbus_fix.py（演示脚本，已被测试覆盖）
- 🗑️ 删除 test_genres_filtering.py（功能重复，已被 test_genres_api.py 覆盖）

### 重构收益

- 📉 减少代码重复约 40-50%
- 🎯 统一测试风格（全部使用 pytest）
- 🔧 提高可维护性（集中管理测试数据）
- ⚡ 提升测试速度
- 📖 提升代码可读性

详细重构方案见 [REFACTOR_PLAN.md](REFACTOR_PLAN.md)

---

**最后更新**: 2026-01-07
