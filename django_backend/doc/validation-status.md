# 当前实现与验证边界

核对日期：2026-10-06。当前文档核对代码基线：`7a3d7f1`。下文 `415550e` / `c9c3d0f` 及各阶段数据均保留为历史证据。本文集中记录现有能力、验证证据的范围及尚未完成的环境接受；运行方式以部署、数据库和测试文档为准。

## 已实现的能力

资源新增/刷新、下载、翻译和推荐核心用例接受能力依赖，默认生产 Adapter 由 composition 装配；HTTP 分组视图与原 Celery 任务名保持兼容。资源任务、渐进外部搜索、取消、阶段结果与终态查询、下载进度通过 API/WebSocket 供前端使用。单用户会话、CSRF、WebSocket Origin 和数据库模式护栏继续生效。模块职责见[任务架构与职责](task-control-architecture.md)，消费者契约见[接口说明](interface.md)。

下载执行使用独立 owner 与失租中止；批量翻译按实际标题字段筛选，异常只收尾本批未完成状态。正常下载成功事件先于数据库持久化、DB 失败仅告警，以及文件/数据库部分成功的原有行为仍保留，不能把接口成功当作完整事务提交证明。

## 隔离验证

重构提交 `c9c3d0f` 的历史执行记录为 **539 passed、24 skipped**，全量 `pre-commit run -a` 通过；该数量对应当时提交和隔离配置，不是本文日期的生产验收或实时测试结果。记录可通过 `git show c9c3d0f:django_backend/doc/backend-refactoring-execution.md` 查看。后续代码变化应重新执行[测试说明](../tests/README.md)中的当前命令，并记录提交、日期和结果。

离线设置使用临时 SQLite、文件目录、无凭证配置、内存缓存和 Channels；网络防护阻止未模拟外部请求。部分锁测试启动临时 Redis Unix socket，验证实际 Lua 所有权和 TTL，不使用项目 Redis。URL/OpenAPI 快照、任务注册/队列/重试、资源数据、图片缓存头、纯用例导入和存在性批量查询都有独立回归。隔离测试不覆盖真实抓取、下载工具的生产运行、PostgreSQL 恢复或混合版本 worker。

### 本轮文档复验

