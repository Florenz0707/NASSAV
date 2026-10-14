# 个人资源状态与通用设置

## 边界与状态所有者

第二阶段建立用户私有收藏、已观看、备注和六项通用界面设置，不包含评分。资源、图片、视频、抓取缓存和服务器配置仍共享；播放进度独立，播放结束不自动标记已观看。现有单操作者登录限制保留，开放多账号须完成[多用户规划](multi-user-roadmap.md)中的完整权限矩阵。

`UserResourceState` 以 `(user, resource)` 唯一保存 `is_favorite`、`watched`、`notes`、`version` 和更新时间；未建立行表示 false/false/空备注，版本0。删除正式资源级联删除其个人状态，删除用户级联删除其状态及设置。播放进度的AVID账本仍沿用原有删除语义。

`UserPreferences` 以user一对一保存JSON配置对象 `preferences`，以及 `created_at`、`updated_at`；头像开关、标题字段、字体、主题、搜索展示样式和默认外部搜索来源均为对象中的覆盖值。原有六项值保持字符串接口，第三阶段另增加推荐与播放偏好键。读取缺省值不创建数据库行，不读取INI、不使用进程缓存；部分更新在短事务中串行化，避免并发保存互相覆盖。代理、Cookie、来源开关、缓存TTL等服务器配置不属于用户设置。

个人资源写入由 `personal_state` 管理；读取投影由相关子查询批量附到共享资源查询，避免逐卡查询。`personal_preferences` 管理数据库设置。HTTP必须以 `request.user.pk` 选择状态，不采信请求中的user；worker共享资源事件不能携带他人的个人备注。个人状态提交可携带 `expected_version`，冲突返回当前状态供用户确认。

## 0033迁移与旧数据导入

0033只新增两张全小写下划线表，不猜测旧数据归属。原AVResource的收藏/已观看列保留为旧版本回退及一次性导入来源，新运行链路不应继续写入这些列。

在维护窗口备份数据库和旧 `config/user_settings.ini`，停止旧版本写入者，使用统一版本完成迁移，然后为已确认的原操作者导入：

```bash
cd django_backend
uv run python manage.py migrate
uv run python manage.py import_personal_data --username nassav --settings-file config/user_settings.ini
uv run python manage.py import_personal_data --username nassav --settings-file config/user_settings.ini --apply
```

Compose维护窗口使用相同数据库模式的一次性新版容器；不要启动旧worker。以下示例为SQLite，PostgreSQL须改为 `--mode postgres`，先只预览，再重复同一命令加 `--apply`：

```bash
python3 scripts/compose_stack.py --mode sqlite run --rm --no-deps api python manage.py import_personal_data --username nassav --settings-file /app/config/user_settings.ini
```

`--username` 必须匹配 `NASSAV_OPERATOR_USERNAME`，账号必须存在且有效。首条命令仅预览；不存在旧INI时省略 `--settings-file`，仅迁入旧资源标记。显式传入文件无法读取、解析或取值非法时整次导入失败，源文件只读且不会补值或写回。已存在的个人状态和设置保留；0034移除导入时间记录，命令仅创建缺失记录。既有行重复执行不覆盖已编辑的值，取消的收藏/观看保留false行。若人工删除个人记录，重跑导入可能重新创建旧值；不再宣称具有全局一次性导入标记。既有设置行存在时保留整组值，不推断哪些字段尚未编辑。

完成导入后INI不再是运行状态；无须挂载可写用户设置文件。尚未导入的原操作者会看到默认设置和空的个人标记，应在对外启动前完成导入。不要通过给所有账号复制旧标记来“兼容”。

逆向迁移删除新表及其个人状态，不恢复第二阶段后新增/修改的收藏、备注、设置；旧共享标记列保持原快照。回退前单独备份新表，并停止新消费者；不要混跑新旧状态所有者。

## 分阶段实施

