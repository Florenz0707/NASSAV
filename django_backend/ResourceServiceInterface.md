# ResourceService 接口设计文档

## 1. 概述

### 1.1 设计目标

重构 `SourceManager` 的职责，将其拆分为：
- **SourceManager**: 专注于下载源管理（获取 m3u8 + source_title）
- **ResourceService**: 负责完整的资源操作流程（组合各 Manager + 数据库 + 文件操作）

### 1.2 职责定义

**ResourceService 的职责**:
1. ✅ 组合并协调多个 Manager（SourceManager, ScraperManager, M3u8Downloader, TranslatorManager）
2. ✅ 数据库操作（AVResource, Actor, Genre 的 CRUD）
3. ✅ 文件系统操作（封面、头像、缩略图的下载和管理）
4. ✅ 业务流程编排（添加资源、刷新资源、删除资源的完整流程）
5. ✅ 缓存管理（HTML、元数据的缓存加载）

**SourceManager 保留的职责**:
1. ✅ 管理多个下载源（MissAV, Jable, Memo）
2. ✅ 根据 avid 获取 source_title 和 m3u8_url
3. ✅ 按权重排序选择源
4. ✅ Cookie 管理（加载、设置、持久化）

### 1.3 架构图

```
┌─────────────────────────────────────────────────────┐
│                  Django Views                        │
│              (ResourceView, etc.)                    │
└───────────────────┬─────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────┐
│              ResourceService                         │
│  ┌───────────────────────────────────────────────┐  │
│  │ 组合的 Managers:                               │  │
│  │  • SourceManager      (获取 m3u8 + title)     │  │
│  │  • ScraperManager     (刮削 Javbus 元数据)    │  │
│  │  • M3u8Downloader     (下载视频，可选)        │  │
│  │  • TranslatorManager  (AI 翻译标题，可选)     │  │
│  └───────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────┐  │
│  │ 自己的职责:                                    │  │
│  │  • 数据库操作 (AVResource, Actor, Genre)      │  │
│  │  • 文件操作 (封面、头像、缩略图)              │  │
│  │  • 业务流程编排                               │  │
│  │  • 缓存管理                                   │  │
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
                    │
        ┌───────────┼───────────┬──────────────┐
        ▼           ▼           ▼              ▼
  SourceManager  ScraperMgr  M3u8Downloader  TranslatorMgr
```

---

## 2. 类定义

### 2.1 初始化

```python
class ResourceService:
    """资源服务 - 负责完整的资源操作流程"""

    def __init__(
        self,
        source_manager: SourceManager,
        scraper_manager: ScraperManager,
        m3u8_downloader: Optional[M3u8DownloaderBase] = None,
        translator_manager: Optional[TranslatorManager] = None
    ):
        """
        初始化资源服务

        Args:
            source_manager: 下载源管理器（必需）
            scraper_manager: 元数据刮削管理器（必需）
            m3u8_downloader: M3U8下载器（可选，用于视频下载）
            translator_manager: 翻译管理器（可选，用于标题翻译）

        Note:
            - source_manager 和 scraper_manager 是必需的
            - m3u8_downloader 可选，不传入时无法下载视频
            - translator_manager 可选，不传入时跳过翻译任务
        """
        self.source_mgr = source_manager
        self.scraper_mgr = scraper_manager
        self.downloader = m3u8_downloader
        self.translator_mgr = translator_manager
```

---

## 3. 公共接口

### 3.1 add_resource()

**功能**: 添加新资源（完整流程：获取信息 → 刮削元数据 → 下载封面 → 保存数据库 → 提交翻译）

