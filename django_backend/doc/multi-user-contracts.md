# 多用户与共享资源池契约（P0）

日期：2026-10-14；核查基线：ae10475；阶段分支：`doc/multi-user-contracts`。

本文冻结[执行计划](multi-user-shared-pool-plan.md)的首版业务契约，记录实际入口与迁移接入点。**设计已确定，运行行为尚未改变**：仍只允许指定operator登录；没有新增表、迁移、普通用户准入或自动回收。后续实现不得以本文中的目标接口冒充现有接口。

## ADR-001：身份、持有与复用

采用“共享存储、独立用户库”。池身份使用服务端规范化AVID，池主键为UUID；媒体来源、质量、凭证共享范围及版本属于产物规格，不通过创建多个同番号池绕过持有约束。

规范化沿用[task_control_rules.normalize_avid](../nassav/task_control_rules.py)：去首尾空格、大写、最长50字符、只接受字母数字起始的字母数字/点/下划线/连字符，禁止`..`。不自动替换连字符、猜测番号别名或合并来源返回的相似番号。现有删除规范化没有同样的长度限制；P1导入预览必须报告超长或冲突记录，不能静默合并。模型规范化与唯一约束均由服务端承担，不只依赖前端或`save()`。

- `UserLibraryEntry`的pending与active均为有效持有；pending必须对应仍有效的添加需求。首次添加失败/取消且没有其他有效需求时释放pending，不制造永久占位。
- 公开搜索摘要可发现资源；正式库列表按本用户持有过滤。详情、正式封面、下载媒体和新播放会话要求有效持有及产物访问范围，管理员另走明确权限。
- 全局“资源已存在”不是“已加入我的库”。搜索与推荐卡片的添加状态以`is_in_my_library`为准；缓存命中后重新投影，不缓存个人授权结论。
- 两用户只能复用授权范围和工作规格兼容的结果。个人凭证产物默认私有，不因另一用户持有同一池而授权私有视频、签名URL或详情。
- 收藏、观看标记、备注、历史和进度均不构成持有；稍后再看只允许有效持有资源。普通移出清除稍后再看并阻断新编辑，宽限期内可保留其他个人标记；实际AVResource回收仍清除其级联标记/备注。历史须在P6改为稳定池身份和标题/番号快照，回收后显示不可播放；进度保留原媒体身份账本与墓碑。

暂不支持别名合并、每用户代理、评分、公开注册、匿名分享和多主机资产发布。新增这些能力须另补身份/权限契约，不能把AVID当成媒体字节身份。

## ADR-002：角色与授权

授权顺序固定为：认证且账号启用 → 动作权限 → 对象归属/有效持有 → 凭证与媒体范围 → 版本/执行代次。对象查询前绑定当前用户，跨账号对象返回404；明确缺少动作权限返回403；不接受body/query提供的owner。

应用角色明确分为用户与管理员，不从`is_staff`、`is_superuser`或指定用户名自动推导新管理员。P2提供显式角色持久化与引导；P8前保留现有operator准入。现有任务控制对superuser的例外只能作为旧路径兼容，不能传播到新共享控制协议。

| 动作域                         | 普通用户                      | 管理员                                           | 状态所有者                  |
| ------------------------------ | ----------------------------- | ------------------------------------------------ | --------------------------- |
| `library.read/add/release`     | 自己的库/需求，添加受配额约束 | 自己的库；管理他人关系须独立审计动作             | 用户持有关系与池            |
| `resource.read/play`           | 有效持有且范围匹配            | 管理资源须有对应动作，仍检查媒体范围             | 池版本、访问策略与播放会话  |
| `operation.request/cancel`     | 仅本用户请求，可脱离共享工作  | 不能借普通取消接口控制其他请求                   | UserResourceOperation与订阅 |
| `work.control`                 | 无权暂停/终止共享工作         | 明确管理权限，理由/版本/request_id/审计          | TaskJob与attempt            |
| `personal.read/write`          | 本用户状态、设置、历史及进度  | 默认也仅自己的；无全员私人数据浏览权             | 现有个人模型                |
| `credential.read/write/revoke` | 自己凭证元信息、盲写及撤销    | 系统凭证管理；他人凭证只允许明确审核/撤销        | SourceCredential及快照      |
| `admin.users/roles/sessions`   | 无                            | 邀请/启停/角色/密码重置/会话撤销，保护最后管理员 | 用户、角色、会话及审计      |
| `admin.resources/gc/quotas`    | 无                            | 下架、保留、回收预览/重试、配额管理              | 池、占用、资产日志及审计    |
| `admin.health/audit/config`    | 无                            | 全局队列/健康/脱敏日志/服务器配置                | 运维投影与审计              |

