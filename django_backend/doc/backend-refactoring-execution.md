# 后端抽象重构执行记录

依据：[执行计划](backend-refactoring-plan.md)、[评估报告](backend-abstraction-report.md)。开始日期：2026-10-04。执行基线：`idle@c9aa701`，包含原分析基线 `106a719` 及文档整理。

用户已授权每个功能/阶段新建分支、质量门槛通过后自动提交并合并到 `idle`；工作树为 `/tmp/nassav-agent-worktree`，默认工作树保持 `dev`。质量门槛不能达成时停止后续阶段，与用户沟通后再决策。测试门槛通过不代表生产/目标环境已验收。

## 阶段状态

| 阶段  | 分支                                        | 状态                           |
| ----- | ------------------------------------------- | ------------------------------ |
| R0    | `chore/backend-refactor-r0-baseline`        | 已完成，质量门槛通过后自动合并 |
| R1    | `enhancement/backend-refactor-r1-contracts` | 已完成，质量门槛通过后自动合并 |
| R2–R7 | 待创建                                      | 未开始                         |

## R0：行为与隔离质量基线

本阶段不改变生产业务实现。新增测试设置、离线网络保护与特征测试，补齐测试网络替身，标识需要真实服务的样本。

### 六条链路行为矩阵

| 链路      | 入口与编排                                                        | 冻结的结果与副作用                                                                                                     | 关键测试                                                                                                        |
| --------- | ----------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| 新增/刷新 | 资源同步、批量、resource jobs → ResourceService                   | 已存在/不存在/不可访问错误映射；HTML先于持久化；封面、metadata、头像、翻译提交顺序；新增事件在完整返回结果后发布       | `test_metadata_format.py`、`test_scrape_jobs.py`、`test_refactoring_baseline.py`                                |
| 删除      | 单条/批量资源或视频入口 → ResourceDeletionService                 | 同AVID文件锁；文件先于数据库；失败返回阶段与确认删除项；可重试；空状态404                                              | `test_resource_deletion.py`                                                                                     |
| 下载      | submit_download_task → download_video_task → VideoDownloadService | 去重、单全局下载锁、队列/进度、CLI执行和输出确认；成功通知先于DB更新；DB更新异常仅告警仍返回成功；finally清理          | `test_download_persistence.py`、`test_refactoring_baseline.py`、`test_download_proxy_isolation.py`              |
| 翻译      | 单条/批量Celery入口 → TranslatorManager                           | 优先original_title、回退source_title；completed跳过；无标题skipped；translating→completed/failed；固定词替换和结果清洗 | `test_translation_cleaning.py`、后续R4补充用例契约                                                              |
| 搜索      | actor/genre详情或search jobs → ExternalSearchService              | 来源能力和默认来源；正常空列表是成功；源失败显式failed；分页进度与终态；取消保留部分结果，终态不被迟到写入覆盖         | `test_search_jobs.py`、`test_external_search_detail_api.py`、`test_missav_search.py`                            |
| 推荐      | RecommenderManager → strategy/seed/factor/recall → snapshot       | 固定随机种子、已有/屏蔽过滤、详情丰富与补量顺序、学习反馈、历史轮转                                                    | `test_recommendations_demo.py`、`test_jable_recommender_pagination.py`、`test_jable_page_lookup_recommender.py` |

下载的“先通知成功、持久化失败仍成功”与资源的“写库失败保留HTML”是现有行为特征，特征测试不意味着这些是推荐的长期一致性策略；修复要单独变更。

### 任务、缓存与会话契约

- Celery兼容名称：`nassav.tasks.download_video_task`、`mock_download_video_task`、`translate_title_task`、`batch_translate_titles_task`及现有运维任务；`nassav.scrape_jobs.run_resource_job`和 `nassav.search_jobs.run_search_job`。资源/搜索入 `scrape`，下载/模拟入 `download`，其他保留原路由。
- resource job：`nassav:scrape:lock:<AVID>`、`nassav:scrape:job:<task_id>`；锁TTL 14,400秒，快照TTL 86,400秒；token salt `nassav.scrape.job`，max age为快照TTL + 锁TTL + 1,860秒。
- search job：`nassav:search:lock:<query hash>`、`nassav:search:job:<task_id>`；继承上述Redis存储TTL；查询deadline 1,800秒、成功结果去重复用300秒；token salt `nassav.search.job`、max age 86,400秒。查询hash包含来源、域名、出口摘要、语言与抓取页数，不能跨上下文复用。
- 快照状态：`queued/running/succeeded/failed/cancelled`，保存时版本递增；终态不可覆盖。搜索取消释放本查询锁，撤销队列失败不撤销已保存取消结果。公开响应不暴露 `query_key`，全局WebSocket只发布路由/版本字段，不发布搜索结果和token。
- SourceManager信息缓存 `source_info:<AVID>` 与Scraper缓存 `scraper_metadata:<AVID>` 保留格式及1小时有效期；外部搜索缓存前缀 `external-search:v4:cn:` 保留其实体/来源/域名/出口/页数/排序上下文。
- Cookie+UA+过期时间+出口摘要是一个会话快照；DB版本校验、手工覆盖清理旧元数据、有限等待、owner检查、失租禁止共享写入、3秒业务页验证、挑战/错域拒绝规则保持。
- 会话刷新key按来源/站点host/路由区分；刷新协调复用会话，不复用其他请求的业务页面。MissAV策略继续按既有配置，重构不自动改变抓取策略或复用开关。

