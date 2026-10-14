# v2.5.1 升级与发布检查

准备日期：2026-10-14。版本字段统一为2.5.1，变更日志见[CHANGES.md](../../CHANGES.md)。范围为`3f6e019..3cbac1f`，包含用户手工调整和已合并阶段；本轮仅准备文档与制品版本，不表示已打tag、远端发布、正式迁移或部署。

## 功能与准入

个人收藏/已观看/备注/稍后再看、JSON通用/推荐/播放设置、推荐归属、显式跨设备接续、去重观看历史和个人中心已实现。评分、注册、角色/配额及多账号业务准入尚未开放，仍要求配置指定的启用operator。资源、图片/视频、抓取事实、代理容量和服务器配置保持共享；实际播放不自动标记已观看或移出稍后再看。

推荐继续经Celery scrape队列执行，来源与浏览器共用Proxy.url/ProxyServer。前端、API、全部worker、唯一Beat和Nginx须统一版本，不能仅部署个人中心或混跑旧共享标记/INI消费者。

## 迁移与已有数据

从v2.5.0的0032升至0036，更早版本先按[v2.5.0历史指南](release-2.5.0.md)核对0027–0032，尤其0028改表名。

| 迁移 | 当前数据变化                                                                                                            | 回退影响                                                            |
| ---- | ----------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| 0033 | 新建个人状态和偏好表，保留AVResource旧标记，不自动推断归属                                                              | 删除新表及个人状态/配置，旧共享快照不反映新编辑                     |
| 0034 | 将已有六项个人设置列原样搬入JSON；移除旧列/legacy_imported_at，增加created_at并保留updated_at                           | 恢复能由旧列表示的值，新增JSON键/created_at丢失，旧导入时间不可恢复 |
| 0035 | 推荐state/snapshot/种子/资源黑名单增加owner，条目/反馈沿snapshot归属；取消旧queued/running推荐job，保留NULL owner旧数据 | 跨用户重复黑名单/种子身份会拒绝回退；新增用户state丢失，旧job不复活 |
| 0036 | 新建空观看历史表，个人状态加入稍后再看，播放会话加入历史sequence/时间                                                   | 观看历史及稍后再看字段丢失，旧收藏/备注/进度保持                    |

0034搬运的是**数据库已有个人设置**，不会读INI。原操作者的旧共享标记/INI和共享推荐数据均需显式导入，未导入时默认个人状态/不可见旧推荐不表示旧数据被删除。0036不从旧进度或watched推测历史。JSON缺失键只读补默认，不建行；PUT只合并明确变更项，废弃键拒绝，删除/改名由显式数据迁移处理。

## 维护窗口与导入顺序

