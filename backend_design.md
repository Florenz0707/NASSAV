# 后端架构设计模式分析报告

## 目录

1. [项目概述](#项目概述)
2. [架构层次](#架构层次)
3. [核心设计模式](#核心设计模式)
4. [模块分析](#模块分析)
5. [设计原则](#设计原则)
6. [优势与改进建议](#优势与改进建议)

---

## 项目概述

NASSAV 是一个基于 Django 的 AV 资源管理系统，采用模块化架构设计，通过多个可插拔的组件实现资源的获取、刮削、翻译和下载功能。

### 技术栈

- **框架**: Django 4.x
- **异步任务**: Celery
- **数据库**: SQLite (支持迁移到其他数据库)
- **日志**: Loguru
- **HTTP 客户端**: curl_cffi

### 核心功能模块

1. **Source (下载源)**: 从视频网站获取 M3U8 流地址和基本信息
2. **Scraper (刮削器)**: 从元数据网站获取详细信息（演员、类型、发行日期等）
3. **Translator (翻译器)**: 翻译日文标题为中文
4. **M3u8Downloader (下载器)**: 下载 M3U8 视频流
5. **ResourceService (资源服务)**: 编排上述组件完成完整业务流程

---

## 架构层次

项目采用经典的分层架构，各层职责清晰：

```
┌─────────────────────────────────────────┐
│         Presentation Layer              │
│    (views.py, urls.py, consumers.py)    │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│          Service Layer                  │
│  (resource_service.py, services.py)     │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│         Business Logic Layer            │
│  (SourceManager, ScraperManager, etc.)  │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│          Data Access Layer              │
│         (models.py, ORM)                │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│           Database Layer                │
│            (SQLite/PostgreSQL)          │
└─────────────────────────────────────────┘
```

### 层次说明

1. **表现层 (Presentation Layer)**
   - 处理 HTTP 请求和 WebSocket 连接
   - 数据序列化和验证
   - 路由配置

2. **服务层 (Service Layer)**
   - 编排业务流程
   - 协调多个管理器完成复杂操作
   - 异常处理和错误传播

3. **业务逻辑层 (Business Logic Layer)**
   - 实现具体业务逻辑
   - 管理多个策略实现
   - 提供统一接口

4. **数据访问层 (Data Access Layer)**
   - ORM 模型定义
   - 数据库查询和操作

---

## 核心设计模式

### 1. 模板方法模式 (Template Method Pattern)

**应用位置**: 所有基类（SourceBase, ScraperBase, TranslatorBase, M3u8DownloaderBase）

**实现方式**:
- 基类定义算法骨架和抽象方法
- 子类实现具体步骤

**示例**:

```python
# SourceBase.py
class SourceBase:
    def get_source_name(self) -> str:
        raise NotImplementedError  # 抽象方法

    def get_html(self, avid: str) -> Optional[str]:
        raise NotImplementedError  # 抽象方法

    def parse_html(self, html: str) -> Optional[AVDownloadInfo]:
        raise NotImplementedError  # 抽象方法

    def fetch_html(self, url: str, referer: str = "") -> Optional[str]:
        # 模板方法：提供通用实现
        # 子类可以直接使用，无需重写
        ...
```

**优势**:
- 代码复用：通用逻辑（如 HTTP 请求、错误处理）在基类实现
- 扩展性强：新增源只需继承基类并实现抽象方法
- 一致性：所有实现遵循相同接口

**实际应用**:
- `MissAV`, `Jable`, `Memo` 继承 `SourceBase`
- `Javbus`, `Busdmm`, `Dmmsee` 继承 `ScraperBase`
- `OllamaTranslator` 继承 `TranslatorBase`

---

### 2. 策略模式 (Strategy Pattern)

**应用位置**: Source、Scraper、Translator、M3u8Downloader 模块

**实现方式**:
- 定义统一接口（基类）
- 多个具体实现（子类）
- 运行时动态选择策略

**示例**:

```python
# 不同的下载源策略
SOURCE_CLASSES = {
    "missav": MissAV,
    "jable": Jable,
    "memo": Memo
}

# 根据配置选择策略
for source_name, source_class in self.SOURCE_CLASSES.items():
    config = source_config.get(source_name, {})
    if config.get("weight"):
        source = source_class(proxy)
        self.sources[source.get_source_name()] = source
```

**优势**:
- 灵活切换：可根据配置启用/禁用不同策略
- 易于扩展：新增策略无需修改现有代码
- 解耦：策略实现与使用者分离

---

### 3. 管理器/注册表模式 (Manager/Registry Pattern)

**应用位置**: SourceManager, ScraperManager, TranslatorManager

**实现方式**:
- Manager 类维护所有可用实现的注册表
- 提供统一接口访问和管理多个实现
- 支持优先级排序和轮询机制

**示例**:

```python
class SourceManager:
    SOURCE_CLASSES = {"missav": MissAV, "jable": Jable, "memo": Memo}

    def __init__(self):
        self.sources: Dict[str, SourceBase] = {}
        # 根据配置注册源
        for source_name, source_class in self.SOURCE_CLASSES.items():
            config = source_config.get(source_name, {})
            if config.get("weight"):
                source = source_class(proxy)
                self.sources[source.get_source_name()] = source

    def get_sorted_sources(self) -> List[Tuple[str, SourceBase]]:
        # 按权重排序返回
        ...
```

**优势**:
- 集中管理：统一管理所有实现
- 配置驱动：通过配置文件控制行为
- 容错机制：支持轮询多个实现直到成功

---

### 4. 依赖注入模式 (Dependency Injection Pattern)

**应用位置**: ResourceService, VideoDownloadService

**实现方式**:
- 通过构造函数注入依赖
- 避免硬编码依赖关系
- 便于测试和替换实现

**示例**:

```python
class ResourceService:
    def __init__(
        self,
        source_manager: SourceManager,
        scraper_manager: ScraperManager,
        translator_manager: TranslatorManager,
    ):
        self.source_manager = source_manager
        self.scraper_manager = scraper_manager
        self.translator_manager = translator_manager
```

**优势**:
- 可测试性：可注入 Mock 对象进行单元测试
- 松耦合：服务不依赖具体实现
- 灵活性：可轻松替换依赖实现

**文件位置**: `resource_service.py:94-100`

---

### 5. 单例模式 (Singleton Pattern)

**应用位置**: 全局管理器实例

**实现方式**:
- 模块级全局变量
- 延迟初始化（Lazy Initialization）

**示例**:

```python
# SourceManager.py
source_manager = SourceManager()

# ScraperManager.py
scraper_manager = ScraperManager(proxy)

# TranslatorManager.py
_translator_manager_instance: Optional[TranslatorManager] = None

def get_translator_manager() -> TranslatorManager:
    global _translator_manager_instance
    if _translator_manager_instance is None:
        _translator_manager_instance = TranslatorManager()
    return _translator_manager_instance
```

**优势**:
- 资源共享：避免重复创建管理器实例
- 状态一致：全局共享同一状态（如已加载的 Cookie）
- 性能优化：减少初始化开销

**注意事项**:
- Python 模块级变量天然是单例
- TranslatorManager 使用函数实现延迟初始化

---

### 6. 服务层模式 (Service Layer Pattern)

**应用位置**: ResourceService, VideoDownloadService

**实现方式**:
- 封装业务流程编排逻辑
- 协调多个管理器完成复杂操作
- 提供高层次的业务接口

**示例**:

```python
class ResourceService:
    def add_resource(self, avid: str, source: str = "any") -> dict:
        # 1. 检查资源是否已存在
        # 2. 从源获取信息
        # 3. 刮削元数据
        # 4. 保存到数据库
        # 5. 提交翻译任务
        # 6. 返回结果
        ...
```

**优势**:
- 业务逻辑集中：避免在视图层堆积业务代码
- 可复用：服务可被多个视图或任务调用
- 事务管理：统一处理数据库事务

**文件位置**: `resource_service.py:84-100`

---

### 7. 责任链模式 (Chain of Responsibility Pattern)

**应用位置**: Manager 类的轮询机制

**实现方式**:
- 按优先级尝试多个处理器
- 第一个成功的处理器返回结果
- 所有失败则返回 None

**示例**:

```python
def get_info_from_any_source(self, avid: str):
    for name, source in self.get_sorted_sources():
        html = source.get_html(avid)
        if html:
            info = source.parse_html(html)
            if info:
                return info, source, html, errors
    return None, None, None, errors
```

**优势**:
- 容错性：单个源失败不影响整体
- 灵活性：可动态调整优先级
- 可扩展：新增源自动加入责任链

**文件位置**: `SourceManager.py:123-164`

---

### 8. 外观模式 (Facade Pattern)

**应用位置**: Manager 类作为子系统的外观

**实现方式**:
- Manager 类封装复杂的子系统交互
- 提供简化的高层接口
- 隐藏内部实现细节

**示例**:

```python
class TranslatorManager:
    def translate(self, text: str, ...) -> Optional[str]:
        # 1. 预处理固定词汇
        # 2. 轮询所有翻译器
        # 3. 后处理结果
        # 4. 返回翻译结果
        # 外部调用者无需了解内部复杂逻辑
        ...
```

**优势**:
- 简化接口：外部只需调用一个方法
- 解耦：客户端不依赖具体翻译器实现
- 易用性：降低使用复杂度

---

### 9. 自定义异常层次 (Custom Exception Hierarchy)

**应用位置**: ResourceService 异常体系

**实现方式**:
- 定义基础异常类
- 派生具体异常类型
- 携带上下文信息

**示例**:

```python
class ResourceServiceException(Exception):
    """基础异常"""
    pass

class ResourceAlreadyExistsError(ResourceServiceException):
    """资源已存在 (409)"""
    def __init__(self, avid: str, resource_data: dict):
        self.avid = avid
        self.resource_data = resource_data

class ResourceNotFoundError(ResourceServiceException):
    """资源未找到 (404)"""
    def __init__(self, avid: str, errors: dict):
        self.avid = avid
        self.errors = errors
```

**优势**:
- 精确错误处理：可针对不同异常类型采取不同措施
- 上下文信息：异常携带详细错误信息
- HTTP 映射：异常类型对应 HTTP 状态码

**文件位置**: `resource_service.py:31-77`

---

### 10. 仓储模式 (Repository Pattern)

**应用位置**: Django ORM 模型

**实现方式**:
- 使用 Django ORM 作为数据访问抽象层
- 模型类封装数据库操作
- 支持复杂查询和关系映射

**示例**:

```python
class AVResource(models.Model):
    avid = models.CharField(max_length=50, unique=True, db_index=True)
    actors = models.ManyToManyField(Actor, blank=True)
    genres = models.ManyToManyField(Genre, blank=True)

    class Meta:
        db_table = "nassav_avresource"
        ordering = ["-metadata_updated_at"]
```

**优势**:
- 数据库无关：可轻松切换数据库
- 类型安全：模型提供类型检查
- 关系映射：自动处理多对多关系

---

## 模块分析

### Source 模块

**目录结构**:
```
nassav/source/
├── __init__.py
├── SourceBase.py      # 基类
├── SourceManager.py   # 管理器
├── MissAV.py          # MissAV 实现
├── Jable.py           # Jable 实现
└── Memo.py            # Memo 实现
```

**职责**:
- 从视频网站获取 M3U8 流地址
- 提供 AVID 和标题
- 提供封面图片 URL

**设计特点**:
1. **职责单一**: 只负责获取下载信息，不处理元数据
2. **Cookie 管理**: 支持自动获取和数据库持久化
3. **权重排序**: 根据配置权重决定尝试顺序
4. **错误追踪**: 记录 HTTP 状态码便于调试

**关键方法**:
- `get_html(avid)`: 获取页面 HTML
- `parse_html(html)`: 解析 HTML 提取信息
- `set_cookie_auto()`: 自动获取 Cookie

---

### Scraper 模块

**目录结构**:
```
nassav/scraper/
├── __init__.py
├── ScraperBase.py       # 基类
├── ScraperManager.py    # 管理器
├── AVDownloadInfo.py    # 数据类
└── Javbus.py            # Javbus/Busdmm/Dmmsee 实现
```

**职责**:
- 从元数据网站获取详细信息
- 提供演员、类型、发行日期、时长等
- 下载封面和演员头像

**设计特点**:
1. **元数据专注**: 只负责元数据，不处理视频流
2. **多站点支持**: 支持 Javbus、Busdmm、Dmmsee
3. **图片下载**: 统一处理封面和头像下载
4. **Referer 处理**: 正确设置 Referer 头避免 403

**关键方法**:
- `scrape(avid)`: 刮削元数据
- `download_cover(url, path)`: 下载封面
- `download_avatar(url, path)`: 下载头像

---

### Translator 模块

**目录结构**:
```
nassav/translator/
├── __init__.py
├── TranslatorBase.py      # 基类（ABC）
├── TranslatorManager.py   # 管理器
└── OllamaTranslator.py    # Ollama 实现
```

**职责**:
- 翻译日文标题为中文
- 支持批量翻译
- 固定词汇预处理

**设计特点**:
1. **ABC 基类**: 使用 Python ABC 强制子类实现接口
2. **重试机制**: 内置重试逻辑提高成功率
3. **固定词汇**: 预处理固定翻译词汇保证一致性
4. **可用性检查**: 启动时检查服务是否可用

**关键方法**:
- `translate(text)`: 翻译文本
- `translate_with_retry()`: 带重试的翻译
- `batch_translate(texts)`: 批量翻译

---

### M3u8Downloader 模块

**目录结构**:
```
nassav/m3u8downloader/
├── __init__.py
├── M3u8DownloaderBase.py  # 基类（ABC）
└── N_m3u8DL_RE.py         # N_m3u8DL-RE 实现
```

**职责**:
- 下载 M3U8 视频流
- 合并分片为完整视频
- 提供下载进度回调

**设计特点**:
1. **进程调用**: 调用外部命令行工具
2. **进度解析**: 解析输出提供实时进度
3. **格式处理**: 自动处理不同输出格式

---

### ResourceService 模块

**文件**: `resource_service.py`

**职责**:
- 编排完整的资源操作流程
- 协调 SourceManager、ScraperManager、TranslatorManager
- 处理数据库操作和文件管理
- 异常处理和错误传播

**核心流程**:

```
add_resource(avid)
    ↓
检查资源是否已存在
    ↓
从 Source 获取下载信息
    ↓
从 Scraper 刮削元数据
    ↓
保存到数据库 (AVResource, Actor, Genre)
    ↓
下载封面和头像
    ↓
提交翻译任务 (Celery)
    ↓
返回结果
```

**设计特点**:

1. **依赖注入**: 通过构造函数注入所有依赖
   ```python
   def __init__(
       self,
       source_manager: SourceManager,
       scraper_manager: ScraperManager,
       translator_manager: TranslatorManager,
   ):
   ```

2. **异常驱动**: 使用自定义异常传播错误
   - `ResourceAlreadyExistsError` (409)
   - `ResourceNotFoundError` (404)
   - `ResourceAccessDeniedError` (403)
   - `ResourceFetchError` (502)

3. **事务管理**: 数据库操作使用事务保证一致性

4. **文件管理**: 统一处理封面、头像、缩略图、HTML 缓存

**关键方法**:
- `add_resource(avid, source)`: 添加资源
- `refresh_metadata(avid, source)`: 刷新元数据
- `load_cached_metadata(avid)`: 加载缓存元数据
- `_save_to_database(info, metadata)`: 保存到数据库

---

## 设计原则

### 1. 单一职责原则 (Single Responsibility Principle)

**体现**:
- **Source**: 只负责获取下载信息，不处理元数据
- **Scraper**: 只负责元数据，不处理视频流
- **Translator**: 只负责翻译，不处理其他逻辑
- **ResourceService**: 只负责流程编排，不实现具体业务

**优势**: 模块职责清晰，易于维护和测试

---

### 2. 开闭原则 (Open/Closed Principle)

**体现**:
- 通过继承扩展功能，无需修改基类
- 新增 Source/Scraper/Translator 只需实现基类接口
- Manager 类通过配置注册新实现

**示例**:
```python
# 新增一个下载源，无需修改现有代码
class NewSource(SourceBase):
    def get_source_name(self) -> str:
        return "NewSource"

    def get_html(self, avid: str) -> Optional[str]:
        # 实现具体逻辑
        ...
```

---

### 3. 里氏替换原则 (Liskov Substitution Principle)

**体现**:
- 所有子类可以替换基类使用
- Manager 类统一处理所有实现，不关心具体类型
- 接口契约一致

**示例**:
```python
# Manager 不关心具体实现，只依赖基类接口
for name, source in self.get_sorted_sources():
    html = source.get_html(avid)  # 多态调用
    if html:
        info = source.parse_html(html)
```

---

### 4. 依赖倒置原则 (Dependency Inversion Principle)

**体现**:
- 高层模块 (ResourceService) 依赖抽象 (Manager)
- 低层模块 (具体实现) 依赖抽象 (Base 类)
- 通过依赖注入解耦

**示例**:
```python
# ResourceService 依赖抽象的 Manager，不依赖具体实现
class ResourceService:
    def __init__(
        self,
        source_manager: SourceManager,  # 抽象依赖
        scraper_manager: ScraperManager,
        translator_manager: TranslatorManager,
    ):
        ...
```

---

### 5. 接口隔离原则 (Interface Segregation Principle)

**体现**:
- 基类接口精简，只定义必要方法
- 子类只需实现相关方法
- 避免臃肿接口

**示例**:
```python
# TranslatorBase 只定义翻译相关接口
class TranslatorBase(ABC):
    @abstractmethod
    def get_translator_name(self) -> str: ...

    @abstractmethod
    def translate(self, text: str, ...) -> Optional[str]: ...

    @abstractmethod
    def is_available(self) -> bool: ...
```

---

### 6. 最少知识原则 (Law of Demeter)

**体现**:
- 模块只与直接依赖交互
- 避免链式调用
- 通过 Manager 封装复杂交互

**示例**:
```python
# 不直接访问 source.some_internal_method()
# 而是通过 Manager 提供的接口
info, source, html, errors = self.source_manager.get_info_from_any_source(avid)
```

---

## 优势与改进建议

### 架构优势

#### 1. 高度模块化
- **优势**: 各模块职责清晰，相互独立
- **体现**: Source、Scraper、Translator、Downloader 完全解耦
- **效果**: 可独立开发、测试、部署

#### 2. 易于扩展
- **优势**: 新增功能无需修改现有代码
- **体现**: 通过继承基类即可新增实现
- **效果**: 支持快速迭代和功能扩展

#### 3. 配置驱动
- **优势**: 行为可通过配置文件控制
- **体现**: 源权重、翻译器选择、域名配置等
- **效果**: 无需修改代码即可调整行为

#### 4. 容错性强
- **优势**: 单点失败不影响整体
- **体现**: 责任链模式轮询多个实现
- **效果**: 提高系统可用性

#### 5. 可测试性好
- **优势**: 依赖注入便于单元测试
- **体现**: 可注入 Mock 对象测试
- **效果**: 提高代码质量

---

### 改进建议

#### 1. 引入接口抽象层

**现状**: 使用基类作为接口，但 Python 缺乏严格的接口检查

**建议**: 使用 `typing.Protocol` 或 `abc.ABC` 定义接口

```python
from typing import Protocol

class ISource(Protocol):
    def get_source_name(self) -> str: ...
    def get_html(self, avid: str) -> Optional[str]: ...
    def parse_html(self, html: str) -> Optional[AVDownloadInfo]: ...
```

**优势**:
- 类型检查更严格
- IDE 支持更好
- 接口契约更明确

---

#### 2. 增强异常处理

**现状**: 异常信息较简单，缺少详细上下文

**建议**: 增强异常信息，添加日志追踪

```python
class ResourceFetchError(ResourceServiceException):
    def __init__(self, avid: str, errors: dict, traceback: str = None):
        self.avid = avid
        self.errors = errors
        self.traceback = traceback
        super().__init__(f"获取{avid}失败: {errors}")
```

**优势**:
- 便于调试和问题定位
- 提供更多上下文信息

---

#### 3. 引入缓存层

**现状**: 每次请求都访问数据库或外部服务

**建议**: 引入 Redis 缓存热点数据

```python
from django.core.cache import cache

def get_info_from_any_source(self, avid: str):
    # 先查缓存
    cache_key = f"source_info:{avid}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    # 缓存未命中，执行原逻辑
    info = self._fetch_from_sources(avid)
    cache.set(cache_key, info, timeout=3600)
    return info
```

**优势**:
- 减少外部请求
- 提高响应速度
- 降低服务压力

---

#### 4. 添加监控和指标

**现状**: 缺少系统运行指标监控

**建议**: 引入 Prometheus + Grafana 监控

```python
from prometheus_client import Counter, Histogram

source_requests = Counter('source_requests_total', 'Total source requests', ['source', 'status'])
source_latency = Histogram('source_request_duration_seconds', 'Source request latency')

@source_latency.time()
def get_html(self, avid: str):
    try:
        result = self._fetch_html(avid)
        source_requests.labels(source=self.get_source_name(), status='success').inc()
        return result
    except Exception as e:
        source_requests.labels(source=self.get_source_name(), status='error').inc()
        raise
```

**优势**:
- 实时监控系统状态
- 快速发现问题
- 数据驱动优化

---

#### 5. 优化数据库查询

**现状**: 可能存在 N+1 查询问题

**建议**: 使用 `select_related` 和 `prefetch_related` 优化

```python
# 优化前
resources = AVResource.objects.all()
for resource in resources:
    print(resource.actors.all())  # N+1 查询

# 优化后
resources = AVResource.objects.prefetch_related('actors', 'genres').all()
for resource in resources:
    print(resource.actors.all())  # 一次查询
```

**优势**:
- 减少数据库查询次数
- 提高列表接口性能

---

#### 6. 引入事件驱动架构

**现状**: 同步处理，耗时操作阻塞请求

**建议**: 使用事件驱动模式解耦

```python
from django.dispatch import Signal

resource_added = Signal()

# 发布事件
resource_added.send(sender=self.__class__, avid=avid, resource=resource)

# 订阅事件
@receiver(resource_added)
def on_resource_added(sender, avid, resource, **kwargs):
    # 异步处理翻译、缩略图生成等
    translate_task.delay(avid)
    generate_thumbnail_task.delay(avid)
```

**优势**:
- 解耦业务逻辑
- 提高响应速度
- 易于扩展新功能

---

#### 7. 完善测试覆盖

**现状**: 缺少系统的单元测试和集成测试

**建议**: 建立完整的测试体系

```python
# 单元测试示例
class TestSourceManager(TestCase):
    def setUp(self):
        self.manager = SourceManager()

    def test_get_sorted_sources(self):
        sources = self.manager.get_sorted_sources()
        self.assertGreater(len(sources), 0)
        # 验证按权重排序
        weights = [config.get('weight', 0) for _, config in sources]
        self.assertEqual(weights, sorted(weights, reverse=True))
```

**优势**:
- 保证代码质量
- 防止回归问题
- 便于重构

---

## 总结

NASSAV 后端架构采用了多种经典设计模式，展现了良好的工程实践：

### 核心优势
1. **模块化设计**: 职责清晰，易于维护
2. **可扩展性**: 支持快速添加新功能
3. **容错性**: 多源轮询提高可用性
4. **可测试性**: 依赖注入便于测试

### 应用的设计模式
- 模板方法模式：定义算法骨架
- 策略模式：支持多种实现
- 管理器模式：集中管理和配置
- 依赖注入：解耦和可测试
- 单例模式：共享全局状态
- 服务层模式：编排业务流程
- 责任链模式：容错和轮询
- 外观模式：简化接口
- 仓储模式：数据访问抽象

### 遵循的设计原则
- 单一职责原则
- 开闭原则
- 里氏替换原则
- 依赖倒置原则
- 接口隔离原则
- 最少知识原则

### 改进方向
1. 引入接口抽象层提高类型安全
2. 增强异常处理和日志追踪
3. 引入缓存层提高性能
4. 添加监控和指标
5. 优化数据库查询
6. 引入事件驱动架构
7. 完善测试覆盖

整体而言，该架构设计合理，代码质量较高，具有良好的可维护性和可扩展性。通过持续优化和改进，可以进一步提升系统的性能和稳定性。

---

**报告生成时间**: 2026-01-21
**分析工具**: Claude Code
**项目版本**: 基于当前 dev 分支
