# 异步刮削、进度反馈与 Compose 部署执行计划

日期：2026-09-26。状态：P1 后端任务接口已在独立功能分支实施，P0 输入部分记录；P2–P5 待执行。P1 检查见 [验证记录](async-scraping-p1-validation.md)。本计划基于当前仓库及[现有 Byparr 验收记录](byparr-rollout-validation.md)；用户确认 Byparr 已在本机正常运行。本文不将本机可用推定为容器内全部链路可用。此前的[Byparr 迁移计划](byparr-migration-plan.md)主要处理浏览器获取模块，本计划处理耗时任务、前端反馈及整套服务部署。

## 结论与边界

先将会等待 Byparr 的资源添加、刷新及批量添加/刷新移入专用 Celery 队列，并沿用现有 WebSocket 加状态查询接口反馈进度。现有下载任务已经使用 Celery、Redis 进度与 WebSocket；首轮保留下载进度通道。SSE 列为有验收门槛的后续评估项，只有现有通道在目标部署环境有可复现问题时才实施。最后使用单套 Docker Compose 编排前端、Django ASGI、刮削 worker、下载 worker、Redis 和 Byparr；定时任务服务按现有定时功能需求纳入。

“异步”首先指 HTTP 提交后立即返回任务号，让耗时抓取在 worker 中运行。它不会让单次 Byparr 请求更快。单次 Byparr 请求在已有记录中曾耗时约 64 秒；必须分别衡量提交响应时间、队列等待时间和任务完成时间。[已有测量](byparr-rollout-validation.md)

首轮任务范围是资源添加与刷新。演员/类别详情中的 Jable 外部搜索、推荐发现、Cookie 自动获取也可能等待浏览器，但它们目前有自己的缓存或交互语义；先测量，再按同一任务模式分批迁移。不会把这些同步读接口悄悄改成返回任务号。下载任务不需要重新异步化，重点是验证进度通道和容器部署。

## 一、已确认的项目事实

| 位置                                                                             | 当前行为                                                                                                          | 对计划的影响                                                                 |
| -------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| `nassav/views.py` 的 `ResourceView`、`RefreshResourceView`、`ResourcesBatchView` | 在 HTTP 请求里直接调用 `ResourceService.add_resource` / `refresh_resource`；批量添加还逐条等待并有固定 `sleep(2)` | 这些接口能等待多次 Byparr 请求；需要先抽出提交与执行职责                     |
| `nassav/resource_service.py`                                                     | 已集中编排源信息、元数据、封面、数据库和翻译                                                                      | worker 调用现有业务流程，并在真实阶段边界上报告进度；不复制另一套刮削流程    |
| `nassav/tasks.py`                                                                | 下载使用 Celery、Redis 锁和进度快照，按秒节流 WebSocket 事件                                                      | 可复用消息发送与快照思路；刮削任务采用独立键空间及队列                       |
| `nassav/consumers.py`、前端 `stores/websocket.js`                                | 已有 Channels WebSocket 和自动重连；下载页断线后轮询                                                              | 刮削先接入这条通道，并加任务状态查询用于首次加载和断线恢复                   |
| `django_project/settings.py`                                                     | `REDIS_URL` 固定为 `localhost`，全局 Celery worker 并发为 1；SQLite 文件位于后端目录                              | 容器化前改为环境可配置；刮削与下载分 worker/队列，避免浏览器等待阻塞下载任务 |
| `vue_frontend/src/api/index.js`                                                  | axios 默认请求超时 30 秒；前端添加/刷新依赖同步返回资源对象                                                       | 前端需适配 `202 Accepted`、任务查询与完成后重新加载资源                      |
| `scripts/byparr/compose.yaml`                                                    | 当前只启动固定 digest 的 Byparr，本机映射 `127.0.0.1:8192`                                                        | 全栈 Compose 使用内部服务名 `byparr:8191`，保留单服务脚本供本机开发          |
| `N_m3u8DL_RE.py`                                                                 | 从后端 `tools/` 调用 Linux/Windows 二进制，并传入代理环境变量                                                     | 下载 worker 镜像需有对应 Linux 架构的二进制、执行权限和输出卷                |

