# 资源版本与读取占用

## 实施状态

P5账本子阶段新增0044及内部读取占用核心；未接入正式版本发布、源/本地播放器、封面HTTP或GC。普通账号登录、共享任务生产派发及自动回收仍关闭。当前生产仍用旧路径，不得把本文的内部模型测试当作正式媒体验收。

## 版本与两个持有指针

ResourceVersion保存pool/lifetime generation、来源/质量、access_scope、owner、无秘密凭证引用和context、父版本、结构化元数据/资产manifest、媒体身份与发布时间。work一对一是发布来源证据；遗留版本导入可无work，但必须显式核对并建立真实资产证据，0044不自动生成版本或猜测公开属性。

版本kind分metadata与video；UserLibraryEntry.current_version与video_version分别持有。元数据刷新不因更新描述而丢失已下载视频的引用；新视频身份由服务端校验，不能按AVID假定同字节或套用进度。ResourceVersionPointer按pool/source/quality/scope/kind唯一，revision用于后续条件切换；刷新失败不切换旧好版本。

public版本必须owner为空，其他范围必须有owner；管理员不因此自动拥有私人媒体。读取先匹配本人有效持有和准确版本/范围，不能只按AVID、全局file_exists或当前共享指针授权。

staging不可读；ready/retired可在授权范围内读取，quarantined/reclaimed不可读。ready等正式版本必须有published_at；字段的不可变发布、manifest/path/marker校验、旧writer及指针CAS仍由下一发布子阶段交付。模型不是防止任意SQL篡改的边界，禁止业务直接修改已发布metadata/manifest/身份。

## 固定读取占用

ResourceReadLease绑定user、专属登录HMAC、账号epoch、固定version、可选播放session、独立revision和空闲/绝对期限。内部VersionReads负责输入契约，DjangoReadLeases负责user→pool→lease短事务；不访问文件、broker或网络。输出只有lease/version身份、状态、revision及期限，不返回文件路径、Cookie、登录key、manifest或源站URL。

一般资产新占用要求本人active持有指向该版本，空闲60秒、绝对120秒。播放占用只接受已合法创建、相同用户/登录且grant精确绑定version/pool/scope的session，最多原session绝对期限及4小时，不授予新播放权限。

移出库拒绝新播放会话和一般资产占用；原固定版本播放session可在既有期限内继续读或重新申请短读取占用，适用于后续Range和暂停后恢复。重新申请不能延长原授权，也不能改为当前新版本。仅有lease ID或同AVID不获得该例外。下架、账号/会话撤销、范围不匹配、版本隔离及超时立即拒绝后续检查/续租。

续租须CAS匹配revision，绝对期限不变；释放幂等，过期/已释放的同request_id不复活。另一个用户、另一个登录或账号epoch变化不能恢复旧占用。指针切换不改变原播放session固定版本。

GC未来不仅检查has_readers，还要检查仍可续读的合法播放session、持有、需求、writer及资产补偿。占用过期不证明writer停止；也不能因为短占用过期就删仍获原session授权的旧视频。文件句柄关闭、流取消与占用收尾必须在网关联调证明，当前核心测试没有实际打开媒体文件。

## 迁移与验证

0044增加三表和两个可空持有指针；不改旧资源/工作/关系、不自动建立正式manifest、不导入文件。逆向丢版本、指针和占用，旧表不能表示新增范围/谱系；回退前停止新消费者并备份这些数据与匹配资产，不能宣称回退恢复媒体。

专项`test_resource_read_leases.py`覆盖私有范围负向、登录/账号epoch、原播放宽限、指针切换、续租/释放真实线程竞争及幂等并发。`test_resource_version_migration.py`覆盖0043→0044→0043→0044及旧资源/请求/订阅/持有保持。临时SQLite/PostgreSQL用于结构与权限隔离，不替代真实浏览器/worker/Range/GC验收。