管理员权限不授予读取Cookie明文、密码、其他用户备注/历史的通用接口。数据库超级用户的运维能力不等同应用角色。强制下架和停用账号立即阻止后续媒体读取；普通移出允许此前合法、固定版本的会话在既有绝对期限内读完，但拒绝新会话、接续和期限扩展。播放器继续保存该用户进度/历史不恢复持有。

## ADR-003：凭证、并发和缓存范围

来源使用不可变凭证快照，任务仅传凭证引用/版本，不传明文Cookie。首版显式选择个人或系统凭证；没有匹配凭证则失败，不能静默使用他人的Cookie。个人产物提升为公共事实默认关闭。

`CredentialResolver`只负责按用户/来源/所需能力解析可用凭证；加解密、刷新、来源HTTP客户端与任务调度分开。专用密钥与key_id支持轮换，密钥缺失失败关闭，不退回明文。GET只返回是否已设置、范围、版本和状态。

刷新租约域为凭证ID、目标host、出口/浏览器上下文；发布检查owner、generation、凭证version和撤销状态。网络在事务外；普通读取不等刷新锁。每个并发操作独立cookiejar/浏览器上下文，禁止全局来源实例共享可变Cookie。代理并发通过[ProxyServer](proxy-concurrency.md)，沿用全局Proxy.url与跨worker容量，不以具体provider分支安排工作，也不与下载代理混用。

缓存键包含公共/私有共享域、凭证引用及版本、host、出口/会话和解析版本。公共事实可共用，但当前持有/黑名单/allowed_actions每次重算；个人签名播放链接与鉴权headers不可进入公共域。凭证撤销拒绝新prepare和旧执行发布，并关闭依赖会话；不得把遗留私有资产自动改为公共。

## ADR-004：共享工作、版本与回收

用户请求和底层工作分别拥有ID、version和允许动作。兼容需求订阅同一工作；发起者不是永久控制者。取消自己的请求只脱离自己的订阅，有其他有效需求时工作继续。最后需求消失才执行已有停止确认/资产收尾协议；已复用的正式版本不能当成请求临时产物删除。普通用户首版不提供“暂停共享任务”。

发布同时检查attempt、执行owner/generation、池lifetime generation、凭证版本及有效需求。失败保留旧好版本；迟到成功不能恢复已取消持有。版本文件不可原地覆盖，读者固定版本，旧版本按真实占用回收。

普通最后持有释放只进入pending_gc，建议宽限默认24小时，由后续配置实现；当前没有该配置或调度器。有效持有/订阅、活跃或暂停任务、读者、promoting/补偿日志及管理员保留均阻止回收。writer租约过期或任务终态不是停止证明。

再次添加对pending_gc撤销调度并提升池代次；deleting/cleanup_failed拒绝原地复活，返回可重试409。GC在共享文件锁内、短事务重新检查引用并CAS领取deleting，随后事务外按日志删除；未知身份保留现场。头像按其他资源引用保留；原站缓存独立TTL；历史快照不保护媒体文件。

