# 代理路由

项目按请求用途选择代理，避免宿主机的系统代理改变下载器的出口。

| 请求                                              | 配置                                                  | 未配置时 |
| ------------------------------------------------- | ----------------------------------------------------- | -------- |
| 视频来源页面直接抓取                              | `config/config.yaml` 的 `Proxy.Enable` 与 `Proxy.url` | 直连     |
| 元数据 scraper（JavBus/Busdmm/Dmmsee、封面/头像） | `config/config.yaml` 的 `Proxy.Enable` 与 `Proxy.url` | 直连     |
| Byparr 浏览器请求                                 | `config/config.yaml` 的 `Proxy.Enable` 与 `Proxy.url` | 直连     |
| `N_m3u8DL-RE` 下载                                | `config/config.yaml` 的 `Proxy.download_url`          | 直连     |

下载器不会回退使用 `Proxy.url`，启动下载器子进程时会清除继承的 `HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY` 及其小写形式。若显式设置 `DOWNLOAD_PROXY_URL` 环境变量，它会覆盖配置文件中的 `Proxy.download_url`；空字符串强制直连。`Proxy.Enable` 同时控制 Django 直接抓取与 Byparr 浏览器出口，不控制下载代理。Django 抓取进程及其他任务的环境变量不受此处理影响。

JavBus 等 scraper 共用全局代理，没有独立的 scraper 代理键。包括同步刮削与持久刮削任务的 HTML、封面、头像请求：启用时使用同一 `Proxy.url`，关闭时持久任务请求明确直连。持久任务的请求层不会再用空的底层 cURL PROXY 覆盖显式代理，也不会被系统 `HTTP_PROXY` 或 `NO_PROXY` 改写路线。Byparr 控制请求继续直连，浏览器访问目标站的代理仍由请求头传入。

```yaml
Proxy:
  Enable: true
  # 本机 Django 使用本机可达地址；容器 Django 应改为 host.docker.internal。
  url: http://127.0.0.1:7077
  download_url: null
```

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

代理 URL 的启动校验与配置优先级见[启动配置契约](configuration-contract.md)。Compose 内的 Django 也需将宿主机代理地址设为 `host.docker.internal`；只有本地 Django 才能直接使用宿主机的 `127.0.0.1`。

## 页面会话路线标识（P1）

`SourceCookie.egress_profile` 使用服务端 `SECRET_KEY` 对有效代理 URL 的协议、规范化主机、端口及认证身份计算 HMAC-SHA256，只保存摘要，不保存代理 URL、密码或公网 IP。宿主机回环代理的 `localhost`、`127.0.0.1` 与 `::1` 被视为同一路线；身份或端口变化会产生不同标识。无可确认路线时不写入自动浏览器会话。页面直连读取会话快照后会检查声明到期时间与当前路线，不匹配则用普通直连请求。摘要只能识别配置变化，不能证明两次请求的实际出口相同；上线前仍需从同一 Django 容器实测出口。修改代理配置或服务端密钥后应重启 API 和 worker，旧路线的会话不会被误用。

P2 在 Byparr 页面通过站点校验后，只对可确认同一路线的 Cookie+UA 候选做一次限时 3 秒的目标页直连探测。只有 HTTP 200、同站点、非挑战且业务结构有效时，才以 P1 的版本校验写入会话；探测失败仍可使用本次已验证的浏览器页面。路线摘要相同仍不代替实际出口验证，正式灰度须继续核对。

P3 刷新锁键由规范化源名、目标站点主机与 `egress_profile` 组成，锁值仅为随机 owner；不包含原始代理、Cookie 或 UA。仅直连 403/挑战后准备刷新共享会话时加锁，正常直连和 `browser_first` 页面不排队。代理路线变化形成不同锁域，旧路线下的会话仍由 P1 的路线校验拒绝复用。

P4 开关关闭时页面请求不使用历史自动会话的 UA 或路线，仍可按旧方式使用人工 Cookie；再次开启时只会使用与当前代理路线摘要匹配且未过期的已验证快照。切换代理凭据、主机或端口后旧摘要不再匹配，需通过新路线重新验证。路线摘要不是出口一致性的证明；Jable 与 MissAV 分别灰度。
