# 多用户、来源凭证与共享资源池执行计划

制定日期：2026-10-14。代码基线：6bedcb6（v2.5.1之后的文档清理）。P0契约见[多用户契约](multi-user-contracts.md)，P1见[共享池架构](resource-pool-architecture.md)，P2见[账号策略](account-policy-architecture.md)。P3–P5已完成下述隔离实现，P6已完成历史、受控文件回收及派发/管理协议；P7已接入会话、个人凭证、本人请求/库命令与持有管理，管理员/本人结果图片已接入，缓存收尾与P8统一验收继续，普通用户登录继续关闭。本轮后续已获SQLite迁移授权；执行范围为隔离数据库，未导入现有实例、发布或清理资源。实施时重新核对HEAD、迁移叶节点和目标配置；当前开发迁移叶节点为0051。

## 1. 目标与首版范围

支持多个启用账号并发操作，个人状态/设置/凭证隔离；公共资源只准备一份，用户通过持有关系加入自己的库，最后一份持有释放后安全回收。管理员管理共享系统，普通用户不能删除他人资源或停止他人仍需要的工作。

首版采用以下设计默认值，已由[P0 ADR](multi-user-contracts.md)冻结；后续改变时先更新ADR及权限测试，再改消费者：

- 存储共享、用户库独立。共享池不是全员自动拥有的资源库；公开搜索摘要可以发现，正式详情、封面、视频和播放请求须有有效持有或管理员权限。跨账号凭证范围另行核查。
- 用户点击添加才建立持有；收藏/已观看/历史、事实缓存不自动算持有。稍后再看限定自己的有效持有；移出库时清除稍后再看、关闭新编辑/播放入口；宽限期内个人标记可暂留供再次添加，正式AVResource回收后原收藏/观看/备注按既有级联规则清理，历史快照和个人进度保留。若要永久保留备注/标记，须在P0另定稳定身份迁移，不默认承诺恢复。
- 公开资源可在身份、来源、规格与授权兼容时复用；私有凭证结果默认私有，不因为AVID相同就公开其媒体或鉴权上下文。
- 普通用户退出库只释放自己的关系。管理员强制下架立即阻止新访问，物理清理仍须停止写入者并处理读取占用。
- 自动回收为异步、有宽限期、可重试过程；建议初始宽限24小时，可由管理员配置。该数值不是当前配置默认值。
- 保留历史标题/番号快照及个人进度，资源已回收时明确不可播放；不以历史记录阻止回收。历史快照策略须在P0冻结，P6完成关系迁移后才启用自动删除。
- 不做评分、开放注册、任意命名播放列表、匿名分享、多宿主机存储集群或个人代理配置。Proxy.url与下载代理的现有用途分工保持。

## 2. 现状与必须改变的消费者

| 当前入口                           | 已有行为                                             | 计划变化                                                |
| ---------------------------------- | ---------------------------------------------------- | ------------------------------------------------------- |
| access.py/is_operator              | 仅指定启用账号可访问                                 | 启用用户准入＋明确管理员/对象权限，P8前不开放普通账号   |
| SourceCookie/CookieRepository      | 每来源一行，全局Cookie/UA/有效期/路线快照，版本校验  | 凭证归属与来源会话分离；所有读取、缓存、刷新显式带范围  |
| TaskRecords.reserve                | kind:avid全局去重，其他owner加入被拒绝，paused也占位 | 私有请求订阅兼容共享执行；取消请求与停止执行分离        |
| ResourceDeletionService            | 正式资源/文件删除，活动任务或promoting日志阻止删除   | 普通移出关系；物理删除只由受控回收/管理员流程调用       |
| AVResource与ProviderFactsCache     | 正式资源和事实缓存独立，资源删除不删缓存             | 增加池身份/版本，缓存补凭证范围，不将事实TTL当持有      |
| UserResourceState/UserWatchHistory | 状态按user，资源删除级联，历史唯一(user,resource)    | 补持有授权；历史迁移至稳定身份/快照，回收不抹掉观看历史 |
| 播放session/progress               | 控制绑定具体登录，个人进度与共享标记独立             | 准备/媒体读取补持有和版本授权，明确资产读取占用         |
| 前端查询与恢复                     | 部分个人缓存已隔离，外部搜索句柄/blob仍有待补齐项    | 账号/登录epoch、凭证与领域revision隔离，登出/撤销失效   |

核对来源：[任务协议](task-control-architecture.md)、[推荐协议](recommendation-architecture.md)、[代理路由](proxy-routing.md)、[代理并发](proxy-concurrency.md)、[抓取缓存](resource-cache-architecture.md)、[观看列表](viewing-architecture.md)、[接口](interface.md)。播放实现另审计nassav/playback下records、progress、gateway、local_gateway、local_files及HTTP入口；当前保留的[本地播放与进度设计](local-playback-and-progress-design.md)作为历史设计参考，不替代源码核对。

## 3. 权限与管理员功能

授权顺序：登录与启用状态 → 动作权限 → 对象归属/持有 → 凭证/媒体范围 → 版本与执行代次。共享工作内部使用明确的系统执行身份，不借发起用户账号绕过授权；所有用户身份由服务端会话确定，不接受body中的owner。

| 动作                       | 普通用户                         | 管理员                                        |
| -------------------------- | -------------------------------- | --------------------------------------------- |
| 查看搜索公开摘要、申请添加 | 按来源能力/配额允许              | 同样受来源能力约束                            |
| 正式详情、封面、播放       | 自己有效持有且媒体范围允许       | 共享系统资源可管理；个人凭证媒体另按授权      |
| 移出库、修改标记/备注      | 仅自己                           | 管理入口不默认读取/编辑他人私密状态           |
| 刷新/下载                  | 提交自己需求，受配额/限流        | 可发维护需求、修复共享版本                    |
| 取消用户请求               | 仅自己，不影响其他订阅者         | 可管理异常请求并记录理由                      |
| 暂停/终止共享执行          | 不直接授予，见P4规则             | 可强制操作并提示受影响需求                    |
| 个人Cookie                 | 写入/更新/撤销自己的；不回显明文 | 查看状态/撤销，不提供读取明文界面             |
| 系统Cookie、代理、来源开关 | 禁止                             | 配置、验证、轮换、停用                        |
| 用户管理                   | 自己基本账号操作                 | 创建/邀请、角色、停用、重置登录凭证、撤销会话 |
| 存储/任务/播放配额         | 查看自己的使用量                 | 设置配额与全局限额                            |
| 下架与物理回收             | 不能删除共享资产                 | 下架、预览引用/占用、受控清理/重试            |
| 运维与审计                 | 仅自己可见状态                   | 队列/worker健康、回收失败、备份恢复及审计     |

管理员账号权限和Django超级用户/后台权限分开定义，不将所有is_staff账号直接放行业务。保留最后一个可用管理员保护，敏感管理动作要求理由、对象版本及幂等request_id；日志保存操作者、对象、动作、时间与结果，禁止Cookie、源站签名URL、密码或备注正文。管理员账号停用/删除须有独立恢复流程。

个人备注/历史不默认提供全员查询或导出。若后续需要隐私排障功能，作为新的受审计权限设计。配额建议按每用户完整媒体逻辑大小计入，物理磁盘同一版本只计一次，避免复用绕过配额；附加配额在同一短事务预留并按幂等结果释放，失败/取消/超时不能重复退还。

## 4. 目标模型与迁移草稿

所有模型声明全小写下划线db_table。以下按职责分批新增迁移，不预占0037及之后的编号；实际实施按当前叶节点生成，保留0036及更早历史迁移。