配额按每用户持有媒体的完整逻辑大小计算，同一物理版本磁盘只计一次。并发预留在user fence内完成；同一请求重试不重复计费，失败/取消仅释放一次预留，复用也不能绕过配额。配额数值与最大并发由部署资源配置决定，P0不编造吞吐或延迟保证。

## 当前入口与消费者迁移清单

全部HTTP业务路径前缀为`/nassav/api`。实际注册见[urls.py](../nassav/urls.py)，默认DRF权限来自[settings.py](../django_project/settings.py)的IsOperator；[SchemaAPIView](../nassav/http_base.py)自身没有新增对象权限。下表目标均待对应阶段实现。

| 当前入口/消费者                                             | 当前状态或授权所有者                                              | 目标接入与阶段                                                                   |
| ----------------------------------------------------------- | ----------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| auth/session、login、logout                                 | auth_views/access，指定operator；Django登录session                | P2角色/停用/会话撤销，P8才开放普通用户                                           |
| resources及尾斜杠别名                                       | resource_views/query，AVResource共享集合＋本用户状态投影          | P1持有查询，P2对象权限，P7分页与添加状态                                         |
| resource/metadata、preview、cover                           | media_views；共享资源/文件，默认operator保护                      | P2先对象授权再ETag/304/打开文件；P5版本范围与读取占用                            |
| actors、genres、detail、avatar及别名                        | catalog_views/media_views；共享演员/类别及作品关系                | P2区分公开摘要与本库作品数，不泄露其他人库存；P3凭证域                           |
| source/list、search-capabilities                            | SourceManager/ExternalSearch能力                                  | P2允许发现已开放能力，P3按凭证能力裁剪                                           |
| source/cookie GET/POST/DELETE                               | SourceCookie全局单来源行，GET返回Cookie；CookieRepository         | P3新凭证盲写；旧明文GET仅兼容operator，开放普通账号前关闭                        |
| search/jobs提交、查询、cancel                               | Redis快照/取消标记，提交带user_id；查询/取消校验task签名token     | P2补当前用户归属，token也绑定owner；P3摘要缓存作用域；P4不复用他人任务句柄       |
| recommendations（含同步/尾斜杠/demo）、options、metrics     | recommendation_views；个人上下文＋公共事实/库存查询               | P2核对私人指标/模拟入口，P3凭证范围；库存改本人持有                              |
| recommendations/jobs、status、cancel                        | DB RecommendationJob.owner，历史generation/执行fence              | 保留本人控制；P3作用域；不改为共享推荐job                                        |
| recommendations/feedback、seed-block、avid-blocklist、reset | 本人历史/反馈/黑名单，repository/jobs历史fence                    | P2保持owner与既有fence；不因共享池取消过滤                                       |
| recommendations/cover                                       | 推荐封面代理/缓存                                                 | P2先核验可访问推荐上下文；P3禁止私有图片跨域缓存                                 |
| resource POST、refresh、resources/batch旧同步入口           | resource_views/composition；直接改共享资源                        | P2管理员兼容入口；普通用户走私有operation，禁止绕过P4发布                        |
| resource/jobs、batch、status                                | 受控TaskJob.owner；当前按类型＋AVID全局去重，其他owner冲突        | P4用户operation/subscription，不放宽owner比较来实现共享                          |
| resource/{avid} DELETE及batch delete                        | ResourceDeletionService；共享文件锁下物理删除并级联               | P2管理员旧语义；普通release用新路由；P6才切安全GC                                |
| downloads提交/batch/mock、DELETE                            | 受控/兼容下载；DELETE物理删除视频；mock限DEBUG                    | P2管理员兼容/禁普通mock；P4用户需求；P5发布；P6删除                              |
| downloads/abspath                                           | 本地文件路径与FilePathPrefix                                      | P2普通用户禁止，改走授权媒体；管理员运维才保留路径                               |
| tasks/jobs/list/status/actions/control/cleanup/retry        | TaskJob.owner，superuser旧例外；request行锁/命令幂等              | P2明确admin动作；P4本人请求快照和取消；工作控制保留管理侧                        |
| tasks/queue/status                                          | 全局Redis/Celery队列投影                                          | P2仅管理权限，普通用户只看自己的请求                                             |
| setting GET/PUT                                             | UserPreferences及定义，request.user                               | 保留JSON部分更新，P2启用状态；不存服务器凭证/配额                                |
| resource/{avid}/status                                      | UserResourceState，user fence/version                             | P1/P2补持有校验，保留草稿冲突与批量投影                                          |
| personal/history、watch-later                               | UserWatchHistory/UserResourceState，本人集合                      | P1移出清稍后再看；P6稳定历史快照，查询保留不可播放项                             |
| playback-sessions提交/status/refresh/close                  | PlaybackSession绑定user＋login_hash，DB代次/期限                  | P2持有/范围/撤销；P5固定资源版本及占用；普通移出受限续读                         |
| playback-sessions manifest/assets/file（含Range/HEAD）      | playback_media.authorize_session、local_gateway，session授权/容量 | P2每次读检查停用/下架；P5固定版本；授权先于条件请求与流打开                      |
| playback-progress/clear/claim及viewed                       | 本人ledger/session/sequence，进度writer独立于历史                 | P2新claim要求持有，已授权续读保存保留；P6不误删账本/墓碑                         |
| WebSocket /nassav/ws/tasks/                                 | TaskConsumer验证operator/session，所有连接共用task_updates组      | P2/P4按user路由安全版本提示；管理队列另授权；撤销即时失效                        |
| Celery tasks、Beat派发/恢复/缓存维护                        | DB任务/attempt、租约、事件出箱；Celery只运输                      | P4系统执行身份与需求fence；P5/P6代次发布/回收，不依赖body用户                    |
| 管理命令及scripts                                           | 受信任运维进程，无HTTP用户上下文                                  | P1显式owner导入预览；P2管理审计；P5/P6同步资源写者，普通账户开放前核查旧直写脚本 |
| Django /admin、/healthz                                     | Django后台权限；健康探针                                          | 与应用admin分开；后台编辑共享模型不得绕过服务协议；健康不返回秘密                |
| 前端resource/推荐/外搜添加状态                              | useResourceAdds及资源store，本轮job_id/version；全局存在性        | P7本人持有/operation，不能以其他人job或已有文件禁用添加                          |
| 前端taskJobs、观看缓存、播放页面                            | 登录epoch/请求revision与job或session版本                          | P7 operation/work分别合并；身份/持有/角色/凭证变更失效缓存与blob                 |

