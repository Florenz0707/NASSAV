# 代理路由

项目按请求用途选择代理，避免宿主机的系统代理改变下载器的出口。

| 请求               | 配置                                                  | 未配置时 |
| ------------------ | ----------------------------------------------------- | -------- |
| Django 直接抓取    | `config/config.yaml` 的 `Proxy.Enable` 与 `Proxy.url` | 直连     |
| Byparr 浏览器请求  | 独立 Byparr 容器的 `PROXY_SERVER`                     | 直连     |
| `N_m3u8DL-RE` 下载 | `config/config.yaml` 的 `Proxy.download_url`          | 直连     |

下载器不会回退使用 `Proxy.url`，启动下载器子进程时会清除继承的 `HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY` 及其小写形式。若显式设置 `DOWNLOAD_PROXY_URL` 环境变量，它会覆盖配置文件中的 `Proxy.download_url`；空字符串强制直连。`Proxy.Enable` 只控制直接抓取，不控制下载代理。Django 抓取进程及其他任务的环境变量不受此处理影响。

本地开发时可以保持 `Proxy.Enable: true` 用于页面抓取，并单独启动直连下载 worker：

```sh
cd django_backend
uv run celery -A django_project worker -l INFO -Q download -c 1 --prefetch-multiplier=1 -n download@%h
```

修改下载代理后要重启下载 worker；`video_download_service` 在进程启动时创建。若某个视频站点要求下载也经过代理，请在 `Proxy.download_url` 填写代理地址。若开发机设置了 `DOWNLOAD_PROXY_URL` 环境变量，先移除它以使用配置文件。全栈 Compose 读取挂载的 `config.yaml`，不会用空环境变量覆盖 `Proxy.download_url`。
