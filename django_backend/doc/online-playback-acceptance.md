# 在线播放 P3–P5：验收与发布边界

日期：2026-10-11。P3/P4 已实现并合并；P5 的隔离与 Linux 桌面验收已执行；关闭容量回收检查未通过，完整发布验收亦有下列目标环境条件；本阶段不得自动合并。不能将短时 Linux Chrome 样本与隔离回归称为全部目标设备或长期验收。

## 交付与验证

| 阶段            | 提交/入口                                             | 已验证范围                                                                                                                                                                                                                          |
| --------------- | ----------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| P3 播放器       | 45ed7be；PlaybackDialog、playbackSession、mediaPlayer | pnpm run check：75 项通过；pre-commit run -a 全通过；合成 TS/fMP4 的真实解码/拖动/暂停/关闭、错误重试、主题/移动、焦点恢复与迟到提交清理                                                                                            |
| P4 一次刷新     | 038ea90；迁移 0030、refresh 接口和兼容基线            | 完整隔离 pytest 912 passed / 28 skipped；前端 76 项；pre-commit 全通过；SQLite 与独立 PostgreSQL 16.15 完成 0029→0030→0029→0030；合成 hls.js 分片 410 触发一次新代次恢复并继续解码                                                  |
| 正式 P1/P2 联调 | 重建后的 c7ccbfa（本轮之前）                          | MissAV ADN-495/Jable SONE-411，经实际 Nginx→API→scrape worker→Redis；准备约 34/51 秒，HEAD 200、Range 206、AES 密钥16字节、匿名401、错误签名403、错误Range416、旧版本409、关闭后410、断连额度归零；登录及会话已清理，用户与资源未变 |
| P5 独立 Compose | 本阶段 Git 提交及 live runner                         | 新前端静态构建、最新后端代码、私有 SQLite/Redis、真实 scrape worker、原有来源出口；不使用 eager task，不操作用户正式数据库/资源目录。Chrome 与 Firefox 均完成两个来源真实首帧、seek、暂停、连续30秒和关闭；详见下表                 |

| Linux 浏览器                | MissAV ADN-495 首帧   | Jable SONE-411 首帧  | 共同结果                                    |
| --------------------------- | --------------------- | -------------------- | ------------------------------------------- |
| Chrome 152 / hls.js         | 4.9秒（短期缓存命中） | 68.4秒（含来源准备） | 解码帧、seek、暂停/继续、连续30秒、关闭通过 |
| Playwright Firefox / hls.js | 51.2秒（含排队/准备） | 6.5秒（缓存命中）    | 同上；不是 Safari 或 Android 证据           |

样本为独立 SQLite/Redis、真实 Celery worker、Nginx 与来源出口；首帧时间受排队、缓存及原站影响，不能作为性能承诺。Chrome 再次完成两来源的显式一次刷新：MissAV/Jable worker 准备约54.5/60.0秒，generation=2、refresh_count=1、原位置恢复并继续解码，关闭后权威状态closed且无manifest_url。旧代次请求410是预期失效，不等于刷新失败。自然签名到期只由合成410用例覆盖，真实网络本次为显式refresh。

最终代码检查：完整隔离pytest **916 passed / 28 skipped**；`pnpm run check` **76 passed**（lint及构建通过）；`pre-commit run -a` 全通过；合成TS/fMP4浏览器回归通过。变更先复现Range、SQLite/WAL锁升级及私有扩展误判，再通过回归。hls.js 动态chunk约525 kB（gzip约162 kB），触发构建大小提示；未改变质量阈值。