```python
def add_resource(
    self,
    avid: str,
    source: str = "any",
    *,
    enable_scrape: bool = True,
    enable_cover_download: bool = True,
    enable_avatar_download: bool = True,
    enable_translate: bool = True
) -> dict:
    """
    添加新资源到数据库

    工作流程:
        1. 检查资源是否已存在（返回 409）
        2. 从 Source 获取基本信息（m3u8, source_title）
        3. [可选] 从 Scraper 刮削完整元数据（original_title, actors, genres, etc.）
        4. [可选] 下载封面图片到 COVER_DIR
        5. [可选] 下载演员头像到 AVATAR_DIR
        6. 保存到数据库（AVResource, Actor, Genre）
        7. [可选] 提交异步翻译任务（Celery）

    Args:
        avid: 视频编号（如 "ABC-123"）
        source: 指定源名称或 "any"（默认）
            - "any": 按权重优先级尝试所有源（Jable > Memo > MissAV）
            - "missav", "jable", "memo": 指定特定源

        enable_scrape: 是否刮削 Javbus 元数据（默认 True）
            - True: 获取完整元数据（标题、演员、类别、时长、发行日期）
            - False: 只使用 Source 提供的基本信息

        enable_cover_download: 是否下载封面图片（默认 True）
            - True: 优先使用 Javbus 封面，失败时回退到 Source 封面
            - False: 不下载封面

        enable_avatar_download: 是否下载演员头像（默认 True）
            - True: 下载所有演员的头像到 AVATAR_DIR
            - False: 只保存头像 URL，不下载图片

        enable_translate: 是否提交翻译任务（默认 True）
            - True: 提交 Celery 异步翻译任务
            - False: 不翻译，translation_status 保持 "pending"

    Returns:
        dict: 操作结果
        {
            "avid": str,                         # 资源编号
            "resource": dict,                    # 资源对象（序列化后）
            "source": str,                       # 使用的源名称
            "cover_saved": bool,                 # 封面是否下载成功
            "metadata_saved": bool,              # 元数据是否保存成功
            "scraped": bool,                     # 是否成功刮削 Javbus
            "avatar_download_count": int,        # 成功下载的头像数量
            "translate_task_submitted": bool,    # 是否提交翻译任务
            "translate_task_id": str (可选)     # 翻译任务ID（异步模式）
        }

    Raises:
        ResourceAlreadyExistsError: 资源已存在（HTTP 409）
        SourceNotFoundError: 指定的源不存在（HTTP 400）
        ResourceFetchError: 无法从任何源获取资源（HTTP 404/403/502）
            - 404: 所有源都返回 404（资源不存在）
            - 403: 某个源返回 403（需要更新 Cookie）
            - 502: 其他网络错误

    Examples:
        # 1. 基本用法（使用所有默认选项）
        result = resource_service.add_resource("ABC-123")

        # 2. 指定源
        result = resource_service.add_resource("ABC-123", source="missav")

        # 3. 只获取基本信息，不刮削元数据
        result = resource_service.add_resource(
            "ABC-123",
            enable_scrape=False
        )

        # 4. 不下载封面和头像（节省带宽）
        result = resource_service.add_resource(
            "ABC-123",
            enable_cover_download=False,
            enable_avatar_download=False
        )

        # 5. 快速添加（不翻译）
        result = resource_service.add_resource(
            "ABC-123",
            enable_translate=False
        )

    Note:
        - avid 会自动转为大写
        - 如果 source="any" 且所有源都失败，返回包含错误码的字典
        - 封面优先级: Javbus > Source
        - 翻译任务是异步的，不会阻塞主流程
    """
```

---

### 3.2 refresh_resource()

**功能**: 刷新已有资源的元数据和 m3u8 链接

