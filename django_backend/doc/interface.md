# 接口文档（概要）

本文档为工程提供简明接口说明，包含新增的预览、缩略图、批量与条件请求支持，便于前端对接与自动化测试。

说明：所有 API 使用统一 envelope 响应格式：

```json
{ "code": <number>, "message": "...", "data": <any>, "pagination"?: {...} }
```

HTTP 状态码仍与语义保持一致（200/201/404/500 等），`code` 为项目内业务码（0/200 表示成功，其他为错误或非标准语义，组件应基于 `code` 与 `message` 做友好提示）。

---

## 获取用户设置

- 方法：GET
- 路径：`/nassav/api/setting`
- 功能：获取用户前端显示配置
- 返回示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "enable_avatar": "true",
    "display_title": "source_title",
    "search_result_display_style": "grid"
  }
}
```

**配置项说明**：

- `enable_avatar`: 是否显示演员头像（`"true"` 或 `"false"`）
- `display_title`: 前端显示哪个标题字段
  - `"original_title"`: 显示原始日语标题
  - `"source_title"`: 显示下载源标题（默认）
  - `"translated_title"`: 显示翻译后的中文标题
- `search_result_display_style`: 推荐页搜索结果展示样式
  - `"grid"`: 标准网格布局（默认）
  - `"masonry"`: 两列瀑布流布局

**配置文件自动重载**：

- 配置存储在 `config/user_settings.ini` 文件中
- 系统会自动检测配置文件的修改时间
- 当检测到文件被外部修改时，会自动重新加载配置
- 这确保了即使手动编辑配置文件，API 也能返回最新的设置

---

## 更新用户设置

- 方法：PUT
- 路径：`/nassav/api/setting`
- 功能：更新用户前端显示配置
- 请求 Body（支持部分更新）：
  - `enable_avatar`: `"true"` 或 `"false"`（可选）
  - `display_title`: `"original_title"` | `"source_title"` | `"translated_title"`（可选）
  - `search_result_display_style`: `"grid"` | `"masonry"`（可选）

示例请求：

```json
PUT /nassav/api/setting
{
  "enable_avatar": "false",
  "display_title": "translated_title",
  "search_result_display_style": "masonry"
}
```

返回示例：

```json
{
  "code": 200,
  "message": "设置已更新",
  "data": {
    "enable_avatar": "false",
    "display_title": "translated_title",
    "search_result_display_style": "masonry"
  }
}
```

错误响应示例（无效值）：

```json
{
  "code": 400,
  "message": "参数验证失败",
  "data": {
    "display_title": ["display_title 必须是 original_title, source_title, translated_title 之一"]
  }
}
```

---

## 获取可用下载源列表

- 方法：GET
- 路径：`/nassav/api/source/list`
- 功能：返回所有可用的下载源名称列表
- 返回示例：

```json
{
  "code": 200,
  "message": "success",
  "data": ["missav", "javbus", "javdb"]
}
```

---

## 获取源 Cookie 列表

- 方法：GET
- 路径：`/nassav/api/source/cookie`
- 功能：获取所有已设置的源 Cookie 配置列表
- 返回字段：
  - `source`: 源名称
  - `cookie`: Cookie 内容
  - `mtime`: 最后更新时间（ISO 8601 格式）

返回示例：

```json
{
  "code": 200,
  "message": "success",
  "data": [
    {
      "source": "missav",
      "cookie": "user_uuid=...; remember_web_...",
      "mtime": "2026-01-03T12:16:13.547333+08:00"
    },
    {
      "source": "jable",
      "cookie": "PHPSESSID=...",
      "mtime": "2026-01-02T20:52:00.122665+08:00"
    }
  ]
}
```

---

## 设置源 Cookie

- 方法：POST
- 路径：`/nassav/api/source/cookie`
- 功能：为指定源设置 Cookie（手动设置或自动获取）
- 请求 Body：
  - `source`: 源名称（必填）
  - `cookie`: 手动设置的 cookie 字符串（可选）
  - `auto`: 是否自动获取 cookie（boolean，可选）

示例请求：

```json
// 手动设置 Cookie
POST /nassav/api/source/cookie
{
  "source": "missav",
  "cookie": "your-cookie-string"
}

