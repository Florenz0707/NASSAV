# Byparr 会话复用 P0 基线与放行记录

日期：2026-09-29。代码基线：`04ca7200bd532cbbb46a2895e0f099cc0384c164`。本记录对应[执行计划](byparr-session-reuse-execution-plan.md)的 P0。**状态：未放行；两时段现场对照和出口核验待完成。** P0 不修改页面策略或生产 Cookie。

## 固定环境

| 项目       | 本次已核对值                                                                                                                                              | 尚需核对                                          |
| ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------- |
| Django     | Compose `nassav-api-1`、默认 worker、下载 worker、scrape worker 各 1 个容器                                                                               | 容器镜像与此 Git commit 的构建对应关系            |
| 数据库     | Django 有效引擎 `django.db.backends.postgresql`                                                                                                           | PostgreSQL 服务版本                               |
| Byparr     | `nassav-byparr-1`，镜像 digest `sha256:874f719518f617d03a60e03411fc5d090647e1a877041e81f8dc965927c7deb6`；另有独立试验容器，须明确只使用正式 Compose 地址 | 正式容器请求日志中的实际代理路线                  |
| 页面策略   | MissAV、Jable 均为 `browser_first`；Byparr 已启用，超时 60 秒                                                                                             | 不切换策略，直到本站点放行                        |
| 直连代理   | `Proxy.Enable=true`；Django 直连从 API 容器发起，路线记为 `route-A`                                                                                       | 代理供应商是否轮换出口 IP                         |
| 浏览器代理 | `ByparrPageClient` 使用同一 `Proxy.url` 配置，转为 `X-Proxy-Server` 及单独认证头；容器回环主机名会映射为 `host.docker.internal`                           | 实测出口 IP 是否相同；相同代理 URL 不能证明同出口 |
| 域名       | Jable `jable.tv`，MissAV `missav.ai`                                                                                                                      | 两时段期间域名是否变化                            |
| 并发       | scrape worker `-c 1`，API 与其他 worker 仍可并发触发获取                                                                                                  | 试验时总并发数及代理出口记录                      |

以上仅记录脱敏的路线标识；不保存代理 URL、凭据、Cookie 值或完整 UA。数据库、策略和容器数量由运行中的 Django/Compose 只读查询；镜像 digest 由 Docker inspect 取得。

## 有效样本与对照协议

先从当时的站点列表或首页取得候选 URL，分别选至少三个 Jable 详情、三个 Jable 列表/搜索/分页和三个 MissAV 详情。每个候选先检查最终域名、挑战标记和对应业务结构：Jable 详情必须有 `hlsUrl`，Jable 列表按 `Jable._is_listing_page_html`，MissAV 详情按 UUID 与编号标题双条件。失效样本记录 HTTP 状态、校验原因和时间，替换后再计入有效样本。另记录不存在、挑战页、结构变化各一例；这些反向样本不得用于证明 Cookie 不能复用。

每个有效页面在两个不同时间窗口分别测：无 Cookie/默认 UA、旧 Cookie/默认 UA、浏览器 Cookie/默认 UA、浏览器 UA/无 Cookie、浏览器 Cookie+UA。再用同一组 Cookie+UA 请求另一有效详情页。每条记录保留目标状态、最终域名匹配、业务校验、毫秒耗时、浏览器调用数和会话首次/最后有效时间；浏览器的 `solution.status` 只作为提供方报告值。所有直接请求与 Byparr 控制请求都从同一 Django 容器发出。若代理轮换，分别测并记录两条请求的实际出口；出口未知时本站点不得放行。

已有方向性证据：9 月 29 日 Jable `Cookie+UA` 同页/跨页约 0.71/0.72 秒通过校验，旧 Cookie、仅 Cookie、仅 UA 为 403；详情见[执行计划](byparr-session-reuse-execution-plan.md)。该探测未完成本节的样本数、两时段和出口核验，不能当成 P0 放行。MissAV 的旧无效详情不计入样本；[此前试验](byparr-trial-results.md)的当前详情只证明浏览器页面结构可用。

[scripts/probe_byparr_session.py](../scripts/probe_byparr_session.py) 提供单页只读探测，默认不发送存储 Cookie 或浏览器 Cookie。完整会话重放需要显式 `--allow-session-replay`，只在获准的试验窗口运行；脚本不写数据库，标准输出只含状态、校验、耗时、Cookie 数量和 UA 是否存在。对照结果应存到不含凭据的 JSONL 记录，按两个时间窗口汇总。脚本每次启动浏览器一次；跨页面复用需要在同一批准的试验中把已获会话用于另一已验证详情页，目前尚未自动化。

## 页面获取与 Cookie 写入入口

| 入口                                                        | 页面路径或写入动作                                                                                                             | 并发边界                                                      |
| ----------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------- |
| `POST /api/resource`                                        | 旧同步添加，经 `ResourceService`、`SourceManager` 到 MissAV/Jable 详情                                                         | 多个 API 请求可并发；绕过 scrape 队列                         |
| `POST /api/resource/refresh/{avid}`                         | 旧同步刷新，同一资源服务路径                                                                                                   | 多个 API 请求可并发                                           |
| `POST /api/resources/batch` 的 add/refresh                  | 旧批量同步操作，同一服务路径                                                                                                   | 单请求内顺序；多个请求可并发                                  |
| `POST /api/resource/jobs` 和 `/api/resource/jobs/batch`     | Celery scrape 队列到资源服务和详情页                                                                                           | 单 scrape worker 当前 `-c 1`；与 API 并发，增加副本后也会并发 |
| Jable 外部搜索、演员/分类详情及推荐                         | `external_search.py`、`recommendation/jable_search.py`、`jable_page_lookup.py` 到 `Jable.search/get_*_videos/get_video_detail` | API 并发；Jable 页面缓存可能掩盖实际请求                      |
| `POST /api/source/cookie`，`auto=true`                      | `MissAV.set_cookie_auto` 浏览器首页或 `SourceBase.set_cookie_auto` 直连首页，写 `SourceCookieRepository`                       | API 并发；不走 scrape 队列                                    |
| `POST /api/source/cookie` 手动；`DELETE /api/source/cookie` | `SourceManager.set_source_cookie` 写入或置空                                                                                   | API 并发；与自动获取竞争                                      |
| `GET /api/source/cookie`                                    | 只读 Cookie 配置                                                                                                               | 不触发页面访问或写入                                          |

普通详情页的 Byparr 成功当前不写 Cookie；`MissAV.set_cookie_auto` 可写浏览器 Cookie，基类自动获取可写直连 Cookie。资源详情页进入前 `SourceManager.refresh_source_cookie` 读取仓库及缓存并更新共享 Source 实例的 `cookie`。这些路径是 P1/P3 的接入边界。

## 当前判定与剩余证据

Jable 与 MissAV 均保持 `browser_first`。Jable 需补齐三个有效详情、三个列表/搜索/分页、反向样本、两个时段的全部对照和同/跨页复现，并证明浏览器与直连实际出口一致。MissAV 还需先取得三个现时有效详情，再独立完成相同核验。此前的单页结果不推断会话寿命。未完成这些项目时，不启动 P1 的站点切换或宣称提速已成立。
