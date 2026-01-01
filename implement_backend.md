# 后端实现说明（供前端对接参考）

说明本次后端改动的接口、参数、返回格式、分页与性能建议，便于前端调用与展示实现。

## 1. 改动概览
- 在现有资源列表接口增加 `actor` 查询参数，用于按演员过滤资源。
- 新增演员统计接口 `GET /nassav/api/actors/`，返回演员列表及每位演员的作品数量（支持分页与排序）。

## 2. 现有接口：资源列表（扩展）
- 路径：`GET /nassav/api/resources/`
- 新增参数：
  - `actor`：可传演员 id（整数）或演员名片段（字符串），后端会：
    - 若为整数，按 `actors__id` 精确匹配；
    - 否则按 `actors__name__icontains` 模糊匹配。
  - 其它现有参数仍然有效：`page`、`page_size`、`ordering`、`file_exists`、`source`、`search` 等。
- 语义：当 `actor` 存在时，返回包含该演员的资源列表；结果去重（`distinct()`）。

示例请求：

GET /nassav/api/resources/?actor=Alice&page=1&page_size=20

示例响应（已包含分页 envelope）：

```
{
  "code": 200,
  "message": "success",
  "data": [ { /* ResourceSummarySerializer 输出 */ } ],
  "pagination": { "total": 123, "page": 1, "page_size": 20, "pages": 7 }
}
```

前端要点：
- 调用仍复用资源摘要序列化器（`ResourceSummarySerializer`），字段包括 `avid`、`title`、`has_video`、`thumbnail_url` 等，可直接复用现有列表组件。
- 如果需要显示“仅包含该演员的资源数量”，请使用 `GET /nassav/api/actors/`（见下）。

## 3. 新增接口：演员列表与作品数
- 路径：`GET /nassav/api/actors/`
- 支持参数：
  - `page`（默认 1），`page_size`（默认 20）
  - `order_by`：可选 `'count'`（默认，按作品数降序）或 `'name'`（按名字升序）
- 返回字段（每项）：
  - `id`：演员数据库 id；
  - `name`：演员名；
  - `resource_count`：该演员关联的资源总数。

示例请求：

GET /nassav/api/actors/?page=1&page_size=50&order_by=count

示例响应：

```
{
  "code": 200,
  "message": "success",
  "data": [ { "id": 1, "name": "Alice", "resource_count": 12 }, ... ],
  "pagination": { "total": 200, "page": 1, "page_size": 50, "pages": 4 }
}
```

前端要点：
- 分组视图（每个演员卡片）可使用 `name` 与 `resource_count`，并在卡片内展示 1-3 个代表缩略图（可在前端再发起一次 `GET /nassav/api/resources/?actor=<id>&page_size=3` 获取示例资源）。
- 推荐在卡片点击时导航到 `/actors/:actorId`（或按名称），该页面复用现有资源列表组件并传入 `actor` 参数。

## 4. 性能与缓存建议
- 已添加数据库索引：
  - 对 `nassav_avresource.metadata_saved_at` 添加索引；
  - 对 M2M 关系表 `nassav_avresource_actors(actor_id)` 添加索引。
- 对于高并发或频繁请求的聚合（如热门演员列表），建议在后端或缓存层（Redis）短期缓存 `/api/actors/` 的分页响应，例如缓存 30s~5min，按需失效（数据更新时/后台任务触发）。
- 前端可以对演员分组页做短时缓存（例如 15~60s）以减少重复请求。

## 5. 错误与边界情况
- 若传入不存在的 `actor` id，`/api/resources/` 返回正常但数据为空（`data: []`）；接口仍返回 200。
- 搜索/模糊匹配可能返回多位演员相关资源，后端使用 `distinct()` 去重；若需要仅匹配完全相同的演员名，请改用演员 id 查询。

## 6. 文档与前端示例调用（快速片段）
- 资源列表（按演员）：

```
fetch('/nassav/api/resources/?actor=Alice&page=1&page_size=20')
  .then(r => r.json())
  .then(body => { /* 渲染 body.data */ })
```

- 演员列表：

```
fetch('/nassav/api/actors/?page=1&page_size=50')
  .then(r => r.json())
  .then(body => { /* 使用 body.data 构建演员卡片列表 */ })
```

## 7. 兼容性与回滚
- 所有对外现有参数未被破坏；若后端新功能出现问题，可短期回滚到不携带 `actor` 的旧行为（前端默认不启用 actor 筛选）。

---

如果你需要，我可以：
- 在 `GET /nassav/api/actors/` 中添加 `examples` 字段（返回每位演员的 1-3 个代表作品的缩略信息），或
- 更新项目 OpenAPI 文档以包含新接口示例。
