# P8 公共来源受控验收（2026-10-15）

## 范围

用户授权继续P8，并明确首版仅验收公共来源，私人来源实站验收保留为未完成。本轮不在实际实例开启普通多用户准入或GC，不启动/重启用户9790服务，不修改其资源、凭证或账号。

验收分支`chore/multi-user-p8-real-source-acceptance`，初始基线5ad69db。使用既有目标备份恢复独立UTF8 PostgreSQL，API仅监听19791；两个实际测试账号通过生产HTTP/CSRF/上下文协议提交，原生Celery solo执行生产任务，不使用eager或替换来源/翻译器。实际全局代理与浏览器配置保持，broker/cache/Channels使用独立前缀；ProxyServer原始Redis容量键仍与相同浏览器端点共享，不清理其他容量或队列。

独立副本启用多用户以测试两个账号，GC仅在回收副本开启；本轮未写实际实例的两项开关。最终只读复核发现实际.env两项已为true（文件最后修改为2026-10-15 20:33:07，Asia/Shanghai），操作者已确认这是其有意开启，要求保留当前配置，本轮未覆盖该文件。此读数仅代表当前配置，不能代替运行消费者或全部P8放行验收。各恢复副本只写专属临时资源目录；DASS-839本地播放仅通过专属API只读原视频目录，该API停止并恢复隔离视频根后才启动下载worker。既有资源未复制为公共版本，也未改动原媒体。

## 已通过的真实链路

| 场景                    | 结果及边界                                                                                                                                                                   |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Jable ADN-495首次添加   | 两个账号、一份SharedWork、一个attempt、一份ready元数据版本；真实来源、图片、翻译与文件发布成功；两人授权轮询后指向同一版本                                                   |
| MissAV SNOS-116首次添加 | 同上；修复后另从全新副本再次运行通过，没有将此前完成任务当新执行                                                                                                             |
| A撤销，B暂停/恢复刷新   | 修复后真实HTTP及worker通过；generation 2、两个attempt；A保持原版本，B转向新版本，撤销者不被新发布重新加入                                                                    |
| 运行中全部撤销          | 两个本人请求均cancelled，无ready版本，执行已收尾，cleanup为not_required                                                                                                      |
| GC持有与宽限            | 持有时preview报告memberships/grace_period；最后释放后建立24小时宽限，只在副本推进时间后再验删除                                                                              |
| GC真实权限失败/重试     | 对副本版本目录设只读，实际unlink失败登记cleanup_failed/file_cleanup_failed；恢复权限，经HTTP重试与default worker完成，两项资产日志deleted、版本reclaimed；MissAV文件哈希保持 |
| 固定公共版本来源播放    | 真实scrape worker准备，HLS清单HTTP200，读取首个媒体资产1024字节；不代表完整视频解码或长时播放                                                                                |
| 播放权限与GC保护        | 其他账号无法读取会话/媒体；移出后原会话在原期限内仍可读，新建会话被拒绝；preview包含playback_sessions；关闭后旧媒体入口拒绝                                                  |
| 公共凭证撤销            | 只在副本撤销MissAV系统凭证；旧播放会话关闭、旧媒体拒绝、source_cache_identity变化                                                                                            |
| 账号停用                | 只在副本停用测试账号；旧登录失效、本人库返回401，另一个管理员仍可访问                                                                                                        |

来源与翻译均走现有生产装配；抓取缓存命中遵循正常协议。本轮没有假造私人站点登录能力，没有为验收修改正式权限或绕过版本fence。

## 阻断发现与独立修复

首次真实刷新暂停恢复在取源前失败，job `bbe4bc72-763d-467e-bbb9-7f1e381231ac`、generation 2，错误SCRAPE_FAILED，日志为`ValueError: 资源不存在`。首个attempt未开始且已invalidated，第二个attempt确认failed/停止；不是代理或凭证重放失败。

