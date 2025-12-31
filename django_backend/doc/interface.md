# 接口文档（概要）

本文档为工程提供简明接口说明，包含新增的预览、缩略图、批量与条件请求支持，便于前端对接与自动化测试。

说明：所有 API 使用统一 envelope 响应格式：

```
{ "code": <number>, "message": "...", "data": <any>, "pagination"?: {...} }
```

HTTP 状态码仍与语义保持一致（200/201/404/500 等），`code` 为项目内业务码（0/200 表示成功，其他为错误或非标准语义，组件应基于 `code` 与 `message` 做友好提示）。

---

## 资源列表（服务端过滤/搜索/排序/分页）

- 方法：GET
- 路径：`/nassav/api/resources/`
- 支持 Query 参数：
  - `search`：按 `avid` 或 `title` 模糊匹配（case-insensitive）
  - `status`：`downloaded|pending|all`（等同于 file_exists）
  - `sort_by`：`avid|metadata_create_time|video_create_time|source`
  - `order`：`asc|desc`
  - `page`、`page_size`
  - `source`：逗号分隔的源列表

示例请求：
```
GET /nassav/api/resources/?search=abc&status=pending&sort_by=metadata_create_time&order=desc&page=1&page_size=18
```

返回：`data` 为数组（资源摘要），响应内含 `pagination` 字段：

```
{
  "code": 200,
  "message": "success",
  "data": [ {"avid": "ABC-123", "title": "...", ...}, ... ],
  "pagination": { "total": 120, "page": 1, "page_size": 18, "pages": 7 }
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
```
{
  "code": 200,
  "message": "success",
  "data": {
    "metadata": { "avid":"ABC-123", "title":"...", ... },
    "thumbnail_url": "/nassav/api/resource/cover?avid=ABC-123&size=small&v=1681234567"
  }
}
```

- 备注：`v` 参数为封面文件的 mtime（用于强缓存失效），前端可直接将 `thumbnail_url` 作为 `<img src>`。

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

## 单项操作返回最新对象

- 新增资源：`POST /nassav/api/resource`（body: {avid, source?}）
  - 返回 `data.resource`：新增后的完整资源对象（可直接合并到列表或详情）
- 刷新资源：`POST /nassav/api/resource/refresh/{avid}`
  - 返回 `data.resource`：刷新后的资源对象
- 删除资源：`DELETE /nassav/api/resource/{avid}`
  - 返回 `data.resource`（删除前序列化对象）和 `deleted_files`

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

2) 批量下载提交
- 方法：POST
- 路径：`/nassav/api/downloads/batch_submit`
- Body：`{ "avids": ["ABC-123","DEF-222"] }`
- 返回：每个 avid 的提交结果（`task_id` 或 409 表示任务已存在）。

前端在处理批量返回时应使用返回的 `resource` 对象做局部合并更新。

---

## 缓存与条件请求（前端要点）

- 对于 metadata/cover/thumbnail，后端会返回 `ETag` 与 `Last-Modified`。
- 浏览器会自动管理条件请求；若使用 `fetch`/`axios` 手动请求，可在请求头中传 `If-None-Match` 或 `If-Modified-Since`，并在收到 `304` 时复用本地缓存。

示例（curl）:
```
curl -i -H 'If-None-Match: "123abc"' "http://<host>/nassav/api/resource/cover?avid=ABC-123&size=small"
```

---

## 缩略图离线生成脚本

- 路径：`scripts/generate_thumbnails.py`
- 用法：
```
python3 scripts/generate_thumbnails.py            # 生成 small,medium,large
python3 scripts/generate_thumbnails.py --sizes small,medium --force
```
- 输出：`resource/cover/thumbnails/{size}/{AVID}.jpg`

建议：若封面量大，先运行该脚本批量生成缩略图以减少首次请求延迟。

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

如需把这些接口自动加入 `openapi.yaml`，或要具体的前端 `fetchResources` 示例（axios/vanilla fetch），我可以继续补充。
