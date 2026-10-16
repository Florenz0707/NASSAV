# 个人播放进度与跨设备接续

## 状态所有者与媒体身份

PlaybackProgress是用户持久状态，PlaybackSession是短期授权；不写AVResource.watched，不存入原站事实缓存。进度核心位于nassav/playback/progress.py，接续投影及HTTP入口沿[接口文档](interface.md)维护。

账本按用户、AVID及服务端媒体身份隔离。本地文件必须匹配固定视频版本；来源身份含scope/context，来源账本键仍不证明远端字节相同。不能仅按AVID跨来源、本地模式或用户套用位置。继续观看只查询本人仍持有且身份匹配的最新账本，不读取原站或泄露来源链接。

## 接口

进度查询、领取、保存、清除和跨设备接续的URL及字段沿[接口文档](interface.md)；入口确认当前用户与会话登录，不接受客户端自选owner或媒体身份。保存和清除分别保留下面的代次/序号护栏。

## 领取、保存与清除

打开页面只读进度，不抢占writer。明确继续播放/跨设备接续先读取最新快照，再以expected_writer_generation和幂等命令领取；以claim返回的位置恢复。保存核查会话generation、writer_generation、单调sequence和版本，旧写入者收到409后转只读，不能自动重新领取。

清除保留墓碑并推进写入代次，零位置也不能被旧请求恢复。账号、登录、资源或媒体身份变化使旧响应和草稿失效。服务端确认的保存结果才可更新本页基线。

## 前端职责

features/playback/lib/playbackProgress拥有媒体事件、串行合并写入及保存权；progressDrafts只作有界且按登录隔离的短期兜底。默认播放偏好由UserPreferences持有，不能把用户偏好与进度writer混用。

同一会话的受控HLS刷新可保留位置并重新绑定generation。新来源会话续播需要用户确认。另一设备接续后，旧页面不能自动抢回保存权。离页合并保存与关闭；浏览器sendBeacon/keepalive未送达由现有TTL兜底。

## 观看历史的区别

观看历史按真实playing事件记录并更新队首，不依赖进度保存权；读取、准备、claim、缓冲或重试不算观看。历史按(user,pool)去重，资源回收保留当时授权摘要但不授予封面/播放权。见[观看列表](viewing-architecture.md)。

## 验证边界

回归必须覆盖双登录争用、旧writer、乱序sequence、清除墓碑、关闭/刷新竞争、身份变化和失败草稿。合成媒体或模拟API不能代替实际来源、长时播放及目标设备验收；发布限制见[发布检查](release-2.5.3.md#验证边界)。
