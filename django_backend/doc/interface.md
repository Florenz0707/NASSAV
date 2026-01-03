# 接口文档（概要）

本文档为工程提供简明接口说明，包含新增的预览、缩略图、批量与条件请求支持，便于前端对接与自动化测试。

说明：所有 API 使用统一 envelope 响应格式：

```
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
    "display_title": "source_title"
  }
}
```

**配置项说明**：
- `enable_avatar`: 是否显示演员头像（`"true"` 或 `"false"`）
- `display_title`: 前端显示哪个标题字段
  - `"original_title"`: 显示原始日语标题
  - `"source_title"`: 显示下载源标题（默认）
  - `"translated_title"`: 显示翻译后的中文标题

---

## 更新用户设置

- 方法：PUT
- 路径：`/nassav/api/setting`
- 功能：更新用户前端显示配置
- 请求 Body（支持部分更新）：
  - `enable_avatar`: `"true"` 或 `"false"`（可选）
  - `display_title`: `"original_title"` | `"source_title"` | `"translated_title"`（可选）

示例请求：
```json
PUT /nassav/api/setting
{
  "enable_avatar": "false",
  "display_title": "translated_title"
}
```

返回示例：
```json
{
  "code": 200,
  "message": "设置已更新",
  "data": {
    "enable_avatar": "false",
    "display_title": "translated_title"
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
```
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

## 资源列表（服务端过滤/搜索/排序/分页）

- 方法：GET
- 路径：`/nassav/api/resources/`
- 支持 Query 参数：
  - `search`：按 `avid` 或各标题字段模糊匹配（case-insensitive）
  - `status`：`downloaded|pending|all`（等同于 file_exists）
  - `sort_by`：`avid|metadata_create_time|video_create_time|source`
  - `order`：`asc|desc`
  - `page`、`page_size`
  - `source`：逗号分隔的源列表
  - `actor`：按演员过滤，可传演员 ID（精确匹配）或名称（模糊匹配）
  - `genre`：按类别过滤，可传类别 ID（精确匹配）或名称（模糊匹配）

示例请求：
```
GET /nassav/api/resources/?search=abc&status=pending&sort_by=metadata_create_time&order=desc&page=1&page_size=18
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
      "metadata_create_time": 1704067200,
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
```
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
```
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
```
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
    {"id": 1, "name": "中文字幕", "resource_count": 150},
    {"id": 2, "name": "人妻", "resource_count": 120}
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
```
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

返回字段：`avid`, `original_title`, `source_title`, `translated_title`, `source`, `release_date`, `duration`, `director`, `studio`, `label`, `series`, `actors[]`, `genres[]`, `file_exists`, `file_size`

---

## 封面与缩略图

- 方法：GET
- 路径：`/nassav/api/resource/cover?avid=<AVID>[&size=small|medium|large][&v=hash]`

行为：
- 无 `size` 时返回原始封面文件（若存在）；有 `size` 时返回对应尺寸的缩略图，路径为 `resource/cover/thumbnails/{size}/{AVID}.jpg`。
- 若缩略图不存在，后端会按需生成并返回（best-effort）。
- 响应包含 `Cache-Control: public, max-age=31536000` 及 `ETag` 与 `Last-Modified`，支持条件请求头返回 `304`。

示例：
```
<img src="/nassav/api/resource/cover?avid=ABC-123&size=small" />
```

条件请求示例：
```
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
  - 返回 `data.resource`：新增后的完整资源对象（可直接合并到列表或详情）

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

1) 批量资源操作
- 方法：POST
- 路径：`/nassav/api/resources/batch`
- Body 示例：
```
{
  "actions": [
    {"action":"add","avid":"ABC-123","source":"any"},
    {"action":"refresh","avid":"DEF-222"},
    {"action":"delete","avid":"OLD-001"}
  ]
}
```
- 返回：`data.results` 为数组，每项包含 `action, avid, code, message, resource?, deleted_files?`。

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
        {"action": "refresh", "avid": "ABC-123", "refresh_m3u8": true, "refresh_metadata": false},
        {"action": "refresh", "avid": "DEF-456", "retranslate": true}
      ]
    }
    ```
  - 返回 `code: 200, message: "refreshed"`，`refresh_info` 包含操作结果，以及更新后的资源数据
- `delete`：删除资源
  - 返回 `code: 200, message: "deleted"` 和删除前的资源数据

2) 批量下载提交
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
    "duration": 30  // 模拟下载持续时间（秒），默认 30，范围 1-300
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
```
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
