# 多用户与共享资源池切换手册

本文对应执行计划P8，描述已有命令和隔离证据。2026-10-15经授权已将确认的PostgreSQL目标从0036升级到0051；[执行记录](postgres-multi-user-migration-20261015.md)区分结构迁移与已确认的独立归属导入及已完成的推荐安全补导入及尚未开放的新模式。新结构当前叶节点为0051；普通准入与自动回收默认关闭。入口与身份协议见[准入架构](multi-user-admission-architecture.md)，资产与回退见[版本架构](resource-version-architecture.md)和[回收架构](resource-gc-architecture.md)。

## 当前证据与实例边界

- 已完成共享订阅、范围凭证、不可变版本、本人库/播放/历史、受控GC、管理与前端隔离；SQLite/PostgreSQL专项、真实HTTP双账号、Chrome/Firefox通过对应阶段门槛。
- 新增原生Redis/Celery solo验收：两份本人HTTP请求共用一个执行，分别测试无人取消、A取消、全部取消；实际临时文件发布、持有指针与取消投影一致，重复task ID不再发布。来源/图片由明确合成Gateway提供，未访问真实来源。Celery非eager，任务名及消息ID沿生产协议，但隔离app装配不等于部署进程验收。
- 管理员恢复演练：临时库模拟无可用应用管理员，CLI预览不写；apply建立审计、提升版本并撤销旧登录；同request UUID重试不再次撤销新登录。
- 真实来源账户、实际ProxyServer出口、部署UID/符号链接挂载和维护窗口尚未验收。此前豁免的HTTPS/真机项不重新作为阻塞；不能因此省略数据归属和资产安全。

2026-10-15只读工作区核查：默认工作树仍在dev，用户前端依赖改动保留。`django_backend/config/config.yaml`声明PostgreSQL；本地另有SQLite文件，最近迁移0031、741条资源，不能当作活动数据库或把它迁到0051充当部署完成。Docker列表仅看到Byparr，不证明没有宿主机API/worker。配置只读取引擎/路径等白名单，SQLite以mode=ro查看迁移和数量；未读取/输出Cookie、密码、密钥，未连接实际PostgreSQL。该快照可能变化，正式操作必须再次确认。

## 一、冻结目标与恢复点

记录目标代码提交、前端制品、数据库引擎/真实路径或库名、配置/环境来源、资源实际挂载路径和进程UID/GID。符号链接要记录最终目标，容器与宿主机视角都核对；不要仅备份链接本身。盘点API、scrape/download/playback worker、beat、恢复脚本等全部消费者，统一版本，禁止旧schema消费者混跑。

明确原操作者和遗留资产归属：旧资源导入仅授予指定原操作者，不能默认为公开。旧收藏/已观看/INI、推荐历史/反馈/黑名单同样不得复制给所有账号。未知Cookie保守隔离，不能因为能访问网站就认定它是公共clearance。

进入维护窗口停止新提交，通过持久任务控制协议处理活跃任务，确认实际写入者停止，再停止旧消费者。不要在线删除锁文件、清空.tasks、仅revoke任务或以租约过期作为停止证明。备份数据库、配置、资源真实目录、凭证keyring和版本一致的恢复点；记录恢复验证结果。已有备份命令`uv run python manage.py backup_database --days <保留天数>`会写备份并清理过期备份，不是只读预览，必须在确认活动配置与恢复点后使用。SQLite文件复制须在停止写入或一致性备份条件下；PostgreSQL使用匹配版本pg_dump，不套SQLite复制方式。

## 二、结构升级与显式归属

下列命令均从django_backend目录执行，先确保NASSAV_CONFIG_PATH/NASSAV_ENV_PATH及进程环境指向同一个已确认目标。不要为方便使用refactoring_test_settings操作实例。

```bash
uv run python manage.py showmigrations nassav
uv run python manage.py migrate --plan
# 确认目标、备份和写入者停止后执行
uv run python manage.py migrate
```

