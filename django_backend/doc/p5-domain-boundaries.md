# 后端模块边界与扩展契约

本文维护当前职责和依赖方向，适用于资源、下载、翻译、推荐、会话与外部搜索。文件名保留以稳定已有链接；验证范围见[验证状态](validation-status.md)，字段和运行步骤分别见[接口](interface.md)、[数据库](database.md)、[推荐](recommendation.md)和[后端 README](../README.md)。

跨前后端设计原则与交付门槛见[重构原则与持续开发约束](../../docs/development-principles.md)，后端执行入口见 [AGENT.md](../AGENT.md)。后续扩展以本文能力边界为基线，不以抽象基类数量衡量设计质量。

## 核心与入口

| 模块                                    | 责任                                           | 依赖与替换位置                              |
| --------------------------------------- | ---------------------------------------------- | ------------------------------------------- |
| http/、http_base、http_parameters、urls | 输入/权限、参数与响应/缓存头映射               | 注入或装配用例，允许简单 ORM 查询           |
| tasks、maintenance_tasks                | task ID/重试/ownership 适配、运维 command 调用 | 保持原任务名；不在核心导入 Celery task 对象 |
| resource_workflow                       | 新增/刷新、来源选择与副作用时序                | resource_contracts、resource_data、展示函数 |
| download_workflow                       | 真实/模拟执行、进度、重试、失租与清理          | download_contracts；CLI 不在用例中解析      |
| translation_workflow                    | 标题选择、单条/批量状态、异常收尾              | translation_contracts；ORM/文本实现分离     |
| recommendation/base、workflow           | 统一流水线、hook 与上下文协调                  | contracts/entities/策略，运行请求副本       |
| source、external_search                 | 来源页面/详情/列表能力、来源排序与缓存上下文   | 页面获取、会话和来源 Adapter                |
| composition                             | 默认配置、工厂与生产 Adapter 装配              | 具体 Django/Redis/文件/来源实现             |

核心不导入 views、Celery task 对象或 composition 默认实例。resource_service 与 recommendation.manager 是仍有 HTTP/job/同步消费者的生产 facade；新核心从独立 workflow 导入。services 保留视频下载执行实现，资源查询归 resource_queries，不再提供过渡来源/列表导出。共享 AVDownloadInfo 在 resource_data；旧 scraper 导入路径仍导出同一数据类。

## 消费能力与生产 Adapter

| 核心消费能力                                            | 生产实现或用途                                                           |
| ------------------------------------------------------- | ------------------------------------------------------------------------ |
| SourceLookup、MetadataProvider                          | SourceManager、ScraperManager；详情与刮削能力                            |
| ResourceReader、ResourcePersistence                     | DjangoResourceReader、DjangoResourcePersistence                          |
| ResourceAssets、TranslationSubmitter、ResourceEvents    | FileResourceAssets、CeleryTranslationSubmitter、SignalResourceEvents     |
| DownloadExecutor、DownloadInfoResolver                  | VideoDownloadService、ResourceDownloadInfoResolver；缓存 miss 可准备资源 |
| DownloadRuntime、DownloadOwnership、DownloadPersistence | RedisDownloadRuntime、DownloadLease、DjangoDownloadPersistence           |
| TranslationRepository、TextTranslator                   | DjangoTranslationRepository、ManagerTextTranslator                       |
| CandidateInventory、RecommendationContextStore          | DjangoCandidateInventory、DjangoRecommendationContext                    |
| RecommendationSource、SeedProvider、SeedSelector        | Jable、LocalPreferenceSeedProvider、PreferenceSeedSelector               |
| CookieRepository、ListingSource                         | SourceCookieRepository、支持列表的来源能力                               |
| CoverLocator、TranslationRequests                       | FileCoverLocator、DjangoTranslationRequests；媒体定位及重新翻译请求      |

canonical contracts 是 ABC/数据输入唯一入口，测试替身实现相同消费者能力；不为纯函数、数据类或简单框架入口增加继承层。资源七项依赖在核心构造时显式传入，默认构造只在 composition；推荐算法不读全局 ORM，存在性按候选集合批量查询。来源关系先解析为 SourceRelations，持久化只接收 ResourceSaveInput，不接收源或 HTML，也不修改输入下载信息。

## 扩展方式

- 新详情来源：实现 SourceBase 必需能力，在 source_factories 注册；由公开 get_source/get_sources/get_home_url 查询，不调用私有别名或外部遍历 sources 容器。
- 新列表来源：实现 ListingSource，并注册 ExternalSourceAdapter 的能力描述及对应 CoverPolicy；通用搜索只消费来源能力、分页、缓存与进度，不加入源名分支。缺少能力的来源显式拒绝。
- 新推荐器/因子：实现 AbstractRecommender 或 RecommendationFactor，注入推荐器工厂和策略 factor builders。主 recommend 流程保留在基类，特殊扩种/补量使用 hook；HTTP 可选项是否开放另按接口契约决定。
- 替换存储/资产/运输：实现对应小能力，在装配替换，先以同一用例测试验证失败、幂等和副作用顺序。实现内 TypeError 不能作为旧签名重试依据。

## 保留的行为

HTML/封面先于 DB，头像和翻译提交在保存后，事件在完整结果后；文件/DB 没有统一补偿事务。真实下载正常成功通知先于 DB 持久化，DB 失败只告警；失租则抑制成功副作用。翻译批量失败只收尾本批仍 translating 项。HTTP 与旧 batch 共用重翻译请求，提交失败保留显式错误。旧同步资源入口继续存在。

