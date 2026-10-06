# 当前实现与验证边界

核对日期：2026-10-05。代码基线：`415550e`，包含后端抽象重构 `c9c3d0f` 和过程文档清理。本文集中记录现有能力、验证证据的范围及尚未完成的环境接受；运行方式以部署、数据库和测试文档为准。

## 已实现的能力

资源新增/刷新、下载、翻译和推荐核心用例接受能力依赖，默认生产 Adapter 由 composition 装配；HTTP 分组视图与原 Celery 任务名保持兼容。资源任务、渐进外部搜索、取消、阶段结果与终态查询、下载进度通过 API/WebSocket 供前端使用。单用户会话、CSRF、WebSocket Origin 和数据库模式护栏继续生效。模块职责见[模块边界](p5-domain-boundaries.md)，消费者契约见[接口说明](interface.md)。

下载执行使用独立 owner 与失租中止；批量翻译按实际标题字段筛选，异常只收尾本批未完成状态。正常下载成功事件先于数据库持久化、DB 失败仅告警，以及文件/数据库部分成功的原有行为仍保留，不能把接口成功当作完整事务提交证明。

## 隔离验证

重构提交 `c9c3d0f` 的历史执行记录为 **539 passed、24 skipped**，全量 `pre-commit run -a` 通过；该数量对应当时提交和隔离配置，不是本文日期的生产验收或实时测试结果。记录可通过 `git show c9c3d0f:django_backend/doc/backend-refactoring-execution.md` 查看。后续代码变化应重新执行[测试说明](../tests/README.md)中的当前命令，并记录提交、日期和结果。

离线设置使用临时 SQLite、文件目录、无凭证配置、内存缓存和 Channels；网络防护阻止未模拟外部请求。部分锁测试启动临时 Redis Unix socket，验证实际 Lua 所有权和 TTL，不使用项目 Redis。URL/OpenAPI 快照、任务注册/队列/重试、资源数据、图片缓存头、纯用例导入和存在性批量查询都有独立回归。隔离测试不覆盖真实抓取、下载工具的生产运行、PostgreSQL 恢复或混合版本 worker。

### 本轮文档复验

