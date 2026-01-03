# 测试代码重构方案

## 一、当前状态分析

### 已重构的测试文件 ✅
1. **conftest.py** - 提供了基础的 fixtures（actor_factory, resource_factory, genre_factory, api_client）
2. **test_actor_avatar_api.py** - 已使用 pytest + fixtures 重构
3. **test_actors_list_filter.py** - 已使用 pytest + fixtures 重构，包含 setup_actors fixture

### 需要重构的测试文件

#### 高优先级（存在严重冗余）

1. **test_actors_api.py**
   - 使用 Django TestCase + setUp 方法
   - 重复创建 Actor 和 AVResource 实例
   - 可以使用 conftest 中的 factory fixtures
   - 冗余：手动 setUp 创建测试数据

2. **test_genres_api.py**
   - 使用 Django TestCase + setUp 方法
   - 重复创建 Genre 和 AVResource 实例
   - 可以使用 conftest 中的 genre_factory 和 resource_factory
   - 冗余：手动 setUp 创建测试数据

3. **test_resources_list.py**
   - 使用 Django TestCase + setUp 方法
   - 重复创建 AVResource 实例
   - 可以使用 conftest 中的 resource_factory
   - 冗余：手动 setUp 创建测试数据

4. **test_views_resource.py**
   - 使用 Django TestCase + setUp 方法
   - 重复创建 APIClient 实例
   - 可以使用 conftest 中的 api_client fixture
   - 冗余：每个测试类都创建 APIClient

5. **test_serializers.py**
   - 使用 Django TestCase + setUp 方法
   - 重复创建测试数据
   - 可以使用 conftest 中的 factory fixtures
   - 冗余：手动 setUp 创建测试数据

#### 中优先级（部分冗余）

6. **test_genres_filtering.py**
   - 独立脚本而非标准测试
   - 包含大量手动 Django setup 代码
   - 应该重构为标准 pytest 测试
   - 冗余：手动 Django 环境设置、手动创建 request

7. **test_user_settings.py**
   - 已使用 pytest，但缺少专用的 settings fixtures
   - 建议：在 conftest 中添加用户设置相关的 fixtures

#### 低优先级（已相对规范）

8. **test_actor_avatar_extraction.py**
   - 纯单元测试，不依赖数据库
   - 代码已经比较简洁
   - 建议：保持现状，仅需要添加少量注释

9. **test_javbus_actor_parsing.py**
   - 使用 Django TestCase，但逻辑合理
   - 依赖外部 HTML 文件
   - 建议：考虑将 HTML 文件加载逻辑抽取为 fixture

10. **test_translator.py**
    - 独立脚本，用于手动测试
    - 依赖外部服务（Ollama）
    - 建议：保持现状，或添加 mock 测试版本

---

## 二、识别的主要冗余模式

### 1. 重复的测试数据创建
```python
# 冗余模式（在多个文件中重复）
def setUp(self):
    self.client = APIClient()
    a1 = Actor.objects.create(name="Alice")
    r1 = AVResource.objects.create(avid="ACT-1", original_title="With Alice", source="S1")
    r1.actors.add(a1)
```

**应该使用：**
```python
# 使用 conftest 中的 fixtures
@pytest.mark.django_db
def test_something(api_client, actor_factory, resource_factory):
    actor = actor_factory(name="Alice")
    resource = resource_factory(avid="ACT-1", original_title="With Alice")
    resource.actors.add(actor)
```

### 2. 重复的 APIClient 创建
```python
# 每个测试类都有
def setUp(self):
    self.client = APIClient()
```

**应该使用：**
```python
# conftest 中已提供
@pytest.fixture
def api_client():
    from rest_framework.test import APIClient
    return APIClient()
```

### 3. 手动 Django 环境设置
```python
# test_genres_filtering.py 中的冗余代码
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")
django.setup()
```

**应该使用：**
- pytest-django 自动处理 Django 环境
- 使用 `@pytest.mark.django_db` 装饰器