根因：共享装配的旧revision回调固定返回None，ControlledScrape仍据此拒绝refresh。按门槛先停止推进并清理临时服务；用户另行授权独立修复。修复提交45348ae，分支fix/shared-scrape-refresh-existence，通过门槛后已合并idle。

现在仅旧兼容路径执行AVResource存在性检查；共享路径继续由本人持有/意图、来源/pool/work/attempt及版本parent/指针CAS负责。无schema、接口或正式数据变更。六种回归覆盖遗留首次刷新/已有版本及无暂停、排队暂停、来源阶段暂停恢复，修复前均复现，修复后通过；再用全新副本重放上述原始场景成功。

验收辅助脚本曾先于用户投影检查active关系；按现有user fence协议先轮询两个本人快照后通过，没有改生产投影语义。GC辅助脚本的结果字段定位也在执行前修正；这两项脚本问题与真实刷新故障分开记录。

## 隔离与文件系统检查

- 共享刷新修复完整后端：`cd django_backend && uv run pytest tests/ --ds=django_project.refactoring_test_settings -v`，1341 passed、28在线跳过，350.27秒。
- 共享执行/旧刮削/版本专项：`uv run pytest tests/test_shared_version_workers.py tests/test_controlled_scrape.py tests/test_version_publication.py --ds=django_project.refactoring_test_settings -q`，SQLite 54 passed；临时PostgreSQL相同专项54 passed。
- 修复前P8原生共享worker/GC派发专项：`test_multi_user_native_acceptance.py`及`test_resource_gc_dispatch_admin.py`，18 passed；上述修复后全量再次包含这些场景。
- 实际宿主机资源根的唯一`.p8-filesystem-*`临时子目录：`test_task_assets.py`、`test_version_publication.py`及`test_resource_gc_files.py`，58 passed。仅测试目录内临时文件与隔离数据库，结束删除该目录；证明当前UID/文件系统协议，不证明旧文件的每一种属主或未来Docker挂载。
- 下载修复完整隔离门槛1345 passed/30 skipped（415.04秒）；固定二进制的本地HTTP 428/并发/明文与AES恢复组合22 passed（92.17秒），原生用例默认跳过、另显式运行。
- 根目录完整`pre-commit run -a`通过后提交。前端无代码变化，未将先前浏览器/200项前端测试标为本轮重新运行。

## 任务追踪确认

用户请求由UserOperation持久保存，底层执行由SharedWork/TaskJob保存；“不再跟踪”仍是浏览器localStorage中的隐藏ID，没有后端隐藏表或对应写接口。跨设备不共享隐藏状态，隐藏不撤销请求、停止任务或移出库。实现见`operationTracking.hide/start`与旧`taskJobs.hide/start`，本轮不改该行为。

## 完整视频的阻断、修复与最终验收

操作者指定已下载DASS-839，若需新下载则使用MIMK-079。DASS-839已通过只读本地播放HEAD 200、Range 206、未登录拒绝及关闭后拒绝，文件大小1,315,392,265字节，前后文件身份未变，未调用worker或来源。其旧布局文件不等同于新共享视频发布。MIMK-079元数据真实获取成功，两个用户下载请求合并为一份SharedWork。临时资源总占用预算5 GiB；实际峰值812,803,505字节（约775 MiB），未触及预算。真实下载约73 MiB时通过HTTP请求暂停、确认paused后恢复，generation 2/两个attempt，恢复后继续取得数据。286.7秒时下载器正常退出但输出识别为空，任务DOWNLOAD_FAILED，未进入完整媒体校验/视频版本发布，因此此项门槛失败。

失败job `6637aa8a-7ea1-48eb-9032-0c1954490977`，stage video_download；两个attempt分别stopped/failed，均有stopped_at，cleanup_state=completed，ready视频版本0、剩余视频文件0。当时日志只记录“未找到输出文件”，旧适配器不保留CLI诊断，因此当时不能据此断言合并、命名或网络根因。暂停恢复由独立HTTP控制观察器执行，原下载观察器的pause_resume_tested=false仅表示该观察器未发起控制；整体验收以download-controls-summary及download-combined-summary为准。