```python
def refresh_resource(
    self,
    avid: str,
    source: Optional[str] = None,
    *,
    refresh_cover: bool = True,
    refresh_avatars: bool = False,
    resubmit_translate: bool = False
) -> dict:
    """
    刷新已有资源的元数据

    工作流程:
        1. 检查资源是否存在（不存在返回 404）
        2. 从 Source 重新获取信息（更新 m3u8, source_title）
        3. 从 Scraper 重新刮削元数据
        4. [可选] 重新下载封面
        5. [可选] 重新下载演员头像
        6. 更新数据库（保留 file_exists, file_size, translated_title）
        7. [可选] 重新提交翻译任务

    Args:
        avid: 视频编号
        source: 指定源名称（可选）
            - None: 使用原有的 source
            - "any": 按权重尝试所有源
            - "missav", "jable", "memo": 指定特定源

        refresh_cover: 是否重新下载封面（默认 True）
            - True: 即使已有封面也重新下载
            - False: 保留现有封面

        refresh_avatars: 是否重新下载演员头像（默认 False）
            - True: 重新下载所有演员头像
            - False: 保留现有头像

        resubmit_translate: 是否重新提交翻译任务（默认 False）
            - True: 即使已翻译也重新提交（覆盖现有翻译）
            - False: 保留现有翻译

    Returns:
        dict: 操作结果（格式同 add_resource）

    Raises:
        ResourceNotFoundError: 资源不存在（HTTP 404）
        SourceNotFoundError: 指定的源不存在（HTTP 400）
        ResourceFetchError: 无法从源获取资源

    Examples:
        # 1. 刷新元数据和 m3u8
        result = resource_service.refresh_resource("ABC-123")

        # 2. 切换到其他源
        result = resource_service.refresh_resource("ABC-123", source="jable")

        # 3. 完全刷新（包括封面和头像）
        result = resource_service.refresh_resource(
            "ABC-123",
            refresh_cover=True,
            refresh_avatars=True
        )

        # 4. 重新翻译
        result = resource_service.refresh_resource(
            "ABC-123",
            resubmit_translate=True
        )

    Note:
        - 刷新操作会保留以下字段：
          * file_exists, file_size（视频文件状态）
          * translated_title（已有翻译，除非 resubmit_translate=True）
          * video_saved_at（视频保存时间）
        - metadata_saved_at 会更新为当前时间
    """
```

---

### 3.3 delete_resource()

**功能**: 删除资源（数据库记录 + 文件）

```python
def delete_resource(
    self,
    avid: str,
    *,
    delete_video: bool = True,
    delete_cover: bool = True,
    delete_avatars: bool = False,
    delete_database: bool = True
) -> dict:
    """
    删除资源

    Args:
        avid: 视频编号
        delete_video: 是否删除视频文件（默认 True）
        delete_cover: 是否删除封面文件（默认 True）
        delete_avatars: 是否删除演员头像（默认 False）
            - 注意：头像可能被多个资源共享
        delete_database: 是否删除数据库记录（默认 True）

    Returns:
        dict: 删除结果
        {
            "avid": str,
            "video_deleted": bool,
            "cover_deleted": bool,
            "avatars_deleted": int,      # 删除的头像数量
            "database_deleted": bool
        }

    Raises:
        ResourceNotFoundError: 资源不存在（HTTP 404）

    Examples:
        # 1. 完全删除
        result = resource_service.delete_resource("ABC-123")

        # 2. 只删除视频文件，保留元数据
        result = resource_service.delete_resource(
            "ABC-123",
            delete_database=False
        )

        # 3. 只删除数据库记录，保留文件
        result = resource_service.delete_resource(
            "ABC-123",
            delete_video=False,
            delete_cover=False
        )
    """
```

---

### 3.4 get_resource()

**功能**: 获取资源信息（仅查询数据库）

```python
def get_resource(self, avid: str) -> Optional[dict]:
    """
    获取资源信息（不触发刮削）

    Args:
        avid: 视频编号

    Returns:
        dict: 资源信息（序列化后），不存在返回 None
        {
            "avid": str,
            "original_title": str,
            "source_title": str,
            "translated_title": str,
            "source": str,
            "release_date": str,
            "duration": int,
            "actors": List[dict],
            "genres": List[dict],
            "m3u8": str,
            "cover_filename": str,
            "file_exists": bool,
            "file_size": int,
            "translation_status": str,
            "metadata_saved_at": str,
            "video_saved_at": str,
            "created_at": str
        }

    Examples:
        resource = resource_service.get_resource("ABC-123")
        if resource:
            print(resource["original_title"])
    """
```

---

### 3.5 load_cached_metadata()

**功能**: 从缓存（数据库）加载元数据

```python
def load_cached_metadata(self, avid: str) -> Optional[AVDownloadInfo]:
    """
    从数据库加载已缓存的元数据

    Args:
        avid: 视频编号

    Returns:
        AVDownloadInfo: 元数据对象，不存在返回 None

    Note:
        - 优先从数据库 AVResource 表加载
        - 返回的是 AVDownloadInfo 对象（兼容现有代码）
        - 用于避免重复请求源网站

    Examples:
        info = resource_service.load_cached_metadata("ABC-123")
        if info:
            print(f"M3U8: {info.m3u8}")
            print(f"Title: {info.title}")
    """
```