0037–0051包含持有、账号、加密凭证、共享工作、版本/目录、历史快照和GC账本。结构迁移不自动指定管理员、不把所有资源授予所有用户、不创建keyring、不激活旧Cookie。0048会回填既有观看历史的pool/展示快照，身份冲突会失败而不是丢弃；逆向遇到资源已回收的历史会拒绝。迁移执行和业务导入应分别记录结果。

以下使用已确认原操作者（示例nassav），预览输出逐项核对后才运行相应apply：

```bash
uv run python manage.py import_resource_library --username nassav
uv run python manage.py import_personal_data --username nassav
uv run python manage.py import_recommendation_data --username nassav
# 确认上面各项归属与冲突后，分别增加 --apply
```

个人设置需要导入旧INI时，personal命令显式增加`--settings-file <旧INI路径>`，不猜文件位置。推荐目标已有个人数据/活动任务时默认拒绝自动合并。确认保留当前个人AVID黑名单时，可显式增加--preserve-personal-blocklist；仅目标历史/种子和旧无owner AVID黑名单均为空、无目标活动job才可补导入。先预览、备份并核对规则，不使用SQL改owner绕过fence。

resource导入建立`legacy:operator:<id>`持有和目录投影，不移动媒体、不伪造manifest、不提升为public版本；旧文件沿原操作者兼容读取。后续明确选择来源/公共或个人范围执行刷新/下载，才产生有发布证据的新版本。未知旧资产会阻止整池GC，不能为了通过验收直接删除旧目录。

## 三、管理员与凭证

首管理员必须是配置中的启用原操作者。先预览，再使用一次生成并记录的UUID执行；响应未知时重试原UUID，不能新建意图。

```bash
uv run python manage.py bootstrap_app_admin --username nassav
uv run python manage.py bootstrap_app_admin --username nassav --apply --request-id <UUID>
```

已有可用应用管理员时拒绝另一次bootstrap；不要通过Django staff/superuser或直接SQL临时提权。多用户模式内置/admin/关闭；日常创建、角色、配额、密码和会话撤销使用应用管理中心。恢复时若配置原操作者不存在/已停用，现有命令会拒绝，需要另行维护决策，不能绕过校验。

在所有消费者可读的受控位置创建专用keyring，父目录事先具备合适权限；不覆盖旧文件，不打印内容：

```bash
uv run python manage.py create_source_credential_keyring --output <绝对keyring路径> --key-id k1
```

将NASSAV_SOURCE_CREDENTIAL_KEYRING_FILE配置到同一挂载文件，并安全备份。不要在日志、Git、浏览器存储中保存密钥。已有keyring不重建；轮换遵循[凭证架构](source-credential-architecture.md)，旧key仍被密文引用时不能移除。

```bash
uv run python manage.py import_source_credentials --actor-id <应用管理员ID>
# 分类、keyring与原始数据确认后可增加 --apply
```

导入保留原Cookie，合法clearance可加密为system；未知/账号Cookie加密隔离，不激活。管理中心只盲写明确分类的system clearance及匹配UA；个人账号Cookie由对应用户盲写自己的凭证，不能共享给所有用户。来源工厂按公共/个人范围决定凭证，未配置/失效不回退另一用户或旧全局Cookie。

## 四、分步启用与验收

第一步在统一新版消费者上设置范围凭证和共享库true，普通准入及GC仍false：

```dotenv
NASSAV_SCOPED_SOURCE_CREDENTIALS=true
NASSAV_SOURCE_CREDENTIAL_KEYRING_FILE=<所有消费者一致的绝对路径>
NASSAV_SHARED_LIBRARY_ENABLED=true
NASSAV_MULTI_USER_ENABLED=false
NASSAV_RESOURCE_GC_ENABLED=false
```

确认原操作者能查看自己的遗留持有/版本、个人状态、下载视频和历史。核对导入前后数量/文件，不把版本为空误判为导入失败或主动删除。验证实际worker由broker获取ID，来源与浏览器通过ProxyServer抽象和全局Proxy.url，下载媒体沿独立下载代理策略；容量/凭证/会话范围不因并发串用。记录来源、范围、是否真实上游、耗时、失败码和脱敏request ID，不记录签名流地址/请求头。