清单覆盖当前urls的全部业务路由与别名、单独媒体函数、WebSocket和后台消费者；新增路由时补入。它是静态接入清单，不是已通过跨用户运行验收。无HTTP上下文的脚本必须显式区分系统事实维护与用户持有导入，不使用“第一个用户”作为owner。

## 锁顺序与现有差异

| 当前入口                              | 已核查的现状                                                    | 目标规则/落地阶段                                                  |
| ------------------------------------- | --------------------------------------------------------------- | ------------------------------------------------------------------ |
| TaskRecords.create                    | reservation文件锁 → 短事务创建job/attempt；active_key类型＋AVID | P4池/规格兼容判定＋订阅，保留停用/暂停工作的保护                   |
| TaskRecords.request/claim/publication | 短事务job写fence，attempt/命令/事件跟随；无用户持有关系         | P4进入事务前按user→pool→work顺序装配；不能先锁job再回调锁user/pool |
| TaskAssets._locks                     | task文件锁 → resource文件锁 → 排序target文件锁                  | 复用顺序；P5/P6在文件锁取得后才开启发布/删除短DB事务               |
| ResourceDeletionService               | resource文件锁内检查活动任务/promoting，删除文件再DB            | P6加读取占用/版本日志/池CAS，不把当前入口当完整GC协议              |
| personal_state/preferences/viewing    | user写fence先于个人行；record_view随后锁session                 | P1/P2新增pool时放在user之后；P5固定session只锁本池，不回头锁user   |
| playback submit/progress claim        | user写fence → session/ledger；close只session                    | P2/P5加入pool/版本先于session；纯close不得反向取得pool/user        |
| recommendation repository/jobs        | 本人历史generation fence；无池锁                                | 保留历史owner/fence；库存读投影，不在历史事务等待池/文件或网络     |
| CookieRepository手动/自动提交         | SourceCookie行锁与updated_at CAS；缓存按来源键                  | P3凭证/快照owner-generation-version CAS，刷新不嵌入user/pool事务   |

