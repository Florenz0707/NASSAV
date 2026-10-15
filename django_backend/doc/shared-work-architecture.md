# 用户请求与共享工作

## 当前实施边界

0042/0043建立共享请求和投影游标，后续已接入派发、HTTP命令、配额、不可变发布、本人列表/媒体及受控回收。公共工作按系统范围合并，私人范围按凭证隔离；旧未分范围任务不自动转换。本文后续子阶段记录按当时边界保留，当前准入见[准入架构](multi-user-admission-architecture.md)，普通登录与自动回收仍默认关闭。

进度/失败投影、释放持有/停用联动与私有提示、正式派发/激活/配额均已接入；私人产物使用P5不可变版本，不把私有元数据交给旧AVResource列或旧文件发布流程。

## 身份与规格

- UserOperation是用户自己的请求及版本；每user/request_id唯一。输出仅自己的operation_id/AVID/kind/action/state/stage/version/短消息与allowed_actions，不把共享job当成本人的可控任务。
- SharedWork关联稳定pool及lifetime generation、规格hash和既有TaskJob。worker owner为系统身份，不继承第一位用户。规格含source、quality、动作、access_scope和非敏感凭证/context证据；目前仅best规格，拒绝未实现的质量选项。
- WorkSubscription按operation一对一关联共享工作。attached是需求，detached是取消，completed保留完成账本；不能通过取消一个用户请求删除其他需求。
- 用户提交的幂等hash只绑定规范化意图，不因为服务器后来更换Cookie/上下文而重新执行同一request_id。共享work hash另含当前解析的凭证/context及pool代次，因此不同规格不误合并。
- TaskAttempt复用现有持久派发记录，不复制一套broker出箱。新增结构不会自动将旧TaskJob升级为共享工作。

## 添加与取消

短事务按user→pool→work/operation/subscription/task进行。首次添加建立pending持有；不按同AVID的旧文件猜测授权，不直接激活已有资源。pending_gc/reclaimed重新添加提升pool代次，清除GC候选时间；deleting/cleanup_failed拒绝。

同公开规格只有一个工作和一个pending TaskAttempt，但每用户保留自己的operation及membership。已结束work退出active dedupe，cancelling工作不重新附加需求；paused保护与执行控制继续由TaskJob协议持有。当前没有ready-version复用，这一授权步骤属于P5。

取消须匹配当前用户、operation version和新的UUID命令，并保存独立回执。重试不重复脱离或控制任务，同request_id不同对象/version拒绝。取消只移出本人订阅；仍有attached需求时不请求停止。最后需求撤销才调用既有TaskRecords.cancel，任务可能进入cancelling，必须等原执行器证明停止；不调用Celery revoke代替协议，不删中间文件。

仅当本人pending持有不再有未结束需求时删除这一持有；原有active持有始终保留。最后持有释放只标记pending_gc，当前不回收文件。GC未来仍须检查共享工作、暂停、未知writer及资产补偿，不能凭pool的pending_gc直接删除。

## 后续接入要求

1. 默认装配解析并授权凭证，提交只记录ID/version证据；基于当前用户配额预留逻辑容量与并发，不能让重用绕过限额。
2. 新HTTP提交/状态/取消按request.user，所有批量操作逐个核查本人operation/version；管理控制另用共享job及审计协议。
3. worker读取冻结规格，缓存和资产提交核查pool generation、凭证版本、attempt及仍有有效需求。先取得共享文件锁再进入短DB提交，不在持DB锁时等待文件、网络或broker。
4. 终态投影锁pool/work，只激活仍attached且授权有效的用户需求；旧执行不能把已取消/移出的用户重新加入。失败/最后取消释放一次预留和首次pending意图，保留active持有。
5. 账号停用和移出先脱离本人订阅，有B需求时保持系统工作；不能沿用P2独占任务的全job取消。
6. 用户WebSocket只携带本人operation安全版本提示；管理员共享频道独立授权。前端以operation_id合并，不以AVID或共享job_id代替归属。

## 迁移与验证

0042是结构扩展，不自动导入或改变账号、持有、旧任务/attempt。逆向会删除新的请求、订阅和回执，旧表不能表达这些关系；切换前备份新增数据，停所有新消费者，不混跑旧版本。

隔离测试`test_shared_operations.py`验证一工作多请求、真正并发创建、幂等、来源规格分离、A取消不停止B、最后取消等待writer停止和原active持有保留。`test_shared_work_migration.py`覆盖SQLite/PostgreSQL升级、回退、再次升级及旧task/attempt/membership保留。当前没有真实共享worker/媒体发布验收，不能把DB测试或手工claim当作真实Celery联调。

## 生命周期子阶段

旧DjangoTaskRecords默认拒绝领取和派发shared_work，JSON过滤同时保留无该键的旧任务；只有显式共享执行适配器才能领取。此开关是内部执行装配能力，不是用户权限开关；当前生产装配不启用，不能为运行共享工作而在旧builder中简单改成true。

移出持有在同一user→pool事务中先脱离本人的所有attached订阅，保留关系到释放完成；账号停用复用这个入口，再按原协议处理独占旧任务。B仍有需求时A退出不停止共享job；最后需求请求停止，cancelling不重复发命令，不提前清理文件。

后台恢复循环注入有界project_pending，每轮最多200条，按用户独立取得user→pool→work→task锁。每个operation有自己的底层版本游标，无公共内容变化只推进游标，不增加公开version或发送提示；不会用全局work游标跳过B，也不会让一直queued的A挡住后续批次。取消/释放及旧pool代次不会被迟到进度恢复。失败仅输出固定短消息与WORK_FAILED，不传播内部checkpoint、Cookie、来源URL或诊断。

