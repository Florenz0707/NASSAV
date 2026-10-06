# 测试分类与隔离验证

从 django_backend 运行。默认 pytest.ini 使用生产设置，离线门槛必须显式指定 refactoring_test_settings；不要把普通 uv run pytest 与隔离命令混用。

## 首选命令与依赖

需要 Python 3.12+、uv、已同步的开发依赖以及系统 redis-server。完整命令：

```bash
uv sync
uv run pytest tests/ --ds=django_project.refactoring_test_settings -v
```

专用设置强制无凭证 config.example.yaml、临时 SQLite/资源/用户设置、内存缓存/Channels，不读取实际 .env，不使用正式数据库模式声明。未模拟的 HTTP/curl/TCP 请求即使被业务吞掉，也在 fixture 收尾时报错。`test_task_network_proxy.py` 单文件使用仅限 loopback 的真实 curl 替身传输护栏，临时 HTTP 服务分别充当目标/代理，校验 HTML、封面、头像、HTTPS CONNECT、环境变量优先级和 Byparr 控制直连；不访问外站，服务结束关闭。临时 Redis 只监听 Unix socket、不开 TCP/持久化，退出时清理；需要系统可启动子进程及本地套接字。当前缺项和历史数量见[验证状态](../doc/validation-status.md)，通过数量须对应提交与日期。

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

`test_task_records.py` 验证持久任务的排队/运行暂停、恢复新 attempt、终止确认、幂等命令、操作者权限、派发失败恢复及真实线程并发；专项也在隔离 PostgreSQL 16 上执行，记录见[任务控制 P1](../../docs/task-control-p1-results.md)。迁移测试必须在 finally 恢复执行前迁移图的叶节点，不能只恢复到所测旧迁移，以免删除后来新增表并污染后续测试。

`test_task_assets.py` 使用真实临时文件与测试 DB 验证私有产物、已有文件/共享头像保护、相同内容回滚、DB 保存失败、多文件提交补偿、停止后崩溃恢复、后续发布 fencing、路径/符号链接拒绝、清理权限失败重试及正式删除 409。与 task_records 的 41 项专项在 SQLite/PostgreSQL 16 验证，见[P2 执行记录](../../docs/task-control-p2-results.md)。测试故障注入不证明真实 worker 崩溃恢复或 CLI 已接入。

`test_controlled_download.py` 与 `test_task_control_http.py` 验证下载停止/提交竞争、暂停释放真实 Redis 槽位、未知 writer 保留归属、分片/AES 身份、推送和 broker 失败、权限与版本输入；`test_local_cli_task_control.py` 默认跳过，设置 NASSAV_LOCAL_DOWNLOAD_BINARY 为固定 P0 二进制绝对路径后，使用本地生成 HLS 和 loopback 做真实 CLI 明文/AES 暂停恢复与全量解码对比（12/240 分片，较大样例暂停时至少 151 个完整分片），核对恢复时完整缓存分片的 HTTP 请求数不增加。所有文件/DB 临时隔离；来源解析/校验 HTTP 为本地替身，此项不是非 eager Celery 或来源网站验收。见[P3 执行记录](../../docs/task-control-p3-results.md)。

test_refactoring_baseline 保留“正常下载先通知成功、DB 写入失败仍成功”以及“资源写库失败保留 HTML、不发布新增事件”的现有顺序。独立下载 owner 回归确认失租不能更新成功；批量翻译错误只收尾本批 translating，保留旧译文和部分完成。语义修复要有明确的新旧对照，不能为了结构迁移改变此类断言。

fixtures/backend_http_contract.json 是迁移前 URL/OpenAPI 消费者快照，不因测试失败自动重建。新增/修改消费者契约时先核对影响，更新说明及快照；仅移动模块不应改变 paths/components。Task registry 和 eager command 样本不等于真实 worker 接受。

## 实时服务和目标环境

refactoring_test_settings 跳过 external 标记；开启外部开关也不会解除该离线门槛的跳过。真实样本需在专用配置/数据库/资源目录下另起进程，不能把实际 Cookie 或生产数据交给本套门槛。

- test_browser_fetch_integration 使用 BROWSER_FETCH_EXTERNAL=1，还需当前有效的 BROWSER_FETCH_URL、BROWSER_FETCH_MISSAV_URL/AVID、BROWSER_FETCH_JABLE_URL/AVID；服务不可用或业务校验失败按失败记录，不算离线通过。
- test_resource_samples、test_real_resource_kir062、test_debug_requests 等旧样本需要 NASSAV_EXTERNAL_TESTS=1，可能写数据库/文件或请求真实站点；使用确认的测试配置与目录。
- Ollama/真实封面/头像等遗留样本按各文件的标记和可用性条件执行，分别报告 skipped、失败和通过，不把跳过写成环境已接受。
- PostgreSQL、API/worker 共享状态、真实下载、HTTPS/WSS 和备份恢复需专用实例与实际记录，见[验证状态](../doc/validation-status.md)。

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

P5 的 `test_controlled_translation.py` 覆盖父子交接、排队/运行/完成竞争、暂停恢复、翻译版本替代、旧单条/批量 success/error 及旧排队消息；`test_persistent_scrape_http.py` 检查实际资源入口的持久身份、操作者和 broker 故障。两者与既有回归在 SQLite/PostgreSQL 执行。主动 response.close 并发出 request_finished 的 HTTP 文件响应测试使用 transaction=True，使连接关闭后下一请求能重新连接；不可用 pytest 原回滚事务模拟真实响应生命周期。范围和命令见[P5](../../docs/task-control-p5-results.md)。

任务控制 P4 的 `test_controlled_scrape.py` 使用真实隔离 DB/文件和可控来源响应覆盖分阶段停止、恢复、版本冲突、部分图片失败和提交补偿；`test_task_network.py` 覆盖阶段预算与内容回调停止。两者连同 `test_task_records.py`、`test_task_assets.py` 在临时 PostgreSQL 验证，环境和命令见[P4 执行记录](../../docs/task-control-p4-results.md)。网络替身验证控制边界，不代表真实来源停止延迟；非 eager worker 和本地网络联调归 P7。

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
