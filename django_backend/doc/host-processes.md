# 宿主机进程管理

本机调试的最小启动步骤见[后端 README](../README.md)。对外服务由同源 HTTPS 网关转发到 API 的环回地址；数据库、Redis 与配置须由所有进程共用。

## systemd 示例

使用 systemd 时，API 和 Beat 各一个服务，worker 使用一个模板服务并启动三个实例。以下示例假定代码位于 `/path/to/django_backend`，`uv` 位于 `/path/to/uv`；数据库和 Redis 配置须与这五个进程一致。API 默认监听 `127.0.0.1:9790`，对外访问由同源 HTTPS 网关转发。

```ini
# /etc/systemd/system/nassav-api.service
[Unit]
Description=NASSAV ASGI API
After=network.target redis.service
[Service]
User=your-user
WorkingDirectory=/path/to/django_backend
ExecStart=/path/to/uv run uvicorn django_project.asgi:application --host 127.0.0.1 --port 9790
Restart=always
[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/nassav-worker@.service
[Unit]
Description=NASSAV Celery %i worker
After=network.target redis.service
[Service]
User=your-user
WorkingDirectory=/path/to/django_backend
ExecStart=/path/to/uv run nassav-worker-%i
Restart=always
[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/nassav-beat.service
[Unit]
Description=NASSAV single Celery Beat
After=network.target redis.service
[Service]
User=your-user
WorkingDirectory=/path/to/django_backend
ExecStart=/path/to/uv run nassav-beat
Restart=always
[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now nassav-api nassav-worker@default nassav-worker@scrape nassav-worker@download
# 只在没有其他 Beat 实例时启用
sudo systemctl enable --now nassav-beat
```

## 配置与版本一致性

API、default/scrape/download worker 读取同一代码版本、数据库/Redis 和来源配置；配置修改后重启持有实例的进程。所有宿主机/容器中只运行一个 Beat。运维任务文件迁移后仍以 nassav.tasks.\* 注册，不应修改 Beat 的任务名。

下载 owner 保护不能与旧版无条件删锁 worker 混用；停止旧进程继续消费、核对在途任务和租约后再执行版本切换验收。具体边界见[Compose 部署](compose-deployment.md#下载-worker-版本切换)，当前接受范围见[部署与验证边界](compose-deployment.md#近期改动与验证边界)。