---

## 4. 私有方法（内部使用）

### 4.1 数据获取

```python
def _get_info_from_source(
    self,
    avid: str,
    source: str = "any"
) -> Tuple[Optional[AVDownloadInfo], Optional[SourceBase], Optional[str], Dict]:
    """
    从源获取资源信息（委托给 SourceManager）

    Returns:
        (info, source_instance, html, errors)
    """
```

```python
def _scrape_metadata(self, avid: str) -> Optional[dict]:
    """
    刮削 Javbus 元数据（委托给 ScraperManager）

    Returns:
        {
            "title": str,              # 原始标题（日语）
            "release_date": str,
            "duration": str,
            "actors": List[str],
            "actor_avatars": Dict[str, str],  # name -> avatar_url
            "genres": List[str],
            "cover_url": str
        }
    """
```

---

### 4.2 文件操作

```python
def _download_cover(
    self,
    avid: str,
    cover_url: str,
    source: SourceBase,
    use_scraper_download: bool = False
) -> bool:
    """
    下载封面图片

    Args:
        cover_url: 封面 URL
        source: 源实例（用于 Referer）
        use_scraper_download: 是否使用 Scraper 的下载方法（Javbus 封面需要）

    Returns:
        是否下载成功

    Note:
        - 保存到 COVER_DIR/{AVID}.jpg
        - 自动生成缩略图（small/medium/large）
    """
```

```python
def _download_avatars(
    self,
    actor_avatars: Dict[str, str]
) -> int:
    """
    批量下载演员头像

    Args:
        actor_avatars: {actor_name: avatar_url}

    Returns:
        成功下载的数量

    Note:
        - 保存到 AVATAR_DIR/{filename}
        - 文件名从 URL 提取（如 305_a.jpg）
        - 如果文件已存在，跳过下载
    """
```

```python
def _generate_thumbnails(self, avid: str) -> None:
    """
    生成缩略图（small/medium/large）

    Note:
        - 保存到 COVER_DIR/thumbnails/{size}/{AVID}.jpg
        - 尺寸: small=200px, medium=600px, large=1200px
    """
```

```python
def _delete_files(
    self,
    avid: str,
    delete_video: bool,
    delete_cover: bool
) -> Tuple[bool, bool]:
    """
    删除资源文件

    Returns:
        (video_deleted, cover_deleted)
    """
```

---

### 4.3 数据库操作

```python
def _save_to_database(
    self,
    avid: str,
    info: AVDownloadInfo,
    source_name: str,
    is_refresh: bool = False
) -> AVResource:
    """
    保存/更新资源到数据库

    Args:
        is_refresh: 是否为刷新操作（保留某些字段）

    Returns:
        AVResource 实例

    Note:
        - 新增时设置 translation_status="pending", file_exists=False
        - 刷新时保留 file_exists, file_size, translated_title
        - 自动创建/关联 Actor 和 Genre
    """
```

```python
def _save_actors(
    self,
    resource: AVResource,
    actors: List[str],
    actor_avatars: Dict[str, str]
) -> None:
    """
    保存演员信息

    Note:
        - 自动创建不存在的演员
        - 更新演员头像 URL 和 filename
    """
```

```python
def _save_genres(
    self,
    resource: AVResource,
    genres: List[str]
) -> None:
    """
    保存类别信息

    Note:
        - 自动创建不存在的类别
    """
```

---

### 4.4 异步任务

```python
def _submit_translate_task(
    self,
    avid: str,
    async_mode: bool = True
) -> Tuple[Optional[str], bool]:
    """
    提交翻译任务

    Args:
        async_mode: 是否异步执行

    Returns:
        (task_id, is_async)
        - task_id: Celery 任务ID（异步模式）
        - is_async: 是否为异步执行
    """
```

---

## 5. 异常定义

