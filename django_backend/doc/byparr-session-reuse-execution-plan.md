# Byparr 会话复用与直连优先执行计划

日期：2026-09-29。状态：待实施。本文接续 [Byparr 迁移计划](byparr-migration-plan.md) 和 [异步刮削计划](async-scraping-compose-plan.md)，只规划页面获取提速；不在本次计划中实现代码。既有数据库迁移和 Compose 部署以当前仓库为准，不沿用旧计划中关于 SQLite 或宿主机服务的历史假设。

## 目标、范围与决策

目标是在有效的浏览器会话可供直连复用时，避免每条页面请求都等待 Byparr。`browser_first` 仍先访问浏览器，`direct_first` 先尝试带站点会话的直连；直连遇到 403、挑战页或其他既有失败时按明确规则回退浏览器。浏览器获取到的 Cookie 与实际 User-Agent 必须成对验证、保存、读取和使用。会话刷新在跨 API/worker 的并发场景下按站点合并；不同详情页仍各自获取页面。

本次范围：MissAV/Jable 页面获取链路、`SourceCookie` 及缓存、Byparr 响应提取、直连结果分类、站点级刷新协调、Cookie 管理接口与设置页的必要兼容、配置、测试、监控日志和上线回滚。允许重构上述边界，但继续复用 `PageFetchService`、`SourceManager`、`SourceCookieRepository` 和现有 Celery/Redis；不改资源表、下载进度通道、推荐排序或 Byparr 服务实现。Jable 列表/搜索/推荐也走页面获取链路，必须纳入回归；媒体下载只做必要回归，不把播放清单 Cookie 改造混入首轮。

当前事实：`PageFetchService` 已支持两种优先顺序，但普通浏览器页面的 Cookie/UA 未持久化；直连 403 被 `SourceBase` 折叠成空结果；`SourceCookie` 只存 Cookie；`scrape-worker` 并发 1，旧同步资源接口及 `POST /api/source/cookie` 的自动获取入口仍可绕过该队列。当前配置模板与运行配置的 MissAV/Jable 均为 `browser_first`。既有 Redis 资源锁按 AVID，不等于站点会话刷新锁。

