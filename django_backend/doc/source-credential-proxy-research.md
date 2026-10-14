# 来源凭证与代理能力核查

核查日期：2026-10-15。范围为 P3 的凭证隔离与浏览器降级策略；本记录不代表正式账户或目标网站验收通过。

## 结论

当前固定版 Byparr 每次请求创建独立浏览器上下文，但它的 `/v1` 输入不接收账户 Cookie 或指定 UA。直接在 JSON 中添加这些字段不会实现凭证注入，实际输入模型会忽略它们。当前 NASSAV 适配器也没有这两个输入。

这不是无法修改的外部限制。应用可以提供两种可替换能力：支持受控凭证注入的浏览器适配器；或者匿名浏览器获取挑战会话后，在独立 HTTP 会话中执行带账户凭证的验证请求。后者可以适配现有固定镜像，但不保证所有网站接受其网络指纹。必须以实际带凭证请求的业务结果判定成功，不能以匿名浏览器成功替代账户请求成功。

调度与隔离能力应由公共 `ProxyServer` 契约声明；业务消费者不能根据 `provider == "byparr"` 选择账户处理策略。浏览器协议差异归适配器负责。

## 镜像与源码证据

只读 `docker ps`、限定字段的 `docker inspect`、`docker image inspect` 已确认唯一运行中的 `nassav-byparr-byparr-1` 使用：

```text
ghcr.io/thephaseless/byparr@sha256:874f719518f617d03a60e03411fc5d090647e1a877041e81f8dc965927c7deb6
org.opencontainers.image.revision=cb2a862386e92f141e8aa3b58f8532ef2fc36ed0
org.opencontainers.image.version=cb2a862386e92f141e8aa3b58f8532ef2fc36ed0-amd64
```

该 digest 与根目录 [compose.yaml](../../compose.yaml) 固定值一致。检查仅输出名称、镜像与版本标签，没有读取环境变量、Cookie 值或已有应用数据。