// 自动获取 Cookie
POST /nassav/api/source/cookie
{
  "source": "missav",
  "cookie": "auto"
}
```

返回示例：

```json
{
  "code": 200,
  "message": "Cookie 设置成功",
  "data": {
    "source": "missav",
    "cookie_set": true
  }
}
```

---

## 清除源 Cookie

- 方法：DELETE
- 路径：`/nassav/api/source/cookie`
- 参数：
  - `source`: 源名称（必填，Query 参数）
- 功能：清除指定源的 Cookie（设为空字符串）

示例请求：

```json
DELETE /nassav/api/source/cookie?source=missav
```

返回示例：

```json
{
  "code": 200,
  "message": "Cookie 已清除",
  "data": {
    "source": "missav",
    "cookie_set": false
  }
}
```

---

## 推荐系统接口

推荐系统的完整设计、分层职责与调用流程见：

- [`recommendation.md`](./recommendation.md)

当前推荐接口为 demo 级实现，主要基于本地库中高频演员/类别与 Jable 搜索结果做轻量召回和排序。

### 获取推荐结果

- 方法：GET
- 路径：`/nassav/api/recommendations/`
- 功能：统一推荐入口
- 支持 Query 参数：
  - `recommender`：推荐器标识，默认 `jable_search`
  - `strategy`：推荐策略标识，默认 `local_preference`
  - `limit`：返回数量，默认 `12`
  - `per_seed_limit`：每个 seed 的召回上限，默认 `12`
  - `actor_seed_limit`：演员种子数量，默认 `5`
  - `genre_seed_limit`：类别种子数量，默认 `5`
  - `exclude_existing`：是否过滤本地已存在资源，默认 `true`
  - `avoid_recent_recommendations`：是否尽量避开最近同配置已经推荐过的结果，默认 `true`
  - `recent_snapshot_limit`：回看最近多少次同配置推荐，默认 `3`
  - `recent_item_limit`：最多读取多少条历史推荐 `avid`，默认 `36`

示例请求：

```json
GET /nassav/api/recommendations/?recommender=jable_search&strategy=local_preference&limit=12&exclude_existing=true
```

返回示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "items": [
      {
        "avid": "ABC-123",
        "title": "Result Title",
        "detail_url": "https://jable.tv/videos/abc-123/",
        "cover_url": "https://assets-cdn.jable.tv/...",
        "source": "Jable",
        "snapshot_id": 12,
        "score": 8.5,
        "reasons": ["命中高频actor: Alice"],
        "raw_metrics": {
          "views": 123456,
          "likes": 789,
          "duration": "01:55:12"
        }
      }
    ],
    "seeds": [
      {
        "seed_type": "actor",
        "value": "Alice",
        "weight": 5.0,
        "source": "local_top_actor",
        "resource_count": 12
      }
    ],
    "summary": {
      "seed_count": 1,
      "item_count": 1
    },
    "meta": {
      "recommender": "jable_search",
      "strategy": "local_preference",
      "snapshot_id": 12,
      "request_fingerprint": "e6fd...",
      "recommender_detail": {
        "id": "jable_search",
        "name": "Jable Search",
        "description": "通过 Jable 搜索页召回候选资源。"
      },
      "strategy_detail": {
        "id": "local_preference",
        "name": "Local Preference",
        "description": "基于本地高频演员与类别的 Jable 搜索推荐 demo。"
      },
      "effective_request": {
        "limit": 12,
        "per_seed_limit": 12,
        "actor_seed_limit": 5,
        "genre_seed_limit": 5,
        "seed_types": ["actor", "genre"],
        "exclude_existing": true,
        "random_seed": 123456789,
        "avoid_recent_recommendations": true,
        "recent_snapshot_limit": 3,
        "recent_item_limit": 36
      },
      "history_context": {
        "recently_recommended_count": 12,
        "recent_history_candidate_count": 18,
        "filtered_history_count": 4
      },
      "learning_context": {
        "feedback_count": 6,
        "learned_avid_count": 4,
        "learned_seed_count": 7
      }
    }
  }
}
```