## 二、工作分期及放行条件

| 阶段             | 主要交付                                                                              | 放行条件                                                 |
| ---------------- | ------------------------------------------------------------------------------------- | -------------------------------------------------------- |
| P0：基线         | 当前单条/批量请求延迟、Byparr 耗时、下载进度与 WebSocket 可用性、目标机架构及代理拓扑 | 记录中能区分 API 等待、队列等待和抓取本身耗时            |
| P1：任务接口     | 新的添加/刷新任务、专用队列、去重、状态快照及查询接口                                 | HTTP 快速返回，任务成功/失败可在刷新页面后查到           |
| P2：前端反馈     | 添加、详情和批量页面处理任务状态；复用 WebSocket，断线用查询补齐                      | 页面不在任务入队时报告“添加成功”；终态与数据库结果一致   |
| P3：进度通道评估 | 实测现有 WebSocket/轮询，并按下文门槛决定是否做 SSE                                   | 下载与刮削断线/重连测试有记录，得出保留或改用 SSE 的结论 |
| P4：Compose      | 可重复构建和启动的全栈镜像、网络、代理、数据卷与迁移流程                              | 全新目录能按文档启动并跑通资源添加和下载                 |
| P5：联调与切换   | 全链路回归、观察数据、备份/回滚演练                                                   | 满足第七节验收门槛                                       |

### P0：测量与部署输入

选至少一条有效 MissAV 和 Jable 资源，以及一个无结果样本，分别记录 API 响应、Byparr 单次耗时、完整业务耗时、失败类型和任务峰值内存。测量当前前端 WebSocket 连接、下载进度回调及回退轮询。核对目标机 CPU 架构、代理所在位置、N_m3u8DL-RE 的容器架构版本及 SQLite 数据量。不要以 `/health` 取代目标页面有效性检查；Byparr 的 `/health` 还会访问外部站点。

### P1：异步任务与接口

1. 增加 `scrape` Celery 队列和单独 worker，初始并发 1、预取 1；保留现有下载 worker 的独立队列和全局下载锁。路由必须明确：下载、模拟下载走 `download`，新增添加/刷新走 `scrape`；其它任务（翻译、定时任务）保留 `default` worker 或明确映射，避免因启动时只监听两个队列而无人消费。
2. 新增 `submit_resource_job(action, avid, source?, options?)` 作为提交接口。API 先做参数校验、已存在/不存在检查，随后原子占有 Redis 去重键并提交 Celery；失败释放键并返回可解释错误。去重作用域至少包含规范化 AVID 与操作类型，同一资源的添加与刷新如何冲突需明确为互斥。返回已有 `task_id`，避免重复抓取。
3. worker 仅传可 JSON 序列化的编号与参数；在 worker 中重新读取数据库和实例化现有 `ResourceService` 依赖。复用 `add_resource` / `refresh_resource`，通过可选阶段回调增加状态，不把完整 HTML、Cookie、代理凭证或模型对象放进消息或 Redis 任务结果。
4. 状态采用 `queued → running → succeeded | failed`，`running` 内使用真实阶段 `source_lookup`、`metadata`、`cover`、`saving`、`translation_queued`。没有可测的总工作量时显示阶段和已耗时间，不虚构百分比；失败保留稳定错误代码和简短可显示信息。下载百分比仍由下载器输出提供。
5. Redis 以 `task_id` 保存最近状态、阶段、更新时间和最小结果，终态保留建议 24 小时；可选记录 `request_id`/AVID 与任务映射以便页面恢复。Celery 结果后端不是给前端的唯一真值。状态写入后再发送 WebSocket 事件；入队后前端先查快照，再接收事件，按版本/时间戳忽略旧事件，解决提交和订阅之间的事件丢失。
6. 锁设置有效期，并只允许持有者续期/释放；worker 崩溃、提交失败及重试都要保持可恢复。按 `task_id` 做终态和数据库写入幂等保护，避免 worker 重试造成重复资源、重复翻译提交或错误释放其他任务的锁。Celery 超时需覆盖单次 Byparr 60 秒乘以候选数量及元数据抓取时间，软/硬超时留清理余量；重试仅用于可恢复网络失败，404/已存在不重试。
7. 新增 `POST /nassav/api/resource/jobs`（`action=add|refresh`）与 `GET /nassav/api/resource/jobs/{task_id}`。提交成功用 HTTP 202，响应含 `task_id`、状态查询路径和任务摘要；查询结果仅含 UI 所需字段及成功后的资源标识。未知/过期 ID 返回明确状态。批量入口新增 `POST /nassav/api/resource/jobs/batch`，逐项校验并返回各项受理、已存在或失败状态，不在一个 HTTP 请求中串行完成抓取。
8. 老 `resource/new`、`resource/refresh/{avid}` 和 `resources/batch` 先保留现有语义供旧调用者使用，在前端切换后记录剩余调用方，再安排下线或版本化；目标是所有受支持的交互入口都使用任务接口。只返回 `task_id` 的新接口不能冒充老接口同步返回的 201/200 资源数据。

