# 资源版本与读取占用

## 实施状态

0044/0045账本、发布、受控执行器及本人库/图片读取已隔离实现；本地固定版本播放已隔离接入；来源在线播放也已隔离接入；完整目录/推荐投影和GC仍待接入。普通账号登录、共享任务生产派发及自动回收仍关闭。当前生产仍用旧路径，不得把本文的内部模型测试当作正式媒体验收。

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

## 发布核心子阶段

0045增加base_pointer_revision。DjangoSharedExecutionRecords消费独立来源context，先在事务外加载密钥/解析来源，再按key policy→私人owner/credential→pool→work→task取得短提交fence。公开共享工作使用actor为空的系统/匿名上下文，不能依赖第一位用户继续启用；私人work只能由对应owner范围的凭证执行。绑定只保存ID/version/host及opaque context hash，不含Cookie、UA或源链接。

VersionPublications.prepare持久分配候选UUID，固定父指针与revision，恢复复用候选。正式资产目标只能位于该版本versions/UUID命名空间；共享执行适配器在准备日志提交前拒绝旧AVID路径或另一版本目标。提升、备份、校验、回滚继续由TaskAssets及原共享flock承担，不另造文件事务。发布callback只读已验证的artifact size/hash/marker，读取/哈希/复制/网络仍在事务外。

manifest按root/kind/path/size/SHA256/marker登记；元数据只接受白名单展示字段及匹配AVID，拒绝m3u8、headers、用户备注、进行中的翻译等。HTML只属于临时工作区，不进入新正式manifest。视频发布要求一项MP4资产，其真实ffprobe/完整解码仍须下载workflow在提交前验证，publisher不重新读大文件或宣称文件扩展名等于媒体合格。

短发布同时CAS父指针与revision，更新失败保留旧指针/字节；较新指针拒绝旧候选并补偿新文件。AVResource仅作稳定个人状态/历史锚点，新私人标题、关系和URL不写共享列。实际库/目录/推荐读取仍待下一消费者子阶段适配版本投影，不能把空共享锚点当成新版资源信息。

用户请求成功须经注入的grant_locked验证ready版本及work/代次/范围/owner/来源/context证据；只激活仍attached且存在的本人持有，不重新创建取消/移出的关系。生产默认投影器尚未装配publisher，新HTTP/配额/worker派发/正式媒体读取仍未开放，完整P4/P5未完成。

来源或pool失效属于仍owned执行的失败，而非旧token静默ignored；旧token仍由原TaskExecutionInvalid拒绝。刮削失败收尾直接用finish检查执行/控制归属，不重复检查已失效来源，避免owned attempt滞留running；取消优先且网络/写入者必须已退出。

专项`test_version_publication.py`使用真实加密来源记录、临时JPEG、DB及资产日志，覆盖双用户激活、撤销/取消、无公共私人数据、失败补偿、较新指针、命名空间及线程竞态；另有实际ffmpeg生成并完整解码的0.2秒MP4验证独立视频指针；不是源站下载、真实Celery或HTTP媒体验收。0045往返保留版本/manifest/持有/读取占用，仅新增CAS基准列；历史staging候选不能因为默认值就获新提交权。

