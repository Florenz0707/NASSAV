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