2026-09-29 的只读探测提供了方向，但不能代替上线验收：Jable 旧 Cookie、单独的新 Cookie 和单独的浏览器 UA 均返回 403；Byparr 新 Cookie **加对应 UA** 后，同页和另一详情页分别约 0.71/0.72 秒通过页面校验，Byparr 两次约 14.82/15.32 秒。MissAV 旧样本的页面未通过现有详情校验，尚无可复用结论。Cloudflare 的通行状态可能随时间和会话行为失效，因此 HTTP 200、Cookie 存在和 `solution.status=200` 都不能单独视为有效页面。[Cloudflare clearance](https://developers.cloudflare.com/cloudflare-challenges/concepts/clearance/)；[Byparr 请求模型](https://github.com/ThePhaseless/Byparr/blob/main/src/models.py)。

## 固定行为契约

| 条件                             | 页面路径                            | 会话处理                                                                         |
| -------------------------------- | ----------------------------------- | -------------------------------------------------------------------------------- |
| `browser_first`                  | 先浏览器，页面无效才按既有规则直连  | 有效浏览器页可提取候选会话，但仅在验证可直连后写入；不因每次浏览器成功而重复写库 |
| `direct_first`，会话可用         | Cookie 与配套 UA 在同一次直连中使用 | 有效页面立即返回，不启动 Byparr                                                  |
| `direct_first`，无会话或会话过期 | 允许一次普通直连；失败再浏览器      | 不把“有 Cookie”当成访问前提                                                      |
| 直连 403 或挑战页                | 浏览器回退；尝试刷新站点会话        | 只有目标页有效且新会话经短时直连验证后才替换旧会话                               |
| 直连超时、连接失败、结构不匹配   | 保留已有有限回退                    | 记录原因；不把全部故障都标为 Cookie 过期                                         |
| 显式 404、候选页不存在           | 保持现有候选 URL 和页面校验语义     | 不刷新会话；是否跳过无益的浏览器尝试须有回归证据                                 |
| `direct_only` 或 Byparr 不可用   | 仅按现有直连能力返回                | 不触发自动刷新；不可用结果不覆盖已有会话                                         |

每个候选 URL 每条路径最多请求一次。回退获得的浏览器页面可直接完成**本次**业务请求；新 Cookie 的直连验证失败仅表示不得将其标为可复用，不应将本次已验证的浏览器页面改判失败。Cookie 可复用失败时，站点级 single-flight 不能让不同页面免于各自的浏览器请求；需要另行测量该场景的瓶颈，不得宣称已完成提速。

## P0：基线与试验放行

1. 固定测试环境的代码版本、Byparr 镜像 digest、数据库引擎、配置策略、代理拓扑、每站点域名和 worker 副本数。标明 Django 直连与 Byparr 是否走同一代理配置及实际出口；若代理轮换 IP，要单独记录，不能以相同代理 URL 推断相同出口。只记录脱敏的路线标识，不记录代理凭据或 Cookie 值。
2. 选至少 3 个当前有效的 Jable 详情页、3 个列表/搜索/分页页和 3 个 MissAV 详情页，另选不存在页面、挑战页及结构变化样本。先验证页面结构，剔除失效样本时记录原因，不用失效页面推断 Cookie 不可用。
3. 在两个时段分别比较：无 Cookie/默认 UA、旧 Cookie/默认 UA、浏览器 Cookie/默认 UA、浏览器 UA/无 Cookie、浏览器 Cookie+UA，以及跨页面复用。记录每组状态、业务校验、耗时、浏览器调用次数与 Cookie 有效时间；样本从同一 Django 容器、相同代理路径发出，探测不更新生产 Cookie 表。
4. 列出所有调用页获取及 Cookie 写入的入口，包括旧同步资源 API、任务 API、Jable 发现/搜索/推荐、MissAV 自动 Cookie 与人工设置/清除。明确哪些入口仍允许并发。

**P0 放行：** Jable 至少在同页及另一有效详情页复现 Cookie+UA 的直连成功；同一组实验能区分 Cookie 和 UA 的作用；MissAV 只有得到有效页面样本后才能单独放行。任何站点若代理出口不一致或有效页面无法直连复用，保持 `browser_first`，继续做浏览器可用性维护，不切 `direct_first`。

## P1：会话模型与兼容迁移

1. 在现有 `SourceCookie` 表上增加可空的 `user_agent`、`expires_at` 和 `egress_profile`。保留 `source_name` 主键、Cookie 字符串与 `updated_at`；不建新表，不存完整 TLS/浏览器指纹、原始代理 URL、账号密码或公网 IP。`egress_profile` 是由**有效代理路由配置**计算的稳定不透明标识，不是出口 IP 证明；标识由包含代理身份要素的规范化路由配置经服务端密钥摘要得到，不保存原始代理凭据。若无法确定 Byparr 与直连出口一致，标记未知并不启用该浏览器会话的自动直连复用。
2. 执行可回退的增量 migration，旧记录保持原 Cookie、空 UA/过期时间/路由标识。旧记录继续用现有默认 UA 尝试一次直连；首次 403 后按新流程刷新。未知过期时间不等于永不过期，实际 403/挑战页优先于时间推断。
3. 将 Cookie 与 UA、到期时间、路由标识、`updated_at` 作为一个不可分割的会话快照从 repository、Django 共享缓存和进程内缓存传递。一次更新只写一组字段；手动 Cookie 无 UA 时清除上次自动取得的 UA/到期/路由信息，删除 Cookie 时所有元数据一并清空。保留旧 `set_source_cookie(name, cookie)` 调用语义，避免其它源的人工 Cookie 行为回归。
4. 用现有 `updated_at` 作为写入前版本检查：Byparr 请求开始时记下版本，写入前在短数据库事务内核对；如人工设置/清除或另一刷新已更新记录，旧浏览器结果不得覆盖较新的值。数据库事务不跨越几十秒的网络请求。PostgreSQL 与 SQLite 测试都需覆盖旧记录迁移及并发写入；正式环境以 PostgreSQL 验收。
5. 评估全局 Source 实例的可变 `cookie` 字段。页面直连应拿一次不可变会话快照组成请求头，避免 API 并发期间 Cookie 与 UA 分别来自不同版本。下载等其它旧调用可保留兼容路径，但不能把不完整会话写回表中。

**P1 放行：** 迁移前后源记录数与 Cookie 内容一致；旧 `GET/POST/DELETE /api/source/cookie` 可用；手动覆盖、清除、跨进程缓存刷新和旧结果晚到均不会产生 Cookie/UA 错配；日志和测试失败输出无 Cookie 或代理凭据。

## P2：直连、浏览器回退与会话验证

1. 让 `SourceBase.fetch_page` 把目标 HTTP 状态、最终 URL、请求耗时和失败类型传给 `PageResult`，不再让 403 只表现为 `EMPTY`。保留 `last_error_code` 对现有资源错误映射的兼容。403 与 HTTP 200 挑战页分开记录；Byparr 的 `solution.status` 仍视为提供方报告值，不替代 HTML 及站点结构校验。[Byparr 响应实现](https://github.com/ThePhaseless/Byparr/blob/main/src/endpoints.py)
2. 将 Cookie、浏览器 UA、直连 `impersonate` 和代理路由的选择集中在页面请求边界，不在 MissAV/Jable 各写一套。优先保留项目 `curl_cffi` 直连能力；P0 实测的 Firefox UA 搭配现有 `chrome110` 只说明当前 Jable 可用，后续指纹策略应以有效页面回归判定，不假设 UA 字符串足以长期通过。
3. 只从**通过同站点、非挑战、站点专属业务校验**的 Byparr 结果提取会话。筛选适用于目标主机及路径、未过期的 Cookie；保留原站点所需 Cookie，不能只截取 `cf_clearance`。空 Cookie、空 UA、异站 Cookie 或校验失败不覆盖已有会话。若不同路径存在同名 Cookie，定义明确选择规则，避免拼接出歧义的 Cookie 头。
4. 对待持久化的新会话做一次初始总预算 3 秒的独立直连探测，要求目标 HTTP 200、同站点、无挑战且业务结构有效；探测失败时仍返回本次有效浏览器页面，但不标记会话可复用。浏览器本来用于页面回退，不为单纯保存 Cookie 额外访问首页；浏览器每次成功但会话未变化时不反复写库。
5. 明确对候选 URL 的行为：MissAV 原有候选顺序、Jable 详情/搜索/列表校验及缓存保持一致；页面无效不得进入资源解析、推荐缓存或 Cookie 持久化。一次调用限制直连重试和浏览器次数，防止 403→刷新→再次 403 的循环。

**P2 放行：** 有效已暖会话只产生一次直连且不调用 Byparr；冷会话/403 在一次浏览器回退后完成本次页面；无效浏览器页、错域、过期 Cookie 和失败探测不会污染数据库；`browser_first`、`direct_first`、`direct_only` 均有离线契约测试。

## P3：按站点合并刷新与管理入口

1. 仅在准备**获取或替换共享会话**时加锁，锁键按规范化源、目标主机和出口标识划分；不要锁住所有直连，也不要把不同详情页的正常抓取错误地合并成一个页面结果。复用项目 Redis 客户端与按持有者释放的锁模式，使用 `SET NX` 加有限租期、唯一 owner、持有者校验释放；租期须覆盖 Byparr 超时、短探测和收尾余量，当前 Byparr 60 秒预算下初始租期为 90 秒；配置超时提高时按控制请求上限、直连探测和收尾余量提高租期，并安全续租。失去锁后禁止写回。[Redis 锁建议](https://redis.io/docs/latest/develop/clients/patterns/distributed-locks/)
2. 持锁者在调用 Byparr 前重新读取会话版本，若另一请求已经刷新且新会话可直连，则直接复用。等待者有限等待、退避并读取共享会话；取得新版本后仅重试一次直连。锁超时、持有者崩溃或 Redis 不可用时，本次页面允许无锁浏览器回退，但不保存共享会话；不能无限等待、丢失本次有效页面或把空会话写入表中。正常的 browser_first 页面请求不在浏览器访问前排队，保存候选会话时只用版本检查。
3. 把旧同步资源接口和 `POST /api/source/cookie` 自动获取入口纳入同一会话协调；不能只在 Celery worker 中加锁。人工设置/清除仍立即生效，靠 P1 的版本检查阻止较早启动的自动刷新反向覆盖人工结果。
4. 如站点浏览器 Cookie 经验证不能转给直连，短时间内记录“不可复用”结果，避免并发调用都做相同的直连探测；这一状态不应阻止各不同页面通过 Byparr 获取业务内容，也不写入长期有效的假 Cookie。

**P3 放行：** 同站点至少 10 个并发 403 请求中，一次可复用会话刷新最多调用一次 Byparr，等待者复用新版本；不同站点不会互锁。覆盖锁超时、owner 崩溃、租期过期后旧 owner 返回、Redis 断连、人工设置与自动刷新竞争；无死锁、无限重试、旧值覆盖新值。若会话不可复用，测试明确显示 single-flight 无法省去不同页面的浏览器获取。

## P4：管理体验、配置和观测

1. Cookie 管理接口保留现有 `source/cookie/mtime` 输出及 `source/cookie/auto` 输入；为人工设置增加可选 `user_agent`，缺省不沿用旧自动 UA。可追加非敏感的会话来源、UA 是否配套及过期状态，但不得在任务事件、Redis 快照或普通日志输出 Cookie 值。
2. 设置页为人工 Cookie 提供可选 UA 输入，并清楚显示“已保存”和“已验证可直连”的区别；自动获取仍使用既有入口。只在界面确需展示时扩展前端 API，不改变资源任务与下载进度协议。
3. 在配置模板中维持 `browser_first` 为安全默认；新增会话复用开关时默认为关闭，并定义显式关闭后回到原页面路径的语义。`direct_first` 按源切换，先 Jable 后 MissAV；代理配置变化后，旧 `egress_profile` 不可误用。配置变更须重启 API 和持有 Source 实例的 worker。
4. 记录可聚合的源、路径、状态、失败原因、浏览器次数、会话版本、锁等待和耗时；不记录 Cookie、完整 UA、原始代理或完整页面。区分任务队列等待、直连耗时、Byparr 耗时、总抓取耗时，避免只看 API 的 202 响应时间。
5. 同步更新 `doc/database.md`、`doc/interface.md`、`doc/configuration-contract.md`、`doc/proxy-routing.md`、`doc/debug.md` 和测试说明。文档应解释旧 Cookie 的处理、会话过期与人工更新、锁粒度、代理出口前提、配置开关及回滚步骤。

**P4 放行：** 旧前端与旧 API 请求不报错；手动无 UA 更新后不误用历史 UA，自动取得的新会话状态准确；开关关闭及恢复不需要清库；脱敏日志能重建一次 403→等待/浏览器→完成的流程。

## P5：测试、灰度与正式验收

1. 离线测试覆盖 P1–P4 的状态组合、策略顺序、错误分类和并发时序。真实站点测试显式启用，默认测试不访问外网、不写生产库；在线测试不能把服务不可用标成跳过通过。迁移在空 SQLite、空 PostgreSQL 和含旧 Cookie 的 PostgreSQL 数据副本上演练。
2. 联调从 Jable 的 `direct_first` 开始，MissAV 保持 `browser_first`。测两时段、每时段至少 20 个有效详情/列表请求，至少 3 个不同详情页，并分别记录冷会话、暖会话、过期回退及浏览器调用率；反向样本包括 403、200 挑战、404、空列表、错域和结构变化。MissAV 须独立达到同样的页面有效性和复用证据后才切换。
3. Jable 首批放行门槛：暖会话有效页面率至少 95%，**挑战页或错误页面误判成功为零**；暖请求 P95 小于 5 秒，且低于同环境 Byparr 单页耗时中位数的 25%；一次可复用会话更新后，连续 10 个不同页面至多触发一次刷新 Byparr 调用。样本、分母、缓存命中和代理出口必须公开记录；未达到门槛就保持该源 `browser_first`。
4. 并发测试分别在现有 scrape worker `-c 1` 与并发 2/同步 API 混合场景执行；检查 Byparr 调用数、Redis 锁、数据库版本、容器内存和任务最终状态。下载进度、媒体下载、Jable 搜索/推荐缓存、手动 Cookie CRUD、资源添加/刷新及 WebSocket 状态查询都做回归。
5. 实施时执行相关测试、`cd django_backend && uv run pytest tests/ -v`、前端改动后的 `cd vue_frontend && pnpm run build && pnpm run lint:fix`，最后在仓库根目录执行 `pre-commit run -a`。记录命令、环境、成功/失败数及未执行原因；有失败不能宣称完成。
6. 灰度先仅启用 Jable；观察至少 24 小时，记录直连有效率、403 比例、浏览器调用率、P50/P95、锁等待、失败回退与任务完成率。出现错误页面入库、持续 403 循环、锁等待无上限、Cookie 人工更新被覆盖，立即停止灰度。

## 上线与回滚

先备份 PostgreSQL 与运行配置，记录镜像版本和两源当前策略；完成兼容 migration 后部署代码，但保持会话复用关闭和原策略。验证旧 API、任务与 Cookie 管理，再仅对 Jable 开启会话复用和 `direct_first`。MissAV 另设放行记录，不能因 Jable 成功而自动切换。

首选回滚为关会话复用、把受影响源恢复 `browser_first`、重启 API/worker；保留新表的可空字段和已有 Cookie，不做破坏性数据库回退。若代码回滚到旧版本，先确认旧 ORM 可忽略新增字段，核对迁移兼容性和备份恢复点；不在服务运行中删列。回滚后验收资源任务、Cookie API、页面结构、下载进度与状态反馈，记录停用时间和触发指标。

## 实施拆分与交付清单

| 批次          | 主要落点                                                                                                 | 独立可审阅交付                                  |
| ------------- | -------------------------------------------------------------------------------------------------------- | ----------------------------------------------- |
| A：会话数据   | `nassav/models.py`、migration、`source/CookieRepository.py`、`CookieRuntimeCache.py`、`SourceManager.py` | 旧数据兼容、会话快照、版本保护及数据库测试      |
| B：请求与回退 | `source/SourceBase.py`、`page_fetching/`、`MissAV.py`、`Jable.py`                                        | 直连状态、配套 UA、有效浏览器会话提取与回退测试 |
| C：并发协调   | 独立站点会话刷新模块，接入旧 API 与 worker 共用链路                                                      | Redis 锁、等待/故障处理、并发测试               |
| D：界面与配置 | `config/template-config.yaml`、Cookie API 序列化/视图、`SettingsView.vue`                                | 人工 UA、状态展示及兼容测试                     |
| E：部署验收   | 本文对应的数据库/接口/配置/代理文档、测试记录                                                            | Jable 灰度与回滚演练；MissAV 单独准入           |

建议按上述批次分提交，分别使用仓库既有的 `[Feat]`、`[Enhancement]`、`[Doc]` 前缀。任一批次未达到该阶段放行条件，不进入依赖它的下一批次。