### 4. 重复的请求/响应验证逻辑
```python
# 多个文件中重复的模式
resp = self.client.get(url)
self.assertEqual(resp.status_code, 200)
body = resp.json()
self.assertEqual(body["code"], 200)
```

**应该抽取为：**
```python
# conftest.py 中添加辅助 fixture
@pytest.fixture
def assert_api_success():
    def _assert(response):
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        return data
    return _assert
```

---

## 三、详细重构方案

### Phase 1: 增强 conftest.py（优先）

#### 添加更多通用 fixtures

```python
# 1. 添加响应验证 helper
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

# 2. 添加带演员的资源创建快捷方式
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

# 3. 添加带类别的资源创建快捷方式
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

# 4. 添加批量创建资源的 fixture
@pytest.fixture
def bulk_resources(resource_factory):
    """批量创建资源"""
    def _create(count, **defaults):
        resources = []
        for i in range(count):
            kwargs = defaults.copy()
            if 'avid' not in kwargs:
                kwargs['avid'] = f"TEST-{i+1:03d}"
            if 'original_title' not in kwargs:
                kwargs['original_title'] = f"测试作品{i+1}"
            resources.append(resource_factory(**kwargs))
        return resources
    return _create

# 5. 添加 Django test client fixture（用于渐进式迁移）
@pytest.fixture
def client(db):
    """返回 Django test client"""
    from django.test import Client
    return Client()
```

### Phase 2: 重构高优先级测试文件

#### 2.1 重构 test_actors_api.py

**重构前的问题：**
- 使用 Django TestCase
- 手动 setUp 创建测试数据
- 使用 self.client 而非 fixture

**重构方案：**
```python
"""
演员 API 测试（已重构）

使用 pytest + fixtures 进行测试
"""
import pytest


@pytest.fixture
def setup_actors_with_resources(actor_factory, resource_factory):
    """创建测试用的演员和资源数据"""
    # 创建演员
    alice = actor_factory(name="Alice")
    bob = actor_factory(name="Bob")

    # 创建资源并关联演员
    r1 = resource_factory(avid="ACT-1", original_title="With Alice", source="S1", file_exists=True)
    r1.actors.add(alice)

    r2 = resource_factory(avid="ACT-2", original_title="With Bob", source="S1", file_exists=False)
    r2.actors.add(bob)

    r3 = resource_factory(avid="ACT-3", original_title="Alice and Bob", source="S2", file_exists=True)
    r3.actors.add(alice, bob)

    return {"alice": alice, "bob": bob}


@pytest.mark.django_db
def test_actor_filter_by_name(api_client, setup_actors_with_resources):
    """测试按演员名称过滤资源"""
    resp = api_client.get("/nassav/api/resources/", {"actor": "Alice"})
    assert resp.status_code == 200

    body = resp.json()
    assert body["code"] == 200

    items = body["data"]
    found_alice = any(
        "Alice" in (item.get("original_title") or "")
        or "Alice" in (item.get("source_title") or "")
        or "Alice" in (item.get("translated_title") or "")
        for item in items
    )
    assert found_alice


@pytest.mark.django_db
def test_actor_filter_by_id(api_client, setup_actors_with_resources):
    """测试按演员 ID 过滤资源"""
    alice = setup_actors_with_resources["alice"]
    resp = api_client.get("/nassav/api/resources/", {"actor": str(alice.id)})

    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert len(body["data"]) >= 2  # Alice 应该有至少 2 个资源


@pytest.mark.django_db
def test_actors_list_api(api_client, setup_actors_with_resources):
    """测试演员列表 API"""
    resp = api_client.get("/nassav/api/actors/", {"page_size": 10, "page": 1})
    assert resp.status_code == 200

    body = resp.json()
    assert body["code"] == 200
    assert isinstance(body["data"], list)

    for item in body["data"]:
        assert "resource_count" in item
```

#### 2.2 重构 test_genres_api.py

