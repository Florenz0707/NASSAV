# Cloudflare 访问方案替代调研

调研日期：2026-09-26。本文只核对官方文档、发布记录、接口源码及本项目现有接入；未访问目标站点，未实测目标站点成功率，也未修改抓取实现。维护活跃、官方演示和宣传成功率都不等于本项目可用性保证。

## 结论

优先验证 **Byparr 的固定稳定版本**：它提供本项目正在使用的 FlareSolverr 风格 GET 接口，接入改动最小。如果希望长期自维护浏览器抓取能力，优先评估 **SeleniumBase CDP Mode**，但需要自己封装服务、浏览器生命周期和失败处理。愿意付费降低维护成本时，比较 **Zyte API** 和 **Bright Data Browser API**。暂不把独立 **Camoufox** 作为最稳妥的默认选择。

这些是基于接口、维护和工程成本的判断，不是成功率排名。应先以相同网络出口和同一组页面验证，再决定替换。

## 自部署候选

| 方案                  | 维护及定位                                                         | 与现有接口关系                                           | 主要限制                                                                   |
| --------------------- | ------------------------------------------------------------------ | -------------------------------------------------------- | -------------------------------------------------------------------------- |
| Byparr                | 官方发布页显示 v3.0.4，包含 TLS 和挑战处理修复                     | 提供 `/v1`、GET 和 `solution.response`，最接近现有客户端 | 并非完整 FlareSolverr API 替代；出口信誉、浏览器依赖与目标策略仍会影响结果 |
| SeleniumBase UC / CDP | 发布页显示 v4.54.12；有持续发布和完整自动化文档                    | Python 浏览器框架，需要封装 HTML 获取服务或独立适配器    | Chromium、浏览器进程、并发及虚拟显示需要自己维护                           |
| Camoufox              | Firefox 分支和 Playwright 风格接口；官方承认经历维护空档并恢复开发 | 不提供 FlareSolverr `/v1` 服务，需要自建适配             | 官方明确提示不适合稳定生产使用，并说明旧内核与指纹不一致影响效果           |