### 获取推荐器与策略选项

- 方法：GET
- 路径：`/nassav/api/recommendations/options`
- 功能：返回可用推荐器、策略和默认值，供前端动态渲染选择区

### 提交推荐反馈

- 方法：POST
- 路径：`/nassav/api/recommendations/feedback`
- 功能：记录当前推荐结果的显式反馈，并将其纳入后续推荐学习信号
- 请求体：
  - `snapshot_id`：该推荐项所属快照 ID
  - `avid`：推荐项资源编号
  - `feedback`：`like | dislike | clear`

示例请求：

```json
POST /nassav/api/recommendations/feedback
{
  "snapshot_id": 12,
  "avid": "ABC-123",
  "feedback": "like"
}
```

返回示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "snapshot_id": 12,
    "avid": "ABC-123",
    "feedback": "like",
    "feedback_value": 1
  }
}
```

### 获取推荐封面代理缓存

- 方法：GET
- 路径：`/nassav/api/recommendations/cover`
- Query 参数：
  - `url`：原始推荐封面地址
- 功能：后端代理并缓存推荐封面，避免前端直接访问受限站点资源

### 兼容 demo 接口

- 方法：GET
- 路径：`/nassav/api/recommendations/demo`
- 功能：兼容旧的 demo 调用方式，当前内部仍走统一 `RecommenderManager`

---

## 资源列表（服务端过滤/搜索/排序/分页）

- 方法：GET
- 路径：`/nassav/api/resources/`
- 支持 Query 参数：
  - `status`：`downloaded|pending|all`（等同于 file_exists）
  - `watched`：`true|false`（按观看状态过滤）
  - `is_favorite`：`true|false`（按收藏状态过滤）
  - `sort_by`：`avid|metadata_create_time|metadata_update_time|video_create_time|source`
  - `order`：`asc|desc`
  - `page`、`page_size`
  - `source`：逗号分隔的源列表
  - `actor`：按演员过滤，可传演员 ID（精确匹配）或名称（模糊匹配）
  - `genre`：按类别过滤，可传类别 ID（精确匹配）或名称（模糊匹配）

示例请求：

```json
GET /nassav/api/resources/?status=pending&sort_by=metadata_create_time&order=desc&page=1&page_size=18
GET /nassav/api/resources/?watched=true                       # 已观看的资源
GET /nassav/api/resources/?is_favorite=true                   # 已收藏的资源
GET /nassav/api/resources/?actor=1                           # 按演员 ID 过滤
GET /nassav/api/resources/?actor=桥本                         # 按演员名称模糊匹配
GET /nassav/api/resources/?genre=中文字幕                      # 按类别名称模糊匹配
GET /nassav/api/resources/?actor=1&genre=2&status=downloaded  # 组合过滤
```

返回：`data` 为数组（资源摘要），响应内含 `pagination` 字段：

```json
{
  "code": 200,
  "message": "success",
  "data": [
    {
      "avid": "ABC-123",
      "original_title": "日语原标题",
      "source_title": "下载源标题",
      "translated_title": "中文翻译标题",
      "source": "missav",
      "release_date": "2025-01-01",
      "has_video": true,
      "watched": false,
      "is_favorite": true,
      "metadata_create_time": 1704067200,
      "metadata_update_time": 1704070800,
      "video_create_time": 1704070800,
      "genres": ["类别1", "类别2"],
      "thumbnail_url": "/nassav/api/resource/cover?avid=ABC-123&size=medium&v=1704067200"
    }
  ],
  "pagination": { "total": 120, "page": 1, "page_size": 18, "pages": 7 }
}
```

**标题字段说明**：

- `original_title`: Scraper（Javbus）获取的原始标题，通常为日语
- `source_title`: 下载源（MissAV/Jable 等）提供的标题
- `translated_title`: 由翻译器生成的中文标题
- 前端可根据需要选择显示哪个标题，或按优先级回退

---

## 演员列表（聚合统计）

- 方法：GET
- 路径：`/nassav/api/actors/`
- 功能：返回所有演员及其作品数统计，支持分页、搜索和排序（包含头像信息）
- 支持 Query 参数：
  - `page`、`page_size`：分页参数（默认 page=1, page_size=20）
  - `order_by`：排序字段，`count`（作品数）或 `name`（演员名称），默认 `count`
  - `order`：排序方向，`asc`（升序）或 `desc`（降序），默认 `desc`
  - `search`：搜索关键词，模糊匹配演员名称
  - `id`：演员 ID，精确查询单个演员信息

示例请求：

```json
GET /nassav/api/actors/?page=1&page_size=20&order_by=count&order=desc
GET /nassav/api/actors/?search=桥本
GET /nassav/api/actors/?id=1
GET /nassav/api/actors/?order_by=name&order=asc
```

返回示例：

```json
{
  "code": 200,
  "message": "success",
  "data": [
    {
      "id": 1,
      "name": "桥本有菜",
      "resource_count": 85,
      "avatar_url": "https://www.javbus.com/pics/actress/abc_a.jpg",
      "avatar_filename": "abc_a.jpg"
    },
    {
      "id": 2,
      "name": "三上悠亚",
      "resource_count": 72,
      "avatar_url": "https://www.javbus.com/pics/actress/xyz_a.jpg",
      "avatar_filename": "xyz_a.jpg"
    }
  ],
  "pagination": {
    "total": 200,
    "page": 1,
    "page_size": 20,
    "pages": 10
  }
}
```

**说明**：

- `avatar_url`：演员头像原始URL（来自Javbus）
- `avatar_filename`：头像文件名（仅文件名，不含路径）
- 头像URL和文件名可能为 `null`（演员无头像或尚未刮削）

---

## 演员头像图片

- 方法：GET
- 路径：`/nassav/api/actors/<actor_id>/avatar`
- 功能：直接返回演员头像图片（JPEG格式）
- 路径参数：
  - `actor_id`：演员ID（整数）

示例请求：

```json
GET /nassav/api/actors/1/avatar
```

返回：

- HTTP 200：返回图片文件（Content-Type: image/jpeg）
- HTTP 404：演员不存在或无头像

使用示例：

```html
<img src="/nassav/api/actors/1/avatar" alt="演员头像" />
```

---

## 类别列表（聚合统计）

- 方法：GET
- 路径：`/nassav/api/genres/`
- 功能：返回所有类别及其作品数统计，支持分页、搜索和排序
- 支持 Query 参数：
  - `page`、`page_size`：分页参数（默认 page=1, page_size=20）
  - `order_by`：排序字段，`count`（作品数）或 `name`（类别名称），默认 `count`
  - `order`：排序方向，`asc`（升序）或 `desc`（降序），默认 `desc`
  - `search`：搜索关键词，模糊匹配类别名称
  - `id`：类别 ID，精确查询单个类别信息

示例请求：

```json
GET /nassav/api/genres/?page=1&page_size=20&order_by=count&order=desc
GET /nassav/api/genres/?search=中文
GET /nassav/api/genres/?id=1
GET /nassav/api/genres/?order_by=name&order=asc
```

返回示例：

```json
{
  "code": 200,
  "message": "success",
  "data": [
    { "id": 1, "name": "中文字幕", "resource_count": 150 },
    { "id": 2, "name": "人妻", "resource_count": 120 }
  ],
  "pagination": {
    "total": 50,
    "page": 1,
    "page_size": 20,
    "pages": 3
  }
}
```

---

## 资源详情预览（首屏）

- 方法：GET
- 路径：`/nassav/api/resource/{avid}/preview`
- 返回：`{ metadata, thumbnail_url }`，用于详情页首屏快速渲染。

示例：

```json
GET /nassav/api/resource/ABC-123/preview
```

返回（示例）：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "metadata": {
      "avid": "ABC-123",
      "original_title": "日语原标题",
      "source_title": "下载源标题",
      "translated_title": "中文翻译标题",
      "source": "missav",
      ...
    },
    "thumbnail_url": "/nassav/api/resource/cover?avid=ABC-123&size=small&v=1681234567"
  }
}
```