统一DB顺序：需要用户fence时先user，再按规范身份排序pool，再operation/work及其子记录；播放路径继续按session→ledger。共享系统发布只锁pool→work/版本，不锁每个订阅用户；通知由提交后的出箱处理。凭证刷新与历史事务独立，不跨域持锁调用新服务。

如用户操作需要文件锁，先取得task→resource→排序target，再开上述短DB事务并重新授权；**禁止持有DB锁等待文件锁**。前置读只是定位锁键，取得锁后必须重读验证。网络、复制、哈希、broker和长文件删除均不在短事务内。稳定flock文件不在线unlink；锁文件存在不是占用证据。

SQLite的短写fence与PostgreSQL行锁实现不同，逻辑顺序相同。以上是目标顺序，不宣称现有所有消费者已遵循新增pool顺序。P1只接持有核心；P4/P5必须覆盖原job优先路径改造的死锁、反向锁和迟到发布故障。

## 目标响应样例与错误约定

新接口沿用`code/message/data/pagination`、session认证与CSRF。以下字段为冻结的最小契约，UUID示例只表示身份，均不是已注册API。提交的request_id为UUID；服务端保存规范payload hash，同用户同键同内容幂等，不同内容409；不能返回其他用户请求快照。

添加请求：`POST /api/library/entries`，body包含`avid`、`source`、`request_id`及可选凭证引用，不接收owner或Cookie。复用已就绪产物返回200，排队返回202：

```json
{
  "code": 202,
  "message": "添加请求已提交",
  "data": {
    "entry_id": "11111111-1111-4111-8111-111111111111",
    "entry_version": 1,
    "membership_state": "pending",
    "is_in_my_library": true,
    "reused": false,
    "operation": {
      "operation_id": "22222222-2222-4222-8222-222222222222",
      "version": 1,
      "state": "queued",
      "allowed_actions": ["cancel"]
    }
  }
}
```

`is_in_my_library`表示有效pending/active持有，只有active且授权范围匹配才提供正式详情/播放；不能由此布尔值直接推导所有动作。查询私有operation返回自己的version/allowed_actions及安全进度摘要；不暴露其他订阅者身份、人数、凭证或原始work检查点。

移出：`DELETE /api/library/entries/{entry_id}`携带expected_version及request_id，成功200，返回`released: true`、`entry_version`和`gc_scheduled`；后者只表示安排候选回收，不表示文件已删，也不透露其他人持有数量。重复同命令返回已记录结果，不能再次清除新一轮持有；再次添加使用新持有代次。

取消：`POST /api/my-operations/{operation_id}/cancel`携带expected_version及request_id，返回本人的取消快照，不承诺立即停底层工作。返回“自己的请求已取消”足够，不返回其他用户需求数。

| HTTP/code | data.error_code或行为                                       | 客户端约束                                                  |
| --------- | ----------------------------------------------------------- | ----------------------------------------------------------- |
| 400       | invalid_input                                               | 展示字段原因，保留输入                                      |
| 401       | 未登录/会话无效                                             | 走既有认证响应，不用build_response默认为200的未映射代码     |
| 403       | action_forbidden / quota_exceeded / credential_scope_denied | 配额拒绝包含本用户维度/限额/用量，不泄露共享池使用者        |
| 404       | object_not_found                                            | 不区分他人对象与不存在；先授权再发304/206                   |
| 409       | version_conflict / request_id_conflict                      | 只给本人可读新快照，不覆盖前端草稿                          |
| 409       | resource_reclaiming                                         | `retry_after_seconds`为有界非负整数；保留输入，明确手动重试 |
| 503       | dependency_unavailable                                      | 可重试失败，不声称请求已完成或自动幂等成功                  |

