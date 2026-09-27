# 代理路由

项目按请求用途选择代理，避免宿主机的系统代理改变下载器的出口。

| 请求               | 配置                                                  | 未配置时 |
| ------------------ | ----------------------------------------------------- | -------- |
| Django 直接抓取    | `config/config.yaml` 的 `Proxy.Enable` 与 `Proxy.url` | 直连     |
| Byparr 浏览器请求  | 独立 Byparr 容器的 `PROXY_SERVER`                     | 直连     |
| `N_m3u8DL-RE` 下载 | 下载 worker 的 `DOWNLOAD_PROXY_URL` 环境变量          | 直连     |

下载器不会回退使用 `Proxy.url`，启动下载器子进程时会清除继承的 `HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY` 及其小写形式。若显式设置 `DOWNLOAD_PROXY_URL`，只有该地址用于下载器。Django 抓取进程及其他任务的环境变量不受此处理影响。

本地开发时可以保持 `Proxy.Enable: true` 用于页面抓取，并单独启动直连下载 worker：

```sh
cd django_backend
DOWNLOAD_PROXY_URL= uv run celery -A django_project worker -l INFO -Q download -c 1 --prefetch-multiplier=1 -n download@%h
```

修改下载代理后要重启下载 worker；`video_download_service` 在进程启动时创建。若某个视频站点要求下载也经过代理，请为下载 worker 显式设置 `DOWNLOAD_PROXY_URL`。全栈 Compose 同样使用此变量；空值和缺省值均表示直连。