- 备注：`v` 参数为封面文件的 mtime（用于强缓存失效），前端可直接将 `thumbnail_url` 作为 `<img src>`。

---

## 资源元数据详情

- 方法：GET
- 路径：`/nassav/api/resource/metadata?avid=<AVID>`
- 功能：获取资源完整元数据（演员、类别、时长等）
- 说明：
  - 返回三个标题字段：`original_title`（日语）、`source_title`（下载源）、`translated_title`（中文）
  - 若需要 m3u8 链接，请使用刷新接口获取
- 支持条件请求（ETag/Last-Modified），返回 304 节省带宽

返回字段：`avid`, `original_title`, `source_title`, `translated_title`, `source`, `release_date`, `duration`, `director`, `studio`, `label`, `series`, `actors[]`, `genres[]`, `file_exists`, `file_size`, `watched`, `is_favorite`

---

## 封面与缩略图

- 方法：GET
- 路径：`/nassav/api/resource/cover?avid=<AVID>[&size=small|medium|large][&v=hash]`

行为：

- 无 `size` 时返回原始封面文件（若存在）；有 `size` 时返回对应尺寸的缩略图，路径为 `resource/cover/thumbnails/{size}/{AVID}.jpg`。
- 若缩略图不存在，后端会按需生成并返回（best-effort）。
- 响应包含 `Cache-Control: public, max-age=31536000` 及 `ETag` 与 `Last-Modified`，支持条件请求头返回 `304`。