**重构策略：类似 test_actors_api.py**
- 将 setUp 逻辑转换为 `setup_genres_with_resources` fixture
- 将所有 `self.assertEqual` 改为 `assert`
- 使用 `api_client` fixture 替代 `self.client`

#### 2.3 重构 test_resources_list.py

**重构策略：**
- 将 setUp 逻辑转换为 fixture
- 可以直接使用 `bulk_resources` fixture（如果添加到 conftest）

#### 2.4 重构 test_views_resource.py

**重构要点：**
- 使用 `api_client` fixture
- 使用 `tmp_path` fixture（pytest 内置）替代手动 tempfile 管理

#### 2.5 重构 test_serializers.py

**重构要点：**
- 将 setUp 逻辑转换为 fixture
- 使用 factory fixtures 创建测试数据

### Phase 3: 重构中优先级文件

#### 3.1 重构 test_genres_filtering.py

**将独立脚本转换为标准 pytest 测试：**
```python
"""
测试类别 API 过滤功能（已重构为 pytest）

验证 GET /api/genres/ 接口是否正确过滤掉未使用的类别
"""
import pytest
from django.db.models import Count
from nassav.models import Genre


@pytest.fixture
def setup_used_and_unused_genres(genre_factory, resource_factory):
    """创建已使用和未使用的类别"""
    # 创建使用中的类别
    used_genre = genre_factory(name="使用中类别")
    resource = resource_factory(avid="TEST-001")
    resource.genres.add(used_genre)

    # 创建未使用的类别
    unused_genre = genre_factory(name="未使用类别")

    return {
        "used": used_genre,
        "unused": unused_genre,
        "used_count": 1,
        "unused_count": 1,
    }


@pytest.mark.django_db
def test_genres_list_excludes_unused(api_client, setup_used_and_unused_genres):
    """测试类别列表 API 过滤掉未使用的类别"""
    response = api_client.get("/nassav/api/genres/", {"page_size": 1000})
    assert response.status_code == 200

    data = response.json()
    assert data["code"] == 200

    # 检查返回的类别中没有 resource_count = 0 的
    unused_in_api = [g for g in data["data"] if g["resource_count"] == 0]
    assert len(unused_in_api) == 0, "API 中不应该有未使用的类别"

    # 验证使用中的类别存在
    genre_names = [g["name"] for g in data["data"]]
    assert "使用中类别" in genre_names


@pytest.mark.django_db
def test_genres_by_id_allows_unused(api_client, setup_used_and_unused_genres):
    """测试使用 ID 查询可以返回未使用的类别"""
    unused_genre = setup_used_and_unused_genres["unused"]

    response = api_client.get("/nassav/api/genres/", {"id": unused_genre.id})
    assert response.status_code == 200

    data = response.json()
    assert data["pagination"]["total"] == 1
    assert data["data"][0]["name"] == "未使用类别"
```

#### 3.2 为 test_user_settings.py 添加专用 fixtures

```python
# 在 conftest.py 中添加
@pytest.fixture
def user_settings_manager():
    """用户设置管理器 fixture"""
    from nassav.user_settings import UserSettings
    return UserSettings()

@pytest.fixture
def reset_user_settings(user_settings_manager):
    """测试前后重置用户设置"""
    # 测试前保存原始设置
    original = user_settings_manager.get_all()
    yield user_settings_manager
    # 测试后恢复
    for key, value in original.items():
        user_settings_manager.set(key, value)
```

### Phase 4: 低优先级文件优化

#### 4.1 test_actor_avatar_extraction.py
- 保持纯单元测试的特性
- 添加更多边界测试用例

#### 4.2 test_javbus_actor_parsing.py
- 考虑将 HTML 文件加载逻辑抽取为 fixture
```python
@pytest.fixture
def javbus_html_content():
    """加载 Javbus HTML 测试文件"""
    html_path = Path(__file__).parent.parent / "JUR-448.html"
    if not html_path.exists():
        pytest.skip("JUR-448.html 文件不存在")
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()
```

