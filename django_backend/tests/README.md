# 测试套件总览

本文档提供 NASSAV 后端测试套件的完整概览和使用指南。

## 抽象重构离线质量门槛

从 `django_backend/` 运行 `uv run pytest tests/ --ds=django_project.refactoring_test_settings -v`。测试配置强制使用无凭证示例配置、临时 SQLite/资源/用户设置、内存缓存和 Channels，并跳过标记为 `external` 的真实服务样本。未模拟的网络调用即使被业务捕获，也会在测试收尾失败；测试进程不连接生产 Redis或外站。具体兼容矩阵和阶段结果见[执行记录](../doc/backend-refactoring-execution.md)。

`test_refactoring_baseline.py` 冻结下载“先通知成功、写库失败仍成功”和资源“写库失败保留HTML且不发新增事件”的现有时序；`test_search_jobs.py` 区分合法空列表与来源失败。真实 Ollama、Javbus封面/头像、资源现场及浏览器样本不算离线通过；需要专门环境验证。

`test_backend_contracts.py` 验证 ABC 必需能力、Manager 工厂替换和翻译可用性延迟检查。`test_session_lifecycle_contracts.py` 验证无数据库会话替换和失租保护，并启动无凭证、禁止 TCP、只监听临时 Unix socket 的 Redis，验证真实 Lua 所有权与 TTL。该套件要求系统提供 `redis-server`；进程与目录在测试结束后清理，不复用项目 Redis。

## P1 会话数据与迁移测试

`test_source_cookie_session.py` 在隔离 SQLite 测试库上验证增量迁移、会话快照、代理摘要、人工 Cookie 覆盖/清除、旧结果晚到、缓存版本与两个并发写入者。该测试不请求外站或写生产库；同一文件也应在隔离 PostgreSQL 测试库运行。

```bash
DB_ENGINE=sqlite DATABASE_PATH=/tmp/nassav-p1-test.sqlite3 NASSAV_CONFIG_PATH=config/config.example.yaml uv run pytest tests/test_source_cookie_session.py -v
```

## P2 页面会话复用测试

`test_browser_session_reuse.py` 离线覆盖直连状态、三种抓取策略、浏览器候选筛选、3 秒验证、人工写入竞争及失败不污染数据库。运行：`DB_ENGINE=sqlite DATABASE_PATH=/tmp/nassav-p2-tests.sqlite3 NASSAV_CONFIG_PATH=config/config.example.yaml uv run pytest tests/test_browser_session_reuse.py -v`。

## P3 会话刷新协调测试

`test_session_coordination.py` 离线覆盖 10 个同站并发请求、不同站点锁隔离、有限等待、租约失效、Redis 断连、人工更新、旧 `auto=true` Cookie API 与不可复用短期抑制。运行：`DB_ENGINE=sqlite DATABASE_PATH=/tmp/nassav-p3-tests.sqlite3 NASSAV_CONFIG_PATH=config/config.example.yaml uv run pytest tests/test_session_coordination.py -v`。测试使用进程内模拟锁，不连接生产 Redis。

## Byparr 页面抓取测试

`test_probe_byparr_session.py` 离线验证 P0 探测脚本的 Cookie 域名/路径/过期筛选、挑战页、错域校验及 MissAV 嵌入脚本误判分类；不会访问外站或读取生产 Cookie。运行：`uv run pytest tests/test_probe_byparr_session.py -v`。P0 现场方案与未完成证据见[基线记录](../doc/byparr-session-reuse-p0-record.md)。

旧的 `test_resource_samples.py`、`test_real_resource_kir062.py` 和 `test_debug_requests.py` 会访问真实目标站，默认跳过；仅设置 `NASSAV_EXTERNAL_TESTS=1` 才运行，其中资源测试可能写入测试数据库和资源文件。

