# 在线播放实现与开发契约

设计见[方案](online-playback-design.md)，真实来源边界见[P0](online-playback-p0-report.md)。本文件维护已实现的行为，不将尚未部署的功能当作目标环境验收。

## P1 会话与准备

新增可逆迁移 0029，表 nassav_playback_session。PlaybackSession 独立于 TaskJob 和正式资产：删除资源级联撤销会话，来源事实缓存不级联删除。用户与当前登录摘要绑定，跨登录的相同用户也不能读取或关闭另一会话。退出登录关闭该登录会话；媒体请求仍须重新检查登录授权。

状态为 queued、resolving、ready、failed、closed；ready 表示已取得播放描述，尚不代表视频解码/目标设备成功。每次提交使用 UUID request_id，同键换资源冲突；每用户最多 2 个未过期活动会话。close 使用 expected_version/request_id，重复关闭命令幂等，关闭递增 generation 和 version、清除描述，旧 worker 不能发布缓存或 ready。

生产开关 NASSAV_PLAYBACK_ENABLED 默认 false；本地与 Compose 环境模板已说明，Compose 显式传入所有后端入口。开启前必须统一 API/worker 版本并应用新增迁移；本轮不执行正式迁移。P2 已提供受控媒体入口；P3/P4 已提供播放器和有界失效刷新；目标环境覆盖与发布条件见[验收记录](online-playback-acceptance.md)。

Celery nassav.tasks.playback_prepare_task 只运输会话 UUID，在 scrape 队列执行来源准备。网络在短 DB fence 外，领取使用 execution_id/generation 与 90 秒租期，网络控制回调续租，300 秒准备期限包含排队。过期或失租不重用执行身份；关闭、资源删除或取消后的旧执行不得发布。没有下载器、图片、HTML、翻译或业务资源保存副作用。

worker 自带恢复循环有界补派 queued、收尾超时/失租、清理超过 24 小时的终态记录；补派最多每 30 秒一次，批次默认 100。不依赖 Beat。TASK_RECOVERY_ENABLED=false 会关闭恢复驱动，应监控 queued；授权状态查询仍检查到期，不无限展示待准备。

SourcePlaybackResolver 消费独立 source scope 和 ProviderFactsCache，复用在线专用 online-playback-v2，隔离来源域名、出口和源站会话版本；沿用 ResourceCache.PlaybackTTLSeconds。旧 playback-v1/m3u8-only 缓存不复用。只获取来源事实，保留实际 Referer、固定 UA、代理路由摘要与源站会话版本。首期 CDN Cookie 策略为 omit，不能向 CDN 无条件转发源站 Cookie；其他来源需要 Cookie 时必须显式扩展带作用域的描述及回归。

P1 尚不承诺根清单的 URI/DNS/媒体能力验证；P2 必须在受控目标策略下完成此步，再提供清单。不能让 P1 准备器在缺少目标策略时直接请求原站返回的任意地址。

## HTTP 契约

三个控制入口保持 code/message/data、operator 登录与 CSRF，响应 no-store；客户端不获取上游 URL、Referer、UA、登录摘要或代理凭据。

| 接口                                                  | 行为                                                                                        |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| POST /nassav/api/resources/{avid}/playback-sessions   | UUID request_id；202 返回 session_id/state/version/generation/allowed_actions；仅已入库资源 |
| GET /nassav/api/playback-sessions/{session_id}        | 当前登录拥有者授权快照；不存在/另一登录 404                                                 |
| POST /nassav/api/playback-sessions/{session_id}/close | expected_version、UUID request_id；版本冲突 409，成功 200                                   |

开关关闭返回 404；匿名 401、非 operator/CSRF 拒绝 403、非法参数 400、容量或版本冲突 409。准备失败只返回 preparation_failed 等公开错误码，不暴露来源异常中的地址或凭证。

## 验证边界

P1 专项 test_playback_sessions.py 覆盖身份/CSRF、提交幂等与容量、关闭/退出登录 fencing、资源删除、补派/失租、失败脱敏以及缓存版本/源站会话隔离。新增接口在 test_http_contracts.py 显式声明，保留原 HTTP/OpenAPI 快照。隔离 SQLite、独立 PostgreSQL 16 均执行 0028→0029→0028→0029；正式数据库迁移和真实 worker 调用仍须部署验收。

