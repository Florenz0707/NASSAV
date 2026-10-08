# NASSAV Django Backend

Django API、Celery 任务和 Channels WebSocket 后端。本文件提供**本地开发入口**；全栈容器部署见[Compose 部署说明](doc/compose-deployment.md)，接口与权限见[接口文档](doc/interface.md)。

## 快速开始

要求 Python 3.12+、`uv` 和 Redis。从本目录执行：

```bash
uv sync
cp config/config.example.yaml config/config.yaml
# 编辑 config/config.yaml 中的 Proxy、Source、Translator 等配置
uv run python manage.py migrate
uv run python manage.py createsuperuser --username nassav
```

`NASSAV_OPERATOR_USERNAME` 可覆盖默认账号名；创建账号时须保持一致，密码在交互提示中设置。会话 Cookie 和 CSRF 保护业务 API，任务 WebSocket 校验登录与 Origin。配置来源及启动错误见[配置契约](doc/configuration-contract.md)。

下载任务需要 `tools/N_m3u8DL-RE`。使用项目支持的平台版本并赋予执行权限；容器构建会按[部署说明](doc/compose-deployment.md)固定下载和校验工具包。

分别在独立终端运行，先启动 Redis，再启动 API 和三个 worker：

```bash
uv run nassav-api
uv run nassav-worker-default
uv run nassav-worker-scrape
uv run nassav-worker-download
# 需要定时任务时，只运行一个调度器
uv run nassav-beat
```

API 默认监听 `127.0.0.1:9790`。默认 worker 不消费 `scrape` 和 `download` 队列；三个 worker 的并发和预取均为 1。若 Compose 中已启动 Beat，不要同时运行本机 Beat。宿主机 systemd 示例见[进程管理](doc/host-processes.md)。前端开发服务器的同源代理设置见[前端 README](../vue_frontend/README.md)。

## 数据库与部署状态

本机默认和基础 Compose 使用 SQLite；PostgreSQL 是显式选择的外部数据库模式。开发 PostgreSQL 库的数据已导入，业务回归、备份恢复验收及正式切换尚未完成。连接方式、schema、模式保护与备份恢复见[数据库文档](doc/database.md)。历史导入与目标环境接受分开记录，见[验证状态](doc/validation-status.md)。

## 开发检查

开发原则与扩展约束见[共同原则](../docs/development-principles.md)、[任务架构](doc/task-control-architecture.md)与[推荐架构](doc/recommendation-architecture.md)及 [AGENT.md](AGENT.md)。

`manage.py check` 使用当前实例配置，运行前确认数据库和资源目录；离线业务门槛使用专用测试设置：

```bash
uv run python manage.py check
uv run pytest tests/ --ds=django_project.refactoring_test_settings -v
```

离线设置强制无凭证模板、临时 SQLite/文件/用户设置、内存缓存/Channels，并阻止未模拟外部请求。锁测试需要本机提供 `redis-server`，只监听临时 Unix socket，测试后清理。真实 Ollama、站点、worker 和 PostgreSQL 验收单独运行并记录；不要直接用默认 settings 全套测试连接当前实例数据。详细分类见[测试说明](tests/README.md)。

仓库根目录运行 `pre-commit run -a`，包括格式、类型、编译及前端检查。结果需对应具体提交和配置，参见[验证状态](doc/validation-status.md)。

## 代码导航

HTTP 在 `nassav/http/` 按业务分组，URL 在 `nassav/urls.py`。核心编排在 resource_workflow、download_workflow、translation_workflow 和 recommendation/workflow；对应 contracts 定义消费能力，composition 装配默认 Adapter。Celery 入口保留 `nassav.tasks.*` 名称，队列/进度在 download_queue，运维薄任务在 maintenance_tasks。生产 facade 保留已有调用方，新核心不要反向导入默认实例。完整接口与扩展规则见[任务架构](doc/task-control-architecture.md)与[推荐架构](doc/recommendation-architecture.md)。

## 详细文档

- [接口、登录与任务 WebSocket](doc/interface.md)
- [数据库模型、模式与备份](doc/database.md)
- [配置校验与覆盖顺序](doc/configuration-contract.md)
- [推荐算法与使用说明](doc/recommendation.md)、[推荐任务架构](doc/recommendation-architecture.md)
- [代理服务器并发与容量](doc/proxy-concurrency.md)
- [持久任务控制、资产提交与扩展约束](doc/task-control-architecture.md)
- [Compose 部署和外部 PostgreSQL](doc/compose-deployment.md)
- [维护与现场验证脚本](scripts/README.md)
- [测试分类与隔离门槛](tests/README.md)
- [当前验证状态与环境接受](doc/validation-status.md)

持久任务的当前架构、执行归属、资产提交及扩展检查清单见[任务控制架构](doc/task-control-architecture.md)。历史阶段的迁移/部署状态只代表记录当时；本轮验收确认及仍需独立验证的范围以[验证状态](doc/validation-status.md)为准。

## License

MIT License

## v2.4.5 推荐任务与升级

推荐生产入口是 `POST /nassav/api/recommendations/jobs`，在 scrape 队列执行；旧 GET 推荐保留同步兼容。下载/刮削 TaskJob 与 RecommendationJob 分别持有状态，不共用暂停/恢复协议。推荐来源与浏览器出口使用全局 Proxy.url，浏览器服务的控制连接直连；外部搜索和推荐共用 ProxyServer 并发能力。

从 2.4.4 升级先备份数据库并执行 `uv run python manage.py migrate`（包含 0026），再以同一版本重启 API 与 worker、更新前端。所有进程保持相同 BrowserFetch.max_concurrency、代理 endpoint 与 Redis 容量域；默认两路，设置 1 可恢复串行。部署使用已有[Compose 入口](doc/compose-deployment.md)，本次文档更新不代替在线迁移或部署操作。

推荐任务包含排队在内的硬期限为 300 秒，网络提前 30 秒收尾；已有核验结果可部分成功，取消、硬超时与来源失败不转成部分成功。详情尝试预算跨补召回共享，来源列表与详情缓存可复用，历史不作为推荐结果缓存；本地推荐封面目前没有自动过期清理，详见[推荐说明](doc/recommendation.md)。
