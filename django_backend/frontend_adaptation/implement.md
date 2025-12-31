# 前端对接实现说明（实现汇总）

本文档总结后端已实现的接口与行为变更，供前端同学尽快对接并优化调用逻辑。

**变更范围（概要）**
- 后端统一响应 envelope：{ code, message, data, pagination? }
- `GET /nassav/api/resources/`：支持服务端过滤/搜索/排序/分页（`search,status,sort_by,order,page,page_size,source`）
- `GET /nassav/api/resource/cover?avid=...&size=small|medium|large`：按需返回原图或缩略图，支持长缓存与条件请求（ETag/Last-Modified）
- `GET /nassav/api/resource/<avid>/preview`：返回 `{ metadata, thumbnail_url }` 用于详情首屏快速渲染
- 单点操作（新增/刷新/删除）现在会在响应中包含最新 `resource` 对象，方便前端局部合并更新
- 批量接口：`POST /nassav/api/resources/batch`（actions：add/delete/refresh）与 `POST /nassav/api/downloads/batch_submit`
- 支持条件请求（`If-None-Match`, `If-Modified-Since`）对 metadata、cover、thumbnail 返回 `304` 减少带宽
- 提供 `scripts/generate_thumbnails.py` 用于一次性为已有封面生成 small/medium/large 缩略图

**统一响应格式 (envelope)**
- 成功示例：

```json
{
  "code": 200,
  "message": "success",
  "data": [ ... ],
  "pagination": { "total": 120, "page": 1, "page_size": 18, "pages": 7 }
}
```

- 失败示例（400/404/500 等）保持 `code/message/data` 语义，HTTP 状态码仍与语义一致。

------------------------------------------------------------

**重要接口与示例**

1) 资源列表（服务端过滤/分页/排序/搜索）
- GET /nassav/api/resources/?search=abc&status=downloaded&sort_by=metadata_create_time&order=desc&page=1&page_size=18
- 返回 `data` 为数组（每项为资源摘要），并在 envelope 中包含 `pagination` 字段。