`test_browser_page_client.py`、`test_page_fetching.py`、`test_browser_fetch_config.py` 与 `test_source_page_fetching.py` 均为离线测试。`test_browser_fetch_integration.py` 使用 `external` 标记，默认在发起网络请求前跳过；显式启用后服务不可用会失败。运行时使用当前确认存在的详情页，避免旧固定编号已失效。

```bash
uv run pytest tests/test_browser_page_client.py tests/test_page_fetching.py tests/test_browser_fetch_config.py tests/test_source_page_fetching.py -v
BROWSER_FETCH_EXTERNAL=1 \
BROWSER_FETCH_URL=http://127.0.0.1:8192 \
BROWSER_FETCH_MISSAV_URL=https://missav.ai/cn/ipzz-912 \
BROWSER_FETCH_MISSAV_AVID=IPZZ-912 \
BROWSER_FETCH_JABLE_URL=https://jable.tv/videos/jur-466/ \
BROWSER_FETCH_JABLE_AVID=JUR-466 \
uv run pytest tests/test_browser_fetch_integration.py -v
```

## 访问与业务隔离回归

[项目质量与运行边界](../../docs/project-quality.md)概述访问和部署要求。本节覆盖 Cookie、设置、资源删除、推荐重置、资源添加/刷新、下载进度、WebSocket 重连和数据库备份的隔离样本。以下命令在 `django_backend/` 下运行；使用无凭证模板与 SQLite 测试库，不连接开发 PostgreSQL。删除及备份样本另用 pytest 临时目录。

```bash
DB_ENGINE=sqlite DATABASE_PATH=/tmp/nassav-p0-pytest.sqlite3 \
NASSAV_CONFIG_PATH=config/config.example.yaml \
uv run pytest tests/test_source_cookie_api.py tests/test_user_settings.py \
  tests/test_recommendations_demo.py::test_recommendation_reset_endpoint_clears_history_but_preserves_blocklist \
  tests/test_scrape_jobs.py::test_single_api_returns_202_with_status_capability \
  tests/test_scrape_jobs.py::test_status_endpoint_returns_snapshot \
  tests/test_metadata_format.py::test_refresh_resource_preserves_existing_actor_relations_when_scrape_fails \
  tests/test_p0_regression.py -q
```

前端任务快照恢复样本：`cd ../vue_frontend && node --test tests/scrapeJobs.test.js`。外站、真实 Worker 与 PostgreSQL 恢复不由上述离线测试覆盖。

## F1 资源删除回归

`test_resource_deletion.py` 使用临时封面、缩略图、视频和备份目录验证单条/批量删除、部分失败与重试、旧同步批量合同、非法编号及同一 AVID 并发。前端 `tests/resourceDeletion.test.js` 验证批量部分失败时本地资源不被误删。

```bash
DB_ENGINE=sqlite DATABASE_PATH=/tmp/nassav-f1-pytest.sqlite3 \
NASSAV_CONFIG_PATH=config/config.example.yaml \
uv run pytest tests/test_resource_deletion.py -q
cd ../vue_frontend && node --test tests/resourceDeletion.test.js
```

## 数据库模式回归

`test_database_configuration.py` 使用隔离子进程验证 Compose 引擎与数据目录声明冲突会在连接前失败，以及 PostgreSQL 连接失败不会创建 SQLite 文件。`test_compose_stack.py` 验证声明初始化、已有目录采用、运行模式不符时的预检拒绝，以及数据目录不可写时的定向修复提示。Compose 的两种模式与三个队列的现行配置见[部署说明](../doc/compose-deployment.md)。

```bash
DB_ENGINE=sqlite DATABASE_PATH=/tmp/nassav-p2-pytest.sqlite3 \
NASSAV_CONFIG_PATH=config/config.example.yaml \
uv run pytest tests/test_database_configuration.py tests/test_compose_stack.py -q
```

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
- **覆盖**: ResourceSummarySerializer
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

---

**最后更新**: 2026-09-28