示例：

```json
<img src="/nassav/api/resource/cover?avid=ABC-123&size=small" />
```

条件请求示例：

```json
If-None-Match: "etag-value"
If-Modified-Since: Wed, 21 Oct 2015 07:28:00 GMT
```

若匹配，后端返回 `304 Not Modified`（无 body），浏览器/客户端使用缓存数据。

---

## 获取视频文件路径

- 方法：GET
- 路径：`/nassav/api/downloads/abspath?avid=<AVID>`
- 功能：返回视频文件的绝对路径，前面拼接 config.UrlPrefix 作为前缀
- 返回示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "abspath": "http://your-server/path/to/video/ABC-123.mp4"
  }
}
```

---

## 任务队列状态

- 方法：GET
- 路径：`/nassav/api/tasks/queue/status`
- 功能：获取当前任务队列状态（包括所有 PENDING 和 STARTED 状态的任务）
- 返回示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "pending": [
      {
        "task_id": "abc123...",
        "avid": "ABC-123",
        "task_type": "download",
        "status": "PENDING"
      }
    ],
    "active": [
      {
        "task_id": "def456...",
        "avid": "DEF-456",
        "task_type": "download",
        "status": "STARTED",
        "progress": 45.2
      }
    ],
    "total_pending": 10,
    "total_active": 2
  }
}
```

---

## 单项操作返回最新对象

- 新增资源：`POST /nassav/api/resource`（body: {avid, source?}）
  - 返回 `data.resource`：精简资源对象，仅包含以下字段：
    - `avid`: 视频编号
    - `original_title`: 原始标题（来自 Scraper，如 JavBus）
    - `source_title`: 源标题（来自下载源网站，如 Jable/MissAV）
    - `translated_title`: 翻译后的标题
    - `source`: 来源网站名称
  - 返回示例：

    ```json
    {
      "code": 201,
      "message": "success",
      "data": {
        "resource": {
          "avid": "ABC-123",
          "original_title": "テストタイトル",
          "source_title": "ABC-123 Test Title",
          "translated_title": "测试标题",
          "source": "Jable"
        },
        "cover_downloaded": true,
        "metadata_saved": true,
        "scraped": true
      }
    }
    ```

  - 资源已存在时（409）也返回相同格式的精简资源对象