| 模型/表名草稿                                        | 关键字段/约束                                                                                  | 状态所有者                                               |
| ---------------------------------------------------- | ---------------------------------------------------------------------------------------------- | -------------------------------------------------------- |
| ResourcePoolEntry/nassav_resource_pool_entry         | 稳定UUID、规范资源身份唯一、nullable resource FK、state、generation、version、gc_after         | 池生命周期，先有身份后有AVResource                       |
| UserLibraryEntry/nassav_user_library_entry           | user/pool唯一、pending/active、期望规格/范围、version、joined_at/updated_at                    | 用户持有意图；pending有效请求也阻止整池回收              |
| SourceCredential/nassav_source_credential            | UUID、source、system/personal、nullable owner、ciphertext、key_id、version、revoked_at         | 凭证归属与撤销；scope/owner组合CHECK，分域唯一约束       |
| SourceSessionSnapshot/nassav_source_session_snapshot | credential、host、出口/浏览器上下文、加密Cookie/UA、版本、generation、有效期、状态             | 单个来源会话；显式上下文唯一/索引                        |
| UserResourceOperation/nassav_user_resource_operation | UUID、user、pool、action、规范work_spec_hash、request_id/payload_hash、state/version、work引用 | 用户请求，唯一(user,request_id)                          |
| TaskWorkSubscription/nassav_task_work_subscription   | operation/work唯一、active/detached、需求类型/版本                                             | 共享执行的有效需求，关联既有TaskJob/attempt              |
| ResourceVersion/nassav_resource_version              | pool/version唯一、来源/媒体规格、access_scope、状态、资产manifest                              | 不可变可用版本；私有凭证版本不能被普通持有关系公开       |
| ResourceUseLease/nassav_resource_use_lease           | pool/version、kind、owner、到期/心跳、generation、关联session/work                             | 读取等临时占用；已有持久任务/promoting日志仍是强保护条件 |
| ResourceGcJob/nassav_resource_gc_job                 | pool/generation、claim owner、state、cleanup_state、错误/重试时间                              | 可恢复的物理清理，不以业务终态代替清理完成               |
| AuditEvent/nassav_audit_event                        | actor/action/object/request_id/time/result，脱敏细节                                           | 管理及关键授权审计，定义保留期与有界清理                 |

模型不是同时一次建完：P1建池/持有，P2权限/审计及配额所需持久记录，P3凭证/快照，P4请求/订阅，P5版本/读取占用，P6清理。按实际职责决定配额独立表，不为单字段配置增加泛化框架。

迁移采取扩展 → 显式回填 → 统一读写切换 → 最后清理旧字段。旧AVResource创建池条目，但既有资源的持有者须由操作者显式确认，默认不按收藏/历史反推归属；回填预览列数量、目标账号和异常身份，不移动媒体文件。旧全局Cookie先加密迁为系统凭证，不复制给全部用户；旧表在兼容窗口只作只读/回退来源，不能双向混写。遇到无法确认账号类型的Cookie按待审核状态处理。

既有资源生成初始版本映射时核查正式文件/marker，不因磁盘目录残留宣称版本有效。旧TaskJob/attempt继续收尾，不直接把旧owner任务变成共享任务；切换前停止/迁完活跃执行或使用明确只读兼容适配。历史回填稳定pool身份、标题/AVID/来源快照后才移除强级联关系；不凭空添加观看事件。

迁移测试覆盖SQLite及UTF8 PostgreSQL升级、回退、再次升级、NULL/条件唯一约束、Unicode、关系和业务数据保持。导入命令默认预览，仅显式apply写入，保留已编辑数据、幂等，拒绝不明确冲突。每批回退的数据损失/重复身份约束随迁移文档注明；不可安全回退时从备份恢复，不强删用户数据恢复旧约束。

## 5. 来源Cookie与缓存协议

CredentialResolver向查询、推荐、刮削、下载准备和播放提供不可变凭证引用/有效会话，不暴露全局可变Cookie。每次并发操作拥有独立HTTP jar/浏览器上下文；用户A的Set-Cookie不能改用户B的会话。来源凭证优先级由请求选择或已保存合法偏好决定，不因个人失败静默改用另一用户凭证；是否退回系统凭证作为显式策略并提示。

刷新过程：读取凭证/快照版本 → 按credential身份＋host＋出口/浏览器上下文领取owner租约 → 事务外验证目标业务页 → 短条件事务检查凭证仍有效、版本/generation/租约及执行身份 → 发布 → 仅释放自己的租约。人工改写/撤销递增版本，使旧刷新及缓存结果失效；不能upsert复活已撤销凭证。UA/上下文变化形成新快照，出口摘要不是实际出口一致性证明，仍需目标环境验证。

正常会话读取不拿刷新锁；刷新同域去重，失败有有界退避，不能触发全站刷新风暴。共享会话是否可并发由通用会话能力声明，必要时限制为1或选择独立会话池；ProxyServer接收session范围限额，仍受全局Redis容量限制，避免嵌套槽位死锁，不按Byparr/provider分支调度。

凭证加密使用专用可轮换服务端密钥/key_id，备份恢复必须包含受保护密钥；密钥缺失时明确不可用，不回退明文。HTTP只返回状态/最后验证时间/掩码，不回传完整Cookie；历史读取明文接口仅在旧operator兼容期保留，开放普通用户前停用。任务参数保存凭证ID及执行绑定的版本，不保存Cookie；实际敏感快照只留于受保护存储/执行内存，媒体会话不在URL暴露凭证。

缓存键显式隔离system/personal身份、凭证版本、host、出口和解析版本；缓存不得仅靠user_id/AVID。公开事实与私有结果分别发布：个人登录特有元数据、签名播放URL、鉴权headers默认不能进入公共复用域。公开元数据提升需明确可共享证据/策略，首版默认关闭个人产物提升；共享库持有不能授予他人私有媒体权限。撤销凭证阻断未来prepare/刷新/提交，并按会话依赖关闭相关播放；已授权生成的长期资产是否保留按冻结的共享策略处理，不自动将其开放。

## 6. 持有、任务与版本协议

### 6.1 添加与复用

1. 校验身份、来源/凭证权限、配额和规范化请求；以user/request_id幂等，同键不同payload返回409。
2. 短事务锁pool行，建立pending持有和用户operation；pending_gc时取消回收并提升generation，deleting或cleanup_failed时返回可重试冲突，不授予旧文件；reclaimed时提升代次重新准备。
3. 从兼容且授权的ready版本选择结果。有完整结果则直接转active，配额仍按用户逻辑大小核查；过期m3u8不算可复用媒体会话。
4. 无结果则加入匹配work_spec_hash的共享执行，或先持久化执行/派发记录再由Celery运输ID。规格至少包含pool身份、动作、来源/媒体规格、凭证/共享域及要求的事实版本，不含原始秘密。
5. 事务外准备，提交同时检查attempt/execution/generation、pool代次、凭证版本及需求仍有效；失败保持旧版本，用户operation独立记录失败；首次添加最后一个需求失败/取消时释放其pending关系和配额预留，但不移除已有active持有，也不在资产清理完成前解除writer保护。
6. 对仍有效订阅发布授权快照，用户operation成功后持有转active。取消后迟到成功不得重新建立该用户持有。

不同来源/字幕/媒体规格不得只凭AVID去重。相同公开资源可共用公开执行；A的个人凭证执行不能直接接受B订阅。任务发起者不是共享执行永久控制者，共享worker使用系统执行授权和明确凭证引用，审计保留发起信息。

### 6.2 取消、暂停与终止

普通用户取消自己的operation会原子脱离订阅并清理该请求的pending意图/配额；仍有有效需求时共享执行继续。最后需求撤销时请求停止，并等待既有停止证明/资产清理，不能直接置执行cancelled后删文件。复用的正式资源不因一次取消回滚。

普通用户第一版不控制共享worker暂停/恢复，只提供“取消我的请求”；管理员才可暂停/恢复/终止共享执行。若后续增加“暂停我的需求”，必须单独定义用户订阅状态，不能复用TaskJob.paused。paused工作占用、失效订阅及恢复代次沿用当前协议，管理员终止须通知仍在等待的用户并保留失败/取消原因。

退出库与取消操作分开：有共享需求时移出自己库要先撤销自己的关联需求，不能撤销他人。账号停用/删除同理，先撤销该账号会话/个人凭证和订阅，再删除持有；共享系统工作有其他需求时继续。网络失败保留幂等ID，前端只中止轮询不能算后端取消。

### 6.3 更新与播放版本

普通用户提交刷新需求，按资源版本/配额/冷却时间合并兼容执行；管理员可提交维护刷新。元数据、图片、翻译和媒体准备结果以新版本发布，失败保留旧可用内容；个人标记/备注不随共享事实更新重置。翻译使用当前共享翻译规则，未来用户自选语言/模型须增加独立规格，不让用户覆盖所有人的译文。

媒体版本目录及manifest不可变，当前版本指针在短提交中切换；覆盖现有正在读取文件的方式必须逐步退出。播放session固定具体授权版本，正常刷新仍检查原身份/代次，不因池更新套用新媒体时间轴。旧版本仅在无持有需求、播放占用、写入/补偿日志时回收。新prepare/claim、详情、封面与缩略图要求有效持有；既有播放的清单、密钥、分片、Range/HEAD须检查登录、版本、凭证范围及下述受限读取授权，不能只检查曾经登录。普通移出后的已有播放是否允许完成按7.2规则执行，登录绑定与进度writer规则保持。每一版本按有效需求的规格/授权范围核算引用，B持有公开版本不会永久保护A已无人需要的私有版本；旧版本读取pin和当前版本指针单独检查。

