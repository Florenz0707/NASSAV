# NASSAV Django Backend

Django API、Celery 任务和 Channels WebSocket 后端。本文件提供**本地开发入口**；全栈容器部署见[Compose 部署说明](doc/compose-deployment.md)，接口与权限见[接口文档](doc/interface.md)。

## 快速开始

要求 Python 3.12+、`uv` 和 Redis。从本目录执行：

```bash
uv sync
cp config/template-config.yaml config/config.yaml
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

本机默认和基础 Compose 使用 SQLite；PostgreSQL 是显式选择的外部数据库模式。开发 PostgreSQL 库的数据已导入，业务回归、备份恢复验收及正式切换尚未完成。连接方式、schema、备份与恢复见[数据库文档](doc/database.md)；正式迁移步骤见[迁移计划](doc/postgresql-migration-plan.md)。该计划中的早期“当前配置”是当时基线，不代表现在的配置。

## 开发检查

```bash
uv run python manage.py check
uv run pytest tests/ -v
```

仓库提交前还需在根目录运行 `pre-commit run -a`。涉及外部 Ollama 的旧集成脚本需要相应服务，隔离环境未提供时应单独记录其结果。

## 详细文档

- [接口、登录与任务 WebSocket](doc/interface.md)
- [数据库模型、模式与备份](doc/database.md)
- [配置校验与覆盖顺序](doc/configuration-contract.md)
- [资源、下载、推荐模块边界](doc/p5-domain-boundaries.md)
- [Compose 部署和外部 PostgreSQL](doc/compose-deployment.md)
- [运行脚本清单](doc/script-inventory.md)及[脚本用法](scripts/README.md)

## License

MIT License
