# Byparr 会话复用 P1 验证记录

P1 只交付可空会话列、完整快照、版本检查和页面直连请求头读取；浏览器结果提取、刷新策略与灰度切换属于后续阶段。未连接生产数据库或执行生产迁移。

## 隔离验证

- SQLite 与 PostgreSQL 16 独立容器均运行 `tests/test_source_cookie_session.py`：覆盖旧 Cookie 行迁移后数量和内容不变、人工覆盖与清除、未知代理路线拒绝自动保存、较早浏览器结果晚到、两个并发写入者只能有一个获胜、共享缓存版本校验、页面 Cookie 与 UA 同一快照、到期与路线失配，以及异常日志不泄漏 Cookie 和代理凭据。
- PostgreSQL 测试使用独立容器及 pytest 自动创建的测试库；测试结束后容器已删除。正式环境仍需在其 PostgreSQL 数据副本上演练迁移。
- 旧 `GET/POST/DELETE /nassav/api/source/cookie` 格式未变化；旧行的 UA、到期时间和路线标识为空。

## 部署边界

`0021_sourcecookie_session_metadata` 是可回退的增量迁移。部署前备份数据库并在生产数据副本上核对迁移前后 `SourceCookie` 行数及 Cookie 内容；生产环境的迁移与放行由验收阶段执行。本阶段不会把任何源切换为 `direct_first`。