```python
class ResourceServiceError(Exception):
    """资源服务基础异常"""
    pass

class ResourceAlreadyExistsError(ResourceServiceError):
    """资源已存在（HTTP 409）"""
    def __init__(self, avid: str):
        self.avid = avid
        super().__init__(f"Resource {avid} already exists")

class ResourceNotFoundError(ResourceServiceError):
    """资源不存在（HTTP 404）"""
    def __init__(self, avid: str):
        self.avid = avid
        super().__init__(f"Resource {avid} not found")

class SourceNotFoundError(ResourceServiceError):
    """指定的源不存在（HTTP 400）"""
    def __init__(self, source: str, available_sources: List[str]):
        self.source = source
        self.available_sources = available_sources
        super().__init__(
            f"Source {source} not found. Available: {', '.join(available_sources)}"
        )

class ResourceFetchError(ResourceServiceError):
    """无法从源获取资源（HTTP 404/403/502）"""
    def __init__(self, avid: str, errors: Dict[str, int]):
        self.avid = avid
        self.errors = errors
        self.http_code = self._determine_http_code(errors)
        super().__init__(
            f"Failed to fetch {avid}: {', '.join(f'{k}:{v}' for k, v in errors.items())}"
        )

    def _determine_http_code(self, errors: Dict[str, int]) -> int:
        """根据错误码确定 HTTP 状态码"""
        if any(code == 403 for code in errors.values()):
            return 403
        elif all(code == 404 for code in errors.values()):
            return 404
        else:
            return 502
```

---

## 6. 模块级单例

```python
# nassav/services/resource_service.py

# 在文件末尾创建全局实例
resource_service = ResourceService(
    source_manager=source_manager,
    scraper_manager=ScraperManager(
        proxy=settings.PROXY_URL if settings.PROXY_ENABLED else None
    ),
    m3u8_downloader=N_m3u8DL_RE(
        proxy=settings.PROXY_URL if settings.PROXY_ENABLED else None
    ),
    translator_manager=TranslatorManager()
)
```

```python
# nassav/services/__init__.py

from .resource_service import ResourceService, resource_service
from .video_download_service import VideoDownloadService, video_download_service

__all__ = [
    "ResourceService",
    "resource_service",
    "VideoDownloadService",
    "video_download_service"
]
```

---

## 7. 使用示例

### 7.1 在 Views 中使用

```python
# nassav/views.py

from nassav.services import resource_service
from nassav.services.resource_service import (
    ResourceAlreadyExistsError,
    ResourceNotFoundError,
    SourceNotFoundError,
    ResourceFetchError
)

class ResourceView(APIView):
    """POST /api/resource"""

    def post(self, request):
        serializer = NewResourceSerializer(data=request.data)
        if not serializer.is_valid():
            return build_response(400, "参数错误", serializer.errors)

        avid = serializer.validated_data["avid"].upper()
        source = serializer.validated_data.get("source", "any").lower()

        try:
            # 🎯 核心调用
            result = resource_service.add_resource(avid, source)

            return build_response(201, "success", result)

        except ResourceAlreadyExistsError as e:
            # 资源已存在
            existing = resource_service.get_resource(avid)
            return build_response(409, "资源已存在", existing)

        except SourceNotFoundError as e:
            # 指定的源不存在
            return build_response(400, str(e), {
                "available_sources": e.available_sources
            })

        except ResourceFetchError as e:
            # 无法从源获取资源
            return build_response(e.http_code, str(e), None)

        except Exception as e:
            logger.exception(f"添加资源失败: {avid}")
            return build_response(500, f"服务器错误: {str(e)}", None)
```

### 7.2 刷新资源

```python
class RefreshResourceView(APIView):
    """POST /api/resource/refresh/{avid}"""

    def post(self, request, avid):
        source = request.data.get("source")

        try:
            result = resource_service.refresh_resource(avid, source)
            return build_response(200, "success", result)

        except ResourceNotFoundError:
            return build_response(404, f"资源 {avid} 不存在", None)

        except ResourceFetchError as e:
            return build_response(e.http_code, str(e), None)
```

### 7.3 删除资源