## 7. 锁顺序、回收与故障恢复

### 7.1 锁与代次

- DB的pool行和关系唯一约束是持有与生命周期真相；ref_count可作投影，不能作为单独删除依据。跨用户添加/释放、配额预留按同pool串行化，用户内个人状态仍沿用已有user fence。
- 任务执行使用既有owner租约/attempt/generation，资源发布再检查pool generation和版本；仅拿Redis锁不足以防失租进程写文件。
- 文件操作复用resource_file_locks和TaskAssetTarget。文件锁顺序保持task → resource → 按规范路径排序的target；只有取得文件锁后才进入必要的短DB提交，不在DB事务里等文件锁。
- 多DB行的锁顺序在P0/P1冻结：需要user fence的操作先user，再按规范身份排序pool，再operation/work相关行；禁止另一路pool→user。共享系统发布只锁所需pool/work，不为了通知用户在持锁事务中遍历取得user fence。
- 网络、下载、复制、大文件哈希和broker发送不进入短DB事务。对慢步骤使用资产日志/条件提交补偿；稳定flock文件不在线unlink。
- 首版单宿主机、各容器同一支持flock的共享文件系统。未来多宿主机须另做分布式协调和条件发布设计，不能以当前锁协议直接部署。

### 7.2 回收状态机

```mermaid
stateDiagram-v2
    ready --> pending_gc: 最后持有释放
    pending_gc --> ready: 宽限内重新添加
    pending_gc --> deleting: 宽限结束且无需求和占用
    deleting --> reclaimed: 资产清理及DB收尾完成
    deleting --> cleanup_failed: 权限或IO失败
    cleanup_failed --> deleting: 重试同代次清理
    reclaimed --> preparing: 新添加提升代次
    preparing --> ready: 合法结果发布
```

pending_gc只标记，不立刻删文件。GC由持久记录＋后台有界派发执行；多个scheduler/worker重复领取只能有一个owner。检查pending/active持有、有效订阅、活跃/暂停任务、读取占用、promoting/补偿日志和管理员保留标记；TaskJob状态终止但清理未完成仍禁止回收。

GC取得共享文件锁后，在短事务中再次检查引用/占用及gc_after，CAS进入deleting并保存claim owner/generation；随后事务外执行日志化删除。所有新attach/播放lease申请同时锁同pool并拒绝deleting，因此删除检查与新引用不能穿透。进入deleting后不允许原地复活；第一版返回409和结构化retry_after_seconds，客户端保留输入并允许重试，不宣称HTTP Retry-After本身会自动重试。

删除前校验目标版本/marker/路径归属，按资产日志幂等推进。崩溃后由恢复任务检查owner、停止证明和已完成资产记录；缺失文件可按已确认日志收尾，身份不明则保留现场。清理失败保留tombstone及错误，不回到ready暴露残缺文件；再次添加须等该代次收尾后准备新代次。

只有最后一个用户移出仍不代表可以杀死正在读取的文件。首版默认普通移出允许已有授权播放在既有绝对期限内完成，但拒绝新会话/接续；只有此前合法创建且固定版本的session获得该受限读取授权，不延长期限或授予其他请求，版本读取占用保护资产；管理员强制下架立即拒绝后续读取，关闭对应会话并等待句柄/worker退出。两种撤销语义由P0冻结，客户端不能自行延长授权。占用租约过期不等于writer停止，未知活跃写入者仍按现有TaskArtifact恢复规则阻止删除。

共享头像、同内容资产、缓存和历史分别处理：头像仍被其他资源引用时保留；仅清理属于该版本的文件，不清空公共目录。原站事实缓存按TTL独立保留、只清缓存记录。历史快照没有媒体访问权，回收后显示“资源已移出/不可播放”，个人进度保持已有AVID账本及清除墓碑协议。

## 8. 接口与前端草稿

下表是候选地址，不是当前可调用接口。P0核对现有URL/envelope后冻结，迁移API不采用悄悄改变旧DELETE含义的方式。

| 入口草稿                                              | 行为/关键契约                                                             |
| ----------------------------------------------------- | ------------------------------------------------------------------------- |
| POST /api/library/entries                             | 建持有/需求，返回用户operation及复用/排队结果；user由会话确定             |
| GET /api/library/entries                              | 只列当前用户的有效/pending库及个人投影，分页/排序保持稳定                 |
| DELETE /api/library/entries/{id}                      | CAS释放当前用户关系，返回released/gc_scheduled，不声称文件已删除          |
| POST /api/library/entries/{id}/operations             | 请求刷新/下载，带request_id和期望版本/规格                                |
| GET /api/my-operations/{id}                           | 私有请求快照，operation_id/version/allowed_actions；共享job信息仅安全摘要 |
| POST /api/my-operations/{id}/cancel                   | 仅取消自己的需求，返回是否仍有共享执行，不泄露他人身份/数量细节           |
| GET/PUT/DELETE /api/me/source-credentials/{id}        | 自己凭证元信息/盲写/撤销；GET不返秘密，PUT带expected_version              |
| /api/admin/users、source-credentials、resources、work | 按明确动作权限管理，版本/幂等/理由/审计齐备                               |
| /api/admin/resource-gc                                | 预览阻塞条件、执行或重试受控回收，无直接路径删除接口                      |

沿用code/message/data/pagination与CSRF；跨账号对象通常404，已认证但无动作权限403，版本冲突409，参数400，配额按冻结契约返回明确错误码。旧资源DELETE在兼容期仅管理员保留原全局语义，普通用户禁止；前端按钮改“移出我的资源库”。普通用户不直接消费其他人的TaskJob owner快照。

共享job的version和用户operation version分别存在，前端taskJobs/view-model按用户operation身份合并，不以AVID或原共享job ID冒充自己的可控任务。WebSocket只推所属用户安全版本提示，补取授权快照，管理员频道单独授权；资源版本事件不包含持有者/凭证/备注。

个人缓存key增加账号＋登录epoch＋领域revision，必要时带credential/media scope；注销、角色/持有撤销和凭证改写使旧响应/恢复句柄/blob失效。外部搜索token从签名持有进一步绑定用户/授权上下文，不能恢复旧账号任务；共享公开搜索内容命中后重新计算is_in_my_library、黑名单和可执行动作，不能用全局库存禁用“加入我的库”。个人响应不进入公共HTTP缓存，图片/Range即使命中缓存也须受授权入口控制。

## 9. 分阶段执行

各阶段使用新分支，从当时最新idle开始；阶段内按模型→核心→HTTP/前端→文档拆聚焦提交，阶段门槛全部通过后合并idle。门槛无法达成就停止该阶段合并，与用户沟通，不靠跳过失败检查推进。

| 阶段/建议分支                          | 依赖   | 必须交付                                                                                  | 阶段验收与停止条件                                                                           |
| -------------------------------------- | ------ | ----------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| P0 doc/multi-user-contracts            | 本计划 | ADR冻结权限、资源身份、凭证共享、移出/下架、历史、配额语义；全部入口/锁顺序清单及响应样例 | 全部消费者有状态/授权所有者；未决项不得当已批准行为                                          |
| P1 feat/resource-pool-membership       | P0     | 池/持有模型，显式旧资源归属预览/回填，attach/release核心；自动回收关闭                    | 双用户/重复添加只有唯一关系，pending计入保护，零持有只标记；SQLite/PG往返数据保持            |
| P2 feat/multi-user-policy-admin        | P1     | 动作/对象授权模块、管理员基础管理与审计、配额预留、停用/会话撤销；operator生产门禁保留    | HTTP/WS/媒体/图片全入口负向授权矩阵；普通用户不能调用旧全局删除/控制                         |
| P3 feat/scoped-source-credentials      | P2     | 系统/个人凭证与快照迁移、密钥轮换、范围resolver、刷新fence、缓存域及ProxyServer会话限额   | A/B不串Cookie，旧刷新不能覆盖人工改写/撤销；私有事实/链接不公共发布；密钥丢失明确失败        |
| P4 feat/shared-work-subscriptions      | P1–P3  | 用户operation/订阅、兼容规格去重、持久派发、独立取消、管理员共享控制、用户快照/WS         | 同公共规格抓取一次；取消A不停止B；最后订阅撤销后确认停止；旧成功不重建持有；broker故障可恢复 |
| P5 feat/resource-version-publication   | P4     | 版本/资产manifest、当前指针、下载/刷新发布、读取占用与授权版本绑定                        | 更新失败旧版可用；播放固定旧版；不同媒体/凭证范围不合并；失租发布无成功副作用                |
| P6 feat/resource-pool-gc               | P5     | 历史快照迁移、GC状态机/宽限/有界调度、资产引用、失败恢复/管理预览；自动apply仍关闭        | 添加对最后释放/GC竞态可线性解释；无活跃writer/读者误删；多次恢复幂等；不删其他资源头像/缓存  |
| P7 feat/multi-user-library-ui          | P2–P6  | 我的库/移出、操作订阅、个人Cookie盲写、管理员页面、账户/域缓存、错误与重试                | 两真实账号浏览器隔离；公共结果可加入各自库；控件五态/键盘/弹窗/深浅/窄屏通过，旧缓存不串账号 |
| P8 chore/multi-user-release-acceptance | P0–P7  | 统一部署/迁移/回填指南，双用户真实worker/来源/GC故障验收，管理员恢复演练                  | 目标验收通过后逐步启普通账号，再启自动GC；任一越权/误删/共享停止问题阻断开放                 |