2026-10-05 在独立工作树运行当前隔离命令，继承 415550e 的业务代码，结果 **539 passed、24 skipped（47.35 秒）**。文档阶段均执行全量 pre-commit；本地链接/章节锚点与调试示例语法另行检查。只维护 Markdown，不执行数据库迁移、登录、线上探针、worker 切换或部署；生成临时 Schema 的 paths/components 与固定契约快照一致；现有生成器告警为 53 条（42 条唯一）、0 错误，详见[接口说明](interface.md#openapi-与契约快照)。

## 待完成的环境验收

| 范围            | 需要记录的证据                                            | 当前边界                                       |
| --------------- | --------------------------------------------------------- | ---------------------------------------------- |
| 外部 PostgreSQL | 独立实例业务回归、备份恢复、切换与回退结果                | 历史开发库导入不代表正式切换；本次不探测实际库 |
| 网关与访问      | 另一设备通过 HTTPS/WSS 登录、CSRF、Origin、重连及断线补查 | 本地/离线代理检查不能代替目标网关验收          |
| 浏览器与来源    | 同路线、同站、非挑战、有效业务 HTML 和完整会话验证        | 不按 HTTP 200 或 Cookie 存在推定来源可用       |
| API 与 worker   | 真实资源任务、默认翻译、下载进度/文件及 WebSocket 终态    | Celery eager 和注册测试不代表 worker 联调      |
| 下载锁版本切换  | 旧 worker 停止消费后的任务、锁及失败恢复检查              | 旧版无条件删锁与新 owner 保护不能混用          |
| 备份与恢复      | 临时目标恢复后的行数、关系与文件可用性                    | 文件创建成功不能代替恢复验证                   |

部署命令见[Compose 部署](compose-deployment.md)，数据库模式和备份规则见[数据库说明](database.md)。阶段数量、实例、代理路线及时间窗口必须来自实际测量，不填补缺失的现场证据。

## 浏览器与真实站点

会话复用开关、来源策略和代理路线见[配置契约](configuration-contract.md)与[代理路由](proxy-routing.md)。MissAV 的会话复用与 Byparr 等待候选未因本轮重构获得生产放行；保留现有配置，不依据纯离线测试提高直连比例或启用实验等待模式。

在线探针、两个窗口、完整业务校验及隔离运行参数在[脚本说明](../scripts/README.md)中维护，离线/在线 opt-in 在[测试说明](../tests/README.md)中区分。历史 NO-GO 只约束其记录的候选、代码和路线，不等于当前代码永远不可用；重新放行仍需目标环境实测、API/worker 联调和观察证据。

## 历史文档与维护规则

部分迁移计划、Byparr 现场记录、质量阶段说明已不在当前文件树中；2026-10-05 的 `415550e` 另清理了五份抽象重构过程文档。现有导航引用长期维护文档，不把缺失历史报告重新包装成当前实测结果。需要追溯时使用 `git log --all -- <旧路径>`，仅在对应文件实际存在的提交中读取。

API 字段在 interface，持久化行为在 database，算法与参数在 recommendation，模块职责在 p5-domain-boundaries，默认配置在 configuration-contract，操作入口在两个 README/Compose/脚本说明，复验命令在 tests/README。改动正文对应章节，避免在文件末尾持续追加互相矛盾的阶段说明。

## 2026-10-06 持久任务控制隔离验收

P0–P7 已在独立阶段分支实现并验证下载与整条刮削（含所属翻译）的暂停、恢复、终止和归属清理，执行记录见[P7](../../docs/task-control-p7-results.md)。SQLite/PostgreSQL 16 各运行九项真实 prefork Celery + 临时 Redis + 固定 CLI + 本地 HLS/图片/翻译 HTTP fixture 用例；实际注入 worker 崩溃、Redis 断线及目录权限错误，确认停止后才清理、正式文件与共享头像保留。前端为真实 Vue/模拟 API/WS 的浏览器验收；后端控制请求通过已授权 APIClient，未验证真实 HTTPS/WSS 会话网关。

该证据替换“本轮完全未做 worker/PG 联调”的范围限制，仅限本地隔离实例。生产库迁移 0022–0025、Docker 中新旧 worker 切换、真实站点、真实翻译模型和目标网关仍待目标环境接受，不因隔离通过自动上线；步骤见[部署说明](compose-deployment.md#持久任务控制版本切换与回滚)。

## 资源删除锁权限修复（2026-10-06）

分支 `fix/resource-delete-lock-permissions`，基线 `ff25555`，提交标题 `[Fix] Report resource lock permission failures before deletion`。真实只读锁目录/锁文件回归先复现未经处理的 PermissionError，修复后单条/批量资源及视频删除共 8 项权限用例通过，删除用例合计 25 项通过。`uv run pytest tests/ --ds=django_project.refactoring_test_settings -v` 完整隔离回归 705 通过、26 跳过，根目录 `pre-commit run -a` 全通过，未修改钩子配置。

本机资源锁目录及现有普通 `.lock` 文件原属主 root，已限定修复为实际后端用户 1000:1000，目录和文件模式保持，锁 inode 保留。原 SNOS-317 与两个现有锁文件均验证可获取；没有对正式资源执行删除、数据库迁移或重启服务。代码变更在辅助工作树合并 `idle`，默认 `dev` 保留，原 DELETE 请求由用户重试验收。

## 持久刮削任务代理修复（2026-10-06）

分支 `fix/task-network-configured-proxy`，基线 `4bf4ab1`，提交 `d879796`（`[Fix] Honor configured proxies in controlled scraper requests`）。原 TaskNetworkControl 的底层 `CurlOpt.PROXY: ""` 在 curl_cffi 设置显式代理之后执行，导致 scraper 实际直连。本地目标/代理服务先复现返回 direct 而非 proxied；改为请求层的无代理默认值后，显式全局代理正常应用，未配置及 Byparr 控制请求仍明确直连。没有新增代理配置键或修改实例配置。

`uv run pytest tests/test_task_network_proxy.py tests/test_task_network.py --ds=django_project.refactoring_test_settings -q` 21 项通过：包含 15 项真实 loopback curl 回归，覆盖三个 scraper 的 HTML/封面/头像、HTTPS CONNECT、显式代理与环境代理/NO_PROXY 的优先级、浏览器控制直连，以及原任务预算/暂停终止检查。完整 `uv run pytest tests/ --ds=django_project.refactoring_test_settings -v` 为 720 通过、26 跳过，`pre-commit run -a` 全通过，钩子配置未改。

全部服务和图片文件为本地临时 fixture，结束关闭/清理。未访问 JavBus 等真实站点，未变更实际代理地址或重启正式 API/worker；目标环境需更新代码、启用已有 `Proxy.Enable/url` 并重启 API/scrape worker 后验收。配置位置及本机/容器地址区别见[代理路由](proxy-routing.md)。

## 封面与任务列表交互修复（2026-10-06）

分支 `fix/resource-covers-task-selection-order`，基线 `bdb29a4`，提交标题 `[Fix] Unify cover fallback and stabilize task selection and ordering`。资源卡片、资源详情与任务详情共享无封面占位；无任务深链时不误匹配缺少 taskId 的任务，同 AVID 的任务保持独立 ID。排序由任务 API 在分页前完成，前端切换排序使旧请求失效。完整隔离后端回归 722 通过、26 跳过，前端 check 通过；resourceTaskFixes 浏览器验收覆盖深浅主题、同 AVID 同类型及跨类型详情、两种时间降序、卡片与详情封面 404 占位。质量门槛为根目录 pre-commit run -a。模拟 API 浏览器验收不代表真实服务联调。

## Docker 下载恢复校验超时修复（2026-10-06）

分支 `fix/download-resume-validation-timeouts`，基线 `2dd02ea`，提交标题 `[Fix] Retain paused downloads after bounded validation timeouts`。只读核查实际 Docker 任务发现恢复执行停在 resume_validation：320 个缓存分片、播放列表 2214 个分片，某分片 20.321s 仅接收 786360/920272 字节后 cURL 28 超时；不是 CLI 启动超时。未修改该正式任务、实际配置或运行服务。

每次 HLS 校验请求期限改为 60s，超时最多尝试两次、间隔 0.5s，失败尝试的部分响应完全丢弃。回调与重试间仍检查暂停/终止，保留所有缓存与当前源字节核对；持续超时回到 paused，错误码 RESUME_VALIDATION_TIMEOUT，允许用户恢复重试，释放执行槽位。内容或轨道不一致仍要求终止后重新下载。

超时与受控下载专项 22 项通过；完整 `uv run pytest tests/ --ds=django_project.refactoring_test_settings -v` 为 725 通过、26 跳过，根目录 `pre-commit run -a` 全通过。临时 Docker 容器使用本地 nassav-backend:dev 镜像、只读挂载修改源码、`--network none`，真实 curl 请求仅访问其临时 loopback 服务，注入 0.25s 的部分响应超时后校验重试成功、缓存保留及暂停优先级；验收报告见[Docker 探针](../../docs/task-control-probes/resume-timeout-docker.json)。临时目录与容器已清理。

该 probe 不证明真实外站、完整 CLI 下载及生产切换已验收；未重新构建部署镜像或恢复原正式任务。更新镜像后需在目标网络复查恢复校验、暂停/终止及视频完整性。参数与探针入口见[配置契约](configuration-contract.md)和[脚本说明](../scripts/README.md)。
