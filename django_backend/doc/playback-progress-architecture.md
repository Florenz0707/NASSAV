# 个人播放进度架构

数据库拥有持久进度；PlaybackSession 拥有当前登录的短期播放授权。进度不进入资源事实缓存，不改变共享 watched，不派发 Celery。多用户扩展见[路线](multi-user-roadmap.md)。

## 模型和媒体身份

迁移0032新增 nassav_playback_progress，唯一(user, avid, media_key)。用户外键删除级联；avid 为字符串，不随资源/会话删除。会话回收不清进度。个人历史首版保留至手动清除或用户删除，无定期自动过期。

local 的 media_key 是既有描述（发布 marker/文件指纹）的规范化摘要；替换/重发布/文件搬迁可能使身份变化，保守视作新视频，不自动套旧位置。source 使用模式、AVID、来源组成账本键，仅用于保存同来源最近位置，不承诺原站字节身份；新会话均要求确认位置。同一会话的受控刷新仍执行原有兼容检查，旧 generation 的进度写入拒绝。

position/duration 为有限秒数，0<=position<=duration<=604800；duration 必须大于0。completed 由播放器 ended 决定，不依据百分比自动完成。重新播放提交 completed=false，允许向后拖动保存。

## 写入协议

GET当前会话progress返回不含凭证的用户/媒体账本摘要ledger_key、位置、时长、完成标志、version、writer_generation、restore_policy及时间，不返回媒体描述/来源URL。local必须复核当前文件，source仅在ready有效授权时访问。

claim携带session_generation、expected_writer_generation、UUID request_id；短事务先锁用户写入fence，再锁播放会话，检查有效期与归属。最近成功领取者拥有写入权，增加writer_generation、保存writer_session、重置序号。同命令重试仅在仍拥有写入权时幂等；旧命令不能抢回已转让或清除的权利。

PUT携带session_generation、writer_generation、sequence、expected_version、UUID request_id、position_seconds、duration_seconds、completed。用户/当前登录/会话代次/写入代次检查后更新，乱序/版本冲突409。同序号同进度payload幂等，改写同序号拒绝。可选布尔close_after_save在同一事务保存并调用既有关闭协议；失去写入权/版本冲突时仅关闭自身会话、返回saved=false，不覆盖其他写入者。该关闭标志不参与进度payload摘要，允许响应丢失后原进度请求追加关闭。已关闭会话仍拒绝重放。网络与文件核查不进入短DB事务。

DELETE资源progress只清当前用户该AVID的所有媒体版本。保留零值墓碑并递增version/writer_generation、撤销writer_session，禁止删除重建造成token复用。重新播放需重新领取，不自动抢权。

## 接口

| 方法   | 路径                                              | 参数                                                       |
| ------ | ------------------------------------------------- | ---------------------------------------------------------- |
| GET    | /nassav/api/playback-sessions/{id}/progress       | 当前登录所属ready会话                                      |
| POST   | /nassav/api/playback-sessions/{id}/progress/claim | session_generation、expected_writer_generation、request_id |
| PUT    | /nassav/api/playback-sessions/{id}/progress       | 归属/版本/序号与位置字段                                   |
| DELETE | /nassav/api/resources/{avid}/playback-progress    | 仅当前用户                                                 |

使用现有operator权限、CSRF、PLAYBACK_ENABLED与no-store；跨登录会话404，关闭/到期410，冲突409，参数错误400。将来开放多用户须先实施权限矩阵，不直接放宽所有业务API。

## 验证边界

专项覆盖幂等、乱序、回退、完成、清除与旧claim重试、多标签、用户隔离、关闭/到期/更换代次、文件版本、CSRF与接口契约。0031↔0032需验证可逆及SQLite/PostgreSQL关系保持；正式数据库迁移和浏览器/真实环境验收分别记录。前端接入后补充保存生命周期。

## 播放器与执行记录