当时按AGENTS.md质量门槛停止条件保留P8分支及失败证据并暂不合并；用户随后授权独立诊断修复并继续。

独立修复926c8c3已通过1345项完整隔离测试（30跳过）、固定二进制22项专项及完整pre-commit后合并idle。真实重放确认分片请求HTTP 428，1241/1437导致CLI内部失败却退出0；默认并发32→4且记录安全诊断。参数对照完整下载/校验/共享发布及本地播放已通过，454秒、峰值1,781,908,581字节。详见[定位与反证记录](download-cli-failure-20261015.md)。最终另从原备份恢复全新副本，以已合并926c8c3及原固定二进制执行：无参数包装器、无强制线程覆盖，不使用此前已下载视频或ready版本代替新下载。最终job `e4bc92f4-df37-46d8-b22d-36ba35e08d86`完成双账号同work、真实暂停/新generation恢复、1437分片下载/合并、全量解码及不可变视频发布，446.2秒，峰值1,781,908,581字节，generation 2/两个attempt。两人指向同一视频版本`448b7ffe-09b6-4f65-bd2e-b92276eeee09`，文件870,155,788字节，固定版本本地HTTP 206通过。

随后仅在副本开启GC：其他登录会话/媒体访问被拒绝；两人释放后原会话仍可Range 206、新会话拒绝；最后释放创建24小时宽限，只在副本推进gc_after后仍因playback_sessions阻塞。关闭后旧媒体拒绝，GC job `d06f7f63-b5e2-4565-aba9-081ed6453ff1`经真实default worker完成，版本reclaimed、资产日志deleted、视频已删除，元数据封面哈希保持。因此完整视频阻断已解除，首版公共来源受控验收范围通过；不将其扩展为私人实站或当前用户运行消费者已更新。独立修复926c8c3已合并idle，P8记录在最终文档门槛通过后合并。

原download-summary的pause_resume_tested=false只记录该观察器未发起控制；最终download-controls-summary及download-combined-summary明确独立HTTP观察器发起的暂停恢复成功，避免错误解读为未测试。

## 剩余项与放行边界

私人来源实站按用户决定保留未完成；正式消费者验收、长时观察及未来Docker部署仍需分别登记。已豁免的HTTPS/真机项不重新设为阻塞。首版公共来源受控范围通过不等于当前实例所有消费者已部署验收或私人站点已验，也不自动更新用户默认工作树或重启其进程。

最终实际库只读复核：资源693、持有693、受管账号1、GC记录0；Jable/MissAV均active/version 2。副本中的凭证撤销、账号停用及文件删除未发生在实际库。

## 私有证据

首轮副本、公共来源/GC结果、失败现场与运维脚本保存于Git忽略目录：

`django_backend/backup/p8-real-source-20261015T124252Z/`

目录0700、文件0600，含恢复副本、脱敏结果和按私有数据处理的服务日志，不提交秘密、原始来源HTML或签名URL。修复后元数据/控制/播放/撤销重放的独立恢复点为`django_backend/backup/p8-real-source-20261015T130809Z/`。本地播放与完整下载失败、暂停恢复、停止/清理证据为`django_backend/backup/p8-real-source-20261015T132153Z/`；只保留图片资产，不归档大型视频。HTTP 428定位与低并发对照保存于`django_backend/backup/p8-real-source-20261015T134405Z/`；正式默认调用和真实视频GC最终证据保存于`django_backend/backup/p8-real-source-20261015T135640Z/`，包含代码/二进制来源核对与私有数据库恢复点，不归档大型视频。所有本轮临时API/worker/PostgreSQL已停止，专属目录和broker前缀已清理，未重启用户服务。本轮使用原持久keyring只读解密，未将密钥复制到该备份目录。
