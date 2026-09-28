# 项目质量与运行边界

本文说明当前应用的访问、配置、任务和模块边界。阶段实施过程已由 Git 历史保留；部署操作以[全栈 Compose 部署说明](../django_backend/doc/compose-deployment.md)为准。
后续实施和验收状态见[补充计划](project-quality-follow-up-plan.md)：资源删除边界与数据库模式护栏已实现并通过隔离自动化检查，目标环境尚未验收。

## 访问与会话

业务 API 使用单用户 Django 会话；浏览器修改请求携带 CSRF 令牌。任务 WebSocket 在加入任务广播组前校验会话与 Origin，前端在会话过期后停止重连。健康探针仅用于内部就绪检查。经反向代理远程访问时，页面、API 和 WebSocket 须同源，使用 HTTPS/WSS，并按部署说明配置可信 Host、CSRF 来源和安全 Cookie。端点规则见[接口文档](../django_backend/doc/interface.md)。

## 数据库、配置与任务

本机和基础 Compose 默认使用 SQLite；`compose.postgres.yaml` 才选择外部 PostgreSQL，密码通过 secret 文件提供。Compose 后端读取数据目录内的持久模式声明；缺失或与所选文件冲突时在连库前失败。部署入口先比较运行容器标签和声明，再执行 Compose。配置来源和优先级见[配置契约](../django_backend/doc/configuration-contract.md)，数据库与备份行为见[数据库文档](../django_backend/doc/database.md)。

Celery 使用 `default`、`scrape`、`download` 三个独立 worker；Beat 只运行一个实例。添加和刷新资源任务返回入队状态，前端结合 WebSocket、状态快照和断线轮询确认终态。开发页面的 HTTP 与 WebSocket 都走同源 Vite 代理。资源、下载和推荐的模块职责见[业务边界说明](../django_backend/doc/p5-domain-boundaries.md)。

## 验证边界

功能已实现：资源删除单条与批量共享服务，批量部分失败保留失败项；数据库模式护栏与部署入口已实现。隔离验证通过：SQLite 后端全量测试、前端检查，以及含 Beat 的 SQLite/PostgreSQL Compose 配置渲染；错误模式和缺失 secret 的启动前拒绝有定向测试。独立 PostgreSQL 完整容器启动、模式误用后的恢复演练和目标环境验收仍未完成。

目标环境的 HTTPS/WSS、真实外站刮削与下载、Ollama 联通、长期运行和备份恢复仍应按部署环境验收。PostgreSQL 开发库已完成数据导入，业务回归、备份恢复验收和正式切换尚未完成；后续步骤仍见[PostgreSQL 迁移计划](../django_backend/doc/postgresql-migration-plan.md)。

历史参考代码目录已从当前仓库移除；其来源仍可从 Git 历史或[上游项目](https://github.com/Satoing/NASSAV)查看。当前构建与运行只使用根目录的 Compose、`django_backend/` 和 `vue_frontend/`。
