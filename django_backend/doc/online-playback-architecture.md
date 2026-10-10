# 在线播放实现与开发契约

设计见[方案](online-playback-design.md)，真实来源边界见[P0](online-playback-p0-report.md)。本文件维护已实现的行为，不将尚未部署的功能当作目标环境验收。

## P1 会话与准备

新增可逆迁移 0029，表 nassav_playback_session。PlaybackSession 独立于 TaskJob 和正式资产：删除资源级联撤销会话，来源事实缓存不级联删除。用户与当前登录摘要绑定，跨登录的相同用户也不能读取或关闭另一会话。退出登录关闭该登录会话；媒体请求仍须重新检查登录授权。

状态为 queued、resolving、ready、failed、closed；ready 表示已取得播放描述，尚不代表视频解码/目标设备成功。每次提交使用 UUID request_id，同键换资源冲突；每用户最多 2 个未过期活动会话。close 使用 expected_version/request_id，重复关闭命令幂等，关闭递增 generation 和 version、清除描述，旧 worker 不能发布缓存或 ready。

生产开关 NASSAV_PLAYBACK_ENABLED 默认 false；本地与 Compose 环境模板已说明，Compose 显式传入所有后端入口。开启前必须统一 API/worker 版本并应用新增迁移；本轮不执行正式迁移。P1 尚未提供正式播放器、媒体入口或刷新接口，不能单独视为可播放的发布。

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
