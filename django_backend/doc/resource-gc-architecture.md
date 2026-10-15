# 共享资源回收账本

## 当前实现边界

0050扩展ResourceGcJob/ResourceGcAsset、pool.retained、version.gc_after及版本deleting/cleanup_failed状态。数据库账本、保护条件、领取/失租/失败fence及受控文件删除已实现；已接入默认关闭的有界派发及operator/admin管理入口，普通登录与正式apply仍待P8。普通准入和自动apply保持关闭，不能用内部claim代替完整回收工作流。

## 所有者与锁顺序

pool是持有/生命周期真相，version是不可变范围资产，GC job是清理进展；文件journal不以业务终态推测已删除。系统enqueue按pool短fence建立幂等active_key，preview只读且仅供提示。worker先取task→resource→有序target共享flock，再claim/检查DB；任何慢哈希、复制、网络、文件锁等待必须在事务外。PostgreSQL的pool锁显式仅锁self，避免nullable resource outer join锁错误；SQLite以原值UPDATE先拿短写入fence。

每次领取生成新owner/有界lease；旧owner、过期lease和整池代次变化拒绝更新。整池deleting拒绝重新添加，宽限内再次添加提升代次使旧排队GC取消。已开始的单版本清理固定UUID墓碑，不因其他范围的新生命周期而套用/删除新版本；同范围pending需求仍保守阻止其启动或恢复。稳定锁文件不unlink。

## 保护条件与宽限

整池必须pending_gc且宽限结束，并且没有pending/active持有。单版本仅在ready/retired、gc_after到期及没有本人/公共持有指针或pending需求时可领取；他人另一个授权版本不永久保护该私人版本。指针本身不是永久引用，领取时在短事务清空对应pointer并递增revision。

两者均保护有效共享work/订阅、活跃/暂停任务、未确认停止的attempt、未完成cleanup/promoting/其他未补偿artifact、有效读lease、仍在原绝对期限内的播放session、管理员retained及其他尚未收尾GC。session保护不依赖当前短pin，关闭session也不等于在途pin已经释放。不按Redis过期、Celery revoke或terminal状态宣称writer停止。

移出/失败释放pending及新版本成功激活时，在现有pool短fence内按真实持有关系维护版本宽限：持有清空timer，首次无持有设24小时，重复扫描不延长。首次无持有前的published_at不能代替最后释放时间。旧未登记版本、staging/quarantined或未映射的传统资产阻止整池回收；不能因没有新manifest就清空AVID目录。

## 日志与失败恢复

manifest按版本UUID/root/kind/path、size、SHA256、marker有界核查；登记每文件planned记录，并与TaskAssetTarget当前epoch核对。异常事务回滚，不切指针、不触摸其他范围。领取后版本和整池分别进入deleting，失败保留cleanup_failed，不能恢复ready暴露残缺文件；重试同job产生新owner，保留journal，不复制重新删除账本。错误仅保存受限error_code，不保存Cookie/签名URL/备注。

后续文件适配器必须在共享锁内NOFOLLOW打开、事务外完整hash及指纹检查，再持久verified→unlink→deleted；已确认日志允许崩溃后缺失文件幂等收尾，未知缺失/归属变化保留现场。最终收尾必须核对全部资产完成再清理正式资源行，保留历史与进度/稳定池墓碑；不能用无条件rmtree或逐资产DB完成代替实际文件验收。

## 兼容与回退

共享模式禁用旧全量/视频删除入口；即使关闭开关，已有持有/版本/回收记录及保留标记仍保护资产，未受管传统资源的旧删除流程保持。新添加/旧删除并发不能绕过新池保护。

0050本身不回收文件、不推测归属。尚无GC证据/保留标记/版本宽限或特殊状态时可往返；已有清理账本或保护状态后拒绝回退丢失证据，应从维护窗口备份恢复。不能运行旧schema消费者继续清理。文件回收、派发及管理实现见下文；正式切换仍须目标验收。

## 受控文件清理子阶段

ResourceReclaimer只编排records/storage能力，composition装配DjangoGcRecords与GcFileStorage；业务核心不引入ORM或默认单例。每次最多处理32个文件，未完成时释放本次owner、保留deleting墓碑并排队同一job；重领沿新owner继续，不重复登记证据。

