# 个人资源状态与通用设置

## 边界与状态所有者

第二阶段建立用户私有收藏、已观看、备注和六项通用界面设置，不包含评分。资源、图片、视频、抓取缓存和服务器配置仍共享；播放进度独立，播放结束不自动标记已观看。现有单操作者登录限制保留，开放多账号须完成[多用户规划](multi-user-roadmap.md)中的权限与推荐隔离。

`UserResourceState` 以 `(user, resource)` 唯一保存 `is_favorite`、`watched`、`notes`、`version` 和更新时间；未建立行表示 false/false/空备注，版本0。删除正式资源级联删除其个人状态，删除用户级联删除其状态及设置。播放进度的AVID账本仍沿用原有删除语义。

`UserPreferences` 以user一对一保存头像开关、标题字段、字体、主题、搜索展示样式和默认外部搜索来源。读取缺省值不创建数据库行，不读取INI、不使用进程缓存；部分更新在短事务中串行化，避免并发保存互相覆盖。代理、Cookie、来源开关、缓存TTL等服务器配置不属于用户设置。

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

`--username` 必须匹配 `NASSAV_OPERATOR_USERNAME`，账号必须存在且有效。首条命令仅预览；不存在旧INI时省略 `--settings-file`，仅迁入旧资源标记。显式传入文件无法读取、解析或取值非法时整次导入失败，源文件只读且不会补值或写回。已存在的个人状态和设置保留，导入时间持久记录，再次执行不会覆盖用户修改或复活取消的收藏。既有设置行存在时保留整组值，不推断哪些字段尚未编辑。

完成导入后INI不再是运行状态；无须挂载可写用户设置文件。尚未导入的原操作者会看到默认设置和空的个人标记，应在对外启动前完成导入。不要通过给所有账号复制旧标记来“兼容”。

逆向迁移删除新表及其个人状态，不恢复第二阶段后新增/修改的收藏、备注、设置；旧共享标记列保持原快照。回退前单独备份新表，并停止新消费者；不要混跑新旧状态所有者。

## 分阶段实施

数据库阶段已提供模型、投影、写入服务和显式导入命令（29d8c37），隔离SQLite完整951通过/28跳过，临时PostgreSQL5通过，pre-commit完整通过。接口阶段4c29b9b将列表/详情及状态更新绑定request.user，通用设置改为数据库，并移除运行时INI管理器；完整SQLite956通过/28在线测试跳过，临时PostgreSQL56通过，pre-commit完整通过。前端阶段已接入详情页个人状态与备注编辑，最终验证记录见下方。隔离测试覆盖用户归属、部分修改、冲突、并发创建、只读导入、幂等、级联及升级/回退/再次升级。真实部署迁移由操作者按维护窗口执行。

现有推荐尚未多用户化，但收藏/观看加权只读取配置中的原操作者个人状态，不再读取旧共享标记，也不汇总其他用户的私有行为。推荐历史、反馈和黑名单仍按原架构维护，后续第三阶段完成整体归属。

## 前端职责与维护

详情页只装配 `PersonalResourcePanel`，组件使用公共AppButton/AppInput并发出updated快照。`personalResourceEditor`独占备注草稿、保存忙碌状态、错误和版本；切换资源、用户、登出及卸载使旧请求失效。跨页面冲突保留草稿，接收当前服务端版本后必须由用户再次点击保存；清空先修改草稿，保存后才清除数据库备注。备注只作为文本显示，不插入HTML；草稿不写入浏览器持久存储。

settings store读取和保存仍经已有setting接口；App在会话身份变化时reset，清空偏好和资源列表中的个人标记，使旧load/save响应失效。页面临时预览仍需点击“保存设置”，后端真值为UserPreferences，不以本地storage或进程对象作为长期状态。

评分、观看历史、推荐历史/反馈/黑名单用户化及开放多账号登录不属于本次范围；共享资产控制仍沿用操作者权限。正式升级须先0033再运行显式旧数据导入，不混跑旧INI/AVResource标记写入者。

## 本轮验证与发布边界

2026-10-13，存储阶段29d8c37、接口阶段4c29b9b已按门槛合并idle，界面与文档阶段使用feat/personal-state-ui独立分支。以下命令保留退出码：

- `cd django_backend && uv run pytest tests/ --ds=django_project.refactoring_test_settings -v`：最终956通过、28在线测试跳过。契约快照对备注/版本说明做显式断言，未重建旧快照。
- 临时PostgreSQL16运行个人状态、0033升级/回退/再次升级、HTTP/设置和搜索默认值：56通过；数据库只监听本轮Unix socket，与正式数据库独立。
- `cd vue_frontend && pnpm run check`：100项单元测试通过，lint及生产构建通过。
- `tests/browser/personalState.cjs`：Chrome和Firefox连接隔离Django/SQLite、临时用户与资源，验证键盘保存、备注清空/刷新/跨页面冲突、收藏和观看筛选、设置页手动保存与刷新、深浅主题及390px布局；无真实来源抓取，WebSocket隔离。原settings浏览器契约回归通过。
- 根目录 `pre-commit run -a`：完整通过，不修改钩子配置。

本轮未执行正式0033迁移、旧数据导入、Docker重建或多账号权限开放；部署操作者须按前文执行并核对实例归属。SQLite/PostgreSQL及浏览器结果不替代正式环境升级验收。
