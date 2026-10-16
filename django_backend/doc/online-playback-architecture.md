# 播放会话、来源网关与本地媒体

本文维护当前实现；接口见[接口文档](interface.md)，不可变媒体授权见[资源版本](resource-version-architecture.md)，个人位置见[播放进度](playback-progress-architecture.md)。目标环境限制见[发布检查](release-2.5.3.md#验证边界)。

## 状态与职责

PlaybackSession是绑定用户、具体登录及账号代次的短期授权；状态为queued、resolving、ready、failed、closed。ready只表示描述已准备，不证明浏览器解码成功。任务记录、共享资源版本和个人进度各自拥有状态，不把播放准备塞进下载TaskJob。

HTTP由http/playback_views.py处理；playback/records.py持有会话、generation、执行UUID、version、租约与期限。composition装配来源和传输。Celery playback_prepare_task只运输会话UUID，在scrape队列进行有界准备；网络在短事务外，发布时复核归属。旧worker、关闭或过期会话不能恢复ready。

创建使用request_id幂等；关闭/刷新还核查expected_version，关闭递增generation并清空描述。GET快照、媒体读取和控制都重新检查登录及对象授权。来源准备失败不能自动回退别人的凭证、本地旧文件或全局AVID路径。

## HTTP 契约

创建使用POST /nassav/api/resources/{avid}/playback-sessions，mode为source或local；查询使用GET /nassav/api/playback-sessions/{id}。关闭与刷新沿对应子路径POST，并携带expected_version及request_id。HTTP只返回授权同源入口与状态，源站地址、Cookie和描述内部身份不能回显。

接口返回queued/ready不代表视频已解码。来源绑定、账号、具体登录或版本失效时按既有错误契约拒绝，不能用任意AVID或管理员角色绕过。完整请求与响应字段见[接口文档](interface.md)。

## 来源播放

创建前读取本人元数据版本的source_name和冻结credential_refs，并确认专用keyring可解密。凭证更新/撤销后需刷新元数据，不用新秘密复活旧授权。原站Cookie不进入HTTP响应、Celery参数、日志或公共缓存。来源抓取使用Proxy.url，不能与视频下载代理混用。

浏览器只取得同源、带不透明资产身份的播放入口。服务端按会话描述改写播放列表，对清单、分片、密钥与初始化资源统一检查目标域名、重定向、响应大小和网络预算。不得恢复任意URL代理。NASSAV_PLAYBACK_ALLOWED_HOSTS必须匹配实际目标站及CDN；代理可信目标策略不能绕过应用授权。

传输由媒体网关负责，Celery不长期转发分片。Redis限制传输容量，DB读取占用保护固定版本；二者不能互相替代。关闭、失败与取消主动释放本人容量，租约到期只作兜底，不能据此证明文件写入者已停止。

## 本地播放

已下载视频通过本地媒体描述与授权Range/HEAD读取，不经来源取流。共享模式创建事务核对本人video_version，固定版本、manifest、marker及内容指纹；坏版本不回退旧AVID视频。库指针刷新不会改变已有会话的读取对象。普通移出允许既有合法授权在原期限内续读，账号变更、下架与损坏拒绝继续读取。

## 前端与刷新

资源详情打开独立/play/:avid标签页；App使用logoOnly导航，播放器固定16:9。hls.js动态加载，适用时由原生video播放本地MP4或原生HLS。会话生命周期归features/playback，不放到资源store。

来源失效刷新有界且受会话generation保护，刷新后保留本页位置并重新绑定；失败明确展示，不无限重试。离页合并进度保存和关闭，不依赖卸载后的回调，未送达由会话TTL兜底。

## 配置与部署

NASSAV_PLAYBACK_ENABLED默认false；NASSAV_PLAYBACK_ALLOWED_HOSTS、NASSAV_PLAYBACK_PROXY_TARGETS_TRUSTED及NASSAV_PLAYBACK_MAX_MEDIA_REQUESTS由服务端统一配置。API和worker必须使用一致配置和代码。

创建会话503先检查响应类别。Credential keyring cannot be loaded发生在媒体准备之前：容器必须挂载原keyring，不能只填宿主机路径或重新生成密钥。显式-f部署保留compose.credentials.yaml，详细命令见[Compose部署](compose-deployment.md#独立来源-keyring-挂载)。/healthz正常不代表来源凭证可用。只读绑定检查不等于真实出画验收。