第二步先在目标的受控测试副本/窗口启用MULTI_USER_ENABLED，创建两个明确测试账号及同用户第二登录，重做以下实际进程验收。后端严格检查该开关依赖前两项，不能单独打开：

| 目标场景                  | 通过条件                                                                                |
| ------------------------- | --------------------------------------------------------------------------------------- |
| 公共相同添加              | 两个本人请求、一份兼容工作、实际来源/图片/版本发布后各自持有；重试不重复扣配额          |
| 私人来源/不同Cookie       | 不共用私人执行/缓存/签名URL，管理员也不能读另一人私人媒体                               |
| 独立取消与全部取消        | A取消不停止B仍需要的工作；全部取消后确认writer停止、清理独立收尾，无迟到发布            |
| 暂停/恢复、重启/重复消息  | 新attempt/generation；旧执行不覆盖，broker断线恢复后不重复发布                          |
| Cookie更新/撤销与账号停用 | 旧来源上下文、登录/WS/媒体授权拒绝；其他用户工作保留                                    |
| 版本更新、播放与回收竞争  | 固定旧读取可完成，新授权受限；active/pending持有、pin、writer和旧资产阻止误删           |
| 挂载权限/故障恢复         | 真实UID、符号链接最终路径下写入/发布/回滚/删除受控；EPERM保留可审计日志，不递归放宽权限 |
| 管理员恢复                | 临时副本预览不写；apply恢复审计与版本，原UUID重试不再次撤销新会话                       |

前端跨Cookie请求携带当前上下文，409仅重查不重放；测试本人JSON、封面/头像、Range、备注、设置、推荐/搜索、任务/WS和keepalive，不只点登录页。两账号并发不能由同一账号两登录代替。

第三步才开放真实普通账号，观察权限拒绝、任务去重、配额、上下文冲突和代理容量。不要在开启当次同时启用GC，便于定位与回退。

## 五、GC单独放行与恢复

先保持执行false，用管理中心预览或CLI：

```bash
uv run python manage.py resource_gc --action preview --target <pool-UUID>
```

核对持有、宽限、版本、读lease/播放、未停止writer、promoting/补偿日志和retained原因。只读预览通过不保证之后一定可删，worker每次重核。旧未映射文件/未知缺失/marker或hash变化必须保留现场，不能手工清日志通过。

目标权限与故障门槛通过后才设NASSAV_RESOURCE_GC_ENABLED=true，先用无共享依赖的受控样本登记并检查完成状态、真实文件及历史留存。调度有界、失败同job重试；管理动作携带actor/reason/对象版本/request UUID。GC批次/宽限沿配置契约与账本规则，不在线删稳定flock文件。

若发现问题，先停止新普通入口/新提交与GC派发，处理正在写入的执行，保持当前代码维护；关闭开关不恢复旧资产布局或权限。保存新关系、凭证、工作、版本/历史/GC账本及匹配文件恢复点，再决定前向修复或整体恢复。不可直接检出旧镜像运行；逆向迁移有保护条件，已删视频不能靠DB回退恢复。

## 六、尚需操作者确认

目标PostgreSQL迁移已获授权并完成，私有恢复点与原数据核对见执行记录。归属/admin已另获确认，693份持有、管理员及两份Cookie加密隔离已落地；随后使用显式安全选项完成7批历史/25种子补导入，保留352条个人黑名单。

后续获授权获取新凭证：Jable/MissAV均通过真实公共页面、全局代理重放及生产范围工厂复验，并沿管理员CAS协议替换为active/clearance版本2，见[凭证刷新记录](source-credential-refresh-20261015.md)。随后另获授权完成[统一服务切换](source-service-cutover-20261015.md)：范围凭证/共享库开启，API与三个worker统一配置并优雅重启，真实HTTP本人库/来源元信息和持久配置下的来源重放通过；普通准入/GC仍关闭。真实共享任务发布、私人账户及挂载故障门槛继续待验，不能以broker ping替代。
