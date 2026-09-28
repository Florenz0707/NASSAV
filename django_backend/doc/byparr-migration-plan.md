# Byparr 迁移与抓取层重构执行计划

日期：2026-09-26。状态：P0–P3 已实施，P4 部分完成，P5 生产观察待执行。本文保留迁移前的基线和设计决策；当前部署、检查结果与剩余验收项以 [Byparr 验收记录](byparr-rollout-validation.md) 为准。调研依据见 [替代方案调研](cloudflare-alternatives.md)。

## 1. 目标与执行原则

以 Byparr 替代当前失效的浏览器抓取路径，恢复 MissAV 详情页及 Jable 详情、搜索和列表页获取，并让后续更换浏览器提供方集中在一个模块内。

允许重构的范围是：浏览器客户端、页面获取与回退、配置装配、相关 Cookie 持久化调用、测试和部署文档。实施采用“先证明可用，再重构，再切换”的顺序。前端、数据库表结构、下载调度、推荐排序不纳入本次改造。历史参考代码目录已在后续版本移除。

用户已确认部署拓扑：Django 运行在宿主机，Byparr 用同机 Docker 部署，后端连接 `http://127.0.0.1:8192`。第 4 节的其他拓扑仅供未来迁移参考；出口和硬件在 P0 记录。

完成标准分为两层：离线测试证明实现正确，真实样本证明当前部署可用。任何一层不通过，都不能宣称迁移成功。

## 2. 已确认现状与设计约束

| 项目       | 当前行为                                                                           | 迁移要求                                           |
| ---------- | ---------------------------------------------------------------------------------- | -------------------------------------------------- |
| 浏览器请求 | `FlareSolverrClient` 使用 `POST /v1`、`request.get`、毫秒超时，返回原始 `solution` | 提供方响应转换为项目内部结果，业务层不读取原始字典 |
| MissAV     | 浏览器优先、直连兜底；浏览器路径只检查 `surrit`，直连非空即接受                    | 保留默认顺序，两条路径使用相同的业务内容校验       |
| Jable      | 直连优先、浏览器兜底；已有详情页和列表页校验器                                     | 保留默认顺序、缓存键和分页行为，复用校验器         |
| 网络出口   | 客户端接收 `proxy` 但不发送给浏览器服务                                            | 明确区分后端控制请求、直连请求和浏览器出口         |
| Cookie     | MissAV 直接操作 ORM；项目已有 CookieRepository 和运行时缓存                        | 复用现有存储与缓存链路，避免旁路更新导致缓存不一致 |
| 实例创建   | `SourceManager.SOURCE_CLASSES` 按源配置创建实例                                    | 在装配处注入页面获取模块，保持现有构造调用兼容     |
| 测试       | `test_flaresolverr.py` 混有 mock、真实网络及写库测试                               | 拆开契约、业务回归与显式启用的在线测试             |

