# 共享资源池与用户持有（P1）

P1新增0037、内部持有核心和显式旧资源导入；当前HTTP、播放、worker与前端尚未切换到共享池，仍只允许operator。P2权限、P4订阅、P5版本、P6回收未完成前，不开放普通用户，不把本阶段视为生产共享库。设计约束见[P0契约](multi-user-contracts.md)。

## 状态所有者与接口

| 模块                                 | 职责                                                                |
| ------------------------------------ | ------------------------------------------------------------------- |
| library_models                       | ResourcePoolEntry共享规范身份与生命周期；UserLibraryEntry按用户持有 |
| library_membership                   | 无ORM的输入/用例契约；消费显式MembershipRecords，不调度或删除文件   |
| library_records                      | user→pool→membership短事务，唯一性、版本冲突、最后释放标记          |
| library_import                       | 已有AVResource归属预览/原子回填；不抓取、不移动文件、不修改个人状态 |
| composition.build_library_membership | 唯一生产默认装配入口；HTTP不直接拼装Adapter                         |

`attach(user_id, avid, source=..., access_scope=...)`仅供内部受信任调用，范围必须由未来resolver提供，不接受客户端自行宣称public。规范化复用task_control_rules；同用户同规格重复调用复用关系，不改版本，不抢占其他规格。新关系始终pending，不因发现文件/旧资源就提升active。P4之前调用方负责对应需求有效性与失败释放，不对外暴露长期无人处理的pending写入口。

`release(user_id, entry_id, expected_version=...)`绑定用户与关系UUID，跨用户/不存在抛LibraryNotFound，版本不匹配抛LibraryConflict并只给本人的快照。移出清除自己的稍后再看、递增其个人版本，保留其他个人字段、其他人状态和正式资源。关系删除后的重复release是not found，重建关系用新UUID；它不是P4持久命令幂等API，不能宣称可重复退配额或取消任务。

pending/active都计入保护。最后释放只标记pending_gc与默认24小时候选期限；没有GC调度器，也没有新配置开关。再次attach撤销期限并提升池lifetime_generation/version，防止将来旧回收claim继续提交。deleting/cleanup_failed拒绝复活；该错误目前由内部异常表达，正式HTTP重试字段在P2/P4接入。暂停任务、读者与资产日志仍须P6再次检查，不能只看持有数删除。

## 模型与删除边界

0037新增`nassav_resource_pool_entry`和`nassav_user_library_entry`。池规范AVID唯一，正式资源引用可空且一对一；持有unique(user,pool)。DB检查合法状态、正整数版本/代次，以及pending_gc的期限必须存在而其他状态为空；按GC状态/期限和用户状态/创建时间建索引。

持有对user和pool使用PROTECT，防止直接删除用户/池而跳过撤销需求与占用。AVResource被现有operator兼容路径删除时池引用SET_NULL；本阶段没有同步改造旧发布/删除消费者，不能仅凭残留active关系认定资源可读。P2授权须要求正式产物存在且范围匹配，P5/P6再接入版本发布和回收协议。

## 旧资源导入

结构迁移不自动创建池/持有，不猜测所有者。维护窗口备份数据库与媒体并停止资源写者，应用0037后执行：

```bash
uv run python manage.py import_resource_library --username <配置中的原操作者>
uv run python manage.py import_resource_library --username <配置中的原操作者> --apply
```

第一条只读预览；第二条才在单事务写入。账号须明确匹配当前operator且启用。预览/apply拒绝规范化身份冲突、异常AVID、已有池引用或生命周期冲突。apply重新检查，任一冲突回滚整批；按规范身份排序锁池，保留已编辑关系与版本。导入关系初始active，访问范围标记`legacy:operator:{user_id}`，不能假定原Cookie/媒体为公共产物。后续凭证阶段需显式分类，不能复制给全部用户。

再次导入只补缺失关系，因此用户手动移出后再运行apply会重新持有；这不是持续同步命令。没有改旧文件路径、资源字段、收藏/观看/备注/进度、Cookie或抓取缓存。本轮只在隔离测试中运行，不对用户现有数据库执行归属apply。

## 迁移回退及验收

0037是加性结构迁移，可回退至0036再升级；回退会删除**新增的池/持有数据**，不会把它们映射回旧共享资源。升级/回退前分别备份新关系和原库，停止新消费者；原资源及个人关系保持，重建持有需再次显式导入。不能通过回退数据库恢复已删除文件。

专项测试覆盖两用户/同用户同时添加、唯一关系、最后释放对新添加、pending保护、旧关系UUID/版本拒绝、删除保护、失败池不能复活、只清本人稍后再看、只读预览、重复导入/整批冲突回滚，以及0036→0037→0036→0037的旧资源/演员/个人状态保持。独立PostgreSQL测试库只使用受限Unix socket，不连接部署服务；隔离验收不代表正式实例升级。

## 执行记录

基线8139061；独立分支`feat/resource-pool-membership`；阶段提交标题`[Feat] Add shared resource pool membership foundation`。SQLite/Pg专项命令为`uv run pytest tests/test_library_membership.py tests/test_library_migration.py --ds=<隔离设置> -v`，SQLite隔离设置为django_project.refactoring_test_settings，PostgreSQL临时设置基于相同无凭证配置仅覆盖一次性socket数据库；各12项通过，退出码0。完整SQLite门槛`uv run pytest tests/ --ds=django_project.refactoring_test_settings -v`：1019 passed、28在线项目skipped，退出码0；`makemigrations --check --dry-run`：No changes detected，退出码0。根`pre-commit run -a`修正格式和动态关联类型注解后重跑；完整门槛通过才提交合并idle。钩子配置未改，已有实例/正式worker/媒体未迁移或联调。

## 当前本人持有管理（P7）

上文P1描述的是基础阶段接口；当前已接入的命令/版本/回收进度见[执行计划](multi-user-shared-pool-plan.md)。`library_catalog.held_entries`仍只投影可读取产物；不能为管理不可用持有而放宽其过滤，避免标题、封面、个人字段或筛选侧信道泄露。

`list_memberships`是独立只读管理投影，按user_id查询原UserLibraryEntry，包含pending和不可用池，但仅返回编号、关系UUID/version、粗粒度池可用性与时间。搜索仅匹配编号；可用标记不授予媒体权限。HTTP受共享模式/操作者/管理账号准入保护，普通多账号仍关闭。释放沿现有持久命令/配额/GC协议，前端冻结确认时的关系证据；旧确认不能自动移出重新添加的新UUID。无新表或schema迁移。