1. 核对数据库引擎/schema、数据目录模式、账号、配置与镜像，记录showmigrations。备份数据库、配置和旧INI，保存旧制品；不把隔离测试或历史实例记录当实时状态。
2. 关闭新任务/播放/推荐入口，停止API、全部worker、Beat等写入者，按[任务部署协议](compose-deployment.md#持久任务控制版本切换与回滚)确认执行器退出及会话收尾。不得在线删锁、清空.tasks或用revoke代替协议。
3. 使用新版与原数据库模式migrate至0036并核对叶节点。详细归属见[个人状态](personal-state-architecture.md)、[推荐](recommendation-architecture.md#用户归属第三阶段)、[观看列表](viewing-architecture.md)。
4. 在开放个人推荐和用户编辑前，为确认的原操作者预览并执行适用的旧数据导入。账号须存在、启用且匹配NASSAV_OPERATOR_USERNAME；示例nassav不是默认密码。
5. 统一重建/启动API、三个worker、唯一Beat及前端/Nginx；Compose migrate服务成功后再启业务入口。已到0036的开发实例按实际状态确认，不重复重建/导入数据库。
6. 做目标环境验收，记录服务版本、迁移/导入数量，再开放入口；前端硬刷新以清理旧包。保持现有播放开关、媒体域名和代理可信条件。

本机维护窗口示例，执行前确认配置指向目标数据库：

```bash
cd django_backend
uv run python manage.py showmigrations nassav
uv run python manage.py migrate --plan
uv run python manage.py migrate
uv run python manage.py showmigrations nassav
uv run python manage.py import_personal_data --username nassav --settings-file config/user_settings.ini
uv run python manage.py import_recommendation_data --username nassav
# 确认预览、归属和备份后，分别执行适用导入
uv run python manage.py import_personal_data --username nassav --settings-file config/user_settings.ini --apply
uv run python manage.py import_recommendation_data --username nassav --apply
```

旧INI不存在时省略--settings-file，仅导入旧资源标记；显式文件无效会拒绝导入，源文件保持只读。已有个人状态/设置行不覆盖，也不借旧INI补缺失JSON键；人工删行后再次导入可能重建旧值。推荐导入遇到目标已有个人推荐数据或活动job时拒绝自动合并，无旧行时重复执行为零操作。已用中间版本的实例先核对既有个人数据，不为套用示例而清空。

Compose从仓库根目录使用相同模式的新版一次性API容器；以下为SQLite，PostgreSQL改--mode postgres并保留原secret/数据库配置。默认预览，确认后在同命令末尾加--apply；不要以宿主机默认SQLite代替容器数据库：

```bash
python3 scripts/compose_stack.py --mode sqlite run --rm --no-deps api python manage.py import_personal_data --username nassav --settings-file /app/config/user_settings.ini
python3 scripts/compose_stack.py --mode sqlite run --rm --no-deps api python manage.py import_recommendation_data --username nassav
```

迁移容器和消费者切换使用[现有Compose入口](compose-deployment.md)。新安装正常migrate并创建操作者即可，不需要伪造旧数据导入；已有账号密码保持。

## 目标环境验收与回退

验收包括登录/CSRF、个人标记/备注版本冲突、设置分区保存及刷新、推荐归属/异步worker、历史去重/重看置顶、单条/批量删除、移出已观看、双设备显式接续/旧writer只读，以及任务控制/资产清理回归。核对旧标记/INI/推荐关系归属原操作者；导入不应修改原站缓存、图片或视频。

优先前向修复。必须回退时关闭入口、停止新消费者并备份个人数据，用当前新代码逆向迁移至旧消费者对应叶节点，再换旧镜像/前端；回v2.5.0通常目标0032，须核对实际迁移图。0035重复身份拒绝回退时先备份并明确处理，不能自动丢个人数据绕过。回退不将新个人标记写回旧AVResource列，也不自动写回INI；数据库/文件/配置恢复须一致，来源签名地址时效不会因回退恢复。

## 已有证据与本轮检查

实现阶段最后完整后端隔离门槛为1007通过/28在线跳过（个人中心列表管理阶段）。0033–0036的SQLite/PostgreSQL升级、回退、再次升级及数据保持分别见个人状态、多用户路线与观看列表文档；专项数量不合并为一次全量PostgreSQL运行。

前端125单元测试、lint/build及完整pre-commit通过。Chrome/Firefox使用临时真实Django/SQLite/Redis/合成MP4验证个人状态、设置、观看列表和双登录接续；推荐偏好/黑名单及最新布局另用模拟API验证，不等于真实外站worker或正式部署。音量位移已复现并修复；导航位移在覆盖式滚动条环境未复现，已固定列宽/滚动条占位并通过四种视口全过程检查。

正式HTTPS/真机按要求跳过，长时播放未完成，Firefox历史真实来源间歇超时继续保留；v2.5.1不将这些限制记为通过。外部搜索任务句柄账号缓存键、blob回收及条件请求仍属[后续缓存计划](../../vue_frontend/doc/personal-cache-plan.md)，开放多账号前须补齐。

本轮只更新文档与版本，执行uv lock --check --offline、pnpm run check、版本/本地链接一致性检查及pre-commit run -a；不重跑全量后端、真实浏览器或正式升级。本轮检查及提交见Git历史，部署操作者另记实际环境验收。

发布准备验证（2026-10-14，分支chore/release-v2.5.1）：后端项目/锁文件及前端版本均为2.5.1；uv lock --check --offline通过，锁文件仅改变项目版本。pnpm run check含125通过/0失败、lint及构建；212个本地链接/锚点、0036迁移叶节点及v2.5.0以下历史变更日志保持检查通过。全量pre-commit通过后提交并合并idle；本轮未执行正式迁移、旧数据导入、部署或远端发布。