Byparr 的源码核验基线为 **v3.0.4**，镜像标签为 **3.0.4**（上游发布工作流去掉前缀 `v`）；实施时复核镜像可拉取性、架构与 digest；不自动切换到滚动标签。该版本支持本项目所需的目标 GET 子集，但不能假设有完整 FlareSolverr session、POST、Cookie 注入或逐请求代理能力。超时统一传大于等于 1000 的整数毫秒，避免其小数值按秒解释的兼容行为。[请求模型](https://raw.githubusercontent.com/ThePhaseless/Byparr/v3.0.4/src/models.py)

该版本 `/health` 会通过浏览器访问 Google；失败不能直接证明本地进程不可用。返回路径将 `solution.status` 设为 200，也不能把它当作可信的目标站 HTTP 状态。必须单独验证内容。[端点源码](https://raw.githubusercontent.com/ThePhaseless/Byparr/v3.0.4/src/endpoints.py)

## 3. 阶段、交付物与放行条件

| 阶段           | 执行内容                                                                       | 交付物                                | 放行条件                                       |
| -------------- | ------------------------------------------------------------------------------ | ------------------------------------- | ---------------------------------------------- |
| P0：基线与环境 | 记录当前代码、配置、镜像、出口和失败表现；检查架构、Docker、可用内存及调用并发 | 环境记录、脱敏样本清单、现状结果      | 能复现并区分服务错误、挑战、无效页面和解析失败 |
| P1：独立验证   | 用独立端口运行固定版本 Byparr，直接验证协议及业务页面                          | 请求结果汇总、版本与 digest、资源指标 | 正向样本取得可解析 HTML；负向样本不被误判成功  |
| P2：模块与配置 | 实现公共 Interface、结果类型、Byparr/FlareSolverr Adapter、配置兼容和依赖注入  | 新模块及离线契约测试                  | 错误分类、超时、旧配置和提供方切换测试通过     |
| P3：业务接入   | 迁移 MissAV/Jable、统一校验和回退、调整 Cookie 存取                            | 业务回归测试及文档                    | 原有行为保留，挑战页不进入正常解析与缓存       |
| P4：部署验收   | 建立持久部署文件，执行完整离线检查和低并发在线对照                             | 验收记录、部署说明、回滚演练记录      | 满足第 8 节门槛                                |
| P5：切换观察   | 切换配置并重启相关进程，逐步恢复任务                                           | 观察记录及遗留项清单                  | 观察窗口内无持续退化，回滚路径可用             |

P1 不通过时，暂停后续重构，保留独立测试环境和证据，判断是否为出口、架构或 Byparr 本身问题；不得通过增加无上限重试把失败掩盖为可用。

## 4. P0–P1：部署与最小验证

### 4.1 基线记录

- 记录工作区现有修改及当前提交，不覆盖用户未提交内容。
- 保存当前配置和 FlareSolverr 镜像 ID、启动参数与日志；备份文件不进入 Git。
- 记录 Django、任务进程及浏览器服务所在网络命名空间，核对三个方向的出口：后端到服务、后端到目标站、浏览器到目标站。
- 记录 CPU 架构、可用内存、共享内存和既有抓取并发，分别记录冷启动与热请求结果。
- 样本使用当前可确认存在的页面，不沿用测试文件里可能已失效的固定编号；记录请求时间、页面类型及期望的解析结果。

### 4.2 独立启动示例

以下是计划执行时的命令，当前未执行。端口 8192 用于与原服务并存；先检查容器名和端口是否已占用，不删除原容器。

```bash
docker pull ghcr.io/thephaseless/byparr:3.0.4
docker image inspect ghcr.io/thephaseless/byparr:3.0.4 --format '{{json .RepoDigests}}'
docker run -d \
  --name nassav-byparr-trial \
  --restart unless-stopped \
  --shm-size=512m \
  -p 127.0.0.1:8192:8191 \
  ghcr.io/thephaseless/byparr:3.0.4
```

`512m` 为共享内存起始值，不是总内存承诺；按实测浏览器峰值调整。镜像标签、代理环境变量及共享内存配置依据 [Byparr 固定版本 README](https://raw.githubusercontent.com/ThePhaseless/Byparr/v3.0.4/README.md)。如目标机器无匹配镜像或浏览器启动失败，先解决兼容性再进入抓取验证。

首次先检查日志与 `/docs` 能否访问，再向 `POST /v1` 请求一个可控测试页面，最后请求样本中的目标页面。请求使用 `cmd=request.get`、`maxTimeout=60000`、`returnOnlyCookies=false`，控制请求超时初始为 70 秒。初次不额外开启媒体屏蔽，避免同时改变多个变量。

当前实现已改为通过 Django 的 `Proxy.Enable/url` 在每次 Byparr `/v1` 请求中传递浏览器代理；宿主机回环地址会映射为容器可达的 `host.docker.internal`。容器的 `PROXY_SERVER` 仅用于没有请求头的调用。代理必须允许来自容器的连接，详见[代理路由](proxy-routing.md)。

### 4.3 拓扑差异

| 拓扑                         | Django 使用的服务地址   | 注意事项                                                       |
| ---------------------------- | ----------------------- | -------------------------------------------------------------- |
| Django 在同机宿主机          | `http://127.0.0.1:8192` | 使用上述 loopback 端口映射                                     |
| Django 与 Byparr 都在 Docker | `http://byparr:8191`    | 同一个自定义网络，使用服务名；Django 容器内 localhost 指向自身 |
| Byparr 在远程主机或 NAS      | 可达的内网地址与端口    | 改用内网监听和网络访问限制，单独验证架构、延迟及代理可达性     |

控制接口只面向后端可达的本机或私网。浏览器出口配置独立于控制连接；适配器不得让内部控制请求意外继承目标站代理设置。

## 5. P2：目标模块与配置迁移

### 5.1 Module、Interface 与 Adapter

新增 `django_backend/nassav/page_fetching/`，以“获取一张经过业务校验的页面”为调用方的主要 Interface。浏览器协议、错误转换和回退集中于此，站点 URL 生成和业务解析仍归各 Source。

建议结构如下；实施时可以合并过小文件，但不扩成通用插件框架。

| 文件           | 职责                                                             |
| -------------- | ---------------------------------------------------------------- |
| `contracts.py` | `BrowserPageClient` 抽象基类、页面结果与失败类型                 |
| `browser.py`   | Byparr 与 FlareSolverr 两个 Adapter，复用已有 GET 协议处理       |
| `service.py`   | `PageFetchService`：按顺序调用、校验结果、执行有限回退和日志记录 |
| `factory.py`   | 解析规范化配置并创建依赖；不在模块导入时发网络请求               |
| `__init__.py`  | 小范围公共导出                                                   |

Interface 约定：

- `BrowserPageClient.fetch(url, *, timeout_ms)`：只获取页面，返回统一结果；不写数据库、不决定站点业务是否成功。
- 页面结果至少包含 HTML、最终 URL、提供方、耗时、可选 Cookie/UA、提供方报告状态，以及可选的失败分类。区分“提供方报告状态”和“可信目标 HTTP 状态”；Byparr 无可靠目标状态时后者为未知。
- `PageFetchService.fetch(url, *, direct_fetch, validator, strategy)`：接收直连调用和站点校验器，返回有效页面或明确失败；不包含特定域名、视频字段或 Cookie ORM 逻辑。
- Source 依赖抽象基类声明的方法；通过可选关键字参数注入模块，保留原有 `Source(proxy)` 调用形式。由 `SourceManager` 完成正常运行时装配，单测可注入 fake。
- 普通网络失败进入结果类型；非法配置和编程错误不统一吞成 `None`。最终在现有 Source 公共方法处转换为原来的返回约定，控制迁移范围。

保留 FlareSolverr Adapter 用于旧配置兼容及回滚，不实现运行时 Byparr → FlareSolverr 自动双重尝试。旧 `flaresolverr_client.py` 暂留为兼容入口，逐步迁移调用后再清理；不得复制两套相同请求与错误处理。

### 5.2 新配置草案

```yaml
BrowserFetch:
  Enable: false
  provider: byparr
  url: http://127.0.0.1:8192
  timeout_ms: 60000

Source:
  missav:
    browser_fetch_strategy: browser_first
  jable:
    browser_fetch_strategy: direct_first
```

这里只展示新增键；实施时合并到现有配置，保留各源的 `domain`、`weight` 等。试运行确认后才在实际运行配置启用；模板默认关闭。策略允许 `browser_first`、`direct_first`、`direct_only`，支持逐源上线。

配置优先级固定为：存在 `BrowserFetch` 时完整采用新配置；只有新配置块不存在时，才将旧 `FlareSolverr` 映射成 `provider=flaresolverr`。新块显式关闭时不能被旧 `Enable=true` 再次打开。二者同时存在时给出一次弃用提示，不逐字段混合配置。

缺省策略保持现状；未知 provider、策略、无效 URL 或超时值应清晰报错。`timeout_ms` 要求至少 1000 且为整秒的毫秒倍数，避免与上游取整语义不一致。配置在启动时读取，变更后重启所有持有 Source 实例的进程。

### 5.3 失败、重试与并发

- 分类覆盖服务连接失败、服务超时、无效 JSON/字段、提供方错误、目标挑战、空页面和业务页面不匹配；将 API HTTP 状态与页面内容分别记录。
- 每个候选 URL 的每种路径最多尝试一次，初期不开适配器内部自动重试。服务连接失败后，本次查找跳过其余候选的浏览器路径，仍允许既有直连路径继续；单个页面失败不永久禁用服务。
- 浏览器默认 60 秒、控制连接使用短连接超时及约 70 秒读取超时；直连沿用现有单次约 15 秒。明确这些是每次请求上限，不是端到端硬截止时间。
- MissAV 有 3 个候选、Jable 有 4 个；最坏耗时须按所有尝试累加评估，并核对 Web 反向代理、任务超时及调用方取消行为。不能只看单页 60 秒。
- P1 使用串行验证。P4 先按全部署一个浏览器请求同时执行验收，再测并发 2；实施限流时明确进程范围，不能把进程内 semaphore 当成跨 worker 的全局限制。只有实际调用并发要求跨进程协调时才接入已有 Redis，避免默认扩大架构。
- 日志记录源、提供方、请求标识、耗时、失败分类及候选序号；不记录 Cookie、代理密码或完整页面内容。不新建监控平台。

## 6. P3：业务行为与 Cookie

### 6.1 页面获取

MissAV 默认 `browser_first`，Jable 默认 `direct_first`；浏览器关闭时均可走直连。两条路径都先经过同一个 Source 校验器，校验不通过不能直接写缓存或进入正常解析。

MissAV 将“包含 surrit”提升为与现有解析器一致的结构校验，例如能提取所需 UUID/播放地址标记；验证过程不得下载媒体，也不得调用带额外网络访问的完整 `parse_html`。Jable 复用详情校验；列表校验补充合法空列表场景，区分零搜索结果、挑战页和页面结构变化。

保留候选 URL 的生成顺序、Jable 搜索/分页/推荐缓存行为。显式不存在页面、最终 URL 异常或结构错误要进入相应失败路径，不用一个状态码或一个词代表成功。直连和浏览器产生相同 HTML 时应给出相同校验结论。

### 6.2 Cookie 与管理接口

- 浏览器页面获取不以“数据库里存在 cf_clearance”为前提，也不额外先访问首页获取 Cookie。
- 不向 Byparr 发送其请求模型未支持的 Cookie、session 或逐请求 proxy 参数。
- 保留手动 Cookie CRUD 及当前 `/api/source/cookie` 请求/响应结构，保留直连路径使用手动 Cookie 的能力。
- MissAV 自动获取 Cookie 改为通过配置中的浏览器 Adapter 访问首页；先确认页面有效，再过滤目标域名适用的 Cookie。没有可用 Cookie 就返回失败，不覆盖已有值；返回 Cookie 也不宣称它一定能在 curl_cffi 中复用。
- 自动保存统一走 `CookieRepository`，遵守 `SourceManager` 的运行时缓存更新链路；不直接新增 ORM 写入路径。Jable 自动 Cookie 行为保持现有逻辑，浏览器 HTML 获取不依赖它。
- Cookie 页面与完整媒体下载分别验收：HTML 成功不等于播放清单或后续下载成功。对下载链路做回归检查，但不把大规模下载计入探测。

不新增数据库字段或迁移。文档说明 Cookie 成功只代表获取和保存成功；不把浏览器服务可用性与 Cookie 状态混为一谈。

## 7. 测试与文件改动清单

### 7.1 自动化测试

新增测试以公共 Interface 的行为为准，覆盖：

1. Byparr GET 请求、毫秒超时、正常响应，以及 HTTP 408/502、连接错误、JSON 无效、字段缺失、`status=error`、空 HTML。
2. `solution.status=200` 但 HTML 是挑战或不存在页面时不得成功；合法空列表可正常返回。
3. 两种提供方与关闭状态、两种优先顺序；首条路径有效则不额外请求，失败后只作有限回退。
4. 旧配置映射、新配置优先、显式关闭、非法配置；旧配置不会意外使用 Byparr。
5. MissAV 候选 URL 与结构解析、Jable 搜索/分页/缓存，以及 Cookie 保存后的缓存可见性、失败不覆盖既有 Cookie。
6. Byparr 控制请求不会误用目标代理；缺少 Cookie 不影响正常浏览器页面结果。

将相关真实网络测试集中到显式 `external` 标记，并增加显式启用开关；只加 marker 不会自动阻止默认执行。未启用时在发请求前跳过，启用验收时服务缺失必须判失败，不可用 skip 冒充通过。保留隔离测试数据库与配置，在线探测默认不写生产库。

测试文件建议：`test_browser_page_client.py`、`test_page_fetching.py`、`test_browser_fetch_config.py`、`test_browser_fetch_integration.py`。迁移 `test_flaresolverr.py` 的相关用例，复用现有 `test_source_cookie_api.py`、`test_jable_search.py`、`test_jable_search_cache.py` 和分页测试；拆分时保持原有回归覆盖。

实施阶段必须执行相关测试、后端全量 `uv run pytest tests/ -v` 及仓库根目录 `pre-commit run -a`。全量套件其他外部依赖须在 P0 核对，报告未具备的服务和未执行项，不能将外部依赖缺失描述为测试通过。

### 7.2 代码与文档落点

| 位置                                                        | 计划改动                                                    |
| ----------------------------------------------------------- | ----------------------------------------------------------- |
| `nassav/page_fetching/`                                     | 新增模块和两个提供方 Adapter                                |
| `nassav/flaresolverr_client.py`                             | 迁移共享逻辑、保留兼容入口                                  |
| `nassav/source/SourceManager.py`                            | 依赖装配，复用 Cookie 缓存更新                              |
| `nassav/source/MissAV.py`、`Jable.py`                       | 接入模块，统一有效性校验，移除提供方字典处理                |
| `nassav/source/SourceBase.py`                               | 只在复用直连接口所需处做最小改造                            |
| `django_project/settings.py`、`config/template-config.yaml` | 新配置、兼容规则与校验                                      |
| `tests/`、`pytest.ini`、`tests/README.md`                   | 契约/回归测试与在线测试启用方式                             |
| `scripts/byparr/compose.yaml`、`scripts/README.md`          | 固定版本部署、环境文件示例、启动/停止/日志说明              |
| 根 `README.md`、后端 `README.md`                            | Byparr 部署、迁移、请求顺序和故障排查                       |
| `doc/interface.md`、`doc/debug.md`、`doc/database.md`       | Cookie 行为说明、验证入口；记录无 schema 变化及既有存储约定 |

初期保留原 `flaresolverr.sh` 供回退使用，不执行其中删除旧容器的命令。新增 Compose 使用独立项目名及端口，记录镜像 digest；部署文件与密钥文件分离。新脚本如需编写，在文件头和 scripts README 中说明参数和用法。

## 8. P4–P5：验收、上线与回滚

### 8.1 建议验收门槛

以下是本项目的初始工程门槛，不是厂商保证，可按 P0 的运行资源和调用方超时收紧：

- 样本至少包含 MissAV 3 个详情页、Jable 3 个详情页及 4 个搜索/列表/分页页面；另设不存在页面、合法空结果、挑战页 fixture 等负向样本。
- 在线正向样本分两个时段各执行一轮，初期串行、请求之间至少间隔 5 秒；隔离或绕过缓存，记录每个样本实际是否调用浏览器，避免直连或缓存掩盖 Byparr 失败。
- 正向页面业务有效率至少 95%，两个源都必须有成功样本；负向误报为零。有效率分母、缓存命中、直连成功和浏览器成功单独报告，不用后续无限重试剔除失败。
- 热请求端到端 P95 不超过初始 70 秒读取预算，超时不超过 5%；冷启动单独统计。20 次请求只作为上线门槛，不构成长周期稳定性证据。
- 容器无 OOM、重启循环和明显进程泄漏；并发 2 测试若不达标，保持串行并记录吞吐限制。
- 离线回归通过、全量检查通过、至少完成一次切回旧配置或直连模式的演练。

### 8.2 切换顺序

1. P1 通过后完成 P2–P4；上线前保留旧配置和旧镜像记录。
2. 暂停发起新的抓取任务，等待在途任务结束，避免新旧配置混跑。
3. 保持原 FlareSolverr 在旧端口；启用新配置，先让一个源使用 Byparr，另一个源设 `direct_only`，验证后再启用第二个源。
4. 重启所有实际持有 Source 实例的 Web/任务进程；确认日志中的 provider 和服务地址已经改变。
5. 在约 24 小时观察窗口内恢复少量正常任务，检查成功率、超时、资源和 Cookie 管理功能，再恢复既有负载。
6. 观察完成后才考虑停止旧容器；删除旧兼容入口另列后续任务，不混入首轮切换。

### 8.3 回滚条件与步骤

触发条件：连续 3 次浏览器服务连接/超时错误、出现挑战页被当作业务成功、OOM/重启循环、Cookie 管理回归，或相对 P4 结果明显持续退化。立即停止新抓取任务并保留脱敏失败证据。

配置回滚优先：把 `BrowserFetch.provider` 和地址恢复为旧 FlareSolverr，或显式关闭浏览器获取进入直连模式；随后重启相关进程。仅恢复旧 `FlareSolverr` 配置不足以覆盖仍存在的新配置块。旧方案已知可能失效，因此回滚恢复的是原行为，不承诺恢复目标站访问。

代码回滚使用实施前记录的版本及匹配配置；保留手动 Cookie 和现有数据库数据，不清库。回滚后验证 Source 装配、Cookie API 和任务完成/失败反馈，再决定是否恢复任务。试验容器确认不再使用后单独停止，不影响旧服务。

## 9. 建议提交拆分与收尾

1. `[Chore] Add pinned Byparr trial deployment and verification guide`
2. `[Enhancement] Introduce browser page fetching adapters and compatible config`
3. `[Fix] Validate source pages consistently across browser and direct fetching`
4. `[Doc] Document Byparr rollout validation and rollback`

每个实施提交包含与其行为直接相关的测试，保持可独立审阅与回滚。实际提交前询问是否需要代为提交，并给出最终提交信息。

最终交付需列出：固定镜像及 digest、最终配置和拓扑、成功率/耗时/资源数据、检查结果、未覆盖项、已演练的回滚命令，以及剩余风险。当前文档只是计划，不代表这些步骤已经完成。