HTTP 字段、URL、任务名、Redis key/TTL、文件路径、metadata 与关系规则由行为测试约束。改变上述语义须单独说明和验证；不能用结构迁移顺便更改。版本切换和目标环境验收见[部署说明](compose-deployment.md)与[验证状态](validation-status.md)。

## 验证入口

任务控制新增 `task_control_rules` 与 `task_records`：前者维护无框架依赖的状态迁移、允许动作和 ExecutionToken；后者是持久任务记录 Adapter，集中处理版本条件更新、操作者归属、执行 fencing、幂等命令和待派发记录。`task_models` 定义记录模型，由 models 注册。派发消费显式 callable，DB 事务内不导入或调用 Celery；旧任务入口暂未接入。详细契约见[任务控制计划](../../docs/task-pause-cancel-design.md)与[P1 执行记录](../../docs/task-control-p1-results.md)。

P2 的 `task_assets.TaskAssets` 独占任务私有文件的登记、校验、提升、回滚和清理；通过 `controlled_transaction` 与 DB 状态所有者协调，不调用记录 Adapter 的私有方法。producer/图像或视频 validator 由消费者传入；提交 persist 回调仅做短 ORM 操作，不含网络、Celery 派发或成功事件。`TaskAssetTarget` 的发布 marker 防止旧恢复覆盖后来的同内容提交。`resource_file_locks` 提供与既有删除相同的资源锁及短目标锁；装配根目录由 composition 提供。已有活动任务阻止正式删除，完整提交入口与新任务创建的并发协调在 P3/P4 接入时完成。资产准备仍未替换旧刮削/下载的文件行为，见[P2 执行记录](../../docs/task-control-p2-results.md)。

P3 `controlled_download` 编排持久控制、下载槽位、私有输出、媒体验证和提交，消费者显式提供 resolver/downloader/lease/persist/guard/project；`ReadOnlyDownloadInfoResolver` 不调用保存工作流。`download_resume` 独占 HLS 身份/分片复用校验，`task_processes` 负责进程身份与退出证明。`task_dispatch` 持久发布 Adapter 仅把待派发记录送 Celery，`task_download_projection` 按 owner 投影 Redis 并发送版本提示，HTTP 层鉴权/校验/裁剪快照。composition 装配资源锁和路径；业务终态及去重由 DB 管理，旧消息暂保留原执行兼容。下载提交回调额外允许有界 Redis owner 验证，不允许 HTTP 抓取、派发或成功事件；大文件 checksum 在 DB fence 外。见[P3 执行记录](../../docs/task-control-p3-results.md)。

[测试说明](../tests/README.md)按链路列出纯用例、Django/临时 Redis Adapter、URL/OpenAPI、任务注册与导入方向回归。无 Django 配置导入、完整能力替身、批量查询次数和原消费者行为共同证明可替换性；不按 ABC 数量或代码移动量判断质量。备份当前没有第三引擎共享需求，保留现有实现，不创建假想插件框架。

P4 `controlled_scrape` 编排分阶段检查点和受控资源提交；`scrape_preparation` 提供任务独立的来源/元数据/图片准备能力，只返回解析输入。`task_network` 负责请求预算、内容回调控制和分块写入；既有 Source/Scraper 的可选 task control 仅装配于新实例。`task_resource_persistence` 校验资源版本、复用原 ORM 保存并登记事件；`task_resource_events` 独占稳定事件出箱和收件去重。提交不包含网络/派发，暂停恢复调用公开 TaskAssets 完成查询而不访问私有路径函数。旧同步保存顺序保持，新受控流程将全部暂存图片与资源统一受控提交；详见[P4 执行记录](../../docs/task-control-p4-results.md)。

P5 `controlled_translation` 编排父任务 fencing、翻译请求、结果及停止确认；`owned_translation` 独占资源翻译 CAS 与中断收尾。`translation_contracts.translation_identity` 定义私有检查点身份，版本/owner 不通过资源 API 展示。主执行由 TaskRecords 持久交接独立 child，task_dispatch 按 role 发布，HTTP 继续处理登录/CSRF/版本输入；task_presentation 裁剪快照和资源标题，框架入口不互相导入。同步/批量 TranslationRepository 同样按本执行 owner 校验结果及异常，生产单条派发带 expected_generation。composition 创建任务专属翻译实例，原共享 TranslatorManager 不携带任务控制。元数据与翻译失效改为单个 ORM 事务，这是 P5 的显式行为变化，文件/DB 仍按 P2 提交日志协调。见[P5 执行记录](../../docs/task-control-p5-results.md)。

P7 `task_recovery` 编排派发补偿、停止身份核查、日志恢复、清理与事件重试，依赖显式 records/assets/dispatch/events/redis/inspect/stop_writers/interrupt；`task_processes` 独占本地进程归属与有界退出证明。TaskRecords 公开恢复 fencing、近期心跳复核及 stopped 日志状态，核心不遍历 Adapter 私有容器。`task_recovery_worker` 只管理 worker 生命周期线程，维护命令调用同一装配用例，扫描不依赖 Beat 或浏览器。CLI/媒体验证子进程继承稳定 job/attempt/owner 标记，覆盖 PID 登记前的父进程崩溃。人工旧实例确认仅是管理命令的运维断言，普通 HTTP 终止不能跳过 writer 退出证明。见[P7](../../docs/task-control-p7-results.md)。
