# 后端实现计划 — 按演员聚合分类查询

## 目标
在后端提供按演员聚合的查询能力，用于前端展示演员分组（演员名、资源数量、示例资源等），同时支持按演员筛选资源列表并保证性能与可测性。

## API 设计
- 选项 A：在现有资源列表接口增加查询参数 `group_by=actor`，返回分组结果。
- 选项 B：新增专用接口 `/api/resources/group-by-actor/`，返回分页的演员分组列表。
- 支持参数：`page`、`page_size`、`actor`（用于返回某演员的资源）以及可选的排序参数。

## 数据查询与 ORM 实现
- 使用 Django ORM 聚合：
  - 例如：`Resource.objects.filter(...).values('actors__id','actors__name').annotate(count=Count('id'), sample=Subquery(...))`。
  - 对于示例缩略图或示例资源，使用 `Subquery` 或 `ArrayAgg`（取决于 DB）避免 N+1。
- 使用 `prefetch_related('actors')` 和必要的索引（actors.name、关联表的外键）以提升性能。

## 序列化与视图层
- 新增序列化器 `ActorGroupSerializer`：字段包含 `actor_id`、`actor_name`、`resource_count`、`examples`（简要资源信息）。
- 在视图中根据 `group_by` 参数选择返回聚合数据或普通资源列表（保持兼容）。

## 性能与缓存
- 对高成本聚合请求在视图层或缓存层（Redis）做短期缓存，或对热门演员预计算聚合。
- 当数据量大时，可考虑使用原生 SQL 或 materialized view 来优化聚合。

## 数据库与迁移
- 如果需要新增索引（例如演员名索引或资源-演员关联索引），编写 Django migration 添加索引。

## 安全与权限
- 复用现有资源权限检查，确保聚合接口遵守相同的访问控制。

## 测试
- 单元测试：聚合查询函数、序列化器输出。
- 集成测试：API 返回格式、分页、过滤与性能基准（轻量）。

## 文档
- 更新 OpenAPI 文档（`generate_openapi.py`）以包含新参数与示例响应。

## 部署与回滚策略
1. 在后端实现并在 staging 环境打开 feature flag。
2. 监控查询耗时与缓存命中率；如出现问题可回滚为按资源返回的旧行为。