文件适配器先按任务、资源、规范target顺序取得稳定flock。整池遇到未映射传统AVID封面/HTML/视频/缩略图在claim前拒绝。读取以dirfd逐层NOFOLLOW打开，核查普通文件/size、完整SHA256及前后inode/device/mtime/ctime；分块检查归属且按时间节流短DB心跳，哈希不放事务。记录verified后，仅stat/unlink进入短pool/owner/marker提交；该有文件副作用的事务不自动重试。unlink后崩溃回滚DB时，已有verified日志允许下一owner对缺失文件幂等收尾，planned缺失则拒绝猜测。

目录仅删除manifest已登记的父目录及版本UUID目录，逐个rmdir，不递归清空；未知文件/链接/非空目录保留并cleanup_failed。锁文件、别的版本、全局头像、推荐/播放缓存与.tasks不由此流程删除。文件全删和目录收尾后，再查保护条件，标记reclaimed；整池只移除中性正式资源行及过期/释放pin和已失效会话，保留稳定pool、个人历史快照、时钟和进度。私人版本清理不影响他人另一个版本。

验证使用真实发布图片/合成MP4、真实SQL与注入IO/崩溃，分别区分权限失败、篡改/符号链接、未确认缺失及未知文件。没有正式源站、目标部署删除或自动GC验收；派发与管理实现见下文，缓存回收及P7/P8继续实施。

## 派发与管理

RESOURCE_GC_ENABLED默认false，启用须SHARED_LIBRARY_ENABLED/SOURCE_CREDENTIALS_ENABLED均开启；RESOURCE_GC_BATCH_SIZE默认32、范围1–100。worker现有恢复循环发现过期候选并向default队列运输GC job ID，独立Celery任务执行文件流程，HTTP不等待哈希/删除。0051单例keyset游标使被读pin/暂停工作保护的早期候选不会永远遮挡后续候选；每轮最多各扫描batch个version/pool，游标锁与pool/用户锁分开，空尾回绕。

排队/过期执行按revision CAS预留60秒派发窗口，broker在事务外；失败保留DB任务，下一窗口重发，不全表发送或依赖Celery结果作为状态。cleanup_failed不自动强制重试，由管理员修复现场后用reason/expected_version/request_id提交，幂等回执与审计同事务保存。管理员保留在deleting前设置，不在已删除部分文件后恢复ready。自动任务的系统领取/资产日志保持，管理审计不含Cookie、路径、签名URL或私密标题。

管理HTTP仍受configured operator与显式app admin双门槛；提供pool列表/只读预览、排队、retention及GC列表/retry，普通登录未开放。默认关闭执行时排队/retry返回409 gc_not_enabled；retention可先保护，不能借管理入口读取他人的私密状态。旧独占资产提交和旧布局修复命令在共享模式关闭；存在范围版本时旧维护工具也拒绝误判其布局。

只读管理命令：`uv run python manage.py resource_gc --target <pool-uuid> [--version-id <version-uuid>]`。写请求另外指定`--action enqueue|retry|retention --actor <app-admin> --reason maintenance --request-id <uuid> --expected-version <pool-version或job-revision>`；retention还需`--retained true|false`。命令只提交持久请求，不直接rmtree。先完成维护窗口/目标验收，再开启执行；不要对未知旧资产伪造marker绕过保护。

单版本保护只关联其实际指针、同范围工作与本版本原work；不同范围的暂停任务不永久占用无引用私人版本，旧未分范围writer仍阻止整池/任何版本清理。同一资源的物理操作仍共用resource flock。真实worker隔离验收使用临时Redis、原生Celery solo、实际handler、HTTP管理命令和真实临时文件，关闭eager；不代替部署或源站账号验收。

## 管理界面

共享模式管理中心提供资源池元信息、访问下架/恢复、保留、整池或指定UUID版本预览，以及回收记录与失败重试。前端只提交既有审计命令，不展示私密元数据/文件路径，不绕过默认关闭的RESOURCE_GC_ENABLED。预览核对对象版本/代次，排队和实际领取仍重新核查。排队成功只代表持久意图，不证明文件已删除；后台状态、journal与停止证明继续由上述协议持有。