## 异步资源任务测试

`test_scrape_jobs.py` 使用内存任务存储和 mock 的业务执行，验证去重、入队失败清理、阶段与终态、批量部分失败及状态查询令牌，不访问外部站点：

```bash
uv run pytest tests/test_scrape_jobs.py -v
```

## 进度通道测试

`test_ws.py` 覆盖并发 WebSocket 握手不受慢速 Celery 队列检查阻塞，以及下载进度事件与刮削阶段事件保持独立。运行：

```bash
uv run pytest tests/test_ws.py -v
```

### Compose Ollama 模型就绪检查

`uv run pytest tests/test_ensure_ollama_model.py -q` 验证可选 Ollama profile 在翻译 worker 启动前拉取并确认当前配置的模型，以及 `OLLAMA_URL` 容器地址覆盖。

## 下载代理隔离测试

`uv run pytest tests/test_download_proxy_isolation.py -q` 验证 `Proxy.download_url` 的默认值、可选环境覆盖，以及下载器子进程不继承 worker 的系统代理变量。

## 数据库配置和备份

`test_database_configuration.py` 覆盖 SQLite 默认配置、PostgreSQL 缺失密码时的快速失败，以及 PostgreSQL 模式清理时保留 SQLite 回滚快照。

```bash
uv run pytest tests/test_database_configuration.py -v
```

P4 离线回归包含 Cookie API 可选 UA 与旧请求清除旧 UA、复用开关默认关闭和显式恢复页面策略；运行 `uv run pytest tests/test_source_cookie_api.py tests/test_browser_fetch_config.py tests/test_page_fetching.py -v`。

`test_resource_deletion.py` 包含缺省缩略图目录的删除回归；运行 `uv run pytest tests/test_resource_deletion.py -v`。测试只使用 pytest 隔离数据库和临时目录，不触碰实际资源文件。

## Byparr 会话复用 P5

隔离全套命令使用当前本地样例 `config/config.example.yaml`，并显式设置测试专用 `NASSAV_ENV_PATH`、`DATABASE_PATH` 与 `NASSAV_RESOURCE_DIR`。PostgreSQL 迁移与会话测试应使用单独测试实例和库；正式站点测试需要 `BROWSER_FETCH_EXTERNAL=1`，服务不可用即失败，不计入离线通过。现场样本数、门槛、24 小时观察及回滚见[P5 记录](../doc/byparr-session-reuse-p5-record.md)。

`test_probe_byparr_media.py` 离线验证第三步隔离 A/B 的顺序平衡、控制请求只改变媒体参数、计时不串请求、失败请求仍纳入时延统计，以及业务就绪等待不会接纳错番号、挑战或缺少播放结构的页面。运行 `uv run pytest tests/test_probe_byparr_media.py -v`；线上方法与结果见[第三步实验记录](../doc/byparr-media-experiment-record.md)。

## Byparr 有界等待及验收门槛

`uv run pytest tests/test_byparr_bounded_wait.py tests/test_assess_byparr_acceptance.py -v` 覆盖错误页继续原等待、业务完成取消闲置任务、慢内容读取的两秒上限、总预算耗尽、请求取消和并发完成时保留原异常；门槛评估拒绝缺少第二窗口、重复番号、慢失败被剔除、直连有效率不足、浏览器调用过多和反向误接纳。在线验证只使用隔离候选，方法见[第四步验收记录](../doc/byparr-candidate-acceptance-record.md)。

- `test_jable_auto_cookie.py`：Jable 自动 Cookie API 的浏览器获取、完整会话保存、失败保护及并发手动写入保护；无额外参数，运行 `uv run pytest tests/test_jable_auto_cookie.py -v`。

## MissAV 与 Jable 搜索源选择

