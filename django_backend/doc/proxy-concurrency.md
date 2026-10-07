# 代理服务器并发能力

## 公共接口与职责

`page_fetching.proxy_server.ProxyServer` 是业务使用的并发接口，不暴露 provider 名称。
`ordered(operation, values, check=...)` 提供有界预取、输入顺序返回、取消检查和退出回收；
每个 operation 必须拥有独立来源/HTTP 会话，只返回结果，由调用者合并业务状态。
调用者必须使用上下文管理器，提前停止后关闭未执行工作并等待已执行操作协作退出。
`slot(timeout_ms, check=...)` 限制实际代理请求；等待期间检查取消与执行归属。

`OrderedProxyServer` 管理单次操作的线程窗口，`RedisProxyCapacity` 管理跨进程容量。
`ProxyPageClient` 装饰任意 `BrowserPageClient`，不依赖 Byparr 协议；来源和推荐流程
不判断 provider。provider Adapter 仍只负责请求协议、出口配置和响应解析。
`PageFetchService.for_lookup` 只隔离临时状态，不能代替独立浏览器会话。

## 配置与失败

使用 `BrowserFetch.max_concurrency`，范围 1–8，默认 2，1 保留串行调度。
旧 `FlareSolverr` 块默认 1；禁用浏览器获取时调度保持串行。
所有进程必须使用同一容量值、代理 endpoint 和 Celery Redis 数据库；同一服务器
不同别名不会自动识别为同一容量域。更换 endpoint/Redis 或提高容量需按部署实例验证。

Redis 使用服务器时间和 owner UUID 原子获取/续期；正常退出只释放自己的槽位，
失去归属拒绝返回成功结果，崩溃槽位通过 TTL 回收。Redis 不可用明确失败，不能绕过限流。
槽位覆盖浏览器请求，不覆盖 ORM、评分、直接 HTTP 或整个 job，避免嵌套操作死锁。
客户端中止连接不保证远端浏览器立即停止；异常中断后的远端清理由代理实现负责。
因此此限流保证客户端受控请求容量，不声称远端崩溃恢复期间精确的活跃页面数量。

## 验证范围

隔离回归覆盖有序返回、实际重叠、提前停止、取消、来源超时、任意 provider 替换、
多个调用者共享真实临时 Redis 容量、失租后的 owner 保护和 Redis 故障。
真实 Jable 2 路实验已确认并发能力，但不能替代 MissAV、2 GB 容器和完整任务链验收。
更高容量需单独测量，不能把单任务窗口乘以 worker 数当作服务容量配置。

## 外部搜索与推荐的接入

外部搜索的第一页单独读取并发布，随后使用 `ProxyServer.ordered` 预取后续页。
乱序完成的结果等待前页再合并；`pages_completed` 只表示连续处理的页号，原生顺序、
去重及版本快照保持。空页/无新增页立即停止后续派发，最多存在窗口内的多余预取；
这些预取结果及错误不影响已经短路的结果。前页失败保留已有部分快照，不写成功缓存。
取消检查传入独立来源和网络 transport，取消后的迟到结果不能发布或填充成功查询缓存。

推荐在每批中并行独立种子，仍按种子输入顺序合并；热门/最新发现来源可并行，
每个 seed 内分页、映射为空后的关键词回退及过滤后补召回保持原有依赖顺序。
详情在协调线程先按 AVID 去重并预留共享尝试预算，再通过公共代理调度获取。
补召回不重置预算；失败/空详情不返还尝试名额，取消或整体失败后未使用的预留也不返还。
详情字段、匹配 seed、评分与最终排名由协调线程更新；严格黑名单仍排除未核验候选。

生产装配为每个操作构造独立 Source、BrowserPageClient 和 TaskNetworkControl。
子控制继承整体 deadline，短阶段 budget 的修改不影响兄弟操作；线程完成后关闭
HTTP transport 和线程本地 Django 连接，包含归属检查打开的连接。
来源业务类和消费者只使用 `ProxyServer`，不得自行创建线程池、读取 provider 名称
决定并发量，或在线修改 SourceManager 单例的任务控制/代理/会话。

并发不增加推荐的 300 秒整体期限；推荐软预算与版本进度见[推荐架构](recommendation-architecture.md)。不改变 URL、
任务名、队列、缓存 key/TTL 和黑名单规则。直接 HTTP 保留全局 Proxy.url；下载代理
仍独立，浏览器控制仍直连。`max_concurrency: 1` 可回到顺序调度，仍保留来源隔离和容量检查。

同一用例的调度器、容量状态和 Redis 连接池由装配共享，不随每个页面重建；
独立 Source/浏览器 transport 只拥有当前操作的会话，关闭它不会关闭共享容量连接。
