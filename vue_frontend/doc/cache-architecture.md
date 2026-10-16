# 前端缓存、图片复用与身份隔离

## 分层与所有者

| 层级                    | 当前策略                                              | 失效边界                                              |
| ----------------------- | ----------------------------------------------------- | ----------------------------------------------------- |
| 资源列表、演员/类别目录 | queryCache内存，默认30秒/20查询，同请求去重，副本返回 | 登录/领域revision变化，写后失效，手动刷新强制重取     |
| 资源详情                | API metadataCache，默认30秒/100项                     | 当前登录身份、资源/个人状态变化                       |
| 来源列表与搜索能力      | API sources缓存5分钟/8项                              | 登录请求身份变化；Cookie读取始终no-store              |
| 观看历史/稍后再看       | viewing内存30秒/8查询，个人中心KeepAlive最多4面板     | 真实播放、个人写入/删除、账号变化；停用面板拒绝旧响应 |
| 用户设置                | settings store已加载/在途去重，5分钟新鲜期            | 登录变化、偏好失效信号；有脏草稿不后台覆盖            |
| 推荐/外搜恢复           | sessionCache按登录/来源身份、有界TTL/容量保存展示数据 | 来源凭证、身份、结果期限变化；不作为授权依据          |
| 正式资源图片            | 浏览器private,no-cache与ETag重验证                    | 每次授权后才可返回304，版本/登录上下文改变URL         |
| Vite哈希制品            | Nginx一年public immutable                             | 内容变更产生新文件名；入口HTML/public稳定文件重新验证 |

## 公开图片与个人图片

正式封面URL保留size、v并补齐当前_context；ResourceCard显式coverSize优先于服务端缩略图提示，默认medium。翻页后再次验证图片可能仍有网络请求，但合法304不重复传输图片主体；不应以请求数量直接推断缓存无效。权限撤销后不得因缓存命中跳过授权。

推荐/外搜图片使用服务器签发的cover_handle及原结果范围；句柄失效时显示占位，不回退任意URL代理，也不通过重新签名延长原搜索结果TTL。媒体、个人JSON和结果图片的缓存头不能为了速度改成公共长期缓存。详见[本人结果图片](../../django_backend/doc/discovery-image-architecture.md)。

## 查询护栏与写后失效

createQueryCache只管理内存、TTL、有界容量与在途去重；领域store拥有登录epoch、规范化参数、revision和展示请求guard。失败不缓存，清空后旧promise不能重新发布；loading/error/清理动作同样检查请求归属。

personalDataEvents在当前标签分发无载荷领域失效信号；preferenceEvents通过localStorage修订标识触发其他标签的storage事件，不传递偏好正文。当前没有通用BroadcastChannel领域同步。同标签写成功使相关资源/目录/个人列表失效，偏好跨标签通知仍核查当前登录；其他领域的跨标签/设备变化依赖焦点、可见性、TTL或现有版本事件。不得宣称所有领域已实时同步。

## 任务和播放不使用普通查询TTL

userOperations按operation_id/version持有本人任务快照。初始化、WebSocket重连、页面恢复可见时补查；进行中任务每2秒查详情，每30秒补查可见任务并刷新/my-operations列表。WebSocket只提示身份/版本，不能代替DB快照与断线兜底。终态和重复版本不重复toast；首次历史载入保持安静，明确提交仍提示当前已接受状态。

播放使用独立session/generation与期限；取消、进度writer、媒体授权不由页面缓存决定。浏览器隐藏列表只改变展示，不停止后台执行。不要把这些控制快照套进30秒资源查询缓存。

## 开发与后续优化

KeepAlive不是数据新鲜度保证。新增缓存必须说明所有者、key、TTL/容量、登出清理、写后失效及迟到请求处理，并验证双账号/同账号重登录、跨页返回、失败重试与容量上限。

尚未统一实现所有JSON接口的ETag/304合并协议，不得把原生img的304行为套到Axios envelope。是否减少30秒任务补查、按不可见页面退避，应先测真实请求量并保留权限/终态重新核查；本版未改变轮询频率。相关测试入口为tests/cache*.test.js及浏览器taskFeedback、resourceImageContext、managementNavigation等；完整验证命令见[前端README](../README.md)。