数据库阶段已提供模型、投影、写入服务和显式导入命令（29d8c37），隔离SQLite完整951通过/28跳过，临时PostgreSQL5通过，pre-commit完整通过。接口阶段4c29b9b将列表/详情及状态更新绑定request.user，通用设置改为数据库，并移除运行时INI管理器；完整SQLite956通过/28在线测试跳过，临时PostgreSQL56通过，pre-commit完整通过。前端阶段已接入详情页个人状态与备注编辑，最终验证记录见下方。隔离测试覆盖用户归属、部分修改、冲突、并发创建、只读导入、幂等、级联及升级/回退/再次升级。真实部署迁移由操作者按维护窗口执行。

第三阶段已将推荐上下文、历史、反馈和黑名单按当前用户隔离，收藏/观看加权读取任务创建者个人状态；不读取旧共享标记或汇总其他用户。旧推荐数据显式导入与0035见[推荐架构](recommendation-architecture.md#用户归属第三阶段)。

## 前端职责与维护

详情页装配 `PersonalResourcePanel`，它独占editor，通过作用域插槽装配图标状态按钮，备注以页面全宽文本展示，编辑弹窗使用公共AppButton/AppInput并发出updated快照。`personalResourceEditor`独占备注草稿、保存忙碌状态、错误和版本；切换资源、用户、登出及卸载使旧请求失效。跨页面冲突保留草稿，接收当前服务端版本后必须由用户再次点击保存；清空先修改草稿，保存后才清除数据库备注。备注只作为文本显示，不插入HTML；草稿不写入浏览器持久存储。

settings store读取和保存仍经已有setting接口；App在会话身份变化时reset，清空偏好和资源列表中的个人标记，使旧load/save响应失效。页面临时预览仍需点击“保存设置”，后端真值为UserPreferences，不以本地storage或进程对象作为长期状态。

评分和开放多账号登录仍未实现；观看历史与稍后观看见[个人观看列表](viewing-architecture.md)；推荐用户化、播放偏好及跨设备接续已在第三/第四阶段实现，共享资产仍沿用操作者权限。正式升级依次应用0033–0035并运行适用的显式旧数据导入，不混跑旧INI/AVResource标记或全局推荐写入者。

## 本轮验证与发布边界

2026-10-13，存储阶段29d8c37、接口阶段4c29b9b已按门槛合并idle，界面与文档阶段使用feat/personal-state-ui独立分支。以下命令保留退出码：

- `cd django_backend && uv run pytest tests/ --ds=django_project.refactoring_test_settings -v`：最终956通过、28在线测试跳过。契约快照对备注/版本说明做显式断言，未重建旧快照。
- 临时PostgreSQL16运行个人状态、0033升级/回退/再次升级、HTTP/设置和搜索默认值：56通过；数据库只监听本轮Unix socket，与正式数据库独立。
- `cd vue_frontend && pnpm run check`：100项单元测试通过，lint及生产构建通过。
- `tests/browser/personalState.cjs`：Chrome和Firefox连接隔离Django/SQLite、临时用户与资源，验证键盘保存、备注清空/刷新/跨页面冲突、收藏和观看筛选、设置页手动保存与刷新、深浅主题及390px布局；无真实来源抓取，WebSocket隔离。原settings浏览器契约回归通过。
- 根目录 `pre-commit run -a`：完整通过，不修改钩子配置。

本轮未执行正式0033迁移、旧数据导入、Docker重建或多账号权限开放；部署操作者须按前文执行并核对实例归属。SQLite/PostgreSQL及浏览器结果不替代正式环境升级验收。

## JSON设置与0034（当前实现）

0033保持历史内容不变；0034增加JSONField（PostgreSQL为jsonb，SQLite使用其JSON支持），将既有六项列值逐项原样搬入JSON后删除这些列和legacy_imported_at，并增加created_at。迁移本身搬运当前数据库已有的个人设置，不读取INI，也不猜测旧共享标记的用户归属。id/user和updated_at保持；旧表无创建时间，旧行created_at为0034执行时间，不能当作原始创建时间。新行created_at是首次保存/显式设置导入的创建时间。

`preference_definitions.PREFERENCE_DEFINITIONS` 是当前键、默认值、类型、枚举和长度的唯一规则入口；业务只能通过personal_preferences读取有效配置，不直接消费原始JSON。API字段自动派生自定义表，不复制另一套默认值与校验。原有六项保留字符串格式（包括true/false），后续新增项按定义严格校验类型。

| 操作/情况                      | 当前行为                                                                 |
| ------------------------------ | ------------------------------------------------------------------------ |
| GET，无记录                    | 返回全部当前默认值，不建行                                               |
| GET，缺少键                    | 用该键当前默认值补齐响应，不补写JSON，不改时间                           |
| GET，存储值非法或根非对象      | 有效项仍使用覆盖值，非法项回退默认值；根非法则全部默认值，不写回         |
| GET，废弃或未知键              | 不读取、不返回，不影响业务；原JSON可保留残留直到数据迁移清理             |
| PUT，部分配置                  | 先全量校验提交对象，再锁用户、读取最新JSON并合并指定键，返回完整有效配置 |
| PUT，空对象或已存值相同        | 空对象不建行；已有值完全相同不更新updated_at                             |
| PUT，显式提交当前默认值        | 作为用户覆盖值保存；不同于缺失键跟随未来默认值                           |
| PUT，未知/删除键、非法值或类型 | 400且整次不写入；null不是重置协议                                        |

新增配置通常只增加定义及需要的界面/业务消费者，存量JSON缺少键会立即使用默认值，不要求表迁移。缺失项跟随默认值变化，已有覆盖值保持用户选择。前端保存仅提交相对最近加载/成功保存值发生变化的字段，避免将GET补齐的默认值全部固化；失败保留差异，登出/身份改变或迟到响应不得改写保存基线。

删除键从当前定义和消费者中移除，GET立即屏蔽、PUT拒绝；通过新增数据迁移清理残留。改名必须用明确的数据迁移将旧值搬到新键，新旧同时存在时保留新值，然后删除旧键；只改定义并不会自动把旧值认作新配置。当前未添加别名，所有现有键名保持；若未来确需兼容旧客户端，显式限定兼容期、仅存新键、拒绝同时提交新旧键，期满拒绝旧键。不在每次PUT清除未知键，避免旧代码删除未来版本的数据，但这不授权混跑不同数据库结构版本。

0034回退会重建旧六列，并从JSON恢复能由旧列表示的值，缺失键使用冻结的历史默认值；无法表示的类型或过长值使用历史默认值，未来新增键丢失。created_at被删除，legacy_imported_at恢复为空（旧导入时间不可恢复），个人资源状态表不受影响。回退前备份JSON数据，在维护窗口停止写入并统一消费者版本。

INI导入只在提供有效设置值且UserPreferences行缺失时创建JSON行；已存在的整组设置保持，不通过缺失键补入旧INI值。仅导入旧资源标记或空配置时不创建设置行。

### JSON改造验证记录

2026-10-13，基线92bb752（dev已合入idle），实现提交6053401，独立分支feat/user-preferences-json，门槛通过后已合并idle。完整隔离后端命令 `uv run pytest tests/ --ds=django_project.refactoring_test_settings -v` 为976通过、28在线测试跳过；临时PostgreSQL16的JSON/个人状态/接口/0033–0034升级回退再次升级共45通过；`pnpm run check` 为103项通过、lint和生产构建通过；完整 `pre-commit run -a` 通过，`makemigrations --check --dry-run` 无差异。类型测试另覆盖JSON中False与0、0.0与0的区别，同值判断不能跳过非法旧类型修复。

Chrome/Firefox通过现有personalState隔离Django/SQLite API套件，设置页手动保存和刷新持久化正常；原settings浏览器交互及提交字段断言通过。WebSocket隔离，无真实来源/worker/正式数据库联调。未执行正式0034迁移、旧INI导入或Docker重建；回退无法保存未来JSON键、created_at及原导入时间，部署前需备份和停止旧消费者。

个人中心UI集中观看列表、通用/播放设置和退出，不改后端状态所有者/接口/数据库。备注编辑弹窗的关闭、Escape及路由离开先提示未保存修改，原生标签页离开提示由浏览器决定；失败/冲突仍保留草稿。详情备注展示仅使用保存过的文本，清空后须保存，不提前伪装成功。