来源：[Byparr 发布记录](https://github.com/ThePhaseless/Byparr/releases)、[SeleniumBase 发布记录](https://github.com/seleniumbase/SeleniumBase/releases)、[SeleniumBase CDP 文档](https://seleniumbase.io/examples/cdp_mode/ReadMe/)、[Camoufox 官方仓库](https://github.com/daijro/camoufox)。

### Byparr：最小改动候选，但应按实际使用子集验收

网上常见的“Byparr 基于 Camoufox”已不能代表当前版本：v2.0.0 使用 Camoufox，v3.0.0 发布标题改为使用 invisible-playwright；v3.0.4 的依赖文件也使用 invisible-playwright。不能把 Byparr 与 Camoufox 当成同一条现行技术路线。[发布记录](https://github.com/ThePhaseless/Byparr/releases)、[v3.0.4 依赖](https://raw.githubusercontent.com/ThePhaseless/Byparr/v3.0.4/pyproject.toml)

核对 v3.0.4 固定版本源码发现：

- 提供 `POST /v1`，`cmd` 默认 `request.get`，但该字段只是兼容字段，实际仅执行 GET。
- 接受 `url`、`maxTimeout`、`returnOnlyCookies`，返回 `status`、`solution.response`、`solution.cookies` 和 `solution.userAgent` 等。
- `maxTimeout` 大于等于 1000 时按毫秒转秒；更小值按秒解释，与 FlareSolverr 的严格毫秒语义并不完全一致。
- 请求模型没有 session、postData 或逐请求 proxy 字段，不能宣称支持完整 session、POST 或代理参数语义。
- 超时与浏览器错误可能以 HTTP 408 / 502 返回，应确认客户端的重试和错误归类。

来源：[v3.0.4 请求与响应模型](https://raw.githubusercontent.com/ThePhaseless/Byparr/v3.0.4/src/models.py)、[v3.0.4 端点实现](https://raw.githubusercontent.com/ThePhaseless/Byparr/v3.0.4/src/endpoints.py)。

官方提供 Docker 镜像，默认端口 8191，支持全局 `PROXY_SERVER`。README 明确不保证挑战通过，并提示 NAS 支持有限；`main` 镜像属于未测试版本。因此验证时应锁定版本，不直接把滚动镜像替换到现有服务。[Byparr README](https://github.com/ThePhaseless/Byparr)

### SeleniumBase：长期自维护候选

CDP Mode 通过 Chrome DevTools Protocol 控制浏览器；官方提供 UC + CDP 和 Pure CDP 使用方式。这比只替换 HTTP 客户端具备更完整的页面交互能力，但它是框架，不是现成的 FlareSolverr 协议服务。[CDP Mode 文档](https://seleniumbase.io/examples/cdp_mode/ReadMe/)

官方 UC 文档明确指出，UC 与普通 headless 模式组合可被检测，GUI 操作在无桌面 Linux 环境需要虚拟显示。不能仅凭本地桌面成功，就假设容器里同样可靠。选型时应验证实际部署模式、浏览器启动成本、并发隔离及超时回收。[UC Mode 文档](https://seleniumbase.io/help_docs/uc_mode/)

### Camoufox：保留候选，谨慎评估稳定性

官方 README 写明项目仍在开发，可能不适合稳定生产使用；2026 状态说明提到曾有一年维护空档、Firefox 基础版本和新发现的指纹不一致导致效果下降，目前重新活跃开发。它提供 Playwright 风格 Python API，但并非一个可以直接替换 `/v1` 的服务器。适合作为后续浏览器实现候选，不宜仅凭“anti-detect”定位认定成熟可靠。[Camoufox 官方仓库](https://github.com/daijro/camoufox)

## 商业候选

| 方案                    | 官方能力                                             | 对本项目的工程判断                                       |
| ----------------------- | ---------------------------------------------------- | -------------------------------------------------------- |
| Zyte API                | `browserHtml` 返回浏览器渲染后的 HTML                | 与现有“获取 HTML → 解析”结构接近，需要新增请求与响应适配 |
| Bright Data Browser API | 托管浏览器，可配合 Playwright、Puppeteer 或 Selenium | 更适合复杂页面交互；需要浏览器会话适配，并评估服务费用   |

来源：[Zyte browserHtml 文档](https://docs.zyte.com/zyte-api/usage/browser.html)、[Bright Data Browser API 文档](https://docs.brightdata.com/products/scraping-browser/introduction)。

以上不代表厂商已确认支持本项目目标域名。付费前需要核实目标域名是否支持、实际计费规则、失败请求成本及可接受的访问频率；本次没有采购、开通账号或调用收费服务。

## 本地接入观察

当前 [FlareSolverrClient](../nassav/flaresolverr_client.py) 使用 `POST /v1` 的 `request.get`，直接取 `solution` 中的 HTML，没有传 session。这与 Byparr 已核对的 GET 子集接近，因此它是最容易隔离验证的方案。客户端保存了 `proxy` 参数，但没有把它放入请求 payload，不能假设浏览器出口与其他 HTTP 请求一致。

现有 MissAV 路径优先使用 FlareSolverr，随后回退 curl_cffi；Jable 路径则先直接请求，再回退 FlareSolverr。README 对 MissAV 的描述与实际顺序存在差异。后续若改实现，应同步描述实际顺序；本次保持代码及已有工作区修改不变。

`curl_cffi` 可以模拟部分浏览器网络指纹，但其官方 FAQ 不保证通过 Cloudflare；不能将其作为能够执行任意浏览器挑战的完整替代。[curl_cffi FAQ](https://curl-cffi.readthedocs.io/en/stable/faq.html)

## 验证与决策建议

1. 先记录当前镜像版本、失败日志、服务健康和实际出口，区分浏览器启动失败、挑战循环、HTTP 拦截及解析失败。
2. 独立部署固定版本 Byparr，通过现有客户端的 GET 子集做小规模对照；成功标准应包括目标业务元素与解析结果，不能只检查 HTTP 200 或服务返回的 `ok`。
3. 记录成功比例、延迟、CPU / 内存、超时和错误内容，并检查列表页、详情页是否表现一致。
4. 若 Byparr 不满足需求，再用相同样本比较 SeleniumBase CDP 与付费 HTML 服务，按稳定性和维护成本选择。

Cloudflare 官方说明验证受到浏览器环境、网络与 IP 变化等因素影响；替换库不一定能解决出口问题。FlareSolverr 官方也提醒，复用 clearance cookie 时需要匹配 User-Agent。不要把本地历史文档中的“cookie 必然绑定 TLS、绝不能复用”当成通用定律；是否可复用需要结合实际挑战和环境验证。[Cloudflare 挑战说明](https://developers.cloudflare.com/cloudflare-challenges/concepts/how-challenges-work/)、[FlareSolverr 官方说明](https://github.com/FlareSolverr/FlareSolverr)

FlareSolverr README 的 Captcha Solvers 部分仍提示其求解器不可用；这是特定能力限制，不能据此推导所有站点或所有请求都失效。本次没有足够日志确定本项目故障根因。[FlareSolverr Captcha Solvers](https://github.com/FlareSolverr/FlareSolverr#captcha-solvers)