2026-10-05 在独立工作树运行当前隔离命令，继承 415550e 的业务代码，结果 **539 passed、24 skipped（47.35 秒）**。文档阶段均执行全量 pre-commit；本地链接/章节锚点与调试示例语法另行检查。只维护 Markdown，不执行数据库迁移、登录、线上探针、worker 切换或部署；生成临时 Schema 的 paths/components 与固定契约快照一致；现有生成器告警为 53 条（42 条唯一）、0 错误，详见[接口说明](interface.md#openapi-与契约快照)。

## 独立专项与历史待验收范围

下表保留原专项要求；本轮任务改进的用户接受另见文末 v2.4.3 确认。未提供对应专项证据的项目仍独立维护，不以历史阶段的待验收措辞否定本轮确认。

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

API 字段在 interface，持久化行为在 database，算法与参数在 recommendation，模块职责在 task-control-architecture，默认配置在 configuration-contract，操作入口在两个 README/Compose/脚本说明，复验命令在 tests/README。改动正文对应章节，避免在文件末尾持续追加互相矛盾的阶段说明。

## 2026-10-06 持久任务控制隔离验收

P0–P7 已在独立阶段分支实现并验证下载与整条刮削（含所属翻译）的暂停、恢复、终止和归属清理，执行记录见P7的历史文件 `../../docs/task-control-p7-results.md`（已在 `0a9b457` 清理，可从该提交的父版本追溯）。SQLite/PostgreSQL 16 各运行九项真实 prefork Celery + 临时 Redis + 固定 CLI + 本地 HLS/图片/翻译 HTTP fixture 用例；实际注入 worker 崩溃、Redis 断线及目录权限错误，确认停止后才清理、正式文件与共享头像保留。前端为真实 Vue/模拟 API/WS 的浏览器验收；后端控制请求通过已授权 APIClient，未验证真实 HTTPS/WSS 会话网关。

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

超时与受控下载专项 22 项通过；完整 `uv run pytest tests/ --ds=django_project.refactoring_test_settings -v` 为 725 通过、26 跳过，根目录 `pre-commit run -a` 全通过。临时 Docker 容器使用本地 nassav-backend:dev 镜像、只读挂载修改源码、`--network none`，真实 curl 请求仅访问其临时 loopback 服务，注入 0.25s 的部分响应超时后校验重试成功、缓存保留及暂停优先级；验收报告见Docker 探针的历史文件 `../../docs/task-control-probes/resume-timeout-docker.json`（已在 `0a9b457` 清理，可从该提交的父版本追溯）。临时目录与容器已清理。

该 probe 不证明真实外站、完整 CLI 下载及生产切换已验收；未重新构建部署镜像或恢复原正式任务。更新镜像后需在目标网络复查恢复校验、暂停/终止及视频完整性。参数与探针入口见[配置契约](configuration-contract.md)和[脚本说明](../scripts/README.md)。

## 原生下载续传修复（2026-10-06）

分支 `fix/native-download-resume`，基线 `53d0e92`，提交标题 `[Fix] Reuse verified local segments for native download resume`。原恢复准备串行重新下载所有已缓存分片，重新部署后仍停在 resume_validation。现改为当前清单/轨道/密钥身份加本地哈希校验，损坏/未知/未完成缓存删除后交由原生 CLI 重下，完整缓存不再请求远程字节。安全边界与兼容部署见执行记录的历史文件 `../../docs/task-control-native-resume-results.md`（已在 `0a9b457` 清理，可从该提交的父版本追溯）。

`uv run pytest tests/ --ds=django_project.refactoring_test_settings -v`：726 通过、28 跳过。专项恢复/超时测试 23 通过；真实 curl loopback 超时探针通过。真实 CLI 来自当前 Docker worker 的 0.5.1 二进制，`NASSAV_LOCAL_DOWNLOAD_BINARY=... uv run pytest tests/test_local_cli_task_control.py --ds=django_project.refactoring_test_settings -q`：明文/AES、12/240 分片四项通过（84.85s）；240 分片用例暂停时保留至少 151 个完整分片，恢复后这些分片 HTTP 请求数不增加，最终全量解码 hash 等于原视频。较大样例先暴露共享内存 SQLite 并发表锁，专项改用临时文件 SQLite 后通过。根目录 `pre-commit run -a` 全通过，未修改钩子配置。

CLI 和网络均仅访问临时 loopback fixture，数据库/输出临时隔离。未重建镜像、切换正式服务或操作原正式任务；真实外站、实际代理和 Docker 正式任务的恢复仍需更新镜像后验收。新旧检查点兼容，已暂停任务可直接恢复；同 URL 且清单/密钥不变时服务器替换分片内容无法检出。

## 后端运行身份与取消任务清理修复（2026-10-06）

分支 `fix/backend-volume-ownership`，基线 `6d5fe89`，提交标题 `[Fix] Align backend runtime ownership and recover cancelled task cleanup`。Compose 所有七个后端入口统一使用非 root 的 NASSAV_UID:NASSAV_GID（默认 1000:1000），Beat PID 移至其运行卷；新增只读预览/显式停止断言的权限准备工具，保留缓存、锁 inode 和正式媒体文件。

专项 15 项通过，真实 Docker UID1000 探针通过全部运行目录、SQLite、flock、缓存删除和本地 HLS 原生下载/清理；完整 `uv run pytest tests/ --ds=django_project.refactoring_test_settings -v` 为 736 通过、28 跳过（80.79s），根目录 `pre-commit run -a` 全通过，钩子配置未改。详细命令与范围见执行记录的历史文件 `../../docs/backend-volume-permissions-results.md`（已在 `0a9b457` 清理，可从该提交的父版本追溯）。

实际实例在全部服务停止时修复 205 个条目的属主为 1000:1000，六个已有锁 inode 不变。PostgreSQL 只读核对发现 HMN-606 取消请求卡在 RECOVERY_UNCONFIRMED，核实旧容器/后代退出后，通过已有 fenced 管理命令收尾该指定 attempt：cancelled / cleanup_state=completed，私有目录删除，正式视频保留。Redis 仅临时启动支持 owner 锁释放，随后恢复停止；没有迁移数据库或启动其他正式服务。现场权限与指定取消收尾已验收，更新后端 Compose 身份后的完整服务运行仍需用户合并代码并重新创建容器验收。

## 旧正式文件权限与覆盖备份修复（2026-10-06）

分支 `fix/legacy-resource-publication-permissions`，基线 `346d758`，提交标题 `[Fix] Back up legacy read-only assets before publication`。实际 scraper UID1000，但 SNOS-317.html 为 root:root 644，os.link 回滚备份触发 Linux protected_hardlinks EPERM；符号链接绑定资源根不是此次原因。上次运行目录修复未覆盖旧正式文件，本次补齐正式文件迁移 opt-in 及发布回退。

TaskAssets 先持久记录 journal，再在 DB fence 外建立旧备份，硬链接受限时分块复制、检查控制/归属、验证 SHA 并原子发布。复制失败/暂停保留正式文件；完成复制但未发布时回滚保留原正式 inode，不以备份副本替换未动过的目标。磁盘错误不隐藏，journal/fencing 与正式提升流程保持。权限脚本默认范围不变，增加 include-published 离线迁移选项。

专项资产/权限 40 项通过；真实 Docker UID1000、network none、临时 SQLite/root:root 644 文件，先实际复现内核 EPERM，再用完整 TaskAssets 验证发布与 DB 失败回滚通过；最终符号链接绑定源复验还覆盖复制完成后的暂停保留原 inode，三个真实内核 EPERM 场景均通过。完整 `uv run pytest tests/ --ds=django_project.refactoring_test_settings -v` 为 743 通过、28 跳过（85.14s），根目录 `pre-commit run -a` 全通过；命令/范围见执行记录的历史文件 `../../docs/legacy-resource-permissions-results.md`（已在 `0a9b457` 清理，可从该提交的父版本追溯）。钩子配置未修改。

现场在共享资源锁和目标锁内逐个修复 110 个旧正式文件的属主为 1000:1000，保留 inode/内容/大小/mtime；真实 scraper 对 SNOS-317.html 的 read/write access 均为 true，正式根目录剩余 root 文件为零。当前服务全程运行，未重启或自动重新抓取失败任务；用户的符号链接挂载可以保留。权限现场已验收，兼容发布代码需更新后端镜像，失败任务仍需重新提交；未宣称真实站点刮削发布通过。

## v2.4.3 本轮验收确认与文档修订

用户在本轮文档修订前明确确认“这轮改进验收完成”。本轮覆盖任务控制与详情、scraper 代理、原生下载续传、容器身份及旧正式资产权限兼容等改进；此前各阶段“需用户验收”的描述是当时记录，不再作为本轮整体未接受的结论。用户没有提供逐项运行日志、迁移清单或网关报告，本文不将该确认推导为所有外站、翻译模型、生产数据库迁移及独立 PostgreSQL 备份恢复专项均已验收。

最新完整隔离业务门槛来自 `bbe3288` 的执行记录：743 passed、28 skipped；真实 CLI、Docker 和 PostgreSQL fixture 的覆盖范围仍以对应历史章节为准。本次仅修改 Markdown，核对 `6801ea6..7a3d7f1` 的提交和当前模块契约；执行根目录 `pre-commit run -a`、相对文档链接检查及 `git diff --check`，不重跑业务探针、不修改运行数据或执行迁移。长期开发入口为[任务控制架构](task-control-architecture.md)，原 P0–P7 计划与报告保留追溯用途。

## v2.4.4 前端收尾与文档修订

前端改进范围为 `1ded0f6..6dc0450`，包括 HTML 语义、交互复用、features/shared/app 布局、请求归属、控件与页面反馈、主题及列表修复。用户在本轮明确结束前端改进；阶段命令与验证范围见[语义重构记录](../../vue_frontend/doc/semantic-refactoring-progress.md)和[UX 改进记录](../../vue_frontend/doc/ux-neutral-progress.md)。最近阶段 `6dc0450` 的前端 lint、60 项单元测试、构建及全仓库 pre-commit 通过；浏览器验证深浅主题品牌渐变一致性、控件对比度与加载状态，使用模拟 API，不推导为新增真实 worker、数据库或生产部署验收。

本次修订更新 2.4.4 变更日志、前端功能说明与前后端项目版本元数据，依赖版本与业务接口不变；核对文档链接，执行前端 check、后端 uv 锁文件一致性检查及根目录 pre-commit。清理对象限已合并本地分支与旧临时开发产物，不清理正式资源、任务资产、锁文件或数据库。

维护收尾：已删除 82 个合入 idle 的旧阶段分支；清理 227 个历史日志、截图、报告/备份和 9 个旧缓存、原型、空测试目录，约 256 MiB。保留 `/tmp/nassav-agent-worktree` 与文档规定的 `/tmp/nassav-browser-audit`。另一个仅含隔离测试设置及字节码的 `/tmp/nassav-task-control-p1-pg` 属主为 nobody，非交互 sudo 要求密码，需用户在本机清理；不涉及正式数据库。

## 推荐改进的验证范围（2026-10-07）

- 来源失败与详情预算：提交 `19b3b06`，后端隔离 **747 passed、28 skipped**。
- 持久推荐 worker 与控制 API：提交 `62bdf97`，后端隔离 **756 passed、28 skipped**。
- 前端异步跟踪：提交 `0d63de3`，`pnpm run check` **65 tests passed**，lint/build 通过。
  `recommendationJobs.cjs` 用模拟 API 验证成功、失败、后台取消请求、移动布局及路由卸载。
- 每阶段执行 `pre-commit run -a`；格式或类型失败修复后重新通过才合并 idle。
- 代理专项使用回环 HTTP/curl 验证生产装配的推荐页面、图片请求经过配置代理；
  Byparr 控制连接直连的既有回归同时通过。

尚未在目标环境应用迁移 0026、重启 worker，未验收真实 Jable、ProxyServer/Byparr、
Celery broker 或 PostgreSQL 并发；隔离 SQLite/模拟浏览器不覆盖这些环境边界。

最终黑名单核验与反馈一致性阶段：后端 **758 passed、28 skipped**，前端
**65 tests passed**。并发回归使用子进程临时文件 SQLite，移除写入 fence 的反例确实
触发并发旧值读取；恢复 fence 后最终点赞计数为 1。浏览器另覆盖未核验候选数量提示。
新架构与后续开发约束见[推荐架构](recommendation-architecture.md)。

## 代理抽象并发接入（2026-10-07）

公共能力阶段提交 `ec0e229`，完整后端隔离 774 passed、28 skipped，
`pre-commit run -a` 通过。消费者接入与本节随 `[Enhancement] Use proxy concurrency
for external search and recommendations` 提交，按本文档的 Git 历史可追溯。

接入回归覆盖外部搜索首屏、乱序、有序部分快照、空页短路和失败不写成功缓存；
推荐独立 seed、热门/最新发现及详情共享预算、取消后不合并、不同 provider 的生产
装配和真实隔离 SQLite 的线程连接/来源生命周期。临时 Unix socket Redis 另验证
三个 spawn 独立进程共同遵守两个槽位，故障失败和失租时保留其他 owner 的占用。
完整后端离线门槛 787 passed、28 skipped，全量 pre-commit 通过，钩子配置未修改。

实际 Byparr 3.0.4 的只读接入验证使用新公共 ProxyServer 接口及现有全局 Proxy.url，
容量为独立临时 Redis；共 5 次 Jable 请求，全部通过同站点、非挑战和业务结构校验。
两个详情并发总耗时 20.981 秒、两个列表并发总耗时 13.023 秒，结束后槽位为零。
未写正式 DB、Cookie、任务或推荐历史。脱敏记录位于
`/tmp/nassav-proxy-abstraction-live-results.json`。

这验证公共调度、真实 provider 传输和临时 Redis 的接入；未验证真实 Celery 推荐/外部
搜索完整 job、MissAV、目标 PostgreSQL 或实际 2 GB 容器容量，也未重启或修改生产配置。
默认 BrowserFetch 并发为 2，旧 FlareSolverr 配置默认 1；所有 API/worker 需统一配置
并重启加载。同 endpoint 的共享容量、取消/远端生命周期限制见[代理并发架构](proxy-concurrency.md)。

## 推荐预算收尾与进度（2026-10-07）

阶段分支 `fix/recommendation-budget`，提交标题 `[Fix] Bound recommendation detail work and preserve verified partial results`。
完整 `uv run pytest tests/ --ds=django_project.refactoring_test_settings -v`：794 通过、28 跳过。
新增隔离回归覆盖目标满足后停止、预算耗尽保留核验结果、黑名单命中继续补足、取消/硬超时
不被吞掉、版本进度与取消 fence、部分结果历史提交和无合格结果失败。
`pre-commit run -a` 为合并门槛，钩子配置未改；执行结果以阶段提交前检查为准。

这是隔离算法/DB/代理回归，不代表已部署的 Docker 推荐任务验收；未重启在线容器，
未提交真实推荐或改变正式数据。提前约 27 秒失败的历史原因仍待新诊断日志确认。

前端阶段 `fix/recommendation-progress-ui` 基于后端提交 `ef8ca31`，提交标题
`[Fix] Show recommendation progress and avoid cancelling failed jobs`。
`cd vue_frontend && pnpm run check`（lint、单元测试、构建）通过；
`NODE_PATH=/tmp/nassav-browser-audit/node_modules NASSAV_CHROMIUM_PATH=/usr/bin/google-chrome NASSAV_BROWSER_ORIGIN=http://127.0.0.1:4189 node tests/browser/recommendationJobs.cjs`
通过。浏览器仅使用模拟 API，覆盖进度、部分成功、失败不重复取消、主动取消、路由清理及
390px 移动布局；资源列表在成功后展示，运行阶段只展示进度计数。根目录全量
`pre-commit run -a` 为最终门槛，无钩子配置更改。仍需部署后完整真实任务验收。
