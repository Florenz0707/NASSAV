# 启动配置契约

来源、刮削和翻译实现由 `nassav/composition.py` 的工厂装配，Manager 可注入工厂用于隔离测试。翻译 Manager 构造和模块导入不检查远端可用性；首次查询可用翻译器或执行非空翻译时检查一次，并发调用共享该检查。检查失败时沿用无可用翻译器的返回行为；该进程实例不自动重复探测，服务恢复后重新创建 Manager 或重启进程。配置解析及 Adapter 构造错误仍在构造时记录。

Django 管理命令、ASGI 和 Celery worker 使用同一个设置加载入口。启动顺序为：读取 `NASSAV_CONFIG_PATH` 指向的 YAML（默认 `config/config.yaml`），校验顶层及必要配置块；读取开发 `.env`（默认 `django_backend/.env`，隔离测试可用 `NASSAV_ENV_PATH` 指定）；再合成进程环境和 YAML 的值。进程环境优先于开发 `.env`，`.env` 只补未设置的变量。数据库 `DB_*` 环境值覆盖 YAML 的 `Database.*`；PostgreSQL 的 `DB_PASSWORD_FILE`/`Database.PasswordFile` 内容覆盖 YAML 明文密码。`DB_PASSWORD` 与密码文件同时有效会报冲突，避免不确定的凭证来源。Compose 的 secret 以 `/run/secrets/...` 文件路径进入 `DB_PASSWORD_FILE`。SQLite 与 PostgreSQL 的 Compose 模式由基础文件和覆盖文件选择，并由数据目录 `db/.nassav-db-mode` 持久声明。`NASSAV_DB_MODE_FILE` 指向容器内该文件；Compose 后端在数据库连接前核对其内容与 `NASSAV_COMPOSE_DB_MODE`、`DB_ENGINE`，缺失或不一致即退出。首次声明及已有目录采用使用根目录 `scripts/compose_stack.py`；仅设置 `DB_ENGINE` 不能切换模式。

`.env` 只接受 `KEY=value`、空行和整行 `#` 注释；值可以用一对单引号或双引号包裹。格式错误、无法读取的 `.env`、空 YAML、非映射顶层、缺少 `Proxy`/`Proxy.Enable`、非法类型和无效数据库引擎都会在启动时失败。错误只包含键名、文件路径或行号，不包含配置值。`DEBUG`、`NASSAV_SECURE_COOKIES` 接受 `true/false`、`yes/no`、`1/0`（不区分大小写）；YAML 中的 `Proxy.Enable`、`FlareSolverr.Enable` 必须是布尔值。端口范围为 1–65535，连接最大存活时间不能为负数。代理 URL 必须有协议和主机；未启用代理时可以保留有效的 URL。`BrowserFetch` 继续使用原有 HTTP(S) URL 与整秒超时规则。

本地模板和 Compose 样例保留各自适用的默认值：本地 `BrowserFetch.Enable: false`、Jable `browser_first`、翻译器地址为 `localhost`；Compose 启用内部 Byparr、Jable `direct_first`、翻译器地址为宿主机网关。这些是部署策略差异。`Proxy` 的关闭状态及下载代理默认直连在两种模板中一致；代理地址的主机名因进程所在网络而异。容器里的宿主机代理应使用 `host.docker.internal` 且服务必须监听容器可达的地址；`127.0.0.1` 在容器内只指向容器自身。下载代理的独立优先级见[代理路由](proxy-routing.md)。