固定提交的官方源码：[请求模型](https://github.com/ThePhaseless/Byparr/blob/cb2a862386e92f141e8aa3b58f8532ef2fc36ed0/src/models.py)、[浏览器创建](https://github.com/ThePhaseless/Byparr/blob/cb2a862386e92f141e8aa3b58f8532ef2fc36ed0/src/utils.py)、[请求执行](https://github.com/ThePhaseless/Byparr/blob/cb2a862386e92f141e8aa3b58f8532ef2fc36ed0/src/endpoints.py)。容器内同名文件已逐项核对；上游 main 正在演进，不能替代固定版本证据。

## 能力矩阵

| 能力                   | 当前应用                               | 固定 Byparr                                                | 后续设计约束                                   |
| ---------------------- | -------------------------------------- | ---------------------------------------------------------- | ---------------------------------------------- |
| 浏览器输入 Cookie      | `BrowserPageClient.fetch` 仅 URL、超时 | `LinkRequest` 不定义 Cookie 字段                           | 不能通过额外 JSON 字段假装支持                 |
| 输入绑定 UA            | 浏览器适配器无该参数                   | 请求模型和 context 创建无指定 UA                           | 声明不可用；不得静默丢弃调用者要求             |
| 返回浏览器 UA / Cookie | `PageResult` 已承载                    | 返回实际请求 UA 和 context Cookie                          | 只作为候选会话，仍须校验来源与业务             |
| 每请求隔离上下文       | 每操作可构造独立适配器/HTTP Session    | 每请求创建 `InvisiblePlaywright`、`new_context()`、新 page | 继续保证账户、Cookie jar 与清理隔离            |
| 每请求浏览器出口       | 适配器传 `X-Proxy-*`                   | `get_browser` 接收请求代理参数                             | 统一使用现有全局 `Proxy.url`，不改为下载出口   |
| 并发与跨 worker 容量   | `ProxyServer`、`ProxyPageClient` 承担  | HTTP 端点可并发创建上下文                                  | 不增加业务层 provider 分支，不嵌套抢占同一容量 |

应用证据：[contracts.py](../nassav/page_fetching/contracts.py)、[browser.py](../nassav/page_fetching/browser.py)、[proxy_server.py](../nassav/page_fetching/proxy_server.py)、[proxy_client.py](../nassav/page_fetching/proxy_client.py)。以上矩阵描述核查时既有接口，新增 P3 实现应以提交后的实际契约为准。

## 运行中的合成验证

在运行容器的 `/app/.venv/bin/python` 中执行了无网络的 fixture：以合成 Cookie、合成 UA 解析 `LinkRequest`；替换 `InvisiblePlaywright` 为内存替身，分别调用两次 `get_browser`，比较上下文身份。

```text
cookie_input_preserved False
ua_input_preserved False
distinct_contexts True
exit code: 0
```

这验证了固定镜像的输入丢弃行为与上下文创建路径。浏览器已被替换，不是两个真实浏览器的并发账户隔离验收。未请求任何真实账号凭证、未向网站请求、未重启或修改容器；没有写入已有应用数据。默认 `python` 不在镜像 PATH，定位其虚拟环境解释器后重跑成功。

## 安全的匿名挑战与带凭证重放

推荐将重放实现为独立能力及明确失败路径，而非扩展当前匿名页面为账户页面：

1. 解析当前用户获准使用的不可变凭证快照，保留 credential ID、version、出口、站点及原始账户 Cookie。拒绝撤销、过期或不匹配来源的凭证。
2. 独立匿名 browser context 只处理获准站点的挑战；账户 Cookie 不交给不支持注入的 provider。验证最终 URL、站点、挑战状态及 UA；匿名内容不提交为私人结果。
3. 对 browser 返回 Cookie 执行域、路径、Secure、过期和控制字符校验。只能合并来源策略显式允许的挑战 Cookie；未知 Cookie 不当成挑战凭证。账户 Cookie 的同名值不得被匿名值覆盖。
4. 在新的 HTTP Session 中使用同一出口、绑定的浏览器 UA、原账户 Cookie 与允许的挑战 Cookie执行请求。只允许经过来源批准的目标和重定向，避免跨站转发 Cookie。若账户凭证要求原 UA 不可改变，必须拒绝不兼容重放，不能静默替换。
5. 重放通过当前来源业务 HTML 校验后才发布 scoped 会话或缓存，并检查 credential version、generation、执行归属与租约。HTTP 200、浏览器 `status=ok` 或存在 `cf_clearance` 均不足以发布成功。
6. 重放仍为挑战、登录页、错误页或身份不确定时失败关闭；不降级成匿名账户结果、不覆写人工账户凭证、不把匿名 Cookie 写回其他用户或全局旧表。

当前 [session.py](../nassav/page_fetching/session.py) 的候选选择保留所有适用 Cookie，不能直接作为上述挑战 allowlist。旧 [session_lifecycle.py](../nassav/source/session_lifecycle.py) 已存在浏览器会话 direct probe 和 CAS，但按全局 source 记录管理、具有 provider 分支，不能原样当作多用户安全实现。

上述重放是依据现有独立直连请求、返回会话与版本提交机制提出的可实现方案，不是已验证的源站兼容性保证。浏览器和 HTTP 客户端 TLS/网络指纹不同，账户 Cookie 的绑定规则也可能不同，失败应保留可诊断且不含秘密的原因。

## 可替换浏览器输入能力

若需要完整浏览器账户访问，可以新增可部署适配器，或维护经审核的浏览器服务补丁：在首次导航前向独立 context 注入带作用域的 Cookie，并显式处理 UA、出口和销毁。Playwright 提供 [context.add_cookies](https://playwright.dev/python/docs/api/class-browsercontext#browser-context-add-cookies) 与 [browser.new_context](https://playwright.dev/python/docs/api/class-browser#browser-new-context) 等 API；底层支持不等于当前 Byparr `/v1` 已提供相同契约，也不保证任意 UA 与其反检测浏览器配置兼容。

`ProxyServer` 对外应表达请求隔离、可用凭证策略和容量；`BrowserPageClient` / 适配器完成协议映射。强制凭证调用不能被仅支持匿名页面的适配器默默接收。可注入 Cookie、可绑定 UA、可重放挑战应分别表达，不合成一个不准确的“支持登录”布尔值。

## 验收与外部帮助边界

当前没有阻止本地 P3 开发的外部阻塞。输入模型缺少字段可以通过受控协议实现或新的可替换适配器解决；安全重放可使用确定性匿名挑战/账户页面 fixture 验证。隔离、版本撤销、Cookie 保留、同名冲突、重定向和失败关闭必须有自动化覆盖。

实际账户登录状态、当前 Jable/MissAV 等站点接受重放、真实多用户浏览器并发与长期凭证刷新尚未验收。只有把这些列为目标环境门槛时，才需要操作者提供受控测试环境及授权账号；不能要求用户在日志或文档粘贴 Cookie。凭证加密生产密钥与迁移处置属于部署环节，不能因缺少生产密钥阻止使用临时密钥的隔离测试，也不能因此自动明文回退。

本报告只新增核查文档；未修改浏览器适配器、凭证处理、配置或部署。正式 P3 的代码验证、格式门槛及目标环境验收由阶段执行记录分别报告。