2) 单资源预览（用于详情首屏）
- GET /nassav/api/resource/ABC-123/preview
- 返回示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "metadata": { "avid":"ABC-123", "title":"...", ... },
    "thumbnail_url": "/nassav/api/resource/cover?avid=ABC-123&size=small&v=1681234567"
  }
}
```

3) 封面与缩略图
- GET /nassav/api/resource/cover?avid=ABC-123
  - 返回原始封面（带 `ETag` 与 `Last-Modified`）
- GET /nassav/api/resource/cover?avid=ABC-123&size=small
  - 返回 `resource/cover/thumbnails/small/ABC-123.jpg`（若不存在后端会按需生成并返回）
  - 响应包含 `Cache-Control: public, max-age=31536000`，并支持条件请求头返回 `304`。

示例：前端加载图片时推荐直接使用 `thumbnail_url`：
```html
<img src="/nassav/api/resource/cover?avid=ABC-123&size=small" alt="cover">
```
- 当浏览器自动带上 `If-None-Match`/`If-Modified-Since` 时，后端会返回 `304`，避免重复下载。

4) 单项操作返回新对象（便于局部合并）
- POST /nassav/api/resource  （新增）
  - 响应 data 示例： `{ resource: { avid, title, file_exists, file_size, ... }, cover_downloaded: true, ... }`
- POST /nassav/api/resource/refresh/{avid} （刷新）
  - 响应 data 包含 `resource` 最新对象
- DELETE /nassav/api/resource/{avid}
  - 响应包含 `resource`（删除前的序列化对象）与 `deleted_files`

说明：前端收到 `resource` 对象后应局部合并到当前列表或详情视图，而不是强制 re-fetch 整页。

5) 批量操作
- POST /nassav/api/resources/batch
  - Body 示例：
```json
{
  "actions": [
    {"action":"add","avid":"ABC-123","source":"any"},
    {"action":"refresh","avid":"DEF-222"},
    {"action":"delete","avid":"OLD-001"}
  ]
}
```
  - 返回 data: `{ results: [ { action, avid, code, message, resource?, deleted_files? }, ... ] }`
- POST /nassav/api/downloads/batch_submit
  - Body: `{ "avids": ["ABC-123","DEF-222"] }`
  - 返回每个 avid 的提交状态与 `task_id` 或 409 表示已存在任务

前端应：
- 在批量操作成功时使用返回的 `resource` 数组/对象做局部合并而非重新拉全表。

------------------------------------------------------------

**缓存与条件请求（前端要点）
- 对于 metadata、cover、thumbnail：后端返回 `ETag` 与 `Last-Modified`。
- 前端/浏览器通常会自动管理条件请求；如果手动发请求（fetch/axios），建议：
  - 当缓存本地维护时，发送 `If-None-Match: <etag>` 或 `If-Modified-Since: <http-date>`；
  - 若响应为 `304` 则使用本地缓存数据或保持现状。

curl 示例（带 ETag）:
```bash
curl -i -H 'If-None-Match: "123abc"' "http://<host>/nassav/api/resource/cover?avid=ABC-123&size=small"
```

------------------------------------------------------------

**缩略图生成脚本**
- 文件：`scripts/generate_thumbnails.py`
- 用法：
```bash
python3 scripts/generate_thumbnails.py            # 生成 small,medium,large
python3 scripts/generate_thumbnails.py --sizes small,medium --force
```
- 默认输出位置：`resource/cover/thumbnails/{size}/{AVID}.jpg`

说明：
- 后端也会在首次请求时按需生成缩略图（best-effort）。若图片量大，建议事先运行脚本做批量生成。

------------------------------------------------------------

**前端需要做的改动（优先级）**
1) 参数化 `fetchResources`：在请求中传入 `search,status,sort_by,order,page,page_size,source`，并以返回的 `data` / `pagination` 渲染列表（不要做整表客户端过滤）。

2) 搜索防抖：为搜索框添加 200~400ms 防抖。

3) 局部合并更新：在新增/刷新/批量操作返回 `resource` 对象时，前端应将这些对象合并到当前页面数据，而不是调用 `fetchResources()` 全表刷新。

4) 使用 thumbnail_url 与条件请求：直接把后端返回的 `thumbnail_url` 作为 `<img>` 的 `src`，依赖浏览器/axios 条件请求以获得 `304` 减少带宽；若手动管理缓存，请保留并传递 `ETag`/`Last-Modified`。

5) 统一错误和响应拦截器：后端始终返回 `{ code, message, data, pagination? }`，请在 `src/api/index.js` 的响应拦截器中统一解析：
```js
// pseudo
if (resp.data && resp.data.code !== 0 && resp.data.code !== 200) throw new ApiError(resp.data.code, resp.data.message)
return resp.data
```
（按项目实际错误码规则调整）

6) WebSocket/SSE：使用现有 `src/stores/websocket.js` 订阅任务事件，ResourceCard/ResourceDetail 订阅并更新 `has_video`、下载进度等（后端已在 `nassav/consumers.py` 支持 task events）。

------------------------------------------------------------

**配置与注意事项**
- 后端默认缩略图路径基于 `django_project/settings.py` 中的 `COVER_DIR`，如需自定义可设置 `THUMBNAIL_DIR`。
- 缓存 `v` 参数：preview 的 `thumbnail_url` 含 `&v=<mtime>`，用于强缓存失效控制；若需要基于内容 hash 替换为 hash，可改为在后端生成。
- 安全：`GET /downloads/abspath` 返回绝对路径仅用于受信任客户端，请前端在 UI 上谨慎展示与复制操作。

------------------------------------------------------------

**测试**
- 后端单元/集成测试已在本地通过：`pytest` 输出：`12 passed, 1 warning`。

------------------------------------------------------------

如需我：
- 提供 `fetchResources` 在前端的示例实现（axios/Fetch 版本），或
- 把上述变更加入 `openapi.yaml`（自动化文档）或 `frontend_adaptation/plan.md` 的补充说明，或
- 将缩略图生成改为后台 Celery 任务以避免请求延迟。

请告诉我优先帮你完成哪一项对接工作。
