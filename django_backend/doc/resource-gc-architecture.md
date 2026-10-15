# 共享资源回收账本

## 当前实现边界

0050扩展ResourceGcJob/ResourceGcAsset、pool.retained、version.gc_after及版本deleting/cleanup_failed状态。数据库账本、保护条件与领取/失租/失败fence已实现；本子阶段没有文件删除适配器、定时派发或开放管理动作。普通准入和自动apply保持关闭，不能用内部claim代替完整回收工作流。

## 所有者与锁顺序

pool是持有/生命周期真相，version是不可变范围资产，GC job是清理进展；文件journal不以业务终态推测已删除。系统enqueue按pool短fence建立幂等active_key，preview只读且仅供提示。worker先取task→resource→有序target共享flock，再claim/检查DB；任何慢哈希、复制、网络、文件锁等待必须在事务外。PostgreSQL的pool锁显式仅锁self，避免nullable resource outer join锁错误；SQLite以原值UPDATE先拿短写入fence。

每次领取生成新owner/有界lease；旧owner、过期lease和整池代次变化拒绝更新。整池deleting拒绝重新添加，宽限内再次添加提升代次使旧排队GC取消。已开始的单版本清理固定UUID墓碑，不因其他范围的新生命周期而套用/删除新版本；新pending需求仍保守阻止其启动或恢复。稳定锁文件不unlink。

## 保护条件与宽限

整池必须pending_gc且宽限结束，并且没有pending/active持有。单版本仅在ready/retired、gc_after到期及没有本人/公共持有指针或pending需求时可领取；他人另一个授权版本不永久保护该私人版本。指针本身不是永久引用，领取时在短事务清空对应pointer并递增revision。

两者均保护有效共享work/订阅、活跃/暂停任务、未确认停止的attempt、未完成cleanup/promoting/其他未补偿artifact、有效读lease、仍在原绝对期限内的播放session、管理员retained及其他尚未收尾GC。session保护不依赖当前短pin，关闭session也不等于在途pin已经释放。不按Redis过期、Celery revoke或terminal状态宣称writer停止。

移出/失败释放pending及新版本成功激活时，在现有pool短fence内按真实持有关系维护版本宽限：持有清空timer，首次无持有设24小时，重复扫描不延长。首次无持有前的published_at不能代替最后释放时间。旧未登记版本、staging/quarantined或未映射的传统资产阻止整池回收；不能因没有新manifest就清空AVID目录。

## 日志与失败恢复

manifest按版本UUID/root/kind/path、size、SHA256、marker有界核查；登记每文件planned记录，并与TaskAssetTarget当前epoch核对。异常事务回滚，不切指针、不触摸其他范围。领取后版本和整池分别进入deleting，失败保留cleanup_failed，不能恢复ready暴露残缺文件；重试同job产生新owner，保留journal，不复制重新删除账本。错误仅保存受限error_code，不保存Cookie/签名URL/备注。

后续文件适配器必须在共享锁内NOFOLLOW打开、事务外完整hash及指纹检查，再持久verified→unlink→deleted；已确认日志允许崩溃后缺失文件幂等收尾，未知缺失/归属变化保留现场。最终收尾必须核对全部资产完成再清理正式资源行，保留历史与进度/稳定池墓碑；不能用无条件rmtree或逐资产DB完成代替实际文件验收。

## 兼容与回退

共享模式禁用旧全量/视频删除入口；即使关闭开关，已有持有/版本/回收记录及保留标记仍保护资产，未受管传统资源的旧删除流程保持。新添加/旧删除并发不能绕过新池保护。

0050本身不回收文件、不推测归属。尚无GC证据/保留标记/版本宽限或特殊状态时可往返；已有清理账本或保护状态后拒绝回退丢失证据，应从维护窗口备份恢复。不能运行旧schema消费者继续清理。物理回收、调度、管理预览/重试及正式切换继续分阶段实施。
