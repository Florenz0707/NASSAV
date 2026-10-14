# 测试分类与隔离验证

从 django_backend 运行。默认 pytest.ini 使用生产设置，离线门槛必须显式指定 refactoring_test_settings；不要把普通 uv run pytest 与隔离命令混用。

## 首选命令与依赖

共享池P1专项为`tests/test_library_membership.py`和`tests/test_library_migration.py`：独立事务barrier覆盖并发添加/最后释放竞态，迁移覆盖0036→0037→0036→0037。SQLite使用下方隔离设置；PostgreSQL须使用独立空测试库与同样无凭证/无外部网络设置，不能覆盖已有实例库。

需要 Python 3.12+、uv、已同步的开发依赖以及系统 redis-server。完整命令：

```bash
uv sync
uv run pytest tests/ --ds=django_project.refactoring_test_settings -v
```

专用设置强制无凭证 config.example.yaml、临时 SQLite/资源/用户设置、内存缓存/Channels，不读取实际 .env，不使用正式数据库模式声明。未模拟的 HTTP/curl/TCP 请求即使被业务吞掉，也在 fixture 收尾时报错。`test_task_network_proxy.py` 单文件使用仅限 loopback 的真实 curl 替身传输护栏，临时 HTTP 服务分别充当目标/代理，校验 HTML、封面、头像、HTTPS CONNECT、环境变量优先级和 Byparr 控制直连；不访问外站，服务结束关闭。临时 Redis 只监听 Unix socket、不开 TCP/持久化，退出时清理；需要系统可启动子进程及本地套接字。当前缺项和历史数量见[部署与验证边界](../doc/compose-deployment.md#近期改动与验证边界)，通过数量须对应提交与日期。

## 按链路定位

表中列出重点测试，完整集合仍以 tests 目录和 pytest 收集结果为准。单文件运行也加相同 --ds 参数，不只设置 DATABASE_PATH。

| 链路          | 重点文件                                                                                                                                                                                | 行为契约                                                                       |
| ------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| 能力/装配     | test_backend_contracts.py、test_backend_final_contracts.py                                                                                                                              | 必需 ABC、工厂替换、延迟可用性、纯导入、任务注册/路由/重试                     |
| 会话          | test_source_cookie_session.py、test_browser_session_reuse.py、test_session_coordination.py、test_session_lifecycle_contracts.py、test_jable_auto_cookie.py                              | 旧行、完整快照、人工覆盖、CAS、候选验证、有限等待、失租与临时 Redis Lua        |
| 页面/来源     | test_page_fetching.py、test_browser_page_client.py、test_source_page_fetching.py、test_browser_fetch_config.py、test_missav_search.py、test_jable_search.py、test_jable_search_cache.py | 策略、超时、业务 HTML、缓存与来源失败                                          |
| 外部搜索      | test_search_jobs.py、test_search_adapter_contracts.py、test_external_search_detail_api.py、test_search_covers.py                                                                        | 能力/排序、新源注册、缓存隔离、签名、版本、取消、partial 与终态                |
| 资源写入/删除 | test_resource_workflow_contracts.py、test_metadata_format.py、test_cover_download_priority.py、test_resource_deletion.py、test_refactoring_baseline.py                                  | 注入全流程、解析输入、metadata/关系、文件与写库顺序、部分失败和重复删除        |
| 资源 job      | test_scrape_jobs.py                                                                                                                                                                     | 202 入队、快照 token、并发/终态/过期/事件                                      |
| 下载          | test_download_workflow_contracts.py、test_download_lock_ownership.py、test_download_persistence.py、test_download_proxy_isolation.py、test_n_m3u8dl_re_progress.py                      | 真/模拟用例、锁竞争、静默 CLI/子进程取消、重试/清理、通知与 DB、代理和输出解析 |
| 翻译          | test_translation_workflow_contracts.py、test_batch_translation_state.py、test_translation_cleaning.py                                                                                   | 标题优先级、单批快照、空/数量不匹配/保存异常和已完成项保留                     |
| 推荐          | test_recommendation_pipeline_contracts.py、test_recommendations_demo.py、test_jable_recommender_pagination.py、test_jable_page_lookup_recommender.py、test_genre_source_mapping.py      | 固定随机输入、原请求不变、批量查询、seed 选择、反馈/屏蔽、分页回退             |
| HTTP/权限     | test_http_contracts.py、test_access_control.py、test_ws.py、test_p0_regression.py、test_source_cookie_api.py、test_views_resource.py                                                    | URL/schema/缓存头、operator/CSRF/Origin、断线恢复和旧字段                      |
| 数据/运行配置 | test_database_configuration.py、test_compose_stack.py、test_cleanup_logs.py、test_ensure_ollama_model.py、test_user_settings.py                                                         | 模式护栏、备份配置、日志清理、模型就绪模拟和默认设置                           |
| 浏览器实验    | test_probe_byparr_session.py、test_probe_byparr_media.py、test_byparr_bounded_wait.py、test_assess_byparr_acceptance.py                                                                 | 探针隔离、计时、失败样本、有限等待和接受门槛；不代表正式采用                   |

```bash
uv run pytest tests/test_backend_final_contracts.py tests/test_http_contracts.py \
  tests/test_download_lock_ownership.py --ds=django_project.refactoring_test_settings -v
```

fixture resource_factory、api_client、ws_headers、settings、tmp_path 等在 conftest 中复用；临时 Redis fixture 位于 test_session_lifecycle_contracts。用例测试通过真实能力接口替换依赖，生产 Adapter 通过隔离实例验证；不靠新增旧私有 wrapper 支持测试。

## 冻结与故障行为

`test_task_records.py` 验证持久任务的排队/运行暂停、恢复新 attempt、终止确认、幂等命令、操作者权限、派发失败恢复及真实线程并发；专项也在隔离 PostgreSQL 16 上执行，当前身份与控制协议见[任务架构](../doc/task-control-architecture.md#任务身份控制与停止确认)。迁移测试必须在 finally 恢复执行前迁移图的叶节点，不能只恢复到所测旧迁移，以免删除后来新增表并污染后续测试。

`test_task_assets.py` 使用真实临时文件与测试 DB 验证私有产物、已有文件/共享头像保护、相同内容回滚、DB 保存失败、多文件提交补偿、停止后崩溃恢复、后续发布 fencing、路径/符号链接拒绝、清理权限失败重试及正式删除 409。与 task_records 的 41 项专项在 SQLite/PostgreSQL 16 验证，当前资产协议见[任务架构](../doc/task-control-architecture.md#私有资产发布与补偿)。测试故障注入不证明真实 worker 崩溃恢复或 CLI 已接入。

`test_controlled_download.py` 与 `test_task_control_http.py` 验证下载停止/提交竞争、暂停释放真实 Redis 槽位、未知 writer 保留归属、分片/AES 身份、推送和 broker 失败、权限与版本输入；`test_local_cli_task_control.py` 默认跳过，设置 NASSAV_LOCAL_DOWNLOAD_BINARY 为固定 P0 二进制绝对路径后，使用本地生成 HLS 和 loopback 做真实 CLI 明文/AES 暂停恢复与全量解码对比（12/240 分片，较大样例暂停时至少 151 个完整分片），核对恢复时完整缓存分片的 HTTP 请求数不增加。所有文件/DB 临时隔离；来源解析/校验 HTTP 为本地替身，此项不是非 eager Celery 或来源网站验收。当前续传边界见[任务架构](../doc/task-control-architecture.md#下载续传边界)。

test_refactoring_baseline 保留“正常下载先通知成功、DB 写入失败仍成功”以及“资源写库失败保留 HTML、不发布新增事件”的现有顺序。独立下载 owner 回归确认失租不能更新成功；批量翻译错误只收尾本批 translating，保留旧译文和部分完成。语义修复要有明确的新旧对照，不能为了结构迁移改变此类断言。

fixtures/backend_http_contract.json 是迁移前 URL/OpenAPI 消费者快照，不因测试失败自动重建。新增/修改消费者契约时先核对影响，更新说明及快照；仅移动模块不应改变 paths/components。Task registry 和 eager command 样本不等于真实 worker 接受。

## 实时服务和目标环境

refactoring_test_settings 跳过 external 标记；开启外部开关也不会解除该离线门槛的跳过。真实样本需在专用配置/数据库/资源目录下另起进程，不能把实际 Cookie 或生产数据交给本套门槛。

- test_browser_fetch_integration 使用 BROWSER_FETCH_EXTERNAL=1，还需当前有效的 BROWSER_FETCH_URL、BROWSER_FETCH_MISSAV_URL/AVID、BROWSER_FETCH_JABLE_URL/AVID；服务不可用或业务校验失败按失败记录，不算离线通过。
- test_resource_samples、test_real_resource_kir062、test_debug_requests 等旧样本需要 NASSAV_EXTERNAL_TESTS=1，可能写数据库/文件或请求真实站点；使用确认的测试配置与目录。
- Ollama/真实封面/头像等遗留样本按各文件的标记和可用性条件执行，分别报告 skipped、失败和通过，不把跳过写成环境已接受。
- PostgreSQL、API/worker 共享状态、真实下载、HTTPS/WSS 和备份恢复需专用实例与实际记录，见[部署与验证边界](../doc/compose-deployment.md#近期改动与验证边界)。

在线探针的参数、来源路径、两个时间窗口和完整业务验证由[脚本说明](../scripts/README.md)维护，业务字段见[接口](../doc/interface.md)。离线门槛拒绝网络和线上实验是否被批准是两个不同条件。

## 前端与仓库检查

从仓库根目录运行 pre-commit；前端独立检查从 vue_frontend 运行：

```bash
pre-commit run -a
cd vue_frontend
pnpm run check
```

check 包含 ESLint、node --test 和构建。前端用例覆盖资源任务快照、任务事件/重连、会话失效、外部搜索取消/partial、代理及删除部分失败；不替代另一设备上的真实网关验收。

Ruff 的规则范围在根目录 `ruff.toml` 显式固定为 `E4`、`E7`、`E9`、`F`，保留 Django 初始化所需的 `E402` 例外。升级 Ruff 版本不会自动扩大检查范围；采用新增规则时应单独评估兼容模块、框架属性和异常契约，再调整范围并修复代码。

## 覆盖率与排查

P5 的 `test_controlled_translation.py` 覆盖父子交接、排队/运行/完成竞争、暂停恢复、翻译版本替代、旧单条/批量 success/error 及旧排队消息；`test_persistent_scrape_http.py` 检查实际资源入口的持久身份、操作者和 broker 故障。两者与既有回归在 SQLite/PostgreSQL 执行。主动 response.close 并发出 request_finished 的 HTTP 文件响应测试使用 transaction=True，使连接关闭后下一请求能重新连接；不可用 pytest 原回滚事务模拟真实响应生命周期。当前所属翻译协议见[任务架构](../doc/task-control-architecture.md#刮削检查点与所属翻译)。

任务控制 P4 的 `test_controlled_scrape.py` 使用真实隔离 DB/文件和可控来源响应覆盖分阶段停止、恢复、版本冲突、部分图片失败和提交补偿；`test_task_network.py` 覆盖阶段预算与内容回调停止。两者连同 `test_task_records.py`、`test_task_assets.py` 在临时 PostgreSQL 验证，当前检查点协议见[任务架构](../doc/task-control-architecture.md#刮削检查点与所属翻译)。网络替身验证控制边界，不代表真实来源停止延迟；非 eager worker 和本地网络联调归 P7。

```bash
uv run coverage run -m pytest tests/ --ds=django_project.refactoring_test_settings
uv run coverage report
```

数据库连接或未模拟网络失败时先确认 --ds，而不是修改正式库或放开网络；Redis socket 启动失败检查系统 redis-server 和本地进程权限。WebSocket 超时先核对隔离 channel layer、本地 IPC、登录与 Origin fixture；真实场景再核对代理 Upgrade。翻译服务失败区分 mock/真实地址，不以本地跳过判断生产模型就绪。

维护命令应先在临时副本运行；tests 下遗留 Shell 脚本不是离线 pytest 门槛，需人工核对当前认证、数据目标和依赖后再执行。编写新的行为测试时复用能力与 fixture，覆盖故障/终态/调用次数等真实契约，不断言纯实现细节。文档中的示例和测试文件清单按当前目录核对，不保留历史 Phase 数量作为当前总数。

### P7 任务恢复

`test_task_recovery.py` 使用真实本地进程和临时 Redis Unix socket，检查：活进程/未知身份不清理；登记前的 orphan writer 退出；仅释放本 owner 的 key；停止 fencing 复核心跳；相同 task_id 重派；管理命令人工确认参数；暂停的 promoting 日志重试。`test_task_assets.py` 另检查已终止但日志未恢复时正式删除返回冲突。

真实 worker/本地 HTTP/CLI 验收脚本是显式入口，不包含在普通离线 gate，见[脚本说明](../scripts/README.md#持久任务恢复与真实-worker-验收)。它采用 APIClient、临时资源和新 Redis，不能替代生产网关/真实来源/容器接受。明文/AES-128 原生恢复 smoke 保留 `NASSAV_LOCAL_DOWNLOAD_BINARY` opt-in，实际内容经解码 hash 校验。

`test_hls_validation_timeout.py` 与 controlled_download 专项覆盖部分响应超时后重试不拼接残缺内容、60 秒预算、尝试上限、暂停优先级，以及持续超时保留暂停状态和恢复动作。容器真实 curl 探针见 scripts/accept_hls_validation_timeout.py 和[脚本说明](../scripts/README.md)。

`test_backend_permissions.py` 验证运行目录预览不写入、停止断言、限定范围、锁 inode/缓存内容保留及符号链接/硬链接拒绝；`test_compose_stack.py` 包含后端运行 UID/GID 一致与非 root 的渲染护栏。

`test_task_assets.py` 还验证旧文件硬链接 EPERM 的备份回退、提交成功、元数据失败回滚、复制中的暂停和磁盘失败不被吞掉；`test_backend_permissions.py` 的正式媒体迁移须显式 include-published，保留 inode/内容且拒绝链接。

代理并发专项：`test_proxy_server.py` 验证任意 provider 的公共容量装饰、有序窗口、取消、失租及真实临时 Redis 共享限额；`test_search_proxy_concurrency.py` 验证外部搜索首屏/乱序/短路/部分失败、推荐独立 seed 与详情共享预算、取消后不合并、不同 provider 的生产装配及线程本地连接清理。业务网络使用替身，Redis 使用 Unix socket；不代表真实来源/worker 容量验收。

## 表名迁移回归

`uv run pytest tests/test_table_name_migration.py --ds=django_project.refactoring_test_settings -v` 使用合成资源、演员/类别关联、任务/attempt/资产/事件/命令及推荐/缓存行，执行 0027→0028→0027→0028，并比对全部字段、主键、关系行与索引/唯一约束。finally 恢复原迁移图叶节点，适用于后续迁移继续加入。PostgreSQL 验证必须另用独立临时实例与测试配置，禁止指向正式库。

## 在线播放 P1

`uv run pytest tests/test_playback_sessions.py tests/test_http_contracts.py --ds=django_project.refactoring_test_settings -v` 验证会话身份、取消/退出登录与发布竞争、租期、补派及缓存上下文。使用隔离 DB 和来源替身，不进行正式迁移或外站请求。表与控制接口见[在线播放架构](../doc/online-playback-architecture.md)。

## 在线播放 P2

test_playback_gateway.py 验证清单/目标策略、Range、取消和背压；test_playback_asgi.py 使用真实 Django ASGI 授权/断连路径；test_playback_redis.py 使用临时 Redis Unix socket 与独立进程验证容量；test_playback_transport_live_local.py 使用真实 TLS/HTTPX，验证 SNI、提前关闭及跟踪内存上限。均不访问正式 DB、CDN 或代理，不代表真实容器/播放器解码验收。部署约束见[在线播放架构](../doc/online-playback-architecture.md#配置与部署)。

`test_playback_curl_transport.py` 验证浏览器模拟 Adapter 的真实隔离 TLS/管道背压、提前关闭、启动取消、读取中关闭与强杀回收、固定 DNS/代理/证书策略及生产装配。低层 curl 网络测试仅使用显式私有 Unix socket 和测试 CA，不允许将正式目标传入离线测试。

## 本地视频播放专项

`test_local_playback.py` 使用临时正式视频、真实Django ASGI及独立Redis验证Range/HEAD/If-Range、登录与cap、同大小替换、真实删除、闲置/断连/迟到打开回收、根符号链接与文件链接拒绝。`test_local_playback_migration.py` 覆盖0030→0031→0030→0031，finally恢复全部叶节点；SQLite与独立PostgreSQL均执行。来源解析/worker明确不应调用；接口字节测试不代表浏览器解码，L2另做合成MP4浏览器验证。

## 播放进度验收

`test_playback_progress.py`覆盖用户/会话隔离、claim竞争、重复与乱序保存、回退、完成、清除墓碑、过期/旧代次；`test_playback_progress_migration.py`验证0031↔0032及原播放关系保持，finally恢复全部迁移叶节点。使用标准隔离设置；PostgreSQL另启临时实例，禁止指向正式库。

真实浏览器从后端启动`NASSAV_LOCAL_PLAYBACK_TEST_SERVER=1 uv run python tests/helpers/local_playback_server.py`（独立SQLite/Redis/合成MP4，回环9791）；从前端启动`NASSAV_VITE_BACKEND_URL=http://127.0.0.1:9791 pnpm exec vite --host 127.0.0.1 --port 4178 --strictPort`。使用helper打印的临时storage-state路径，前端执行`NASSAV_PROGRESS_STORAGE_STATE=<临时路径> node tests/browser/playbackProgress.cjs`；Firefox加`NASSAV_BROWSER_ENGINE=firefox`，Playwright模块/浏览器安装按前端README。storage-state含临时登录凭证，禁止提交或打印内容，结束停止helper/Vite并清理专用目录。无显式storage-state时该专项跳过。

## 个人资源状态与数据库设置

`tests/test_personal_state.py` 验证用户隔离、并发部分修改、版本冲突、旧数据显式归属和只读幂等导入；`test_personal_state_http.py` 覆盖列表/详情/状态/设置/搜索默认值与ETag归属；`test_personal_state_migration.py` 对0033执行升级/回退/再次升级并保留旧共享数据与关系。均使用指定隔离settings，PostgreSQL验证使用独立临时数据库，不对正式实例运行测试。

JSON配置的 `test_json_preferences.py` 覆盖缺省只读补齐、增删/改名键失效、严格类型、时间戳、并发部分更新与导入不建空配置；`test_json_preferences_migration.py` 验证0034保留六项旧值、用户归属/更新时间/个人关系及升级/回退/再次升级。与个人状态组一起在SQLite和独立PostgreSQL运行。

推荐用户隔离覆盖test_recommendation_user_isolation.py与test_recommendation_ownership_migration.py（往返、关系保持、重复个人身份拒绝回退）；个人播放设置覆盖test_playback_preferences.py，均在refactoring_test_settings运行，不连接正式数据。真实合成视频偏好浏览器入口见vue_frontend/tests/browser/playbackPreferences.cjs，登录文件仅取本地临时fixture。

跨设备覆盖test_playback_continuations.py：用户隔离、最新ledger后过滤、完成/近尾/清除/删除、来源或本地文件版本变化、批量固定查询数、登录绑定/保存权转移及旧writer拒绝。独立PostgreSQL测试库必须使用UTF8（例如TEST.CHARSET=UTF8与TEMPLATE=template0），不能用SQL_ASCII验证中文JSONB。local_playback_server提供两个同用户的独立登录，只在明确opt-in和9791–9799测试端口运行；退出先关闭临时播放会话，再停止其专用API/Redis并清理临时目录。

观看列表验证：test_viewing.py覆盖用户/登录归属、去重置顶、恢复/重试/乱序、并发、版本冲突、删除与HTTP；test_viewing_migration.py覆盖0035→0036→0035→0036。隔离播放服务器设置NASSAV_VIEWING_TEST_FIXTURE=1额外生成LOCAL-SECOND合成MP4，供前端tests/browser/viewing.cjs真实API验收；使用两份临时登录storage state，禁止连接正式数据库。