P7界面原型/只读装配可提前，但不能在P2–P6协议未完成时开放真实动作。P2首先覆盖管理员用户/角色/会话/来源/任务基础；配额界面、GC面板和敏感运维动作分别随对应后端阶段交付，不能做前端假成功。备份恢复仍走维护窗口命令，不默认开放一键破坏性恢复。

建议开关在实施时统一进入启动配置契约：多用户准入、共享池读写切换、GC自动apply默认关闭，回收宽限/批次/重试、会话范围容量有界校验；来源凭证与账户配额由DB持有。开关只能改变是否开放入口，不用关闭功能绕过数据授权或假装回到旧数据结构。同步本地/Compose配置样例；不在实现前增加无消费者配置项。

## 10. 测试矩阵与质量门槛

| 场景                                          | 必须证明的结果                                                    |
| --------------------------------------------- | ----------------------------------------------------------------- |
| A/B同时首次添加，相同/不同request_id          | 一份兼容工作、各一份持有；重复同键不扣两次配额                    |
| A/B来源或私有凭证不同                         | 不串会话、不泄露签名URL，不误加入私有执行                         |
| A取消、B等待；最后需求取消；暂停/恢复         | 各用户结果正确，共享执行仅按冻结控制规则停止，新attempt拒绝旧提交 |
| 取消后迟到成功、broker派发重复、worker重启    | 不复活用户关系，派发/事件幂等，可按持久记录恢复                   |
| 最后释放与新添加、GC标记/claim/删除各节点竞争 | pending_gc可取消；deleting明确可重试；不会成功授权已删除文件      |
| 更新与播放/下载/旧版本GC并发                  | 当前指针原子切换，旧读取可完成，旧writer不能覆盖新版本            |
| 刷新与Cookie人工更新/撤销/密钥轮换并发        | 持久/Redis/进程缓存都不能恢复旧凭证；匿名/私有范围正确            |
| Redis/代理/浏览器/数据库不可用                | 不绕过授权、限流或lease检查，失败/部分成功明确且不发布假成功      |
| EPERM、复制/删除失败、进程被杀、promoting残留 | 资产日志可恢复，未证明停止保留现场，清理终态独立，错误可审计      |
| 账号停用/删除、角色降级、管理员下架           | 请求/会话/订阅及时撤销，旧WS/token/blob不能继续发新授权请求       |
| URL/UUID猜测、跨用户分页/封面/Range/缓存恢复  | 全入口拒绝越权，普通用户不见其他人的Cookie/备注/任务参数          |
| 大量无持有资源、过期占用、重复调度            | 清理有界、索引覆盖、无全表无限扫描，过期租约不替代writer停止证明  |

实现阶段至少执行根pre-commit run -a；后端变更执行完整隔离pytest，新增迁移另在SQLite/PostgreSQL覆盖升级→回退→再次升级。前端代码执行pnpm run check，交互/主题/生命周期另做Playwright。模拟API、eager任务、传参测试只证明其层级，不替代真实worker、ProxyServer、来源或正式数据库。

```bash
pre-commit run -a
cd django_backend
uv run pytest tests/ --ds=django_project.refactoring_test_settings -v
# 回到仓库根目录后进入前端
cd ../vue_frontend
pnpm run check
```

并发验收使用可控barrier/故障注入与独立事务，不只靠串行调用或sleep制造概率；断言调用次数、授权快照、资产路径/marker、有效关系和占用。负载目标由P0结合部署资源冻结：记录N用户、每用户M并发、后端峰值/延迟、ProxyServer上限及清理批次，不在未测量前承诺性能数字。至少覆盖两独立用户和同用户双登录，不能只用双登录证明跨用户隔离。

## 11. 上线与回退

1. 核对引擎/叶节点、资产目录、共享文件系统能力、密钥备份、旧operator、活跃任务/session及全部消费者版本；备份DB/配置/媒体恢复点。
2. 先做隔离库和目标模式预演，关闭业务新提交，停止所有旧写入者，按现有停止协议处理活跃执行，禁止混跑。
3. 新版迁移及只读导入预览，人工确认归属后apply；核对资源/文件数、关系数、初始版本、Cookie分类和加密状态，记录异常而不默默丢弃。
4. 所有消费者统一版本，operator门禁保持，仅管理员验证新库和共享工作；GC先dry-run，核对候选/阻塞原因。
5. P8验收通过后按受控账号逐步打开普通用户；监测授权拒绝、重复工作、配额差异、刷新冲突、清理失败及代理容量。
6. 再启有宽限、有界批次的自动GC；首批逐项抽查，保留审计与回退恢复点。

回退首先关闭普通账号/自动GC/新任务，不直接切旧镜像。停止新消费者，备份新增关系/私有凭证/操作/版本/历史快照，再依据实际迁移图用新代码逆向；用户持有与私有凭证无法用旧全局表表达，不能自动压成一份Cookie或共享收藏。已回收媒体不能由DB逆向迁移重建，须从备份恢复或重新准备；新多版本目录旧代码不能识别时保持维护窗口并恢复匹配文件布局。不存在安全回退映射时前向修复或整体恢复，不为启动旧代码删除冲突行。

## 12. 阶段完成判定与本文件维护

每阶段更新接口、数据库、任务/缓存/代理/观看职责、配置及必要前端契约，CHANGES写当时未发布分类，已发布历史不改。执行记录包括基线/分支/提交、命令退出码、通过/跳过、迁移数据检查、API模拟/真实worker/目标验收范围及未决问题；不把本计划标成已实现。