当前[build_response](../nassav/api_utils.py)没有401/429映射，P2需要显式认证HTTP状态，配额首版固定403而非新增429。媒体成功/错误沿用媒体协议，不强行把二进制包装成JSON；流开始后不能把状态改成成功业务消息。

## P1迁移前交付边界

下一阶段先新增两表，不一次建设凭证、版本、配额和GC表：

| 表                         | P1字段/约束                                                                                                                      | 迁移及回填约束                                                                                 |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| nassav_resource_pool_entry | UUID PK；canonical_avid唯一；AVResource可空一对一引用；state；lifetime_generation/version正整数；gc_after；created_at/updated_at | 引用SET_NULL保留池身份；受控删除仍禁止绕过服务；回填有效现有AVID，不移动文件                   |
| nassav_user_library_entry  | UUID PK；user/pool FK；pending/active状态；需求规格/授权范围；version正整数；created_at/updated_at；unique(user,pool)            | user删除须先受控撤销需求/播放；pool有持有时PROTECT；移出由服务删除关系，幂等记录不能随关系删掉 |

P1关系版本不能单独承担删除后重建的请求幂等；P4持久operation未引入前，attach/release核心保留调用方幂等边界、不开放新用户HTTP写入口。旧全局API维持operator语义，不提前把其DELETE改成release。P1完成关系回填不代表版本/私有媒体复用已经实现。

结构迁移不自动分配所有者；导入命令必须显式指定启用操作者，默认只读预览，apply另授权。不按收藏/历史推测，未知/冲突记录拒绝；已存在用户关系不覆盖。当前叶节点0036，实施前再次核对后生成新增迁移，保留历史文件。数据库、配置/加密密钥和媒体备份、维护窗口及旧writer停机均在实际实例迁移前确认。

用户本轮要求“需要执行数据库迁移即停下”。因此P0只交付契约、清单和P1结构草稿；**未执行makemigrations/migrate、导入、迁移测试或正式DB连接**。P1实施和SQLite/PostgreSQL升级→回退→再升级验收须在下一轮明确迁移范围后进行，不为绕过停止条件提前进入依赖P1的P2–P8。

## 验证记录与后续门槛

P0核查范围：urls及别名、默认权限、auth/access、媒体函数、WebSocket、任务预留/控制/文件锁、个人状态/播放写fence、来源Cookie与推荐历史fence、后台命令和前端添加/任务消费者。全部有现状状态所有者、目标权限所有者及实施阶段。

P0门槛为新链接/JSON样例有效及根`pre-commit run -a`通过；本阶段纯文档，不运行会建立迁移测试库的后端pytest。真实并发、代理、Cookie隔离、worker停止、媒体读取和GC均未验收，不能以静态清单替代。每阶段实现后补故障注入与全量隔离门槛；P8至少两独立用户、同用户双登录，记录部署资源、N/M并发与延迟/容量。没有可用部署测量前不发布性能承诺；该项是后续目标环境门槛，不是本次静态P0已验证项目。

执行记录：`python3`检查本次新增/修改链接及JSON样例，14条本地链接和1份JSON通过，退出码0；`git diff --check`退出码0。首轮全仓钩子受到uv缓存只读限制，恢复缓存访问后编译检查通过；格式钩子修正Markdown后重新暂存并运行完整`pre-commit run -a`，最终结果以阶段提交记录为准。钩子配置未修改。提交以`[Doc] Freeze multi-user P0 contracts and migration boundary`定位，门槛通过后合并idle；该提交不包含模型或迁移。
