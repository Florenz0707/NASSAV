# 启动配置契约

来源、刮削和翻译实现由 `nassav/composition.py` 的工厂装配，Manager 可注入工厂用于隔离测试。翻译 Manager 构造和模块导入不检查远端可用性；首次查询可用翻译器或执行非空翻译时检查一次，并发调用共享该检查。检查失败时沿用无可用翻译器的返回行为；该进程实例不自动重复探测，服务恢复后重新创建 Manager 或重启进程。配置解析及 Adapter 构造错误仍在构造时记录。

Django 管理命令、ASGI 和 Celery worker 使用同一个设置加载入口。启动顺序为：读取 `NASSAV_CONFIG_PATH` 指向的 YAML（默认 `config/config.yaml`），校验顶层及必要配置块；读取开发 `.env`（默认 `django_backend/.env`，隔离测试可用 `NASSAV_ENV_PATH` 指定）；再合成进程环境和 YAML 的值。进程环境优先于开发 `.env`，`.env` 只补未设置的变量。数据库 `DB_*` 环境值覆盖 YAML 的 `Database.*`；PostgreSQL 的 `DB_PASSWORD_FILE`/`Database.PasswordFile` 内容覆盖 YAML 明文密码。`DB_PASSWORD` 与密码文件同时有效会报冲突，避免不确定的凭证来源。Compose 的 secret 以 `/run/secrets/...` 文件路径进入 `DB_PASSWORD_FILE`。SQLite 与 PostgreSQL 的 Compose 模式由基础文件和覆盖文件选择，并由数据目录 `db/.nassav-db-mode` 持久声明。`NASSAV_DB_MODE_FILE` 指向容器内该文件；Compose 后端在数据库连接前核对其内容与 `NASSAV_COMPOSE_DB_MODE`、`DB_ENGINE`，缺失或不一致即退出。首次声明及已有目录采用使用根目录 `scripts/compose_stack.py`；仅设置 `DB_ENGINE` 不能切换模式。

`.env` 只接受 `KEY=value`、空行和整行 `#` 注释；值可以用一对单引号或双引号包裹。格式错误、无法读取的 `.env`、空 YAML、非映射顶层、缺少 `Proxy`/`Proxy.Enable`、非法类型和无效数据库引擎都会在启动时失败。错误只包含键名、文件路径或行号，不包含配置值。`DEBUG`、`NASSAV_SECURE_COOKIES` 接受 `true/false`、`yes/no`、`1/0`（不区分大小写）；YAML 中的 `Proxy.Enable`、`FlareSolverr.Enable` 必须是布尔值。端口范围为 1–65535，连接最大存活时间不能为负数。代理 URL 必须有协议和主机；未启用代理时可以保留有效的 URL。`BrowserFetch` 继续使用原有 HTTP(S) URL 与整秒超时规则。

本地模板和 Compose 样例保留各自适用的默认值：本地 `BrowserFetch.Enable: false`、Jable `browser_first`、翻译器地址为 `localhost`；Compose 启用内部 Byparr、Jable `direct_first`、翻译器地址为宿主机网关。这些是部署策略差异。`Proxy` 的关闭状态及下载代理默认直连在两种模板中一致；代理地址的主机名因进程所在网络而异。容器里的宿主机代理应使用 `host.docker.internal` 且服务必须监听容器可达的地址；`127.0.0.1` 在容器内只指向容器自身。下载代理的独立优先级见[代理路由](proxy-routing.md)。

资源目录默认是后端根目录的 `resource/`；隔离测试可以设置 `NASSAV_RESOURCE_DIR`。启动时会创建资源和日志目录，文件系统错误直接使进程失败。用户界面的 `user_settings.ini` 在首次使用时创建和补齐，`manage.py check` 不再为其写文件。信号接收器在 `AppConfig.ready()` 注册；日志文件 sink 每进程只添加一次。配置修改后须重启持有配置的 API/worker；修改 Compose 环境变量则须重建容器。

## P4 会话复用开关

`BrowserFetch.session_reuse_enabled` 只接受 YAML 布尔值，省略时为 `false`。关闭时保留原有 `browser_first` 页面次序与人工 Cookie 直连能力；配置为 `direct_first` 的源暂按 `browser_first` 执行，且不提取、验证或写入自动可复用会话。开启后才按各源 `browser_fetch_strategy` 执行；先只将 Jable 设为 `direct_first`，MissAV 维持 `browser_first` 直至独立验收。切换开关、策略或代理配置后，重启 API 与持有 Source 实例的 worker。回滚时关闭开关并把受影响源恢复 `browser_first`，不清理 Cookie 表。

R7 将资源默认七项能力、下载 resolver、推荐 context/inventory/source factory、翻译 Adapter 及媒体定位集中在 composition；核心用例构造函数不创建默认 ORM/队列依赖。没有新增配置键或修改 config.example.yaml 默认值。任务分文件后仍以原 nassav.tasks.\* 名称注册，队列名、Redis key/TTL、路径和代理配置保持。