| 阶段  | 当前状态       | 完成证据                                                                                                                       |
| ----- | -------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| P0    | 契约已交付     | [ADR、实际消费者/锁顺序、响应样例与验证范围](multi-user-contracts.md)；仅文档                                                  |
| P1    | 基础已实现     | 0037、内部持有与显式导入；SQLite及独立PostgreSQL专项通过，见[执行记录](resource-pool-architecture.md#执行记录)                 |
| P2    | 基础已实现     | 0038/0039、显式应用角色/审计/管理/配额/会话撤销；[执行记录](account-policy-architecture.md#执行记录)                           |
| P3    | 隔离实现已完成 | 0040/0041存储、范围消费者及密钥策略；生产开关保持关闭，真实站点验收待P8                                                        |
| P4    | 子阶段已实现   | 0042–0046订阅、生命周期、worker、持有命令与配额；消费者切换继续实施                                                            |
| P5    | 子阶段已实现   | 0044/0045不可变发布、本人库/图片、固定本地及冻结来源播放、0047目录与范围消费者                                                 |
| P6–P8 | 目标验收中     | P6/P7隔离实现及P8受控准入、原生worker/恢复演练已交付；[切换手册](multi-user-cutover.md)列明目标门槛，普通准入/自动回收默认关闭 |

初始计划提交ae10475，文档基线6bedcb6，分支doc/multi-user-shared-pool-plan；当时仅编写计划及导航。P0后续执行基线ae10475、分支doc/multi-user-contracts，记录见[契约验证范围](multi-user-contracts.md#验证记录与后续门槛)。两轮均检查新增链接及pre-commit完整门槛，未新增模型、接口、配置、worker或正式数据写入，也未恢复用户删除的历史文档。

### P3存储子阶段记录

0040与加密凭证/快照、盲写HTTP、导入及轮换先落地，详见[凭证架构](source-credential-architecture.md)。P3仍在执行：来源工厂、网络会话、缓存发布及ProxyServer范围能力尚待切换；不把子阶段当完整P3。

存储子阶段隔离门槛（2026-10-15）：全量SQLite `uv run pytest tests/ --ds=django_project.refactoring_test_settings -v` 为1062 passed、28 skipped；临时PostgreSQL专项为21 passed；`makemigrations --check --dry-run`无差异。`pre-commit run -a`全仓检查通过后提交。28项在线/opt-in跳过未当作目标环境通过；未执行现有实例迁移、Cookie导入或管理员引导。

### P3范围消费者记录

独立分支`feat/scoped-source-runtime`：0041 key policy、可选新来源模式、范围resolver/fork、ProxyServer能力、先领取刷新租约及有界复用、缓存和推荐提交fence、系统源播放引用/撤销及配套UA。详情见[凭证架构](source-credential-architecture.md#范围消费者与运行切换)。

2026-10-15隔离门槛：全量SQLite1078 passed/28 skipped；PostgreSQL专项37 passed；模型迁移无差异；`pre-commit run -a`全部通过。修复两个验收辅助问题：失败逆向迁移测试恢复最新schema，跨进程容量测试在统一启动屏障后开始等待预算，原容量断言保留。真实站点账户/代理出口、普通账号准入、私人任务资产、版本与GC仍须后续验收；当前配置默认旧模式，现有实例未迁移。P4–P8继续待实施。

### P4模型/核心子阶段

新增0042及内部请求/订阅/独立取消，详见[共享工作架构](shared-work-architecture.md)。完整P4仍在执行：配额、HTTP、worker规范/终态投影与事件尚未接入；私人发布依赖P5，不使用旧公开资源写入路径。没有在现有实例创建请求或派发共享任务。

P4模型/核心隔离门槛（2026-10-15）：SQLite全量1087 passed、28 skipped；临时PostgreSQL专项9 passed；模型迁移无差异；完整pre-commit通过。分支`feat/shared-work-subscriptions`，基线321614e；仅隔离数据库，没有真实共享worker/发布联调。

P4生命周期子阶段基线e2682f1，分支`feat/shared-work-lifecycle`：0043逐用户游标、后台有界进度/失败投影、移出/停用联动、事务后私有提示以及旧派发/领取保护。完整P4的成功激活、配额及HTTP仍待P5发布协议接入，不开放普通账号。

生命周期子阶段隔离门槛（2026-10-15）：全量SQLite1101 passed、28 skipped；临时PostgreSQL专项41 passed；模型迁移无差异；完整pre-commit通过。执行记录不包含真实共享Celery、源站账号、正式媒体或部署数据库验收。

P5账本子阶段基线d57421c，分支`feat/resource-version-ledger`：0044及内部读取占用，详见[资源版本](resource-version-architecture.md)。尚未接入正式发布、播放器/封面/GC及旧文件导入，完整P4/P5仍在执行。

P5账本隔离门槛（2026-10-15）：全量SQLite1111 passed、28 skipped；临时PostgreSQL专项10 passed；模型迁移无差异；完整pre-commit通过。仅DB/授权占用核心，未打开媒体或验证真实版本发布。

P5发布核心子阶段基线04e0214，分支`feat/scoped-version-publication`：0045、冻结来源fence、版本文件命名空间、指针CAS/资产日志、注入成功持有激活及来源失效收尾。真实worker/HTTP/配额、正式库和媒体投影、GC仍待接入；生产共享派发继续关闭。

P5发布核心隔离门槛（2026-10-15）：全量SQLite1125 passed、28 skipped；临时PostgreSQL专项38 passed；模型迁移无差异；完整pre-commit通过。专项含实际生成并完整解码的0.2秒MP4及真实文件日志/线程竞争；未进行来源下载、真实Celery或HTTP媒体联调。SQLite并发控制只读检查采用有界重试，不重跑文件提升。

共享执行器子阶段基线5980af4，分支`feat/shared-version-workers`：受控流程策略、ID-only持久派发/worker、范围来源装配/全局代理、翻译先于不可变发布、独立下载租约及默认关闭开关。尚无共享库HTTP/配额、正式版本查询/媒体/GC或普通登录开放；完整P4/P5仍在执行。

共享执行器隔离门槛（2026-10-15）：全量SQLite1140 passed、28 skipped；临时PostgreSQL专项75 passed；模型迁移无差异；完整pre-commit通过。默认装配检查覆盖独立来源及全局scraper代理，真实临时Redis验证租约与恢复；来源/下载替身只证明编排，不代表真实worker/站点下载、HTTP版本读取或正式实例已迁移。

持有命令/配额子阶段基线4e964fd，分支`feat/library-commands-quota`：0046、本人命令回执/意图代次、ready复用、每持有者逻辑配额和HTTP写入/任务快照。库/目录/推荐/媒体版本投影、GC及正式准入仍未完成，生产开关保持关闭。

持有命令/配额隔离门槛（2026-10-15）：全量SQLite1155 passed、28 skipped；随后补齐配额HTTP错误码及专用动作校验，HTTP/旧契约专项11 passed；临时PostgreSQL17 passed，含0046往返。模型迁移无差异，完整pre-commit通过。旧HTTP快照保留，只精确登记授权新增URL。未启用现有实例共享模式、没有真实Celery/媒体验收。

本人库/版本图片子阶段基线d0cf4f0，分支feat/version-library-reads：批量本人投影、旧读取入口的可选切换、登录绑定图片短占用、manifest/marker/内容及NOFOLLOW校验，个人写入在user fence内再次核查持有。无新schema。SQLite全量1170 passed/28 skipped，临时PostgreSQL40 passed，完整pre-commit通过后提交；真实播放器、目录/推荐、GC与前端/普通准入继续实施。详见[版本读取记录](resource-version-architecture.md#本人库与图片读取子阶段)。

固定本地播放子阶段基线7f0fd21，分支feat/version-bound-playback：本人固定video版本/账号epoch、真实MP4 Range/HEAD/在途断开、不可变文件身份与独立DB读取占用、版本化标题/接续批量查询。SQLite全量1184 passed/28 skipped，PostgreSQL最终专项37 passed（另有兼容专项39 passed），完整pre-commit通过后提交。无新schema/现有实例切换；源在线播放、目录/推荐/GC及P7/P8继续实施。详见[固定本地播放](resource-version-architecture.md#固定本地播放子阶段)。

冻结来源播放子阶段基线e61ef44，分支feat/scoped-version-source-playback：本人元数据版本/冻结引用、独立来源/全局代理、准备权限fence、媒体读取pin与取消安全收尾、scope/context进度账本。SQLite全量1193 passed/28 skipped，临时PostgreSQL40 passed，迁移无差异，完整pre-commit通过后提交。合成上游不代替真实账号/worker；目录/推荐、GC及P7/P8继续实施，见[冻结来源播放](resource-version-architecture.md#冻结来源播放子阶段)。

用户目录投影基础基线21b14d6，分支feat/owned-catalog-projection，0047新增本人term/link与明确现有关系投影；成功激活/旧显式导入同步、移出级联，统计只读本人当前合法版本。HTTP目录/外部搜索/推荐继续实施，不开放普通账号。

目录投影基础隔离门槛（2026-10-15）：SQLite全量1198 passed/28 skipped、临时PostgreSQL17 passed；0047往返保留旧资源/M2M/持有/版本事实，只增减可重建派生表。完整pre-commit通过后提交，现有实例未迁移；消费者与P6–P8继续。

目录消费者基线a5333ed，分支feat/owned-catalog-consumers：原目录/头像/筛选与推荐本地种子/名字黑名单、命名实体外部搜索和旧job namespace/epoch fencing。SQLite全量1210 passed/28 skipped、PostgreSQL56 passed，完整pre-commit通过后提交；无新schema/普通准入。图片缓存、观看列表版本化与P6–P8继续实施，详见[目录消费者](resource-version-architecture.md#用户目录消费者子阶段)。

推荐图片范围子阶段基线060e599，分支fix/scoped-recommendation-images：来源上下文目录、全局代理/独立来源、凭证及账号失效检查、受限图片/无重定向、dirfd发布与安全读取、HTTP私有缓存头。范围缓存不替代本人结果句柄授权。普通账号和自动GC保持关闭，观看历史/GC及P7/P8继续。

图片范围隔离门槛（2026-10-15）：全量SQLite1220 passed/28 skipped，随后补充生产装配/目录链接检查，专项12 passed；PostgreSQL图片及凭证26 passed，最终图片专项12 passed。模型无差异；完整pre-commit通过后合并。验证使用真实加密记录/文件与合成上游，不含真实源站或普通账号准入。

### P6历史前置子阶段

基线38117f9，分支feat/durable-viewing-history：0048稳定池身份/个人展示快照、资源SET_NULL、固定版本事件核查、本人版本观看列表、不可用历史及原CAS删除。历史不保护媒体、不赋予访问权限；回收后无法无损回退旧非空关系时显式拒绝，不强删历史。后续GC状态机、UI及P8继续。

历史快照隔离门槛（2026-10-15）：全量SQLite1227 passed/28 skipped，专项13 passed；临时PostgreSQL12 passed含0048往返和0036兼容，最终专项13 passed含实际MP4/批量查询。模型迁移无差异，完整pre-commit通过后提交。现有实例未执行迁移；回收仅在测试模拟资源行删除，正式GC继续实施。

### P6回收账本子阶段

基线daa043b，分支feat/resource-gc-ledger：0050版本宽限/管理员保留/回收与资产日志；整池与单版本真实引用保护、只读preview、幂等enqueue、owner/lease/代次领取/失败/恢复、pointer墓碑、旧删除防绕过。尚不删除文件或派发GC；物理适配器/管理/调度及P7/P8继续。开发约束见[回收架构](resource-gc-architecture.md)。

回收账本首次全量：1236 passed/28 skipped、1项跨进程代理测试失败；独立41d0022修复测试观察者提前释放，未改生产容量/钩子，其全量1228 passed/28 skipped。GC改动按独立stash身份恢复到原分支，追加版本宽限专项SQLite11 passed、PostgreSQL回收/读占用20 passed后重新执行完整门槛；首次失败不记为通过。

第二轮回收全量：1238 passed/28 skipped、1项观看置顶失败。独立3e8aaf6用0049持久单调时钟修复同值/回拨及删除后CAS复用，其全量1232 passed/28 skipped、SQLite/PostgreSQL专项各17 passed。恢复后GC迁移顺延0050，继续重验；未提交迁移可顺延，历史0049保持不改。

0050回收账本最终门槛（2026-10-15）：全量SQLite1244 passed/28 skipped，SQLite回收/观看/迁移组合24 passed；PostgreSQL回收/0049时钟迁移13 passed。201资产只用一次目标epoch读取，单次领取最多64版本/1024资产；超界需先按版本收尾。模型迁移无差异，完整pre-commit通过后提交，正式文件删除/生产派发仍未启用。

### P6受控文件子阶段

基线f2e071d，分支feat/resource-gc-files：实际NOFOLLOW/dirfd/hash/fingerprint清理、verified→unlink→deleted日志、崩溃重试、有界多批次与目录收尾、原播放/过期pin保护、稳定历史与时钟保留。只处理已确认manifest资产，不提供生产派发或管理apply。调度、未知/旧资产迁移及P7/P8继续。

受控文件阶段隔离门槛（2026-10-15）：全量SQLite1256 passed/28 skipped，随后补充目录链接和失租unlink专项，最终SQLite14 passed；PostgreSQL文件/账本24 passed、最终文件14 passed。真实临时图片/合成MP4与数据库fence，不含正式站点或部署删除；完整pre-commit通过后提交。无新schema，派发/管理与P7/P8继续。

### P6派发与管理子阶段

基线7e970c4，分支feat/resource-gc-dispatch-admin：0051公平发现游标、默认关闭的ID-only Celery/default派发与恢复冷却、管理预览/保留/排队/重试及审计幂等、只读默认CLI、旧写入口/布局维护关闭；修正生产builder的可选缩略图根回退。隔离原生Redis/Celery已连续三轮通过，未启正式自动GC。缓存回收、初始旧资产映射及P7/P8继续。

派发与管理隔离门槛（2026-10-15）：SQLite全量1274 passed/28 skipped；最终配置/HTTP/游标/管理专项60 passed；临时PostgreSQL39 passed，含0051升级、回退、再次升级。真实Redis/Celery测试恢复current/default app及finalizer，最小顺序回归11 passed，随后全量通过。模型迁移无差异，完整pre-commit通过。现有实例未迁移、未启自动回收，P7/P8继续。

### P7会话与缓存基础子阶段

基线9a3ec64，分支feat/session-cache-isolation：已有登录/session补充只读能力与不透明缓存身份；前端统一请求登录代次、迟到401保护、身份变化重置/组件重建、目录/队列清理及推荐/外部搜索/任务/离线进度缓存隔离。同账号两个真实登录的HTTP/SQLite浏览器验收不替代P7跨用户或P8目标验收；普通准入保持关闭，凭证/个人库/管理UI继续。

会话基础隔离门槛（2026-10-15）：SQLite全量1277 passed/28 skipped；PostgreSQL会话/权限12 passed；前端130单元测试、lint及构建通过。Chrome与临时安装的Firefox均通过真实HTTP/SQLite同账号换登录与迟到设置响应；真实MP4进度专项通过，任务详情和推荐恢复模拟浏览器回归通过。无新schema或现有实例切换；P7其余界面及P8继续。

回收验收时钟修正：基线2f8af4d，分支fix/gc-expiry-test-clock。原测试失租断言通过，但随后重新领取偶发返回deleting；墙钟回拨5秒的单变量探针复现同形失败，无新保护条件。测试改为注入协议时钟、按实际lease_until推进并覆盖立即/延迟恢复；保留全部unlink与实际删除断言，不修改生产领取/保护协议。凭证UI暂存后继续实施。

时钟修正门槛（2026-10-15）：原时序30次定向重复通过，单变量回拨探针1 passed/1 failed复现；修正后SQLite回收专项27 passed、PostgreSQL文件专项15 passed，全量SQLite1278 passed/28 skipped，pre-commit完整通过。无生产代码/schema或部署修改。

GC场景时间一致性补齐：基线fa7f4dd，分支fix/gc-fixture-clock-consistency。随后全量中发现候选公平性和私人范围场景因墙钟基准不同而触发grace_period。统一unheld场景、HTTP/CLI/原生worker的GC adapter协议时钟，发现器共享同一注入时间并覆盖宿主±5秒偏移；正式回收与其他域时钟均未改动。所有宽限/占用/删除断言保留。

一致性门槛（2026-10-15）：GC组合专项SQLite41 passed，补充续租边界后PostgreSQL42 passed；全量SQLite1281 passed/28 skipped；完整pre-commit通过。修正仅测试时间与说明，不修改生产默认时钟、宽限、领取或清理规则。

### P7个人来源凭证子阶段

基线56936a7，分支feat/personal-source-credentials-ui：添加页按模式装配个人盲写/旧兼容界面，Cookie/UA必填、CAS冲突保留草稿、撤销与未保存确认；来源缓存身份由本用户/系统元信息及密钥策略派生，HTTP写响应立即返回，来源页面重建但添加表单保留。真实Chrome/Firefox配临时HTTP/SQLite/keyring通过深浅主题、第二登录竞争、撤销、窄屏及不落浏览器存储检查，不访问真实来源站点。共享库命令/个人operation/管理UI、范围结果图片句柄及P8继续，普通准入未开放。

个人凭证子阶段门槛（2026-10-15）：SQLite全量1282 passed/28 skipped，PostgreSQL凭证/会话24 passed；前端132单元测试、lint与构建通过，完整pre-commit通过。Chrome和Firefox最终均以真实HTTP/SQLite/临时0600 keyring完成两主题、字段校验、CAS冲突/重载、撤销、嵌套确认、窄屏滚动、不持久化秘密与添加表单保留检查。无新schema、真实来源请求或现有实例切换；普通准入仍关闭。

### P7本人库状态基础子阶段

基线493ac08，分支feat/library-membership-status：无schema变更，新增最多100项的本人关系状态查询及前端30秒/500项内存缓存，entry_id/version复用现有CAS；按登录/请求序号隔离并在前台核查后失效。不新增全局库版本计数器，避免额外写入和锁顺序。消费者、本人操作与管理UI及P8继续实施，普通准入保持关闭。

本人关系状态隔离门槛（2026-10-15）：`uv run pytest tests/ --ds=django_project.refactoring_test_settings -v`为1291 passed/28 skipped；临时PostgreSQL关系专项20 passed。`pnpm run check`包含缓存过期、重叠请求、错误/迟到响应、切换前抑制传输及有界分批回归，lint/测试/构建通过；完整`pre-commit run -a`通过后提交。无新schema、真实站点请求或实例变更；本阶段没有视觉布局修改，后续共享库动作须继续真实HTTP浏览器验收。

### P7本人操作请求界面子阶段

基线59d3d99，分支feat/personal-operation-tracking：共享模式跟踪本人operation，不读取旧全局任务/队列；列表详情复用公共展示，撤销仅本人需求，CAS/幂等、部分失败、旧登录及提示乱序有独立回归。DownloadsView保留DEBUG开关，兼容模式独立装配。临时HTTP/SQLite/Redis浏览器fixture通过核心协议创建真实本人/他人订阅，不派发网络worker，不构成跨用户准入或真实来源验收。添加/刷新/下载命令与管理界面、结果图片句柄及P8继续，普通登录与自动GC未开放。

本人operation界面隔离验收（2026-10-15）：Chrome单项撤销及Firefox勾选后的批量撤销通过真实HTTP/临时SQLite/Redis测试；均验证两主题、弹窗Escape、窄屏、已撤销状态与阶段、按钮禁用、隐藏后重载，前端未请求旧任务或全局队列。只读核查临时DB：两条本人请求cancelled，另一位测试用户的请求和仍有其需求的共享job保持queued。此过程未运行来源worker，不等同多账号登录或目标部署验收。

本人请求界面最终门槛：`uv run pytest tests/test_library_http.py tests/test_shared_operations.py tests/test_account_access.py --ds=django_project.refactoring_test_settings -q`为23 passed；`pnpm run check`通过，包含本人请求归属、CAS冲突、结果未知幂等重试、乱序列表/提示及WebSocket不读取旧队列的回归。已有旧任务/DEBUG浏览器模拟回归通过，区别于上述真实HTTP验收。后端生产代码无变更、无schema变更；完整`pre-commit run -a`通过后提交。

### P7共享库命令界面子阶段

基线cb9f589，分支feat/shared-library-commands-ui：添加页显式来源/公共或个人模式、共享刷新/下载统一选择弹窗、本人移出/批量移出与部分失败展示；命令固定关系及幂等证据，响应丢失后重试不先重建关系意图。旧资源写入口、自动any/部分刷新/删除共享视频不用于共享模式。测试fixture仅在显式NASSAV_LIBRARY_UI_TEST_FIXTURE下给明确临时操作者导入合成资源，不导入实例或猜测现有归属。推荐/外部卡片状态与管理UI、结果图片句柄及P8继续。

共享库命令界面隔离验收（2026-10-15）：Chrome与Firefox均通过真实HTTP/临时SQLite/Redis的公共添加、完整刷新、下载与移出；缺个人凭证返回403且不回退公共，表单保留编号；未确认弹窗关闭不提交。实际移出成功后丢弃首次HTTP响应，再点击使用相同关系版本/request UUID取得幂等回执；另一条合成持有保留。Firefox另覆盖窄屏、两主题、焦点及弹窗边界；Chrome只读复核动画稳定后的移动端深浅主题截图。库命令/HTTP/配额专项25 passed；来源worker未启动，未验证实际抓取或部署资产删除。

### P7远程卡片与图片缓存归属子阶段

基线0046f88，分支feat/shared-remote-library-state：推荐/外部卡片从本人关系获取状态，挂载合批、可见页面唯一计时器、失效/重试/卸载与长列表保留；添加能力不被恢复的旧added集合拦截。封面object URL按登录/库失效同步撤销，旧成功/错误/回退与组件旧版本不能重新发布。本阶段不改变后端协议或来源图片授权；本人结果图片句柄、管理UI与P8继续，普通准入保持关闭。

远程卡片子阶段隔离验收（2026-10-15）：Chrome/Firefox通过生产RemoteLibraryActions与真实临时HTTP/SQLite的合批查询、忽略旧added、pending查看请求、定时发现本人撤销（他人需求保留）、网络故障重试与最后卸载停止计时器。仅测试宿主HTML与浏览器时钟受控，接口和持有变更真实，不等同完整推荐/外部抓取或跨用户准入验收。单元覆盖长列表保留/裁剪、旧注册不清新登录计时器、object URL撤销/并发/迟到错误回退及旧added提交护栏；完整前端与提交门槛通过后提交。

### P7本人持有管理子阶段

基线aa5b6c2，分支feat/library-membership-management：独立有界本人关系列表包含不可用/pending，保持正式资源过滤、不返回元数据；资源库弹窗提供单项/当前页批量移出。补强渲染关系CAS，旧行不能自动移出重新添加的新UUID；旧未知命令仍幂等重放。演员/类别批量入口同步本人移出语义并正确保留部分失败。无schema变更，管理UI/本人结果图片句柄及P8继续。

本人持有管理最终隔离门槛（2026-10-15）：`uv run pytest tests/ --ds=django_project.refactoring_test_settings -v`为1303 passed/28 skipped；临时PostgreSQL管理/状态/配额专项31 passed。Chrome与Firefox真实HTTP/临时SQLite/Redis通过不可用行元数据不披露/释放、嵌套Escape、另一设备释放再添加后的旧行CAS拒绝、当前页批量移出，以及窄屏/深浅/焦点/滚动恢复。只读核查他人持有、原AVResource与合成MP4仍保留。前端新增查询乱序/卸载、缺失结果计数和旧关系保护回归，完整`pnpm run check`与`pre-commit run -a`通过后提交；未触及实例/真实来源worker或自动GC。

### P7管理员账号界面子阶段

基线ed03628，分支feat/admin-account-ui：管理中心按应用管理员能力装配，接入已有账号创建、差量角色/启停/配额、撤销登录、密码重置与最近100条审计。命令冻结目标版本/UUID、冲突保留输入、秘密清空与当前登录归属；普通准入仍关闭，创建管理账号不自动打开登录。未改后端协议/schema，来源与GC管理、本人结果图片句柄及P8继续。

管理员账号界面首轮隔离验收（2026-10-15）：Chrome配真实HTTP/临时SQLite/Redis通过创建、配额CAS冲突/保留输入、配额差量修改、密码重置丢失响应的同UUID重放、角色切换、会话撤销、停用/启用、最后管理员拒绝、普通账号登录拒绝、审计及移动端两主题/焦点。只读核查仅一条密码重置审计、启用不恢复已移出的持有、另一用户仍需要的共享job保持queued。SQLite与临时PostgreSQL账号管理/权限专项各19 passed；无后端生产代码/schema变更。

管理员账号界面最终门槛：Firefox同样通过上述真实HTTP/临时数据库流程；密码重置的结果未知重试沿用原UUID/版本，数字格式变化不产生配额策略写入。最终前端check及完整pre-commit通过后提交，无正式账号创建、普通登录开放或实例数据变更。

### P7系统来源凭证界面子阶段

基线73a0c19，分支feat/admin-system-credentials-ui：管理中心接入已有system盲写/撤销协议，仅接受已分类访问验证Cookie，填写配套UA与审计原因；固定版本/UUID、结果未知重放、冲突保留、身份变化清空和来源缓存失效。个人账号Cookie不自动提升为公共凭证；现有来源元信息保留撤销入口。无后端生产代码/schema变更，资源/GC管理与本人结果图片句柄及P8继续。

系统凭证界面隔离门槛（2026-10-15）：前端完整check通过；SQLite凭证专项20 passed。Chrome与Firefox配真实临时HTTP/SQLite/Redis/keyring通过账号Cookie前置拒绝、盲写、响应丢失同UUID重试、版本冲突保留输入、撤销和嵌套Escape/窄屏两主题；GET/审计/浏览器持久存储均无秘密。只使用合成Cookie，不访问真实来源。完整pre-commit通过后提交，普通登录和自动GC保持关闭。

系统凭证PostgreSQL补验：同一凭证专项20 passed，独立临时数据库；前端无schema/迁移变化。

### P7共享资源生命周期界面子阶段

基线ee1163d，分支feat/admin-resource-lifecycle-ui：管理中心资源池/回收记录接入既有下架、保留、只读预览、排队和失败重试；原因/CAS/UUID、保护条件及结果未知重试独立管理。GC默认关闭时不能触发排队/重试，界面不提供开关或直接文件删除。无生产后端/schema变化；隔离helper增加显式GC验收空池/失败记录，普通准入及P8继续。

资源管理隔离验收（2026-10-15）：Chrome使用GC关闭的真实临时HTTP/SQLite/Redis验证预览阻塞、禁止排队、保留CAS冲突、下架响应丢失后的同UUID重放、恢复访问及两主题/窄屏。Firefox在新临时实例显式启用GC，仅对无文件空池登记回收，并将合成cleanup_failed记录重试为queued；两个真实持久请求入Redis，未启动文件/来源worker，不宣称文件删除已验收。前端补命令后列表刷新期间的busy护栏；PostgreSQL生命周期/账号专项24 passed。全量SQLite及提交门槛记录见后续。

资源生命周期最终门槛：全量SQLite1303 passed/28 skipped，PostgreSQL专项24 passed；最终前端check通过。核查过渡结束后的桌面及窄屏截图，公共主题/单内容滚动/嵌套确认正常；增加畸形/不一致预览拒绝用例。完整pre-commit通过后提交，不变更生产开关、资产或归属。

### P7管理员全局执行界面子阶段

基线9dc2f99，分支feat/admin-shared-work-ui：管理中心接入既有全局任务列表及审计控制，allowed_actions、固定job版本/UUID、原因与二次确认；明确与本人撤销的影响边界。状态排序/分页和文件清理独立展示，不读取配置或凭证，不以登记等同停止。后端协议/schema不变，图片结果句柄与P8继续。

全局执行隔离门槛（2026-10-15）：Chrome与Firefox通过真实临时HTTP/SQLite/Redis的暂停结果未知重放、恢复旧版本拒绝/刷新、恢复/终止和本人请求投影，Firefox复核暂停审计无重放重复；窄屏/两主题/嵌套Escape通过。SQLite账号/权限/共享请求专项27 passed，前端完整check通过，额外覆盖清理重试API路径与动作白名单。没有运行来源writer或声明文件已清理；完整pre-commit通过后提交。

### P7本人结果图片句柄子阶段

基线97a137d，分支feat/owned-discovery-images：推荐/搜索投影签发本人结果句柄，原URL入口仅留旧模式；推荐随快照JSON保存版本化内部范围证据，搜索沿Redis证据及只读详情补图。缓存/传输检查结果、来源和账号代次，缺历史证据不猜测回填。无DDL迁移；普通准入与P8继续。

本人图片阶段首轮验证：图片/范围/推荐与搜索组合84 passed，补充稳定句柄专项后图片23 passed；PostgreSQL图片及推荐job专项36 passed。Chrome生产卡片配真实临时HTTP/SQLite/Redis/预填合成PNG验证两个结果句柄、URL参数拒绝、私有响应、缺句柄不回退、删除搜索键/重置历史后旧图片404。仅宿主HTML受控，不抓取真实站点；Firefox及全量门槛继续。

本人结果图片最终隔离门槛（2026-10-15）：全量SQLite1314 passed/28 skipped，PostgreSQL36 passed，前端完整check通过；Chrome/Firefox均以新的临时fixture通过真实图片HTTP和生产卡片，缺句柄无URL回退、搜索TTL删除和历史重置旧句柄404。旧推荐恢复、外部渐进分页模拟回归通过。无DDL、真实来源请求或现有实例写入；完整pre-commit通过后提交，缓存收尾和P8继续。

### P7缓存与HTTP命令兼容收尾

基线89e4e55，分支fix/shared-ui-cache-and-command-ids：真实Chrome探针确认HTTP非localhost缺randomUUID而getRandomValues可用，统一10处命令消费者的安全UUID工具；不改变既有幂等意图保留。关系轮询只在已知快照变化时推进领域revision，沿现有列表/封面失效通道，重复快照不重查。无后端/schema变化，P8准入与上下文护栏继续。

缓存/HTTP兼容收尾隔离门槛（2026-10-15）：Chrome与Firefox均在真实非安全HTTP WebCrypto环境运行生产UUID工具，200个安全v4唯一；宿主HTML受控且无外网请求。两浏览器另配真实临时HTTP/SQLite/Redis验证关系变化revision增加一次、相同轮询不失效、合批/重试及卸载无查询循环。前端完整check通过，后端生产/schema不变；完整pre-commit通过后提交。

### P8受控准入与跨Cookie子阶段

基线95d7dee，分支feat/multi-user-admission-context：严格默认关闭准入开关，依赖共享库/来源范围；统一HTTP/原生媒体/WS准入，关闭可绕过审计的内置Django后台。上下文在业务前拒绝旧Cookie页面操作，读冲突只读重查，不自动重放；图片/keepalive/WS覆盖同一身份。无DDL、不启用实例开关。

SQLite全量1325 passed/28 skipped，PostgreSQL准入/权限/启动专项22 passed；Chrome真实临时HTTP/SQLite/Redis/keyring双账号验证公共合并、私人隔离、配额、取消、旧GET/PUT/logout拒绝及停用/WS撤销。Firefox以全新临时实例完成相同原生双账号验收；前端check与完整pre-commit通过后提交。来源worker、受控恢复与切换手册继续，不将排队等同来源执行成功。

### P8原生worker与受控恢复子阶段

基线baf2bbe，分支chore/multi-user-native-acceptance：新增非eager Redis/Celery solo集成验收，真实本人HTTP/CSRF提交、共享派发、版本文件和投影。可控来源屏障分别验证0/1/2位取消；重复task ID由实际第二次执行信号证明未重新发布，不把结果后端旧缓存当新执行。合成Gateway替换来源I/O，隔离app执行生产execute_shared/ControlledScrape/发布协议，不宣称真实来源/部署进程通过。

管理员CLI在临时库模拟无可用应用管理员，验证预览只读、恢复版本/审计/撤销和同UUID重试不再次撤销。专项SQLite4 passed，PostgreSQL与GC原生派发组合18 passed；全量SQLite1329 passed/28 skipped，完整pre-commit通过。切换手册记录实际配置声明PostgreSQL、本地SQLite为旧0031且不代表活动实例；未迁移实例或打开开关，需确认目标与归属后继续部署验收。

P8本轮提交：受控准入baf2bbe（基线95d7dee）；原生验收与切换手册基线baf2bbe，提交由chore/multi-user-native-acceptance记录。两阶段独立分支、质量门槛通过后合并idle；未操作实例数据库，实际PostgreSQL目标/维护窗口与旧归属需操作者确认。

### P8已授权PostgreSQL结构迁移

基线bf83195，分支chore/multi-user-postgres-cutover。用户新增PostgreSQL迁移授权后，核对dbb/nassav及无活动消费者，生成私有pg_dump备份、恢复到隔离UTF8 PostgreSQL预演，再执行目标0036→0051；15项迁移OK，39张原表6267条原行/字段摘要保持，0待迁移、无模型差异。只允许Django生成新模型权限，不修改原用户授权。业务导入/管理员引导仅只读预览，旧Cookie不激活，普通准入/GC仍关闭；归属及后续目标验收待确认。详情及备份位置见[执行记录](postgres-multi-user-migration-20261015.md)。完整pre-commit通过后提交合并；未将隔离测试冒充目标来源/部署验收。

操作者后续确认旧归属/admin及Cookie只隔离：目标已建立693份nassav持有、显式admin；保留已有42条个人状态与设置，两份凭证加密quarantined且解密核对通过。预演遇到352条个人AVID黑名单触发推荐导入保护；7批旧历史/25种子尚未合并，已询问补空历史/种子的规则，不绕过保护。专用keyring持久保存于Git忽略的secrets，未改默认工作树源码或配置。新模式开关继续关闭。

### P8保留个人黑名单的安全补导入

基线cdc36a1，分支fix/recommendation-import-preserve-blocklist；操作者确认保留352条个人AVID黑名单并补空历史/种子。新增显式--preserve-personal-blocklist，默认严格拒绝合并不变；只在目标历史/种子和旧AVID黑名单为空、无目标活动job时转移归属，保留item/feedback和黑名单原行；两侧历史generation推进一次，重放不再推进。无schema变更。

SQLite推荐专项11 passed、PostgreSQL同组11 passed，补修原生worker fixture注册后组合15 passed。原生测试曾因此前Ruff移除不同名fixture导入而报3个setup error，已使用显式模块赋值修复并在稳定格式化后重跑全量；不把未启动测试当跳过或成功。实际备份恢复预演通过7批历史/25种子归属、352条黑名单及其他个人/反馈/凭证摘要保持。完整质量门槛通过后才执行目标补导入。

后续真实来源门槛：实际全局代理localhost:7077和浏览器服务localhost:8192的TCP探测可达，但真实凭证resolver因两份quarantined记录拒绝公共来源且不回退匿名。不能激活未知旧Cookie来通过验收；需要有效且已分类的新凭证，四个新模式开关继续false。

安全补导入最终结果：稳定格式化后全量SQLite1335 passed/28 skipped，SQLite/PG推荐专项各11 passed，原生组合15 passed，完整pre-commit通过；实际目标已补入7批历史/25种子，352条黑名单及反馈/个人/凭证摘要不变，重放[0,0,0]且generation不再推进。已留前后私有恢复点。功能门槛已通过，剩余真实来源门槛因隔离凭证阻断，需要操作者提供有效已分类的新凭证，不启用未知旧Cookie或四个新模式开关。
