# PostgreSQL 多用户结构迁移记录（2026-10-15）

## 授权、目标与范围

操作者明确授权“授权指定 PostgreSQL 迁移并继续”。使用idle基线bf83195的迁移，在独立分支chore/multi-user-postgres-cutover记录执行；默认工作树dev及用户前端依赖改动保留。未同步或启动旧dev消费者。

实际目标来自原工作树的忽略配置/环境：PostgreSQL 16.15，127.0.0.1:5432，database=dbb，schema=nassav。目标原叶节点0036，资源693条；旁边的旧SQLite没有修改。核查时无其他数据库客户端/项目服务进程，29个任务均为终态，45个attempt均已成功/停止/失败，3个播放会话均closed，推荐任务为空。配置原操作者nassav存在且启用。

此次先完成结构迁移与只读预览；操作者随后确认归属/admin及Cookie只隔离后，进一步执行了不受推荐冲突影响的持有、个人标记、管理员和凭证隔离导入。没有认定旧数据公开，没有打开来源范围、共享库、多用户登录或自动GC。

## 备份与预演

迁移前先对39张既有表记录原字段、行数和规范JSON逐行有序摘要，django_migrations单独记录。摘要不含可还原行数据，完整manifest和备份均不入Git。

恢复点：`/tmp/nassav-agent-worktree/django_backend/backup/multi-user-pg-20261015T084815Z/`。目录0700，database.dump为0600，使用匹配版本pg_dump自定义格式、no-owner/no-acl生成完整数据库备份，714813字节；pg_restore目录检查成功。备份前后重新核对无消费者及摘要一致。SHA256、原迁移列表、操作脚本和完整执行日志在同目录，禁止提交或输出备份内容。该恢复点位于/tmp工作树，清理工作树前须转存到操作者的受控备份位置。

在独立Unix socket PostgreSQL端口55467中新建空UTF8数据库，真实pg_restore恢复，再执行0036→0051。恢复前后39张原表共6267条原行/原字段保持一致。

首轮严格全表相等检查发现auth_permission和django_content_type新增模型权限；目标库当时尚未修改。核对后用新恢复库重做：原34个content type、136条权限行及所有原用户授权关系保持；允许新增25个content type和100条对应权限，不对任何账号自动授予这些权限。不是忽略整个权限表，而是保留原ID范围逐行摘要。其余业务表精确核对原字段/全部行。第二轮预演通过后才放行目标迁移。

## 目标执行与验证

执行前再次核查消费者、终态和原数据摘要；使用5秒DDL锁等待、120秒statement timeout。逐项执行0037–0051，15个迁移均OK，目标最终为0051_gc_discovery_cursor。

迁移后39张原表、6267条原行在原字段范围内摘要一致；包括资源、个人状态/设置、原用户授权、旧Cookie、历史任务及关系数据。新模型/字段按迁移产生，不自动提升资产公开范围或分配管理员。

随后在数据库会话default_transaction_read_only=on下执行预览与模型核对：

| 项目                                         | 结果                                                                |
| -------------------------------------------- | ------------------------------------------------------------------- |
| 迁移图待执行项                               | 0                                                                   |
| makemigrations --check --dry-run             | No changes detected                                                 |
| import_resource_library --username nassav    | 693条资源，applied=false                                            |
| import_personal_data --username nassav       | 39条旧资源标记，未指定旧INI，未写入                                 |
| import_recommendation_data --username nassav | 7批旧历史、25条种子、0条资源黑名单，未写入                          |
| bootstrap_app_admin --username nassav        | applied=false，未建立应用角色                                       |
| 原MissAV/Jable Cookie                        | 均不满足系统clearance校验；只报告分类，不显示Cookie值，未激活或导入 |

操作命令显式设置NASSAV_CONFIG_PATH/NASSAV_ENV_PATH指向已确认原配置。运行器自身注入DEBUG=release会触发严格布尔校验，执行时env -u DEBUG使项目.env中的DEBUG=false生效；没有修改项目配置或放宽配置校验。

## 已确认归属后的独立导入

操作者随后明确确认“确认归属和管理员；Cookie只隔离”。先在已恢复的副本预演，发现推荐导入保护条件：目标已有352条个人AVID黑名单，即使历史/种子尚空也拒绝自动合并。没有绕过保护；旧7批历史/25种子仍保留无owner状态，已另行询问是否扩展安全导入能力。

其余步骤在隔离副本验证后执行到目标，且在导入前另留before-ownership.dump（0600）：

- bootstrap_app_admin：nassav显式应用admin、version=1，独立幂等UUID与一条account.bootstrap审计；未修改Django密码或创建新登录。重放原UUID不重复引导。
- import_resource_library：新增693份legacy:operator:1持有与691个pool（2个pool已由既有历史迁移产生），未移动文件、未创建公开版本；重复执行新增0。
- import_personal_data：新增0条，原有42条个人状态及已有通用设置行保持完全一致，没有指定INI或覆盖现有值。
- import_source_credentials：Jable/MissAV各一份加密system/account记录，均quarantined；解密校验与原值一致，但不输出秘密、不激活、不改原SourceCookie。