```python
class ResourceDeleteView(APIView):
    """DELETE /api/resource/{avid}"""

    def delete(self, request, avid):
        try:
            result = resource_service.delete_resource(avid)
            return build_response(200, "删除成功", result)

        except ResourceNotFoundError:
            return build_response(404, f"资源 {avid} 不存在", None)
```

---

## 8. 测试策略

### 8.1 单元测试（Mock）

```python
# tests/test_resource_service.py

import pytest
from unittest.mock import Mock, patch
from nassav.services import ResourceService

@pytest.fixture
def mock_managers():
    """Mock 所有依赖的 Manager"""
    return {
        "source_mgr": Mock(),
        "scraper_mgr": Mock(),
        "downloader": Mock(),
        "translator_mgr": Mock()
    }

def test_add_resource_success(mock_managers):
    """测试成功添加资源"""
    service = ResourceService(**mock_managers)

    # Mock 返回值
    mock_managers["source_mgr"].get_info_from_any_source.return_value = (
        Mock(m3u8="https://example.com/video.m3u8", title="Test"),
        Mock(get_source_name=lambda: "missav"),
        "<html>...</html>",
        {}
    )
    mock_managers["scraper_mgr"].scrape.return_value = {
        "title": "テスト",
        "actors": ["Actor A"],
        "genres": ["HD"]
    }

    result = service.add_resource("TEST-001")

    assert result["avid"] == "TEST-001"
    assert result["metadata_saved"] == True
    mock_managers["source_mgr"].get_info_from_any_source.assert_called_once()

def test_add_resource_already_exists(mock_managers):
    """测试添加已存在的资源"""
    service = ResourceService(**mock_managers)

    with patch("nassav.models.AVResource.objects.filter") as mock_filter:
        mock_filter.return_value.first.return_value = Mock(avid="TEST-001")

        with pytest.raises(ResourceAlreadyExistsError):
            service.add_resource("TEST-001")
```

### 8.2 集成测试（真实网络）

```python
# tests/test_integration.py

import pytest
from nassav.services import resource_service

@pytest.mark.integration
def test_add_resource_real_network():
    """测试真实网络请求"""
    # 使用已知存在的 AVID
    avid = "SSIS-001"

    # 清理测试数据
    AVResource.objects.filter(avid=avid).delete()

    # 执行添加
    result = resource_service.add_resource(avid, source="missav")

    # 验证结果
    assert result["avid"] == avid
    assert result["metadata_saved"] == True
    assert result["cover_saved"] == True

    # 验证数据库
    resource = AVResource.objects.get(avid=avid)
    assert resource.original_title
    assert resource.m3u8

    # 验证文件
    cover_path = Path(settings.COVER_DIR) / f"{avid}.jpg"
    assert cover_path.exists()
```

---

## 9. 与现有代码的对比

### 9.1 代码量对比

| 指标 | 现有 SourceManager | ResourceService |
|------|-------------------|-----------------|
| 总行数 | 541 行 | ~400-500 行（预估） |
| save_all_resources | 260 行 | 拆分为多个私有方法 |
| 数据库操作 | 混杂在 save_all_resources | 独立的 _save_to_database |
| 文件操作 | 混杂在 save_all_resources | 独立的 _download_cover 等 |
| 职责清晰度 | ❌ 混杂多种职责 | ✅ 单一职责 |

### 9.2 调用方式对比

**现有方式**:
```python
# views.py
info, source_inst, html, errors = source_manager.get_info_from_any_source(avid)
if not info:
    return build_response(404, "获取失败", None)

save_result = source_manager.save_all_resources(avid, info, source_inst, html)
resource_obj = AVResource.objects.filter(avid=avid).first()

return build_response(201, "success", {
    "resource": serialize(resource_obj),
    **save_result
})
```

**新方式**:
```python
# views.py
try:
    result = resource_service.add_resource(avid, source)
    return build_response(201, "success", result)
except ResourceFetchError as e:
    return build_response(e.http_code, str(e), None)
```

**改进点**:
- ✅ 简化调用（一行完成所有操作）
- ✅ 明确的异常处理
- ✅ 返回格式统一
- ✅ 职责分离（Views 不再直接操作数据库）