根 pre-commit 与完整隔离 pytest 是每阶段门槛。提交与实际结果见 Git 历史和阶段收尾，后续播放链路变更继续维护本文件。

## P2 异步 HLS 网关

ready 查询返回带短期签名的同源 manifest_url，不泄漏上游地址。GET/HEAD manifest/{asset_id} 与 assets/{asset_id} 同时校验当前登录、用户、会话 generation、idle/absolute 期限、资源存在和代理路由。关闭、退出登录或资源删除后立即拒绝新请求；在途请求每 0.5 秒复核并关闭上游、释放容量。签名链接不能脱离登录分享。

manifest 模块有界解析 VOD，将多级/音轨清单、相对地址、签名查询、AES-128 密钥、初始化段注册为 Redis 私有映射，保留 IV 和 byte range。仅支持 identity AES-128；直播、LL-HLS、变量替换、未知 URI 扩展和 DRM 明确拒绝。清单上限 1 MiB、20,000 行、10,000 引用，单会话最多 10,000 资产、嵌套深度 8；映射 TTL 不超过剩余绝对期限且最多 4 小时。关闭后授权失效，映射自然过期，不在线删除共享锁。

policy 只接受 HTTPS/443、无凭据/片段的显式允许域名，逐跳验证重定向及全部 DNS 结果，拒绝非公网地址。默认 transport 改为 CurlPlaybackTransport，以项目 IMPERSONATE 浏览器模拟能力读取媒体；HTTPX Adapter 保留为替换实现，不做隐式失败回退。禁止自动重定向和 Cookie/Authorization 转发，禁用环境代理改写。直连通过 CURLOPT_RESOLVE 固定已验证 IP，同时保留原始域名、Host、SNI 和证书验证。媒体沿用全局 Proxy.url，不使用 Proxy.download_url 或静默回退；Byparr 不参与媒体请求。

代理的最终 DNS/CONNECT 目标由代理解析，本机 DNS 检查不能保证其一致。必须确认代理自身拒绝私网/保留地址，再设置 NASSAV_PLAYBACK_PROXY_TARGETS_TRUSTED=true；否则拒绝代理媒体请求。此配置不会自动创建代理 ACL。

Redis 原子容量由全部 API 进程共享，全局默认 16、每会话 4；容量不足返回 429，不排队。owner 租约 45 秒、每 10 秒续约，失租停止，只释放自身 owner，进程崩溃后自然到期。媒体单请求总期限 45 秒、读取期限 15 秒、连接 5 秒，单段上限 16 MiB、读取块 16 KiB，不落盘或整段缓存。仅清单、16 字节密钥及最多 64 KiB 附属数据有界缓冲。

GET 支持单一 bytes Range，验证真实 206/Content-Range/长度，不伪造部分响应；HEAD 不读取媒体体。拒绝 HTML、异常编码和超大响应，过滤 Set-Cookie/Location 等上游头。响应 no-store；头发送前返回脱敏错误，发送后失败只能中断流。Django 原生异步 ASGI 入口负责断连清理；Nginx 媒体路径禁用缓冲/缓存；Nginx 和 Uvicorn 访问日志移除能力查询串。

### 配置与部署

- NASSAV_PLAYBACK_ENABLED 默认 false；开启前在维护窗口应用 0029，统一 API、scrape worker 和 Nginx，确认恢复驱动启用。
- NASSAV_PLAYBACK_ALLOWED_HOSTS 默认空，拒绝全部目标；配置逗号分隔的已审核域名或 *.example.com，包含清单、音轨、密钥与分段所需域名。
- NASSAV_PLAYBACK_PROXY_TARGETS_TRUSTED 默认 false；仅在代理目标 ACL/DNS 边界核查后开启。
- NASSAV_PLAYBACK_MAX_MEDIA_REQUESTS 默认 16，允许 1–128；结合带宽/内存调整，Redis 必须可用。

本轮不执行正式迁移或部署。P3/P4 已实现，P5 长期与目标设备验收仍按[记录](online-playback-acceptance.md)分项维护；ready 不代表所有资源或设备可解码。

### 验证范围