持久专用keyring位于`/home/florenz/NASSAV/secrets/source-credentials.json`，恢复副本为同目录source-credentials.recovery.json，文件均0600、Git忽略；不把密钥存入/tmp或数据库备份目录。只新增部署秘密文件，原工作树源码/配置保持未改。未来启用范围消费者时必须显式配置NASSAV_SOURCE_CREDENTIAL_KEYRING_FILE为实际可读路径；容器需正确挂载，不把宿主路径直接当容器路径。

目标导入与重复执行均核对AVResource、SourceCookie、既有UserResourceState/UserPreferences原数据摘要不变；持有693份，版本0份，凭证2份且全部隔离。执行日志有原Django session无法被当前签名配置解码的警告，没有输出session数据；当前配置下这些旧session不被接纳，不以成功引导宣称所有历史签名配置的会话均已逐条验证。

## 尚待确认与继续条件

结构升级及上述独立导入已完成。推荐导入因352条既有个人黑名单保护而暂停，需要决定保留黑名单同时补空历史/种子的合并规则。普通准入和自动GC继续关闭；后续真实来源、ProxyServer及部署消费者验收不能由本次结构/归属迁移替代。

启动API/worker前应使用0051对应的idle代码，并统一全部消费者；原默认dev仍是旧代码，不因目标表已经升级就可以混跑。数据库迁移不等于前端制品部署、来源worker/真实ProxyServer或挂载权限验收。恢复需维护窗口和匹配数据库/媒体/配置，不能在实际目标做演示性回退。

本分支不新增生产代码或schema；源码仍为已通过1329项隔离后端回归、前端200项检查和原生双账号/worker专项的bf83195。上述数字是代码基线的隔离证据，本次新增证据是恢复预演、目标迁移及只读核对；文档提交另执行完整pre-commit，不把历史测试重新标作本次目标联调。

最终只读复核通过：0051、资源/持有各693、显式admin、个人黑名单352、旧历史7/种子25未归属、凭证2份全部隔离，四个新模式开关仍false。另保存after-ownership.dump和SHA256（0600文件/0700目录）；专用55467预演服务已停止，包含真实恢复副本的临时集群数据目录已清理，正式5432服务未停止。完整pre-commit通过后提交并合并idle。

## 推荐安全补导入已执行

操作者进一步确认保留352条黑名单并补空历史/种子。独立分支fix/recommendation-import-preserve-blocklist新增--preserve-personal-blocklist，默认严格拒绝合并保持；该选项也拒绝已有历史/种子、旧AVID黑名单或活动job。旧无owner及目标历史generation各推进一次，拒绝旧同步writer，重放不再推进。无schema变更。

先将after-ownership.dump恢复到全新隔离PostgreSQL预演；再通过SQLite/PG推荐专项各11项、原生worker组合15项、稳定格式化后的完整SQLite1335 passed/28 skipped及完整pre-commit，才对真实目标执行新选项。期间发现此前Ruff误删不同名fixture导入造成原生测试setup错误，已用显式模块别名修复并重跑全量，不忽略错误。

实际结果：7批历史、25条种子全部归nassav；352条个人AVID黑名单逐行摘要保持。原反馈/条目/种子关联、AVResource、SourceCookie、个人状态/设置及加密凭证摘要保持；历史/种子的非owner字段保持。再次执行返回[0,0,0]且两侧generation不再变化。导入前后分别保留before-recommendation-import.dump与after-recommendation-import.dump，操作脚本/日志/结果及SHA256位于前述私有恢复点。

早前“推荐暂停”段落为发现保护条件时的阶段记录，现已解决。仍未完成的目标门槛是实际来源/ProxyServer与部署worker/挂载验收：TCP层实际代理localhost:7077及浏览器服务localhost:8192可达，但Jable/MissAV真实凭证resolver在只读核查中均因quarantined记录拒绝公共来源，按契约不回退匿名。需要新的、有效且已分类的clearance或对应用户个人凭证；不能启用未知旧Cookie来通过验收。来源范围/共享库/普通准入/自动GC四个开关继续false。

## 后续新凭证刷新

上述隔离状态是当时的阶段快照。后续已获授权获取并验证新的公共挑战凭证；两来源现为active/clearance版本2，生产范围工厂从库读取后真实重放与解析均通过。旧未知Cookie没有激活或覆盖，新恢复点及验证边界见[凭证刷新记录](source-credential-refresh-20261015.md)。本轮未切换运行配置或重启服务，真实worker/共享发布及挂载验收仍待完成。