### P2：前端进度与数据更新

- 在资源 store 新增独立的任务状态映射和查询方法；添加页、详情页、批量页从“等待结果”改成“已排队／正在查找资源／正在保存／已完成／失败”。入队后只提示已受理，收到终态后再提示成功或失败。
- 页面加载或切回前台时使用任务 ID 查询最新快照；WebSocket 事件只是加速更新。重连后主动重新查询仍未结束的任务，避免错过终态。页面离开时清理临时订阅/定时器，终态刷新资源列表或详情以获取最终数据库数据。
- 事件至少含 `task_id`、`job_type=scrape`、AVID、状态、阶段、时间戳；事件类型与下载现有 `task_started` / `progress_update` 区分，或在统一事件中明确 `job_type`，避免下载页误读刮削事件。前端只显示与自己提交/恢复的任务相关的状态。现有全局 WebSocket 广播机制在多用户部署前需补上访问控制和订阅范围；任务查询接口不能凭任意 ID 泄漏数据。
- 批量结果保持逐项独立，能显示部分成功；批量删除视频和删除资源不自动并入刮削队列。刷新中 `retranslate` 参数需要保持“先刷新再翻译”的原顺序，并防止重复提交翻译任务。

## 三、SSE 决策：先验证现有通道

当前下载已有 Celery → Redis/Channels → WebSocket → 前端，断线可轮询；新增 SSE 会同时维护两套实时连接和重连逻辑。首轮采用 WebSocket + 快照查询，覆盖本次刮削反馈，下载沿用已运行路径。[下载任务实现](../nassav/tasks.py)、[前端连接实现](../../vue_frontend/src/stores/websocket.js)

P3 在目标 Compose 环境记录 WebSocket 成功连接率、代理升级头是否正常、断线恢复到真实状态的时间、下载进度更新间隔以及并发连接数。若 WebSocket 在目标代理环境中持续无法稳定工作，或者只有单向推送且 SSE 显著简化部署，再做单独原型：对一个任务提供 SSE 状态流，接入相同 Redis 快照与事件模型，不重写 worker；验证浏览器重连、终态补查、心跳、反向代理缓冲关闭、空闲超时、连接数和鉴权。原型达到与 WebSocket 相同的状态一致性后，再决定是否迁移刮削与下载；否则保留现有通道。

即使实施 SSE，也不能把“推送到达”作为唯一真值。断线重连需要先查状态或用事件 ID 补齐，终态查询必须保留；客户端不应无限维持已结束任务的连接。下载高频输出继续节流，避免 SSE/WS 推送压垮 API 服务。SSE 的实施结果须在文档中给出数据和明确结论。

## 四、全栈 Compose 设计

建议在仓库根目录新增 `compose.yaml`、后端和前端各自 Dockerfile，以及一份示例环境文件；现有 `scripts/byparr/compose.yaml` 保留给宿主机开发，但不能与全栈 Compose 同时占用相同端口或重复启动 Byparr。初始拓扑：

```text
浏览器 ──> 前端网关 ──HTTP──> Django ASGI ──> Redis / SQLite
                │                  │
                └──WebSocket───────┘
                                   └──Celery scrape worker ──> Byparr
                                      Celery download worker ──> 下载器
                                      Celery default worker / Beat（需要时）
```