默认投影器仍拒绝publication_not_ready且暂不选成功job；P5发布核心已提供可注入grant证据，注入后只激活仍attached的本人持有，生产装配待后续接入。不能以TaskJob.succeeded或同AVID文件存在作为激活证明。配额和新HTTP仍未开放，这一子阶段不代表完整P4。

用户提示仅为operation_id/version，提交成功后发送到本人的task_user频道，不进入旧全局组或管理员广播。提示投递失败不回滚业务，由下一次授权快照补查；当前前端尚未消费新事件。

0043仅增加默认0游标，原有请求/订阅/持有/工作不变；逆向只丢游标，重新升级从0重建。测试覆盖SQLite/PostgreSQL往返、双用户真实线程释放/投影竞争、停用、取消后迟到状态、无发布证据拒绝激活、批次公平与事务回滚不发提示。模拟claim/派发回调不代表真实Celery或媒体发布验收。

## 执行器子阶段

新Celery任务`nassav.tasks.shared_work_task`只接收job ID，request.id对应持久attempt；派发只选shared_work，不进入旧Redis AVID队列/旧worker。broker失败保留pending，补派复用attempt ID，重复或旧消息不能领取或把其他running执行改失败。结果只返回status/job_id并关闭Celery结果存储，不复制私有checkpoint/源链接。

`build_shared_workflow`按冻结source/credential选择模板与独立操作来源；私人owner来自可信凭证行，公开模板actor为空。来源与scraper共用全局Proxy.url；下载仍用download代理；ProxyServer能力与容量不按具体provider决定。模板不安装操作control，fork绑定当前control，新fetcher/transport任务结束逐个关闭；一个关闭异常不跳过其余清理。

刮削复用ControlledScrape，新增显式publication策略；目标进入版本UUID目录，HTML只留临时工作区。翻译在短提交外完成，成功后metadata snapshot固定；翻译失败不切指针并报告failed，取消由原停止协议收尾。不会用旧AVResource所属翻译修改已发布版本。下载复用ControlledDownload、HLSResumeGuard和完整媒体验证，仅把最后目标/persist替换成版本策略。

不同范围的同AVID下载持有各自job租约，仍共享一份全局下载槽位；private workspace及正式目标均独立。共享progress/queue键单独命名，不清旧AVID投影。恢复仅从可信DB job ID导出租约键，再校验归属；不接受日志中的任意Redis key。停止证明及未知writer保留规则不变。

`NASSAV_SHARED_LIBRARY_ENABLED`默认false，要求同时启用范围凭证；共享库HTTP、配额、版本/媒体与GC已分阶段接入，但目标验收前不能开放普通准入。Compose将开关/密钥容器路径传给全部后端消费者，切换时统一版本与重启，不能只开开关而混跑旧写入者。后台在启用时装配ready发布证据的用户投影，提示仍只发送所属用户。

专项`test_shared_version_workers.py`为真实DB/文件＋显式来源/下载替身，验证编排与装配，不是实际Celery/站点下载；`test_shared_download_leases.py`用Unix socket临时Redis验证作用域与恢复；真实worker/Proxy/来源/媒体仍按P8验收。

## 持有命令、意图与配额子阶段

0046保存UserLibraryCommand持久回执、持有的按kind需求generation、operation对应generation/预留及安全progress/timeline。移出回执独立于被删持有，新一轮添加后重放旧DELETE不能删新关系；用户命令只有expected_version/request_id，owner由session决定。

新managed请求按kind提升本人意图，先建立新订阅再撤销本人的旧同kind需求；同公开work仍有B或新A需求时不停止。元数据与视频意图分开，保持各自已发布引用，刷新可以在成功时转向合法新来源/个人范围；失败不先改旧指针。grant只由仍存在且generation匹配的本人持有接受，不把旧执行附加到新意图。

有配额账号每请求预留并发槽；未知视频大小保守预留剩余逻辑额度，既有ready视频复用不做无意义全剩余额度预留。最终grant在user fence核查当前本人逻辑总量，超额只失败该请求/退款，不终止其他人或删共享正式视频。大小来自已验证version.file_size，旧导入无video版本时保留旧文件数据兼容统计；不按物理去重后的份额减免。

用户request幂等hash包含规范化意图、credential_mode和expected_entry_version，不含动态服务器凭证/version；先查本人旧回执再解析来源，撤销/改写之后重试不会重新抓取/计费。新操作只允许public系统/匿名或personal本人凭证，personal不存在拒绝，不能回退别人的Cookie。来源publish fence在派发前完成短接受事务，broker不进入DB锁。

add/download可直接复用ready指针，但必须范围、来源/质量、当前credential/context及拥有者一致，不能凭AVID/文件存在复用。重添提升pool代次，只复用正式证据，不恢复旧attempt；refresh强制新准备。成功复用不创建新TaskAttempt；正在结束的work不重新附加需求。

新HTTP先保留operator＋受管角色＋共享库开关准入：提交、移出、刷新/下载请求、本人operation状态/集合/取消。普通账号仍关闭。集合稳定降序分页，进度只允许数值percent和格式化速度/ETA，timeline裁剪到100条合法stage/state/time；不返回原work、订阅人数、源链接或Cookie。

共享库列表/完整版本资源与媒体投影仍由后续子阶段接入；当前LibraryEntries只有POST，不应宣称它已替代旧GET资源列表。GC/正式多用户准入也仍关闭。
