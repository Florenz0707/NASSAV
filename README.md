# NASSAV - AV 资源管理系统

基于 Django、Celery 和 Vue 的资源管理系统，提供多源获取、元数据刮削、异步下载、推荐和实时任务进度。项目基于 [Satoing/NASSAV](https://github.com/Satoing/NASSAV) 重构；历史参考代码已从当前仓库移除。

## 功能与入口

- 资源浏览、搜索、添加、刷新、下载与批量操作；按演员和类别聚合。
- 三个 Celery 队列分别处理默认任务、刮削和下载；持久任务支持单条/批量暂停、恢复、终止与停止后的私有产物清理。
- 推荐通过独立持久任务在 scrape worker 执行，支持进度、取消、反馈、历史避让和黑名单；外部搜索与推荐共用代理服务器并发能力。
- 单用户 Django 会话保护业务 API 和任务 WebSocket；登录后使用浏览器 Cookie 与 CSRF 令牌。
- [前端页面与本地开发](vue_frontend/README.md) · [后端本地开发](django_backend/README.md) · [后端接口](django_backend/doc/interface.md) · [数据库说明](django_backend/doc/database.md)
- [仓库开发规范](AGENTS.md) · [后端任务架构与职责](django_backend/doc/task-control-architecture.md) · [前端开发契约](vue_frontend/doc/development-contracts.md)

## 快速开始

默认 Compose 使用 SQLite，包含前端网关、API、Redis、Byparr 和三个 worker。所有后端服务统一使用 `.env` 的 `NASSAV_UID:NASSAV_GID`（默认 1000:1000），首次部署或切换 root 旧实例前按部署说明准备绑定目录权限。首次部署按[全栈 Compose 部署说明](django_backend/doc/compose-deployment.md)准备 `.env`、配置文件和数据目录，然后从仓库根目录运行：

```bash
python3 scripts/compose_stack.py --mode sqlite init
python3 scripts/compose_stack.py --mode sqlite config --quiet
python3 scripts/compose_stack.py --mode sqlite up -d --build
python3 scripts/compose_stack.py --mode sqlite exec api python manage.py createsuperuser --username nassav
```

账号密码由 `createsuperuser` 的交互提示设置。若修改 `NASSAV_OPERATOR_USERNAME`，用户名须与其一致。默认页面仅监听 `127.0.0.1:9780`；远程访问需同源 HTTPS 反向代理，并按部署说明配置 Host、CSRF 和安全 Cookie。Beat 在 `scheduler` profile 中启用且全系统只运行一个实例。

PostgreSQL 模式连接外部数据库，需密码 secret 和 `compose.postgres.yaml` 覆盖文件；具体命令与回滚步骤见[部署说明](django_backend/doc/compose-deployment.md#外部-postgresql可选)。最近只读核查的实例已使用 PostgreSQL 并应用至迁移 0027；迁移 0028 尚未执行，备份恢复与高并发性能仍需专项验收。默认 Compose 仍使用 SQLite；首次启动需声明数据目录的数据库模式，后续 `up`、`ps`、`logs`、`exec`、`down` 使用相同模式的部署入口。直接误用基础 Compose 时，应用会在连接数据库前拒绝模式冲突；不要仅修改 `.env` 的 `DB_ENGINE` 来切换。数据库行为见[数据库模式与备份说明](django_backend/doc/database.md)；开发导入与正式切换的边界见[部署与验证边界](django_backend/doc/compose-deployment.md#近期改动与验证边界)。

本机开发分别参照[后端说明](django_backend/README.md#快速开始)和[前端说明](vue_frontend/README.md#本地开发)；Vite 开发页的 API 和 WebSocket 使用同源代理。启动检查、代理路由和数据目录的细节统一记录在[配置契约](django_backend/doc/configuration-contract.md)、[代理路由](django_backend/doc/proxy-routing.md)和[Compose 部署说明](django_backend/doc/compose-deployment.md)。

## 当前功能与验证状态

资源添加/刷新通过异步任务执行；演员和类别外部搜索支持来源选择、渐进结果、取消和终态补查。下载和批量翻译的 owner/异常收尾修复、资源/下载/翻译/推荐用例分层已实现；消费者 URL、响应字段和 Celery 任务名保持。

用户此前已确认任务、资产权限与推荐系统可用。2.4.5 后新增共享原站事实缓存、外部搜索聚合/任务结果缓存，以及可逆表名迁移 0028；添加资源仍由受控任务补齐事实和资产，删除正式资源保留详情缓存。实现概况统一见[变更日志](CHANGES.md)，时效、清理与开发约束见[缓存架构](django_backend/doc/resource-cache-architecture.md)。

最近后端完整隔离门槛为 860 passed、28 skipped；表名迁移在 SQLite 和独立 PostgreSQL 17 各 2 项专项通过，前端最近为 72 项测试通过。浏览器验收使用模拟 API/WS，MissAV 仅有一个真实样本的受控只读验证；这些结果不代表正式迁移或服务联调已完成。本次文档修订不部署、不执行正式迁移，分项证据和剩余范围见[部署与验证边界](django_backend/doc/compose-deployment.md#近期改动与验证边界)。

## 文档导航

- 本地开发：[后端](django_backend/README.md)、[前端](vue_frontend/README.md)
- 消费者与数据：[接口与权限](django_backend/doc/interface.md)、[数据库与备份](django_backend/doc/database.md)、[推荐系统](django_backend/doc/recommendation.md)
- 架构与配置：[持久任务控制与资产提交](django_backend/doc/task-control-architecture.md)、[推荐架构](django_backend/doc/recommendation-architecture.md)、[代理并发](django_backend/doc/proxy-concurrency.md)、[持久抓取缓存](django_backend/doc/resource-cache-architecture.md)、[配置契约](django_backend/doc/configuration-contract.md)、[代理路由](django_backend/doc/proxy-routing.md)
- 运行与复验：[Compose 部署](django_backend/doc/compose-deployment.md)、[进程管理](django_backend/doc/host-processes.md)、[脚本](django_backend/scripts/README.md)、[测试](django_backend/tests/README.md)、[部署与验证边界](django_backend/doc/compose-deployment.md#近期改动与验证边界)

## 版本更新

完整历史与后续变更日志统一维护在 [CHANGES.md](CHANGES.md)。

## 许可证

本项目基于原仓库 [Satoing/NASSAV](https://github.com/Satoing/NASSAV) 重构开发，遵循相同的许可证。

## 致谢

感谢 [Satoing/NASSAV](https://github.com/Satoing/NASSAV) 原项目的启发和基础代码。