- `frontend` 构建 Vue 静态产物并通过网关提供 `/`；将 `/nassav/api/` 和 `/nassav/ws/` 转发到 Django ASGI，WebSocket 路径设置升级头、合适空闲超时。若 P3 最终选 SSE，还需为事件路径关闭代理缓冲并配置流式超时。对外仅发布前端网关端口。
- `api` 使用 ASGI 服务器，`scrape-worker`、`download-worker`、`default-worker`、可选 `beat` 从同一后端镜像启动。worker 与 API 使用相同代码版本、配置和数据卷，但分别设置队列与并发；Beat 必须保证单实例。先构建镜像，再以一次性 Compose 任务运行 `manage.py migrate`，成功后启动 API/worker；不要让每个副本并发运行迁移。
- `redis` 承担 Celery broker/result、Django cache 和 Channels channel layer；将当前硬编码的 `REDIS_URL` 改成环境变量，容器中统一 `redis://redis:6379/0`。Redis 使用专有内部网络与持久化卷，并验证队列重启恢复策略；API/worker 等待它就绪。不要将 Redis、Byparr 端口对外发布。
- `byparr` 使用现有验证过的 digest 及共享内存配置。`BrowserFetch.url` 在容器内为 `http://byparr:8191`，不能沿用宿主机的 `127.0.0.1:8192`。容器健康不以访问 Google 的 `/health` 单独定论；启动后做独立控制接口与样本页探测。配置变更后重启 API 和所有持有 Source 实例的 worker。
- SQLite 首轮继续使用，但数据库文件及 WAL/SHM 放同一持久化目录，由 API 与 worker 共享，验证并发写入及 `database is locked` 情况；必要时配置适当 busy timeout，按备份方案同时处理 WAL/SHM。资源文件、封面、视频、配置、日志及 Beat 状态各自有明确持久化路径。不要把 `config.yaml`、`user_settings.ini` 或已有资源数据烘进镜像；迁移前备份数据库与资源目录并演练恢复。若 SQLite 写锁影响并发，再单列 PostgreSQL 迁移，不在首轮同时更换数据库。
- 下载镜像必须包含与容器 CPU 架构匹配的 `N_m3u8DL-RE`，并验证执行权限、依赖、临时目录、输出目录及路径映射。当前代码根据 `BASE_DIR/tools` 查找二进制，镜像布局需要保持一致。容器只安装生产依赖，并有独立的构建缓存与 `.dockerignore`。
- 容器内 Django 直连代理、Byparr 浏览器代理、下载器代理是三个独立路径：分别来自现有 `Proxy.url`、Byparr 的 `PROXY_SERVER`、下载 worker 的代理配置。当前 Byparr 已在无代理的 Docker 默认出口工作；全栈首测先复现该出口，不默认启用新代理。若代理在宿主机，Linux 容器通过显式网关名称/可达地址访问，并核验代理监听与防火墙；`localhost` 在每个容器中都不同。配置 `NO_PROXY` 或显式禁止内部 `api`→`byparr`、`api`→`redis` 流量误走外部代理，不在日志输出代理凭证。
- 配置项 `SECRET_KEY`、`DEBUG=false`、`ALLOWED_HOSTS` 和可信来源需在 Compose 环境明确设置。当前 API 默认无认证类，而 WebSocket 会向连接者广播任务状态；若网关暴露公网，先按应用现有访问模型限制访问并规划任务级鉴权，否则任务状态与资源信息可被任意连接者读取。健康检查、重启策略和资源上限要覆盖浏览器和 worker，但不能把 `depends_on` 当作业务可用证明。

## 五、测试、验收与回滚

### 必须补充的自动化测试