专项覆盖 URI、AES 密钥、fMP4 初始化引用、恶意目标/DNS、Range、取消、慢读取及关闭。真实隔离 Redis 验证代次、容量所有权和跨进程限额；完整 Django ASGI 路径验证登录、签名、Range 与 disconnect。Unix socket TLS 测试使用真实 HTTPX、证书与 16 MiB 上游，验证 Host/SNI、按需读取、提前关闭及小于 3 MiB 的跟踪内存峰值。这些隔离验证不替代 CDN、代理 ACL、容器多客户端和浏览器解码验收；fMP4 当前验证清单引用，未新增正式播放器解码验收。

## 阶段执行记录（2026-10-10）

P1 提交 dbb243f 已经合并 idle：完整隔离 pytest 868 passed / 28 skipped，pre-commit run -a 通过；SQLite 和独立 PostgreSQL 16 完成 0028→0029→0028→0029。P2 使用独立 feat/playback-p2 分支，提交身份以 Git 历史为准；门槛为完整隔离 pytest、pre-commit run -a、前端 pnpm run check 与无网络临时 Nginx 容器 nginx -t。所有测试只验证隔离行为，不执行正式数据库迁移、容器部署或 P3 页面接入。

## MissAV 媒体传输修复（2026-10-11）

现场对照中，同一新地址、全局代理和请求头下，HTTPX/普通 curl 返回 403 HTML，Chrome 模拟 curl 返回 200；只修改 UA 无效。这证明需要浏览器模拟传输能力，但不单独断言某个 TLS 扩展是根因。能力通过 PlaybackTransport 装配，不在网关按来源分支；Jable 和 MissAV 使用同一适配器。

curl_worker 是私有单请求协议进程，不是 Celery 业务任务：不初始化 Django、不访问 DB/Redis、不保存媒体。请求及代理凭据只通过 stdin 传入，stderr 不收集；stdout 首行是有界元数据，之后为媒体字节。单 hop 独立进程/句柄，无 Cookie jar，每次重定向先销毁旧进程再验证新目标。无 shell、不使用外部 curl 可执行文件或默认 AsyncSession stream。

子进程同步 WRITEFUNCTION 以最多 16 KiB 块写入阻塞管道；父进程 asyncio StreamReader limit=16 KiB，消费者变慢时管道自然背压，不使用无界生产队列或 communicate 整体收集。管道、TLS/内核缓冲和进程基础 RSS 仍存在；单请求一个进程带来额外内存/启动成本，部署并发应结合实际 RSS 调整，不能将跟踪 Python 内存当完整 RSS。

关闭先取消在途管道读取，再 terminate 子进程，边有界排空残余管道边等待退出；1 秒未退出则 kill 并回收。不能仅等待 wait 而不处理暂停的 stdout，否则可能死锁。网关释放容量前退出该 hop；进程崩溃保留 owner 租约自然过期机制。父进程被杀时无业务状态写入者，子进程断管退出或最长 45 秒传输期限终止。

保留 HTTPS 域名/DNS/代理可信边界、逐跳验证、Range/大小/HTML 校验、签名和登录授权，控制接口/迁移/配置项不变。新增测试覆盖真实本地 TLS 背压、取消、强杀回收、模拟配置/DNS 固定、重定向拒绝和生产装配；现场候选复测不等于运行容器已经部署修复，也不替代正式登录会话或播放器解码验收。