`test_missav_search.py`：列表 URL/排序、现有抓取策略、同站业务结构、源映射、关键词回退、禁用/未知源、失败不缓存、视频变体去重。无额外参数，运行 `uv run pytest tests/test_missav_search.py tests/test_external_search_detail_api.py -v`。

## 中文外部搜索、图片与后台任务

`test_missav_search.py` 增加中文路径、空结果和动态前缀回归。`test_search_covers.py` 覆盖源隔离、图片域名限制、原子缓存、下载大小及 Cookie 不外传。`test_search_jobs.py` 覆盖任务 API、真实业务调用边界、去重、终态复用、失败重试、超时、队列故障及持久化默认源。

运行：`DEBUG=false NASSAV_CONFIG_PATH=config/config.example.yaml DB_ENGINE=sqlite DATABASE_PATH=/tmp/nassav-search-tests.sqlite3 uv run pytest tests/test_missav_search.py tests/test_search_covers.py tests/test_search_jobs.py tests/test_user_settings.py -v`。离线测试使用模拟存储，不访问正式数据库或 Redis。现场脚本见 scripts/README.md。

## 逐页外部搜索

`uv run pytest tests/test_search_jobs.py tests/test_access_control.py -v`，无需公网或正式 Redis。覆盖 MissAV/Jable 的演员/类别累计去重、running 阶段快照、后续页失败后保留结果与重试、不缓存残缺列表、终态保护、通知负载以及已登录 WebSocket 透传。前端 `pnpm run test` 验证逐页呈现、推送/查询竞态与旧版本防护。

`test_search_jobs.py` 还覆盖带签名凭证的取消接口、排队任务释放锁后重试、运行任务取消后停止后续页及保留阶段结果。前端 `externalSearchTask.test.js` 覆盖提交响应未到时点击取消，最终仍调用后台取消接口。

## 来源扩展契约

`uv run pytest tests/test_search_adapter_contracts.py --ds=django_project.refactoring_test_settings -v` 验证新增列表 Adapter 无需修改通用能力/排序流程、缓存上下文隔离，以及实现内 TypeError 不重试旧签名。生产 Jable/MissAV 和测试替身均消费 ListingSource；源特有封面规则在 CoverPolicy 中维护。

## 资源用例注入

`uv run pytest tests/test_resource_workflow_contracts.py --ds=django_project.refactoring_test_settings -v` 验证无数据库新增/重复/刷新、来源纯解析、其他来源映射写入与输入不被持久化修改；配合 metadata、封面优先级和 R0 失败时序回归运行。

### 下载 owner 与失租验收

`uv run pytest tests/test_download_lock_ownership.py --ds=django_project.refactoring_test_settings -v` 使用临时 Redis（仅 Unix socket、无持久化）和本地静默 CLI，覆盖旧 owner 释放/续租/进度/清理、重复投递、心跳失租、成功抑制及清理异常。无需服务凭证或外站网络。

`tests/test_download_cli_cancellation.py` 追加 POSIX 进程组验收：子进程忽略 SIGTERM 且保留 stdout，失租取消仍须及时结束调用。测试有独立兜底清理计时器，防止失败样本留下本地进程。

### 下载用例替换验收

`uv run pytest tests/test_download_workflow_contracts.py --ds=django_project.refactoring_test_settings -v` 不启动 worker、不访问数据库或网络，通过真实 ABC 替身验证下载及模拟用例的结果、超时、重试和清理，以及资源缓存未命中的准备与回退。

`tests/test_batch_translation_state.py` 使用临时 SQLite 和翻译替身，验证原始/来源标题选择、skip_existing、返回数量异常、翻译器异常及部分保存失败收尾。

`tests/test_translation_workflow_contracts.py` 不访问 DB 或 worker，验证单条/批量共享标题优先级、状态规则及单条结果 envelope。

`tests/test_recommendation_pipeline_contracts.py` 验证纯算法、固定种子、输入不变、注册新推荐器、纯种子排序、批量查询上限及无 Django 配置导入。