- 提交接口：参数、重复提交、Redis 不可用、入队失败释放锁、批量部分成功、旧接口兼容。
- worker：正常/404/挑战/超时、重试、崩溃后锁过期、阶段顺序、资源只写入一次、翻译只提交一次、终态快照可查。
- 前端：202 后不提前显示成功；WS 事件先于查询返回、重复/乱序事件、断线补查、页面刷新、批量部分失败；下载页面原有进度不被刮削事件影响。
- Compose：镜像构建、配置路径、迁移任务、Redis/Byparr 内网解析、WebSocket 升级、下载器运行及共享目录写入。真实外部页面测试保持显式启用，不混进默认单元测试。

实施完成后执行相关测试、`cd django_backend && uv run pytest tests/ -v`、`cd vue_frontend && pnpm run build && pnpm run lint:fix` 和根目录 `pre-commit run -a`。现有全量测试记录曾因缺少 Ollama 出现翻译相关失败；应区分环境依赖与本次回归，不能把失败写成通过。[既有记录](byparr-rollout-validation.md)

### 目标验收门槛

- 提交接口在本机或目标环境 P95 小于 2 秒，且不因一次 60 秒 Byparr 请求超时；任务总耗时按阶段单独报告，不将其算入提交响应。
- 单条与批量添加/刷新完成后，数据库资源、封面、翻译状态与当前同步流程一致；不存在页保持失败，挑战页不会标为成功。
- 浏览器限流从并发 1 开始，在记录 Byparr 峰值内存后再试并发 2；下载仍能在刮削队列忙时启动，不会被全局 worker 并发 1 阻塞。
- 前端在线状态与查询快照最终一致；断线和刷新后在一个查询周期内恢复；成功/失败终态不丢失、不重复显示。
- 从空 Compose 环境启动，完成迁移、至少一条资源添加/刷新、一次下载、前端 WebSocket、持久化卷重启及代理路径验证。下载的进度与文件本身都应检查。
- 在目标环境用小规模样本记录失败率、队列等待、单次 Byparr 耗时、任务耗时、API P95、下载吞吐、容器内存和 SQLite 锁错误；用结果调整并发与超时，不以固定宣传成功率替代实测。

### 上线与回滚

按顺序上线：先部署 Compose 内部依赖及下载通道回归，再部署刮削 worker 和任务 API，随后让前端小范围走新接口，最后切换默认交互入口。切换前备份数据库、配置和资源文件，停止新的长任务并等待在途任务完成。旧宿主机部署和独立 Byparr Compose 保持可恢复；正式切换时避免两个栈同时写同一 SQLite 数据库或下载目录。

回滚时先停止新提交，等待/终止在途任务并记录任务 ID；恢复前端与 API 到同一版本，恢复旧配置及旧进程，重新检查 Redis 锁、终态快照、数据库和下载文件。数据库若已有新版本写入，按前述备份/迁移兼容性评估，不能只回退镜像。SSE 若只做原型，可单独关闭，不影响已经稳定运行的 WebSocket/下载路径。

## 六、建议实施文件与提交拆分

| 交付内容                       | 预计位置                                                                                          |
| ------------------------------ | ------------------------------------------------------------------------------------------------- |
| 资源任务、状态存取、去重与消息 | `django_backend/nassav/tasks.py` 或独立任务模块，配套任务状态模块                                 |
| 新提交/查询接口及文档          | `django_backend/nassav/views.py`、`urls.py`、`doc/interface.md`、`doc/debug.md`                   |
| 业务阶段回调                   | `django_backend/nassav/resource_service.py` 与必要的 Source/Scraper 接口                          |
| 队列、Redis、容器配置          | `django_backend/django_project/settings.py`、`config/template-config.yaml`、Compose 和 Dockerfile |
| 前端任务状态及页面             | `vue_frontend/src/api/index.js`、`stores/resource.js`、`stores/websocket.js`、添加/详情/批量页面  |
| 部署与验证                     | `README.md`、两端 README、`django_backend/scripts/README.md`、相关测试与验收记录                  |

建议按四个可审阅提交推进：`[Feat] Add asynchronous resource scrape jobs and status API`、`[Feat] Show resource scrape stages through existing task updates`、`[Chore] Add full Compose deployment with Byparr and separate workers`、`[Doc] Record end-to-end validation and streaming decision`。若 P3 的证据支持 SSE，再单独提交 SSE 原型与验收，不和 Compose 迁移捆绑。