前端生命周期、恢复提示和有界离线兜底见[开发契约](../../vue_frontend/doc/development-contracts.md#播放进度记忆)。源HLS仅按来源保存最近位置、新会话确认；本地版本变化返回空进度，不尝试套用另一个文件的进度。

后端阶段131204a：`uv run pytest tests/ --ds=django_project.refactoring_test_settings -v`：945 passed / 28 skipped；独立Unix socket PostgreSQL16进度/迁移/任务专项28 passed；SQLite0031→0032→0031→0032，最终恢复全部叶节点；`pre-commit run -a`通过。新增模块暂存后纳入完整门槛，不以未跟踪文件检查结果代替提交门槛。短SQLite锁竞争重试复用db_retry，重试整个短事务，无网络副作用。

前端阶段执行`pnpm run check`与`pre-commit run -a`，真实隔离helper/回环Vite/Playwright浏览器专项命令见[测试说明](../tests/README.md)。正式数据库尚未执行0032迁移；部署更新后运行migrate并统一API版本。回退0032会删除新增进度数据，应先备份。

前端/离页阶段（feat/playback-progress-frontend，提交以Git历史为准）：最终隔离后端946 passed / 28 skipped；独立PostgreSQL进度/0032可逆迁移/任务协议29 passed；`pnpm run check`含91项测试、lint和构建通过。Chrome和Firefox真实隔离Django/SQLite/Redis/合成90秒MP4验证刷新/键盘/移动深色布局、回退、多标签、清除、路由离开、完成后从头及进度接口503不阻塞视频。合成TS/fMP4的模拟来源会话另验证确认续播、解码/拖动及一次失效刷新；不当作真实来源worker联调。浏览器关闭不保证keepalive送达，测试finally只通过授权接口清理本轮创建的会话，服务端TTL仍是生产兜底。未执行用户数据库迁移、容器部署、真机或长时验收。

## 用户播放偏好（第三阶段）

UserPreferences JSON增加playback_volume（数值0–1，默认0.8）、playback_muted（布尔，默认false）、playback_rate（数值0.5/0.75/1/1.25/1.5/1.75/2，默认1）、playback_subtitles_enabled（布尔，默认true）、playback_default_mode（auto/local/source，默认auto）。音量/倍速接受JSON整数与小数但拒绝布尔和数值字符串；其余已有定义仍严格按原类型。无需新增数据表或批量补写，GET缺失值只读补齐，PUT按合法键部分合并。

个人设置提供显式保存；播放器加载用户配置后设置音量、静音、defaultPlaybackRate和playbackRate，原生volumechange/ratechange经500ms合并及单写入队列保存，仅写实际变化。初始化事件不回写默认值，卸载移除监听，旧登录代次的writer不再发请求/应用迟到响应。失败提示不妨碍播放，保留设置草稿供设置页重试。字幕偏好仅应用于媒体已有字幕/说明轨道，HLS沿既有引擎subtitleDisplay，原生轨道按字幕开关显示，不创造字幕或承诺外站一定提供字幕；原生菜单切换字幕本次有效，跨设备默认值通过设置页保存。

通用`/play/:avid`入口使用个人默认模式；auto根据元数据索引优先local，否则source，最终文件身份仍由后端核验，失败不隐式换源。明确`?mode=local|source`优先于默认设置；详情页两个入口始终传明确mode，继续观看也保留原模式。设置不是播放进度，不影响写入权或媒体身份，不使用worker保存；source准备仍由原异步worker完成。

## 跨设备接续（第四阶段）

进度记录属于user，播放会话仍属于user与具体登录会话，不能用另一设备的session_id控制其播放。新增GET `/api/playback-progress?limit=6`返回本用户近期未完成资源，limit上限24，最多检查limit×4（不超过96）条最新候选，每个AVID只取最新ledger后再判断完成/清除/近尾，避免旧版本未完成记录复活。先批量查共享资源及发布事实，再进行有界文件stat，不哈希大文件、不抓取来源、不派发worker；删除资源、文件更换/缺失、来源更换的记录不展示，保留数据库进度以支持显式清除及后续恢复。列表不是完整历史接口，超过扫描窗口的旧记录不保证展示。

列表不返回播放链接、路径、session_id、登录hash、user_id或writer token，Cache-Control=no-store。标题与封面仍为共享事实，源站模式标注需确认；点击创建正式的新播放会话，重新核验权限、来源及媒体身份，列表结果不构成媒体授权。本地locator.identities批量读取file_exists、正在发布状态及marker；正式session创建仍持资源锁重新核验。

进度快照增加writer_active和is_writer两个布尔值，不暴露其他设备身份。它们只说明一个未关闭/未到期会话持有保存权，不等于该设备正在播放；不是最终授权。仅打开新页面或GET快照不claim。另一页面持权时前端显示“在此接续”“从头播放”“仅播放，不保存进度”；明确选择接续后GET最新进度，再以expected_writer_generation及幂等UUID领取，使用claim返回的最新位置，避免提示弹出后旧设备继续保存造成回退。源站仍需确认时间轴，时长不兼容或近尾从头。

竞争中的409要求再次明确确认，不自动重试抢占；旧页面后续保存409后继续可播放但只读，可显式“在此接续保存”。不远程暂停旧设备，也不以WebSocket、客户端时间戳或localStorage覆盖服务器归属。合法本地未上传草稿仅在其版本/代次仍匹配且无其他活跃写入者时作为兜底；claim时版本已经变化则以数据库最新值为准。

首页ContinueWatchingPanel归属播放feature，按mount/可见或聚焦/手动刷新读取，卸载使旧响应失效；清除后刷新即消失。刷新失败保留当前列表，禁用播放能力时不展示该入口；小屏固定16:9播放器内的接续操作支持内部滚动，末项可达。进度/偏好沿已有个人表，不新增第四阶段迁移，不包含评分、播放列表、公开注册或普通用户共享资产权限。
