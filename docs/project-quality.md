# 项目质量与运行边界

本文说明当前应用的访问、配置、任务和模块边界。阶段实施过程已由 Git 历史保留；部署操作以[全栈 Compose 部署说明](../django_backend/doc/compose-deployment.md)为准。
后续未完成的职责收口、部署防误操作与目标环境验收见[补充计划](project-quality-follow-up-plan.md)。

## 访问与会话

业务 API 使用单用户 Django 会话；浏览器修改请求携带 CSRF 令牌。任务 WebSocket 在加入任务广播组前校验会话与 Origin，前端在会话过期后停止重连。健康探针仅用于内部就绪检查。经反向代理远程访问时，页面、API 和 WebSocket 须同源，使用 HTTPS/WSS，并按部署说明配置可信 Host、CSRF 来源和安全 Cookie。端点规则见[接口文档](../django_backend/doc/interface.md)。

## 数据库、配置与任务

本机和基础 Compose 默认使用 SQLite；`compose.postgres.yaml` 才选择外部 PostgreSQL，密码通过 secret 文件提供。各后端进程必须连接同一个预期数据库；配置矛盾、缺键或无效凭证在启动时明确失败，不回退到 SQLite。配置来源和优先级见[配置契约](../django_backend/doc/configuration-contract.md)，数据库与备份行为见[数据库文档](../django_backend/doc/database.md)。

Celery 使用 `default`、`scrape`、`download` 三个独立 worker；Beat 只运行一个实例。添加和刷新资源任务返回入队状态，前端结合 WebSocket、状态快照和断线轮询确认终态。开发页面的 HTTP 与 WebSocket 都走同源 Vite 代理。资源、下载和推荐的模块职责见[业务边界说明](../django_backend/doc/p5-domain-boundaries.md)。

## 验证边界

SQLite 和 PostgreSQL 两种 Compose 模式已在隔离数据目录验证配置、迁移、API、三个队列和 Beat；前端的会话、任务恢复、WebSocket 代理与重连有自动化测试。这些检查只证明隔离环境中的行为。

目标环境的 HTTPS/WSS、真实外站刮削与下载、Ollama 联通、长期运行和备份恢复仍应按部署环境验收。PostgreSQL 开发库已完成数据导入，业务回归、备份恢复验收和正式切换尚未完成；后续步骤仍见[PostgreSQL 迁移计划](../django_backend/doc/postgresql-migration-plan.md)。

历史参考代码目录已从当前仓库移除；其来源仍可从 Git 历史或[上游项目](https://github.com/Satoing/NASSAV)查看。当前构建与运行只使用根目录的 Compose、`django_backend/` 和 `vue_frontend/`。