Compose 所有后端服务以 `.env` 中 `NASSAV_UID:NASSAV_GID` 运行（默认 1000:1000），须与宿主机账号及绑定卷权限匹配。使用 prepare_backend_permissions.py 在停止写入者后准备运行目录；切换身份必须重建容器。详见[部署权限说明](compose-deployment.md#后端运行身份与任务目录权限)。

资源目录默认是后端根目录的 `resource/`；隔离测试可以设置 `NASSAV_RESOURCE_DIR`。启动时会创建资源和日志目录，文件系统错误直接使进程失败。通用界面设置保存在按用户隔离的数据库表中；运行时不读写 `user_settings.ini`，旧文件仅供[显式导入](personal-state-architecture.md)。信号接收器在 `AppConfig.ready()` 注册；日志文件 sink 每进程只添加一次。配置修改后须重启持有配置的 API/worker；修改 Compose 环境变量则须重建容器。

## 会话复用与来源策略

BrowserFetch.session_reuse_enabled 只接受 YAML 布尔值，省略为 false。它只控制配套 Cookie+UA、过期/路线校验、自动验证保存和刷新协调，不改写各源 browser_fetch_strategy；关闭时 direct_first 仍先直连，使用已有 Cookie 的传统方式。页面顺序分别为 direct_first、browser_first、direct_only，以来源配置为准。开启完整复用后才使用经验证的配套会话；不自动修改正式配置或放行 MissAV。

更改开关、来源策略或代理配置后重启 API 与持有 Source 实例的 worker。关闭复用与改为 browser_first 是两个独立操作；不要通过清空 Cookie 表代替配置切换。默认本地和 Compose 样例、模板具体值以上文为准，验收边界见[部署与验证边界](compose-deployment.md#近期改动与验证边界)。

## 默认依赖装配

资源七项能力、下载 resolver、推荐 context/inventory/source factory、翻译 Adapter 和媒体定位在 composition 构造，核心不创建 ORM/队列默认实例。没有因职责整理新增配置键。队列、路径、Redis key/TTL、代理覆盖顺序保持；架构和替换规则见[任务架构](task-control-architecture.md)与[推荐架构](recommendation-architecture.md)。

## 任务下载控制（P3）

当前采用实现默认值，尚无新增 YAML 开关：CLI watchdog 100ms、心跳/进度约 1s、等槽位 200ms 且最长 1800s；HLS 清单/密钥的每个校验请求总预算 60s（连接 5s + 55s），超时最多尝试两次，间隔 0.5s，最大 64 MiB；TERM 等待 2s，再 KILL 和退出核查。均为配置/实现期限，不能视为实际来源停止 SLA。恢复校验持续超时保留私有产物并回到 paused（RESUME_VALIDATION_TIMEOUT），允许恢复重试；清单/轨道/密钥身份不一致仍要求终止并重新下载。恢复仅在本地核对缓存哈希并清理损坏/未知/未完成分片，由 CLI 原生复用完整缓存；不再逐片重新下载缓存内容。相同 URL 且清单/密钥不变时无法检测服务器替换字节。校验和 CLI 只使用 DOWNLOAD_PROXY_URL，显式禁用环境代理及 NO_PROXY 绕过。

私有输出位于 COVER_DIR/AVATAR_DIR/VIDEO_DIR 各自 `.tasks/<job_id>/`，根不能重叠。正常租约 TTL 仍为 3600s；writer 退出无法确认时，仅仍属本 owner 的 key 会持久保留而不自动过期，须身份核查恢复。暂停没有自动过期清理。P7 已接入每个真实 worker 的后台恢复扫描，不依赖可选 Beat。见[资产提交架构](task-control-architecture.md)。

受控刮削默认来源阶段 180s、元数据 60s、封面/单头像 45s，任务请求内容最多 20MiB、图片/HTML 写入最多 16MiB；浏览器 maxTimeout 限为 60s，控制请求总传输最多 75s。TaskNetworkControl 不修改来源策略；来源页面和元数据 scraper 共用 `Proxy.Enable/url`，显式代理由请求层正常应用，未配置时明确禁用环境代理；Byparr 控制请求保持直连。只安装到任务新建的实例。翻译整体预算 180s、可用性 5s、单请求最多配置 timeout 与 60s 的较小值；仍使用原活动配置、模型和固定词逻辑。quiet 网络请求在期限内退出前仍是 pausing/cancelling，参数不是来源停止 SLA。暂无新增 YAML 参数，见[受控刮削与翻译架构](task-control-architecture.md)。

## 后台任务恢复默认值

P7 没有新增 YAML 或 .env 键。worker ready 启动独立扫描线程，每 15s 尝试一次；30s 心跳过期触发核查，sent 未领取/清理失败默认 300s 后重试，每类扫描默认最多 100 项。管理命令可指定 stale/retry/limit，调整扫描期限仍不能将活着或未知的 writer 判成已退出。自定义测试设置可覆盖 TASK_RECOVERY_INTERVAL/ENABLED，隔离联调采用 5s；这些不是普通 YAML 的开关。恢复 Loop 关闭使用 worker shutdown，线程退出最多等待 3s，不强制杀扫描线程。

进程核查限于相同 host、boot_id、PID namespace；容器换代无法确认原实例时保留 RECOVERY_UNCONFIRMED，须管理员确认原实例全部退出后使用维护命令。跨主机自动停止和共享 worker terminate 不在该能力内；步骤见[部署说明](compose-deployment.md#持久任务控制版本切换与回滚)。

BrowserFetch.max_concurrency 是代理服务器的公共容量配置，只接受 1–8 的整数（不接受布尔值），BrowserFetch 块中省略该字段时默认为 2；旧 FlareSolverr 块默认 1。禁用 BrowserFetch 时业务调度保持串行。默认装配通过 Redis 对同一 url 的浏览器请求统一限流，不按 provider、来源或出口路线分割容量；所有 API/worker 必须使用相同 url、Redis 与容量配置。Redis 不可用时明确失败，不静默取消限流。业务通过 ProxyServer.ordered 消费有序、有界并发，容量占用只覆盖实际浏览器 IO，任务结束不删除其他 owner 的槽位。详见[代理并发架构](proxy-concurrency.md)。

## 持久抓取缓存

可选 ResourceCache 块统一用于 API/worker；省略时使用安全默认值。SourceTTLSeconds 默认 604800、ScraperTTLSeconds 默认 2592000，范围 1–31536000；PlaybackTTLSeconds 默认 300，范围 1–3600。MetadataRetentionDays 默认 90（1–3650），PlaybackGraceHours 默认 24（1–720），CleanupBatchSize 默认 500（1–5000）。均拒绝布尔值、非法整数或越界值，块本身须为映射。新鲜期改动只影响新发布记录，配置后重启 API/worker/Beat。定期清理依赖 Beat，手动统计/有界清理入口和部署边界见[持久抓取缓存](resource-cache-architecture.md)。

## 外部搜索任务结果复用

可选 YAML `ExternalSearch.ResultTTLSeconds` 控制已成功外部搜索任务结果的复用时长（秒），默认 300，范围 0–86400；0 禁止已完成结果复用，但同查询 queued/running 任务仍去重。拒绝布尔值、非法整数和越界值，ExternalSearch 块须为映射。本地与 Compose 配置样例均提供此项；修改后同步重启 API 与 scrape worker。

任务结果新鲜期从 completed_at 起算，强制重新搜索跳过已完成结果。Redis 查询 owner 按剩余复用时间有条件保留，不延长后来执行者的锁；任务快照保留一天，签名查询凭证覆盖执行预算及最大复用窗口。该项不改变 Jable 来源列表 TTL、聚合结果 TTL 或数据库原站详情 TTL。

### 外部搜索聚合结果与已有详情

`ExternalSearch.CacheEnabled` 默认 true，控制完整聚合结果缓存；`ExternalSearch.AggregateTTLSeconds` 默认 300，范围 1–86400 秒，关闭使用 CacheEnabled=false。结果缓存采用 Redis/Django cache，不新增数据库表。键隔离演员/类别身份、来源、域名、出口、排序及采集页数，缓存完整集合供不同分页复用。API/scrape worker 同步重启使配置生效。ResultTTLSeconds 控制任务身份复用，与聚合缓存独立，设为 0 仍可能命中来源或聚合缓存；强制重新搜索跳过相应读取。

异步任务缓存回调仅在授权终态为 succeeded 后执行，取消先赢不得写成功缓存；失败/部分结果不发布完整聚合缓存。缓存只保存列表原站字段，不保存 in_library/detail_cached 等投影；读取时批量查询当前库存与已有有效数据库详情，不为列表追加详情请求。已有详情可补充缺失标题/封面，列表不被伪装成完整来源元数据/m3u8；添加时仍补齐缺失事实。

## 专用来源凭证密钥（未发布）

`NASSAV_SOURCE_CREDENTIAL_KEYRING_FILE`指定权限0600的专用AES密钥JSON文件，仅新凭证存储/导入/轮换消费者使用。缺失或无权读取时明确不可用，不回退SECRET_KEY。格式、轮换及备份见[凭证架构](source-credential-architecture.md)。不将真实文件写进配置示例或Git；容器挂载必须保留私有权限。旧抓取仍走原Cookie，尚未切换。