---

## 10. 迁移检查清单

### 10.1 Phase 1: 实现 ResourceService
- [ ] 创建 `nassav/services/resource_service.py`
- [ ] 实现 `ResourceService` 类
- [ ] 实现 `add_resource()` 方法
- [ ] 实现 `refresh_resource()` 方法
- [ ] 实现 `delete_resource()` 方法
- [ ] 实现所有私有方法
- [ ] 定义异常类
- [ ] 创建模块级单例

### 10.2 Phase 2: 单元测试
- [ ] 创建 `tests/test_resource_service.py`
- [ ] 测试 `add_resource()` 成功场景
- [ ] 测试 `add_resource()` 异常场景
- [ ] 测试 `refresh_resource()`
- [ ] 测试 `delete_resource()`
- [ ] 测试私有方法（可选）
- [ ] 覆盖率 > 80%

### 10.3 Phase 3: Views 迁移
- [ ] 修改 `ResourceView.post()` (第 815-932 行)
- [ ] 修改 `RefreshResourceView.post()` (第 1057-1108 行)
- [ ] 修改 `BatchOperationView.post()` (第 1309-1649 行)
- [ ] 修改其他 15 处调用点
- [ ] 更新导入语句
- [ ] 更新异常处理

### 10.4 Phase 4: 清理 SourceManager
- [ ] 删除 `save_all_resources()` 方法
- [ ] 删除 `load_cached_metadata()` 方法
- [ ] 删除 `__init__` 中的 `scraper` 初始化
- [ ] 更新类注释

### 10.5 Phase 5: 集成测试
- [ ] 运行完整测试套件：`uv run pytest tests/ -v`
- [ ] 测试所有 API 端点
- [ ] 测试真实网络请求
- [ ] 测试并发场景

### 10.6 Phase 6: 文档更新
- [ ] 更新 `doc/interface.md`
- [ ] 更新 `AGENT.md`（补充 ResourceService 说明）
- [ ] 更新代码注释
- [ ] 添加类型提示

---

## 11. 后续优化方向

### 11.1 异步接口支持
```python
class ResourceService:
    async def add_resource_async(self, avid: str, source: str = "any") -> dict:
        """异步版本（ASGI 优化）"""
        from asgiref.sync import sync_to_async

        # 使用 Django async ORM
        existing = await AVResource.objects.filter(avid=avid).afirst()
        if existing:
            raise ResourceAlreadyExistsError(avid)

        # ... 其他异步操作
```

### 11.2 缓存优化
```python
from django.core.cache import cache

def add_resource(self, avid: str, source: str = "any") -> dict:
    # 检查缓存
    cache_key = f"resource:{avid}"
    cached = cache.get(cache_key)
    if cached:
        raise ResourceAlreadyExistsError(avid)

    # ... 添加资源

    # 更新缓存
    cache.set(cache_key, result, timeout=3600)
```

### 11.3 批量操作优化
```python
def add_resources_batch(
    self,
    avids: List[str],
    source: str = "any"
) -> List[dict]:
    """批量添加资源（并行处理）"""
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [
            executor.submit(self.add_resource, avid, source)
            for avid in avids
        ]
        results = [f.result() for f in futures]

    return results
```

---

## 12. 总结

### 12.1 核心改进
1. ✅ **职责分离**: SourceManager 专注源管理，ResourceService 负责业务流程
2. ✅ **接口简化**: 一行代码完成完整操作
3. ✅ **异常明确**: 使用自定义异常替代返回码判断
4. ✅ **易于测试**: 依赖注入，方便 Mock
5. ✅ **易于扩展**: 新增功能只需修改 ResourceService

### 12.2 预期收益
- **代码可读性**: ⬆️ 50%
- **维护成本**: ⬇️ 40%
- **测试覆盖率**: ⬆️ 30%
- **开发效率**: ⬆️ 30%

### 12.3 风险控制
- ✅ 分阶段实施，降低风险
- ✅ 完整单元测试，保证质量
- ✅ 集成测试验证，确保功能
- ✅ 文档同步更新，便于维护