执行器子阶段已将两个受控workflow接入版本策略与同步翻译，生产开关默认关闭；共享库HTTP/配额与正式读取消费者仍待接入，见[共享执行器](shared-work-architecture.md#执行器子阶段)。

## 本人库与图片读取子阶段

基线d0cf4f0，分支feat/version-library-reads，不新增schema。library_catalog批量投影本人active/pending持有及当前元数据/独立视频版本，个人状态使用资源锚点的关联子查询。全局AVResource保持中性；私有来源的标题/关系仅在本人的授权版本投影中显示，不写Actor/Genre全局表。旧导入的public/legacy操作者关系保留明确兼容读取；有版本指针时不回退其他来源或全局数据。数据库查询限定本人、可用pool与合法pool/kind/owner/state，pending不展示他人的准备结果。

LibraryImages协调授权与占用，DjangoVersionImageLocator负责manifest/marker与受限文件打开，HTTP只组装FileResponse。锁顺序是共享resource flock之后user→pool→lease；hash/stat在短DB事务外。图片以openat/NOFOLLOW遍历版本目录，实际内容SHA256及stat匹配后才读；每块传输前后检查登录、epoch和持有，关闭幂等释放。单图上限32MiB，原图响应不生成新缓存。失败打开关闭句柄/占用，登录已撤销时占用TTL兜底；稳定锁文件不unlink。

个人更新在user fence内再次锁pool并核查持有，不能因权限入口旧检查通过就越过稍后移出。当前仅资源列表/详情/预览与版本cover/avatar HTTP，播放器与目录/推荐关系仍需独立接入；默认共享开关/普通准入不变。专项test_version_library_reads.py使用真实加密记录、JPEG、DB和认证HTTP，含两个用户隔离、批量查询数、猜测地址、坏marker/内容、父/末端符号链接、移出后流及个人写入拒绝；不代表真实Celery或视频媒体联调。

本子阶段隔离门槛（2026-10-15）：全量SQLite1170 passed、28 skipped；PostgreSQL专项40 passed；个人状态/权限与读取专项SQLite38 passed，旧HTTP契约及读取专项21 passed。流式HTTP使用真实事务测试，关闭响应会触发Django连接清理；不得以pytest外层回滚事务冒充该生命周期。完整pre-commit通过后提交。本阶段无新迁移，现有实例/普通登录/真实视频仍未切换。

## 固定本地播放子阶段

基线7f0fd21，分支feat/version-bound-playback。本地提交在原resource文件锁内获取视频版本/marker/fingerprint，随后user→pool短事务核查本人准确video指针及descriptor版本一致；竞争时拒绝创建错误媒体会话。grant保存version/pool/scope和account_epoch，不返回manifest/路径/签名来源信息。既有会话读取固定旧版本，ready/retired可以完成原播放；普通移出拒绝新会话但不关闭原授权，下架、账号/角色代次或坏资产立即拒绝后续读取。

DjangoVersionVideoLocator消费不可变manifest、TaskAssetTarget及真实FD，openat/NOFOLLOW拒绝父目录/末端符号链接，stat/fingerprint拒绝同大小替换；不在每个Range重新哈希大视频，发布SHA256/marker和稳定文件身份是证据。源站凭证撤销不使合法已下载静态资产变成他人资源，也不自动删视频。仅public/legacy有效持有可走旧文件兼容；已有版本坏证据不回退旧路径。

ASGI传输沿原全局/单session Redis容量和取消清理流程，另由PlaybackVersionRead固定版本短占用，每20秒CAS续租、绝对期限不变；关闭不能复活同一请求的占用。HEAD、正常完成、拒绝及断开收尾关闭FD/容量/DB pin，失效登录导致DB收尾拒绝由TTL兜底。GC还必须保护所有合法开放播放session，不能只检查短pin。接续列表批量核对本人当前视频身份与标题；当前源播放的私有上下文/版本绑定仍由后续子阶段接入，不开放普通登录。

专项test_version_local_playback.py使用真实加密记录、TaskAssets发布、ffmpeg生成且完整解码的MP4、认证ASGI Range/HEAD和真实临时Redis，覆盖指针竞争/固定旧版、私有范围、坏marker/内容/符号链接、移出/下架、续租/关闭与接续。不是目标站点源播放、真实共享Celery或正式实例切换。

固定本地播放隔离门槛（2026-10-15）：SQLite全量1184 passed/28 skipped；PostgreSQL最终专项37 passed，另有旧本地播放/占用/权限专项39 passed。源开关开启时本地HTTP明确不读取来源凭证；实际在途disconnect归还FD、Redis容量和DB pin。角色记录移除不回退legacy授权，原session epoch变化不能重新pin。修复接续入口局部settings导入遮蔽，全量重新通过。无新迁移；完整pre-commit通过后提交，未进行现有实例、源站或真实共享Celery验收。

## 冻结来源播放子阶段

基线e61ef44，分支feat/scoped-version-source-playback，无新schema。来源prepare从本人current_version读取source/credential_refs，事务外核查专用keyring可解密，短创建事务再次匹配当前版本refs，grant保存version/scope/epoch/source_name，私有source不从中性AVResource.source推断。凭证更改/撤销后旧元数据不能借新Cookieprepare，须刷新元数据；不静默退回系统或他人凭证。

ID-only播放worker按session冻结引用构造独立来源，每次解析先核查当前凭证owner/version、登录用户有效性、账号epoch及pool/版本；不为了检查可用性初始化未授权的全局来源实例，非范围Cookie回写明确拒绝。来源工厂仍使用全局Proxy.url，下载代理不参与；网络/解密不进入短DB提交。旧未版本化路径保留系统引用兼容，新元数据版本的私人信息不复制到全局表。

清单/密钥/分片入口每次查原固定授权及当前凭证，采用同一独立DB版本pin，原全局/单session Redis容量继续约束。异步关闭在独立cleanup task内完成；正常、HEAD、错误、撤销和断开均回收传输与占用，失效登录无法DB收尾时由既有TTL兜底。原合法播放可在移出后的原期限内完成，角色、下架和凭证撤销拒绝继续；新refresh/进度claim仍需当前有效持有。

来源进度media_key在版本化会话加入scope/context_revision，避免同AVID/provider的公共与私人时间轴混用；仍仅是provider账本，绝非字节相同证据，续播继续confirm。继续观看只匹配本人当前元数据范围与最新ledger，不自动回退旧范围进度。不修改未版本化旧账本key，也不因新增模式复制历史位置。

专项test_version_source_playback.py包含双用户加密记录、真实DB与短占用、默认来源装配、合成源站HTML/媒体响应、认证ASGI及真实临时Redis，验证Cookie/UA不串、全局代理传参、缓存/进度范围、HTTP提交、旧提交拒绝、在途撤销收尾。上游传输为受控替身，不能当成真实站点/个人账号、Byparr出口或Celery目标联调。

冻结来源播放隔离门槛（2026-10-15）：SQLite全量1193 passed/28 skipped；临时PostgreSQL40 passed；SQLite来源/进度专项14 passed，范围/旧准备兼容30 passed。模型迁移无差异，完整pre-commit通过后提交。验证包含真实Redis和DB，但源站HTML及媒体传输是替身，不表示实际Jable/MissAV个人Cookie、Byparr或真实Celery已验收。
