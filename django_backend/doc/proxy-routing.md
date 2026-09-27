# 代理路由

项目按请求用途选择代理，避免宿主机的系统代理改变下载器的出口。

| 请求               | 配置                                                  | 未配置时 |
| ------------------ | ----------------------------------------------------- | -------- |
| Django 直接抓取    | `config/config.yaml` 的 `Proxy.Enable` 与 `Proxy.url` | 直连     |
| Byparr 浏览器请求  | `config/config.yaml` 的 `Proxy.Enable` 与 `Proxy.url` | 直连     |
| `N_m3u8DL-RE` 下载 | `config/config.yaml` 的 `Proxy.download_url`          | 直连     |

下载器不会回退使用 `Proxy.url`，启动下载器子进程时会清除继承的 `HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY` 及其小写形式。若显式设置 `DOWNLOAD_PROXY_URL` 环境变量，它会覆盖配置文件中的 `Proxy.download_url`；空字符串强制直连。`Proxy.Enable` 同时控制 Django 直接抓取与 Byparr 浏览器出口，不控制下载代理。Django 抓取进程及其他任务的环境变量不受此处理影响。

本地开发时可以保持 `Proxy.Enable: true` 用于页面抓取，并单独启动直连下载 worker：

```sh
cd django_backend
uv run celery -A django_project worker -l INFO -Q download -c 1 --prefetch-multiplier=1 -n download@%h
```

修改下载代理后要重启下载 worker；`video_download_service` 在进程启动时创建。若某个视频站点要求下载也经过代理，请在 `Proxy.download_url` 填写代理地址。若开发机设置了 `DOWNLOAD_PROXY_URL` 环境变量，先移除它以使用配置文件。全栈 Compose 读取挂载的 `config.yaml`，不会用空环境变量覆盖 `Proxy.download_url`。

## Byparr 浏览器出口

Django 向 Byparr 的 `/v1` 发送页面请求时，把启用的 `Proxy.url` 拆成 `X-Proxy-Server` 和可选的 `X-Proxy-Username`、`X-Proxy-Password` 请求头。Django 到 Byparr 的控制请求保持直连，不继承宿主机系统代理。`Proxy.Enable: false` 或 `url: null` 时不发送这些请求头。只在没有请求头时，Byparr 才会使用容器的 `PROXY_SERVER` / `BYPARR_PROXY_SERVER` 默认值；项目正常抓取无需另配容器代理。

本地 Django 在宿主机、Byparr 在容器中时，`Proxy.url` 可以写宿主机的 `http://127.0.0.1:<端口>`；发送给 Byparr 的地址会换成 `http://host.docker.internal:<端口>`。两个 Compose 文件都声明了 `host-gateway`，但代理还必须允许来自容器的连接。远程代理主机名保持不变。代理认证可以写在 `Proxy.url` 中，Django 会拆入单独的请求头；不要将凭证写进提交文件或日志。

修改 `Proxy.Enable` 或 `Proxy.url` 后重启 Django API 与 scrape worker，使已创建的抓取客户端读取新配置；无需重启 Byparr。若启用了容器默认代理，即使 `Proxy.Enable: false`，没有请求头的 Byparr 请求仍按其默认代理出口工作。