### Interface 契约登记模板

R1起每个新增或收敛的Interface都应登记下列内容，并使用生产Adapter和测试替身验证真实变化点：

| 项目         | 必须明确的内容                                                                 |
| ------------ | ------------------------------------------------------------------------------ |
| 输入与返回   | 规范化责任、可空字段、结果类型、来源上下文；不得要求消费者遍历内部实例容器     |
| 错误         | 不支持、业务不存在、合法空结果、访问失败、超时、内部错误如何区分及对外兼容映射 |
| 副作用与顺序 | 网络、文件、DB、任务和事件的执行时机；失败后的确认结果                         |
| 幂等与所有权 | 重复投递、CAS、租约丢失、终态保护、重试可重复的步骤                            |
| 并发与状态   | 请求局部状态、进程缓存、共享状态、批量读取要求                                 |
| 可观测性     | 事件字段、状态版本、脱敏规则、调用次数/有限等待预算                            |

### 可复现的离线质量门槛

从工作树 `django_backend/` 运行：

```bash
uv run pytest tests/ --ds=django_project.refactoring_test_settings -v
```

设置模块强制使用无凭证模板、无开发.env、临时SQLite和资源目录；缓存与Channels使用进程内实现，用户设置也在临时目录。会话fixture和相关测试使用模拟Redis/JobStore。模块关闭翻译器的启动探测，真实Ollama测试归入external，不作为离线通过证据。

离线fixture阻止未模拟的requests/curl_cffi调用及IPv4/IPv6 socket连接；即使业务捕获异常，测试收尾仍报告未模拟网络错误。测试自己的网络替身可覆盖阻断方法。此保护限当前测试进程，不是子进程的网络隔离器；启动子进程测试自行使用临时路径和无凭证配置，连接失败样本只指向本机不可用端口。真实站点、Redis/PostgreSQL和worker验收需独立环境。

被标为external的翻译、Javbus真实抓取、资源样本、浏览器现场样本在该门槛中跳过；普通项目设置下现有显式现场运行方式保留。缺少非入库HTML样本导致的既有skip需单独记录，不把跳过样本计为通过。

从工作树根目录运行：

```bash
pre-commit run -a
```

### 本阶段补齐的缺口及验证结果

- 资源写库失败后的HTML与新增事件、下载成功事件/写库异常/清理顺序、搜索空结果与错误分别新增行为测试。
- 推荐屏蔽样本补充详情丰富替身；MissAV无效列表样本补充直连回退替身。Javbus真实封面样本及真实翻译样本标为external，不隐藏普通业务测试失败。
- 启动入口子进程明确选择生产配置模块，避免继承父进程离线测试配置而绕过启动验证。
- 首次全套：451 passed、23 skipped、10 failed、4 errors。失败来自上述隔离缺口和受限环境WebSocket本地通信；修正测试隔离后相关83项通过，获准本地运行的WebSocket 3项通过。
- 全套最终结果：**465 passed、24 skipped，45.24秒**。跳过为external现场样本及缺少非入库HTML的既有样本；没有失败或网络保护错误。新增下载测试在全套重载模块场景下也通过，未依赖陈旧单例引用。
- 全量 `pre-commit run -a` 的首轮仅格式化器修改文件，其余类型/编译/构建/测试检查通过；采用格式化结果后复验全部通过。提交 `77e149c` 已合并到 `idle`。

## R1：能力契约与装配

基线 `77e149c`。Source、Scraper 改为必需方法受 ABC 约束；列表能力单独声明，Memo 保持不支持列表的异常。移除无消费者的四份重复 Protocol，下载输出确认沿用 Downloader ABC；封面 URL 允许为空，源错误允许分类字符串。

SourceManager、ScraperManager、TranslatorManager 接受工厂，具体实现的默认注册集中在 `composition.py`。新增测试来源和刮削器无需修改 Manager。消费者使用公开 `get_source/get_sources/get_home_url`，不再访问来源内部容器和私有查询；旧私有别名暂作迁移兼容，R7 核查删除。

| 契约               | 输入、返回及错误                                                            | 副作用、并发与兼容                                                            |
| ------------------ | --------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| Source/Scraper ABC | 下载详情/metadata 解析沿用原对象与 dict；封面可空；未实现必需方法不能实例化 | 网络和缓存模板未改；工厂未启用的实现不构造                                    |
| ListingSource      | 实体、term、页码、排序、刷新；返回列表，未支持时显式拒绝                    | Jable/MissAV 实现；搜索错误与空结果映射未改                                   |
| Manager 公开查询   | 来源名不区分大小写；未找到返回 None；列表返回容器快照                       | 保留来源实例的状态；源信息缓存和优先级配置未变                                |
| Translator 可用性  | 首次公开查询或非空翻译探测；失败沿用无可用翻译器结果                        | 构造不联网，同实例通过锁只探测一次；恢复需重建实例。重试/固定词与批量规则不变 |

验证：新增契约测试 **18 passed**；定向兼容测试 **60 passed**；离线全套 **483 passed、24 skipped，45.56秒**。全量 `pre-commit run -a` 通过，包括类型、编译及前端构建/测试检查。真实远端、Redis/PostgreSQL、混合 worker 和目标环境仍未验收。
