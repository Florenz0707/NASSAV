# 已下载视频播放与进度保存：设计草案

状态：L1本地MP4后端与L2前端接入已实现，当前实现以[播放架构](online-playback-architecture.md#已下载-mp4-播放l1)为准；进度保存L3/L4尚未实现。下文保留原方案；视频身份最终复用已有资产marker与文件指纹，不新增video_generation。详情页“点击播放”现已打开新标签页本地模式。PlaybackPlayer.position 只在本标签页内恢复，刷新网页或再次打开不会保存位置。

## 已下载视频直传

正式视频位于 VIDEO_DIR/<avid>.mp4；AVResource.file_exists 是索引提示，创建描述仍需校验真实文件。建议让已下载资源的“点击播放”打开同一播放页的本地模式，通过同源 video.src 读取正式 MP4。保留来源在线播放入口，不悄悄切换媒体时间轴。

本地模式不抓取来源、不使用 ProxyServer、不派发 Celery 准备任务。MP4 容器不保证其编码可被浏览器解码；首版验收 H.264/AAC，不支持时明确报错，暂不隐式转码。

### 分层、接口与迁移草稿

- 创建服务接受 mode=source|local，通过装配的媒体提供者准备描述；共享用户/登录授权、会话所有权、关闭、版本和期限。默认请求仍采用 source；source 维持 worker 准备，local 检查已发布文件后返回 ready。
- PlaybackSession 新增显式 media_kind 字段，旧记录迁移为 source。descriptor 区分 hls/mp4，前端选择 HLS 引擎或原生 MP4，复用页面及卸载清理。
- GET/HEAD /api/playback-sessions/{id}/file：校验当前登录、会话代次、期限、资源及发布身份；只返回同源入口，不泄漏文件绝对路径。拒绝 .tasks、临时文件和任意用户路径。
- 定位器以 VIDEO_DIR 和规范化 AVID 定位，解析后的目标必须在批准的视频根内。现有根目录符号链接部署需可用；具体文件链接需明确校验策略，不能开放任意外部目标。
- 支持单一 bytes Range、206/416、Content-Range、Content-Length、HEAD、ETag/If-Range；分块发送，断连关闭文件句柄。[Range](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Range_requests)用于播放器按需读取与拖动。

首版建议有界 ASGI 文件传输，磁盘读取在线程或异步适配器执行；设置本地并发和空闲限制，不将远端单段大小、45秒期限套到整个 MP4。[Django 文档](https://docs.djangoproject.com/en/5.2/ref/request-response/#fileresponse-objects)指出同步文件 API 在 ASGI 下的限制，不能直接将 FileResponse 视为已解决流式传输。

后续可评估 Django 鉴权后 X-Accel-Redirect，Nginx internal location 使用只读挂载处理 Range。[internal](https://nginx.org/en/docs/http/ngx_http_core_module.html#internal)可阻止直接外部请求，但不能沿用应用在途检查；关闭会话不保证立即停止已授权长响应，需另定撤销/删除语义，不作为首版默认方案。

### 文件发布、替换与删除

复用 resource_file_locks：在短资源/目标锁内确认发布身份并取得句柄，不持锁直到整段播放结束。file_exists、AVID 和相同大小不能证明媒体没变。

实际实现复用TaskAssetTarget.marker及文件dev/inode/size/mtime_ns/ctime_ns；新发布/回滚沿用既有资产epoch。原有文件无marker时按指纹绑定，不新增视频版本字段，不在短DB事务哈希大视频；同大小替换亦失效。外部手工原地篡改不能承诺字节恒等。

删除视频/全资源、替换发布使旧版本会话失效；新 Range 拒绝，在途循环确认撤销后关闭句柄。浏览器已缓冲的字节无法撤回。Linux 已打开文件即使 unlink 仍可能占磁盘，在途循环约0.5秒核查后关闭句柄，删除API不等待所有传输退出，不能用目录消失证明已回收每个句柄。复用既有删除/资产日志协议；关闭播放不会删除正式视频。

## 播放进度

建议数据库持久化，按用户隔离并支持跨浏览器恢复；localStorage 仅兜底最后一次未上传位置，不存来源地址、Cookie 或签名 URL。

新增 PlaybackProgress，表名 nassav_playback_progress：

| 字段                                             | 用途                                          |
| ------------------------------------------------ | --------------------------------------------- |
| user、avid、media_key                            | 用户、规范化资源标识、被核验的媒体版本/时间轴 |
| position_seconds、duration_seconds               | 最近位置与已知时长，有限非负值                |
| completed                                        | 完成状态，与资源 watched 独立                 |
| version                                          | 服务端写入版本                                |
| writer_generation、writer_session、last_sequence | 当前写入者及事件归属                          |
| updated_at                                       | 最后保存时间                                  |

唯一键 (user, avid, media_key)。建议不级联 AVResource 删除，便于重新添加恢复；用户删除级联清理，另提供手动清历史。completed 不自动修改目前共享的资源 watched。

### 写入与恢复协议

1. 取得合法媒体描述后读取进度；实际开始播放时显式取得写入代次。最近开始播放的标签拥有写入权，旧页仍能播放但提示不再保存，不用客户端时间戳决定归属。
2. PUT 携带合法会话、媒体版本、writer_generation、sequence、expected_version 和幂等 UUID；短事务检查用户/归属再更新。乱序、重试、注销后的请求不得覆盖新状态。
3. timeupdate 节流约15秒；pause、seeked、ended、visibilitychange 隐藏时补存。一个在途写入、合并待发最新位置，pagehide 带 CSRF 的 keepalive 尽力提交，不保证末次成功。[timeupdate 频率随负载变化](https://developer.mozilla.org/en-US/docs/Web/API/HTMLMediaElement/timeupdate_event)，不应每个事件访问数据库。
4. 保存最近位置而非最大位置，允许回退后保存。首版以 ended 标记完成，再播放可清除 completed；近尾阈值留作明确产品策略。
5. loadedmetadata/可 seek 后校验时长并限制有效范围，提供“继续上次 / 从头播放”，不强制自动播放；接近结尾默认从头。重新开始同样需要合法写入归属。
6. 本地版本 UUID 绑定正式文件；远端 manifest_identity 只是保守兼容检查，不能证明字节恒等。不同会话或本地/来源之间不只凭 AVID 自动续播，可显示上次位置供确认；不同版本保留独立记录，不以临时 URL 作为永久媒体身份。

迁移验证 SQLite/PostgreSQL 升级、回退、再次升级。会话终态清理不清播放进度；历史保留期独立，首版建议手动清理。

## 建议执行顺序

1. L1：媒体版本、定位器、MP4/Range 接口；验证鉴权、断连、路径、删除/替换竞争、大文件内存及符号链接部署。
2. L2：local/source 描述适配与已下载入口；真实 MP4 首帧、拖动、暂停及退出验证。
3. L3：进度表、归属/幂等协议与迁移；覆盖多用户、多标签、乱序、回退、替换和注销。
4. L4：节流保存、恢复提示、重新开始及离页兜底；覆盖刷新恢复、网络失败及末次写入丢失。

各阶段独立分支，质量门槛通过后合并 idle。L1/L2已实施；L3/L4仍为后续方案，不保存跨页面播放进度。