P5 发现并修复 Chrome 原生视频对清单发送 Range 时原网关返回416的问题。合法单 Range 对重写清单/密钥/小型 data 返回完整200，使用当前响应长度，不伪造206或转发上游 Range；分片/init 保持原206/416，多 Range/语法非法仍416。依据 [RFC 9110 Range](https://www.rfc-editor.org/rfc/rfc9110.html#section-14.2)，服务器可以忽略 Range 并返回完整表示。专项覆盖原生探测请求和既有媒体语义；不降低域名、登录、签名、大小或容量限制。

P5 的真实媒体并发暴露 SQLite/WAL 控制事务读后升级写锁的问题。关闭与刷新现在先以受授权身份取得短写 fence 再读取版本，避免媒体心跳插入导致 SQLITE_BUSY_SNAPSHOT；跨连接文件/WAL 回归先复现 database is locked，再验证状态/期限保持和无遗留写线程。不把全量串行测试通过当作该并发场景已验收。

当前桌面 MSE 浏览器优先使用已实测的 hls.js，缺少 MSE 才回退 video 原生 HLS。Chrome 的 canPlayType 声明不足以保证匿名文件扩展的受控网关能由原生引擎解码；本次原生 Chrome 尝试未作为通过证据，Safari/iOS 必须另测。引擎选择按能力，不按来源名或 User-Agent 分支。

清单身份摘要仅保留已支持的标准 HLS 结构标签和匿名化 URI引用，忽略注释、空行与未知扩展，依据 [RFC 8216 6.3.1](https://www.rfc-editor.org/rfc/rfc8216.html#section-6.3.1)。真实 MissAV 轮换私有 token 行此前误触发不兼容；已用专项先失败后通过回归覆盖。轨道、时长、序列、discontinuity、IV、byterange、密钥及初始化字节仍受严格校验，不放宽 URL/来源策略。不兼容旧摘要的会话需关闭重建，升级期间不得混跑校验版本。

离线浏览器入口：`NODE_PATH=/tmp/nassav-browser-audit/node_modules node tests/browser/playback.cjs`，在 vue_frontend 目录运行、配合本地 Vite。该用例明确走 MSE/hls.js，不把 Chrome 原生模式当作 hls.js 失效恢复验收；原生 HLS 的错误恢复使用手动重试，Safari/iOS 必须真机验证。

## P5 停止条件：关闭后的容量回收未通过

两次真实浏览器轮次都完成关闭，权威会话为closed且descriptor为空，没有写入资源文件。首次立即检查容量计数仍有一个租约，独立环境停止后重新创建，使用新的临时登录复验两来源：两者再次解码、seek、暂停、连续15秒并关闭。随后四次采样（间隔3秒）均显示：活动会话0、媒体curl生产者0、global ZSET未过期租约1。采样末断言失败（exit1），不能将停止容器或租约最终TTL回收视作正常主动释放验收通过。

当前证据只确认未及时主动释放，尚未确定是取消/finally竞态、上游请求清理路径或其他原因；不得声称容量会永久泄漏。稍后收尾观察同租约已到期约49秒，说明此样本有期限兜底、没有证明持续续租；原始计数不等于仍占用可申请容量。仍需定位主动释放退出路径，补充可复现回归后重新验收。本轮私有数据库共15个播放会话全部closed、descriptor为空，两次自己的临时登录均删除；资源文件0。独立Compose服务和凭据文件在收尾移除，正式实例未修改。

P5代码修复与文档保留阶段分支，不自动合并；是否先独立修复、如何安排后续真机验收，由用户决定。隔离pytest/pre-commit通过不覆盖这项真实服务失败。

## 仍需目标环境完成

- 用户正式实例更新 P3/P4/0030 后，经实际 HTTPS 反向代理验证 Secure Cookie、CSRF、清单/密钥、seek、关闭、退出登录及暂停超过空闲期限。
- Chrome、Firefox、真实 Safari/macOS/iOS、Android 对两个来源分别验收首帧、seek、暂停、关闭和不兼容提示。Playwright WebKit 不作为真实 Safari 证据。
- 自然签名到期、长时连续播放、代理目标 ACL/DNS、多个慢客户端的 RSS/进程数/连接回收，以及与真实下载/刮削同时执行。不得为验收添加或下载用户资源，必须另取得对应副作用授权。
- 不将短期事实 TTL 当作签名有效期，不宣称字节相同或无缝刷新。不同源/轨道/密钥/init 不兼容时保留明确错误，由用户重新开始。

上述项是 P5 完整发布验收条件，当前环境不可自动完成真机与正式 HTTPS 项。功能默认保持关闭，用户正式配置未改；仅可对已核对来源/设备做受控开放。

## 更新与回滚

1. 备份并核对活动数据库模式及来源/代理/CDN 配置，按现有 Compose 入口选择 sqlite 或 postgres；不得直接更改 DB_ENGINE 切换已有部署模式。
2. 暂停在线播放入口（NASSAV_PLAYBACK_ENABLED=false），通过原版本操作员登录关闭所有旧会话或等待期限回收；不手动清理资源目录、锁文件或共享 Redis key。
3. 维护窗口统一所有 API/worker、前端/Nginx 和恢复驱动。新旧模型不得混跑。用新镜像迁移至0030，再一起启动消费者；不在 agent 本轮擅自运行正式 migrate 或重建用户容器。
4. 核查 PLAYBACK_ALLOWED_HOSTS、全局 Proxy.url 出口及可信目标策略；保留 no-store/禁用Nginx buffering，设置服务并发额度，确认 scrape worker 和恢复扫描运行。使用既有脚本 `python3 scripts/compose_stack.py --mode 当前模式 ...` 执行 build、run --rm migrate、up -d；postgres 模式沿用叠加配置。
5. 开启单用户受控验收并执行下述 live runner，收集脱敏状态/耗时与媒体解码证据。准备失败可关闭并重试；不兼容不可绕过校验。
6. 回滚先关闭入口并撤销会话，停止新消费者再切回已知镜像。可保留0030字段进行代码回滚；若确须退至0029，只能在全部新消费者停止并备份后执行逆向迁移，新基线/次数丢失，正式资源及下载数据保留。

## 真实浏览器探针

`vue_frontend/scripts/verify-playback-live.cjs` 为显式 opt-in，只使用已有两条资源；由操作者提供临时 Playwright storage-state 文件，origin 必须是授权验收环境。它创建/关闭播放会话，允许准备短期缓存，不添加正式资源、不下载视频文件，不改密码。默认连续播放30秒（15–300可配置），可显式开启一次 refresh；跟踪实际视频帧、seek/暂停/继续及权威终态。例子见[前端README](../../vue_frontend/README.md#在线播放器验收)。

探针关闭播放会话是尽力操作，结束仍应核对 DB 中的 state/descriptor、删除自己的临时登录并清理凭证文件；不能只凭浏览器退出证明释放完成。清理会话记录由有界恢复驱动在终态24小时后执行，URI映射自然TTL回收；不在线删除稳定任务锁。