- 刷新资源：`POST /nassav/api/resource/refresh/{avid}`
  - 返回 `data.resource`：刷新后的资源对象
  - **支持细粒度刷新参数**（Body JSON，可选）：
    - `refresh_m3u8`: 是否刷新 m3u8 链接（默认 `true`）
    - `refresh_metadata`: 是否刷新元数据（从 source 重新抓取，默认 `true`）
    - `retranslate`: 是否重新翻译标题（默认 `false`）
  - 示例：

    ```json
    // 只刷新 m3u8 链接
    POST /nassav/api/resource/refresh/ABC-123
    {"refresh_m3u8": true, "refresh_metadata": false, "retranslate": false}

    // 只重新翻译
    POST /nassav/api/resource/refresh/ABC-123
    {"refresh_m3u8": false, "refresh_metadata": false, "retranslate": true}

    // 刷新元数据并重新翻译（注意：会先刷新元数据获取新标题，再执行翻译）
    POST /nassav/api/resource/refresh/ABC-123
    {"refresh_metadata": true, "retranslate": true}
    ```

  - 响应包含：
    - `resource`: 更新后的资源对象
    - `metadata_refreshed`: 是否刷新了元数据
    - `m3u8_refreshed`: 是否刷新了 m3u8
    - `translation_queued`: 是否已提交翻译任务（异步）
    - `cover_downloaded`, `metadata_saved`, `scraped`: 保存结果

- 删除资源：`DELETE /nassav/api/resource/{avid}`
  - 返回 `data.resource`（删除前序列化对象）和 `deleted_files`

- 下载视频：`POST /nassav/api/downloads/{avid}`
  - 功能：提交视频下载任务（异步，使用 Celery）
  - 前提：资源元数据必须已存在
  - 返回示例：

    ```json
    {
      "code": 202,
      "message": "下载任务已提交",
      "data": {
        "avid": "ABC-123",
        "task_id": "celery-task-id",
        "status": "pending"
      }
    }
    ```

  - 如果视频已下载，返回 `code: 409, message: "视频已下载"`
  - 如果任务已存在，返回 `code: 409, message: "下载任务已存在"`

- 删除视频：`DELETE /nassav/api/downloads/{avid}`
  - 功能：删除已下载的视频文件
  - 返回示例：

    ```json
    {
      "code": 200,
      "message": "success",
      "data": {
        "avid": "ABC-123",
        "deleted_file": "ABC-123.mp4",
        "file_size": 1234567890
      }
    }
    ```

前端应在收到 `resource` 对象后做局部合并更新，而非整页刷新。

---

## 批量接口

1. 批量资源操作

- 方法：POST
- 路径：`/nassav/api/resources/batch`
- Body 示例：

```json
{
  "actions": [
    { "action": "add", "avid": "ABC-123", "source": "any" },
    { "action": "refresh", "avid": "DEF-222" },
    { "action": "delete-video", "avid": "XYZ-001" },
    { "action": "delete-all", "avid": "OLD-999" }
  ]
}
```

- 返回：`data.results` 为数组，每项包含 `action, avid, code, message, resource?, deleted_files?, deleted_file?, file_size?`。

**操作说明**：

- `add`：添加资源
  - 如果资源已存在，返回 `code: 200, message: "already exists"` 和现有资源数据
  - 如果资源不存在，从指定 source 获取并创建，返回 `code: 201, message: "created"`
  - 如果获取失败，返回 `code: 404, message: "获取信息失败"`