#### 4.3 test_translator.py
- 保持独立脚本形式（用于手动测试）
- 考虑添加基于 mock 的自动化测试版本

---

## 四、实施步骤建议

### 第 1 步：完善 conftest.py（1-2 小时）
- [ ] 添加 `assert_api_response` fixture
- [ ] 添加 `resource_with_actors` fixture
- [ ] 添加 `resource_with_genres` fixture
- [ ] 添加 `bulk_resources` fixture
- [ ] 添加 `client` fixture（用于渐进式迁移）
- [ ] 添加用户设置相关的 fixtures

### 第 2 步：重构高优先级文件（3-4 小时）
- [ ] 重构 `test_actors_api.py`
- [ ] 重构 `test_genres_api.py`
- [ ] 重构 `test_resources_list.py`
- [ ] 重构 `test_views_resource.py`
- [ ] 重构 `test_serializers.py`

### 第 3 步：重构中优先级文件（2-3 小时）
- [ ] 重构 `test_genres_filtering.py`
- [ ] 增强 `test_user_settings.py`

### 第 4 步：优化低优先级文件（1-2 小时）
- [ ] 优化 `test_javbus_actor_parsing.py`
- [ ] 为 `test_translator.py` 添加 mock 版本

### 第 5 步：整理和文档（1 小时）
- [ ] 更新 tests/README.md
- [ ] 确保所有测试通过
- [ ] 移除不再使用的测试文件或脚本

---

## 五、预期收益

### 代码质量提升
1. **减少代码重复：** 预计减少 40-50% 的测试代码行数
2. **提高可维护性：** 集中管理测试数据创建逻辑
3. **统一测试风格：** 全部使用 pytest 风格，告别 Django TestCase

### 开发效率提升
1. **更快的测试编写：** 使用 fixtures 可以快速组合测试场景
2. **更好的测试隔离：** 每个测试自动清理数据库
3. **更灵活的测试组合：** pytest 的 fixture 系统支持灵活组合

### 测试可读性提升
1. **更清晰的测试意图：** fixture 名称明确表达测试需求
2. **更少的样板代码：** 不再需要 setUp/tearDown
3. **更好的错误信息：** pytest 提供更详细的断言失败信息

---

## 六、风险和注意事项

### 风险
1. **测试行为变化：** Django TestCase 的事务处理与 pytest-django 略有不同
2. **依赖变更：** 需要确保 pytest-django 正确配置
3. **学习成本：** 团队需要熟悉 pytest fixtures 概念

### 缓解措施
1. **渐进式迁移：** 一次重构一个文件，确保测试仍然通过
2. **保留原文件：** 重构前创建备份或新分支
3. **充分测试：** 重构后运行完整测试套件确保功能不变

### 配置检查
确保 `pytest.ini` 配置正确：
```ini
[pytest]
DJANGO_SETTINGS_MODULE = django_project.settings
python_files = tests.py test_*.py *_tests.py
python_classes = Test*
python_functions = test_*
addopts =
    --reuse-db
    --verbose
    --strict-markers
markers =
    django_db: mark test as requiring database access
```

---

## 七、总结

### 核心改进
1. **统一使用 pytest + fixtures** 替代 Django TestCase
2. **集中管理测试数据创建** 在 conftest.py 中
3. **消除重复代码** 通过可复用的 fixtures
4. **标准化测试结构** 提升代码一致性

### 推荐实施顺序
1. ✅ Phase 1: 增强 conftest.py
2. ⭐ Phase 2: 重构高优先级文件（最大收益）
3. Phase 3: 重构中优先级文件
4. Phase 4: 优化低优先级文件（可选）

### 成功标准
- [ ] 所有测试使用 pytest 风格
- [ ] 测试代码行数减少至少 30%
- [ ] 没有重复的测试数据创建逻辑
- [ ] 所有测试通过且行为不变
- [ ] 测试执行时间不增加（或略有减少）