参考：[libcurl 写入回调](https://curl.se/libcurl/c/CURLOPT_WRITEFUNCTION.html)、[固定 DNS](https://curl.se/libcurl/c/CURLOPT_RESOLVE.html)、[Python 子进程管道与等待](https://docs.python.org/3.12/library/asyncio-subprocess.html)。

2026-10-11 现场候选复测：在现有 API 容器以临时模块加载修复 Adapter，仍使用生产网关/域名策略和全局代理；MissAV ADN-495 新清单完成重写，首段 206/65,536 字节，域名 surrit.com；Jable SONE-411 同样通过，AES 密钥 200/16 字节，首段 206/65,536 字节。来源刷新只保留在内存，DB 写入被拒绝，资产映射/容量为探针私有内存，未创建正式会话或修改部署。故此证据验证传输修复与媒体协议，不验证正式 Redis 容量、登录会话生命周期或解码。

## P3 详情页播放器

资源详情的在线播放按钮打开同源 `/play/:avid` 新标签页，由该页拥有会话和播放引擎；页面卸载和 pagehide 执行清理，原详情页退出不影响播放。保留下载及本地路径操作。前端会话及引擎的所有权、清理和测试入口见[前端契约](../../vue_frontend/doc/development-contracts.md#在线播放器p3)。本地合成视频验收与正式 worker/媒体联调分开记录；正式 HTTPS 与真机验收已按用户要求跳过，长期播放及 Firefox 历史超时仍保留验证限制，见验收记录。

## P4 有界失效刷新

迁移 0030 为会话增加 refresh_count 与 manifest_identity，不修改正式资源/下载缓存。refresh 接口使用登录/CSRF、版本与命令 UUID，同一会话只允许一次；并发请求合并到同一次准备，切换 generation/execution UUID，保留绝对期限和兼容基线。准备强制更新 online-playback-v2，通过显式 validator 在事务外核查新清单后才能发布 ready；取消、删除、失租或超时后的旧执行无法发布。

网关记录实际已读取清单的规范化结构 SHA-256：替换 URI 为按引用位置确定的标识，保留轨道、CODECS、时长、媒体序号、IV、BYTERANGE 等。AES 密钥和 fMP4 初始化段分别记录完整字节哈希；数据库不保存原 URL、密钥或媒体字节。128 条有界基线包含所见清单的待读取密钥/init 依赖，未补齐时不允许刷新。普通初始化段最多 256 KiB；仅 Range 读取的 init 暂不支持自动刷新。刷新验证最多 120 秒、共用生产目标策略/来源代理/Redis 容量，所有清单再次解析；结构、密钥或 init 不兼容即 media_identity_changed，不自动恢复位置。相同结构不能证明远端视频字节恒等，此处只承诺保守兼容检查。

上游 401/403/404/410 统一返回 source_access_failed/410，表示来源拒绝读取，不断言一定是签名过期。hls.js 的该类读取失败（包括非致命事件）只请求一次会话刷新，暂停旧加载，重新准备成功后恢复本次位置及播放/暂停意图；其他错误显示明确重试。原生 HLS 无法可靠提供 HTTP 状态，错误走显式重试，不猜测自动刷新。会话轮询保留同代次已签发入口，避免重新签名触发播放器重复销毁。关闭/pagehide 尽力关闭，TTL 及 worker 恢复循环兜底；既有 30 分钟空闲、4 小时绝对、24 小时终态清理不变。

## P5 验收与部署入口

阶段提交、隔离/真实协议/浏览器覆盖、尚未满足的设备和长时条件，以及更新与回滚步骤维护于[在线播放验收记录](online-playback-acceptance.md)。新版本须统一 API、所有 worker 和前端/Nginx，并应用 0030；本轮不更新用户的正式容器或正式数据库。

### 清单刷新校验的非语义字段

身份摘要忽略注释、空行及未识别扩展标签，保留已支持标准标签与引用拓扑（RFC 8216 6.3.1）。私有签名 token 不构成媒体身份；时间轴、轨道、加密/init 等变化仍拒绝恢复。新旧摘要算法不得混跑，更新前关闭旧会话。

## 容量租约的取消边界

容量申请以有界 Redis 线程执行，HTTP 取消不能终止线程。申请任务必须在 shield 下等待；取消或回包失败时先等申请落定，再按本次 owner 补偿释放，不能留下迟到写入。正常释放由唯一清理任务负责，多个释放调用共同等待；重复取消不能打断停止心跳、等待已有续租及 Redis owner 删除。取消仍传播给调用者，不把断连变成成功响应。

`async_cleanup.finish_owned_task` 只等待已明确归属且自身有时限的操作，供媒体进程与容量清理复用；不得用于无限网络等待。生产 Redis socket/connect timeout 保持2秒。释放遇 Redis 不可用仅记录脱敏告警并保留既有45秒租约/90秒key TTL兜底，不删除其他owner，不宣称已主动释放。

回归先复现申请取消、释放重复取消、Redis写成功后回包丢失三种遗留；真实隔离Redis验证自身计数归零及其他owner保持，真实Django ASGI disconnect测试使用Redis容量而非替身计数。目标Compose回收与播放器验收另在P5记录，不由这些隔离测试替代。

## 后续方案

已下载视频直传及个人播放进度的接口、迁移与边界见[设计草案](local-playback-and-progress-design.md)，尚未实现。
