# 用户请求与共享工作

## 当前实施边界

P4先交付模型和内部请求核心，0042扩展SharedWork、UserOperation、WorkSubscription及用户命令回执。仍未开放HTTP入口或普通用户登录；生产未创建共享请求，也未修改现有任务归属。不得把这一子阶段当成完整P4。

真实派发/恢复、worker提交与终态投影、配额、释放持有/账号停用联动和WebSocket尚待接入；私人产物的可执行发布需要P5不可变版本。当前内部核心只接受public，新私人需求明确拒绝，不把私人结果交给旧AVResource/文件发布流程。

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
