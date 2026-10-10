# 在线播放实现与开发契约

设计见[方案](online-playback-design.md)，真实来源边界见[P0](online-playback-p0-report.md)。本文件维护已实现的行为，不将尚未部署的功能当作目标环境验收。

## P1 会话与准备

新增可逆迁移 0029，表 nassav_playback_session。PlaybackSession 独立于 TaskJob 和正式资产：删除资源级联撤销会话，来源事实缓存不级联删除。用户与当前登录摘要绑定，跨登录的相同用户也不能读取或关闭另一会话。退出登录关闭该登录会话；媒体请求仍须重新检查登录授权。

状态为 queued、resolving、ready、failed、closed；ready 表示已取得播放描述，尚不代表视频解码/目标设备成功。每次提交使用 UUID request_id，同键换资源冲突；每用户最多 2 个未过期活动会话。close 使用 expected_version/request_id，重复关闭命令幂等，关闭递增 generation 和 version、清除描述，旧 worker 不能发布缓存或 ready。

生产开关 NASSAV_PLAYBACK_ENABLED 默认 false；本地与 Compose 环境模板已说明，Compose 显式传入所有后端入口。开启前必须统一 API/worker 版本并应用新增迁移；本轮不执行正式迁移。P2 已提供受控媒体入口；正式播放器和失效刷新留到后续阶段，不能单独视为可播放的发布。

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

根 pre-commit 与完整隔离 pytest 是每阶段门槛。提交与实际结果见 Git 历史和阶段收尾，后续 P2/P3 继续维护本文件。

## P2 异步 HLS 网关

ready 查询返回带短期签名的同源 manifest_url，不泄漏上游地址。GET/HEAD manifest/{asset_id} 与 assets/{asset_id} 同时校验当前登录、用户、会话 generation、idle/absolute 期限、资源存在和代理路由。关闭、退出登录或资源删除后立即拒绝新请求；在途请求每 0.5 秒复核并关闭上游、释放容量。签名链接不能脱离登录分享。

manifest 模块有界解析 VOD，将多级/音轨清单、相对地址、签名查询、AES-128 密钥、初始化段注册为 Redis 私有映射，保留 IV 和 byte range。仅支持 identity AES-128；直播、LL-HLS、变量替换、未知 URI 扩展和 DRM 明确拒绝。清单上限 1 MiB、20,000 行、10,000 引用，单会话最多 10,000 资产、嵌套深度 8；映射 TTL 不超过剩余绝对期限且最多 4 小时。关闭后授权失效，映射自然过期，不在线删除共享锁。

policy 只接受 HTTPS/443、无凭据/片段的显式允许域名，逐跳验证重定向及全部 DNS 结果，拒绝非公网地址。transport 使用 HTTPX 异步流，trust_env=false，不自动跟随重定向，不转发 Cookie/Authorization。直连固定已验证 IP，同时保留 Host、SNI 和证书验证。媒体沿用全局 Proxy.url，不使用 Proxy.download_url 或静默回退；Byparr 不参与媒体请求。

代理的最终 DNS/CONNECT 目标由代理解析，本机 DNS 检查不能保证其一致。必须确认代理自身拒绝私网/保留地址，再设置 NASSAV_PLAYBACK_PROXY_TARGETS_TRUSTED=true；否则拒绝代理媒体请求。此配置不会自动创建代理 ACL。

Redis 原子容量由全部 API 进程共享，全局默认 16、每会话 4；容量不足返回 429，不排队。owner 租约 45 秒、每 10 秒续约，失租停止，只释放自身 owner，进程崩溃后自然到期。媒体单请求总期限 45 秒、读取期限 15 秒、连接 5 秒，单段上限 16 MiB、读取块 16 KiB，不落盘或整段缓存。仅清单、16 字节密钥及最多 64 KiB 附属数据有界缓冲。

GET 支持单一 bytes Range，验证真实 206/Content-Range/长度，不伪造部分响应；HEAD 不读取媒体体。拒绝 HTML、异常编码和超大响应，过滤 Set-Cookie/Location 等上游头。响应 no-store；头发送前返回脱敏错误，发送后失败只能中断流。Django 原生异步 ASGI 入口负责断连清理；Nginx 媒体路径禁用缓冲/缓存；Nginx 和 Uvicorn 访问日志移除能力查询串。

### 配置与部署

- NASSAV_PLAYBACK_ENABLED 默认 false；开启前在维护窗口应用 0029，统一 API、scrape worker 和 Nginx，确认恢复驱动启用。
- NASSAV_PLAYBACK_ALLOWED_HOSTS 默认空，拒绝全部目标；配置逗号分隔的已审核域名或 *.example.com，包含清单、音轨、密钥与分段所需域名。
- NASSAV_PLAYBACK_PROXY_TARGETS_TRUSTED 默认 false；仅在代理目标 ACL/DNS 边界核查后开启。
- NASSAV_PLAYBACK_MAX_MEDIA_REQUESTS 默认 16，允许 1–128；结合带宽/内存调整，Redis 必须可用。

本轮不执行正式迁移或部署。P3 播放器、P4 失效刷新和 P5 长期目标环境验收仍待执行；ready 不代表所有资源或设备可解码。

### 验证范围

专项覆盖 URI、AES 密钥、fMP4 初始化引用、恶意目标/DNS、Range、取消、慢读取及关闭。真实隔离 Redis 验证代次、容量所有权和跨进程限额；完整 Django ASGI 路径验证登录、签名、Range 与 disconnect。Unix socket TLS 测试使用真实 HTTPX、证书与 16 MiB 上游，验证 Host/SNI、按需读取、提前关闭及小于 3 MiB 的跟踪内存峰值。这些隔离验证不替代 CDN、代理 ACL、容器多客户端和浏览器解码验收；fMP4 当前验证清单引用，未新增正式播放器解码验收。

## 阶段执行记录（2026-10-10）

P1 提交 dbb243f 已经合并 idle：完整隔离 pytest 868 passed / 28 skipped，pre-commit run -a 通过；SQLite 和独立 PostgreSQL 16 完成 0028→0029→0028→0029。P2 使用独立 feat/playback-p2 分支，提交身份以 Git 历史为准；门槛为完整隔离 pytest、pre-commit run -a、前端 pnpm run check 与无网络临时 Nginx 容器 nginx -t。所有测试只验证隔离行为，不执行正式数据库迁移、容器部署或 P3 页面接入。