- `refresh`：刷新资源
  - **支持细粒度刷新参数**（可选，默认全部刷新）：
    - `refresh_m3u8`: 是否刷新 m3u8 链接（默认 `true`）
    - `refresh_metadata`: 是否刷新元数据（默认 `true`）
    - `retranslate`: 是否重新翻译（默认 `false`）
  - 示例：

    ```json
    {
      "actions": [
        { "action": "refresh", "avid": "ABC-123", "refresh_m3u8": true, "refresh_metadata": false },
        { "action": "refresh", "avid": "DEF-456", "retranslate": true }
      ]
    }
    ```

  - 返回 `code: 200, message: "refreshed"`，`refresh_info` 包含操作结果，以及更新后的资源数据

- `delete-video`：只删除视频文件（保留元数据）
  - 返回 `code: 200, message: "视频已删除"`，包含 `deleted_file` 和 `file_size`
  - **数据库操作**: 更新记录标记视频不存在（`file_exists=False`）
  - **保留内容**: 元数据记录、封面图片、备份目录
  - 示例返回：

    ```json
    {
      "action": "delete-video",
      "avid": "ABC-123",
      "code": 200,
      "message": "视频已删除",
      "deleted_file": "ABC-123.mp4",
      "file_size": 1234567890
    }
    ```

- `delete-all` 或 `delete`：删除全部数据（视频+元数据+封面+备份）
  - 返回 `code: 200, message: "已删除全部数据"` 和删除前的资源数据
  - **删除内容**: 视频文件、封面图片、备份目录、数据库记录
  - 示例返回：

    ```json
    {
      "action": "delete-all",
      "avid": "ABC-123",
      "code": 200,
      "message": "已删除全部数据",
      "resource": {...},
      "deleted_files": ["ABC-123.jpg", "ABC-123.mp4"]
    }
    ```

1. 批量下载提交

- 方法：POST
- 路径：`/nassav/api/downloads/batch_submit`
- Body：`{ "avids": ["ABC-123","DEF-222"] }`
- 返回：每个 avid 的提交结果（`task_id` 或 409 表示任务已存在）。

前端在处理批量返回时应使用返回的 `resource` 对象做局部合并更新。

---

## 模拟下载（仅 DEBUG 模式）

- 方法：POST
- 路径：`/nassav/api/downloads/mock/{avid}`
- 功能：模拟下载任务，用于测试下载流程（不实际下载视频）
- 仅在 `DEBUG=True` 时可用
- 请求 Body（可选）：

  ```json
  {
    "duration": 30 // 模拟下载持续时间（秒），默认 30，范围 1-300
  }
  ```

- 返回示例：

  ```json
  {
    "code": 202,
    "message": "模拟下载任务已提交",
    "data": {
      "avid": "ABC-123",
      "task_id": "mock-task-id",
      "duration": 30
    }
  }
  ```

---

## 缓存与条件请求（前端要点）

- 对于 metadata/cover/thumbnail，后端会返回 `ETag` 与 `Last-Modified`。
- 浏览器会自动管理条件请求；若使用 `fetch`/`axios` 手动请求，可在请求头中传 `If-None-Match` 或 `If-Modified-Since`，并在收到 `304` 时复用本地缓存。

示例（curl）:

```json
curl -i -H 'If-None-Match: "123abc"' "http://<host>/nassav/api/resource/cover?avid=ABC-123&size=small"
```

---

## 响应 Envelope 约定

- `code`：业务层码，`200`/`0` 表示成功（视端点而定），非 2xx 需参考 `message` 字段并处理错误。
- `message`：可展示的错误/成功信息
- `data`：主载荷（资源数组、单个 resource、results 等）
- `pagination`（可选）：当返回分页集合时包含 `total,page,page_size,pages`。

---

## 示例前端注意事项（简短）

- `fetchResources` 应将 `search,status,sort_by,order,page,page_size,source` 传给后端，直接使用后端返回 `data` 与 `pagination` 渲染。
- 搜索框添加 200–400ms 防抖，减少请求频率。
- 在新增/刷新/批量接口返回 `resource` 时做局部合并更新。
- 图片直接使用 `thumbnail_url` 作为 `img.src`，依赖浏览器自动带条件头，或手动在 axios 中传 `If-None-Match`。

---
