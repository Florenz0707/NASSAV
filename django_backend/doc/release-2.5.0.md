# v2.5.0 升级与发布检查

准备日期：2026-10-13。版本字段统一为2.5.0；变更日志见[CHANGES.md](../../CHANGES.md)。本文件是发布准备及维护窗口指南，不表示远端发布、正式数据库迁移或容器升级已经执行。

## 范围与消费者

本次汇总2.4.5之后的实现，基线`e562185..9c0eb83`：持久原站/短期播放事实缓存和外部搜索缓存链路、表名规范化、来源HLS与已下载MP4播放、个人播放进度、任务添加状态与推荐/详情页面修复。多用户仅提供[规划](multi-user-roadmap.md)，仍要求指定启用operator账号。

API、全部Celery worker、唯一Beat及前端/Nginx必须统一版本、配置与数据目录。Redis共享容量、来源代理仍沿用Proxy.url；本地MP4不请求来源、不走代理、不派发准备worker。进度由数据库持久化，不进入共享资源watched或提供者缓存。

## 数据库升级范围

| 迁移 | 变化与注意事项                                                   |
| ---- | ---------------------------------------------------------------- |
| 0027 | 原站元数据与短期播放缓存独立表；删除正式资源保留事实缓存         |
| 0028 | 12个模型、14张物理表改为小写下划线；停止旧表名消费者，不混跑     |
| 0029 | 用户/当前登录拥有的短期播放会话                                  |
| 0030 | 会话刷新身份与代次，旧执行不能发布                               |
| 0031 | 本地播放模式，旧会话默认source                                   |
| 0032 | 个人进度表，唯一(user, avid, media_key)；资源/会话删除不级联进度 |

从2.4.5升级须应用0027–0032；已在中间版本的实例按实际showmigrations补齐。2026-10-08关于0027的只读记录是历史快照，不代表当前数据库。此轮未核查正式实例迁移状态，禁止按旧记录猜测或重复导入数据库。

## 发布前及维护窗口

1. 确认当前数据库引擎、数据库/schema、数据目录模式和运行镜像版本；记录`showmigrations nassav`，保存当前镜像/代码与配置以便回退。不以修改DB_ENGINE进行引擎迁移。
2. 备份数据库和配置，确认正式资源目录可恢复；备份方式与恢复限制见[数据库](database.md)。数据库备份包含个人进度；回退迁移会删表，备份不能省略。
3. 确认本次制品版本与质量门槛，完成下方检查。已有operator保留账号与密码；新安装才运行createsuperuser，默认用户名nassav不等于默认密码nassav。
4. 关闭播放入口/新任务提交，停止API、三个worker和Beat等写入者，按[部署说明](compose-deployment.md#持久任务控制版本切换与回滚)确认旧执行器退出并处理活跃任务/会话。不得在线删锁文件、清空.tasks或只用revoke替代控制协议。
5. 使用新版本运行migrate至最新叶节点0032。PostgreSQL表名维护窗口和锁超时命令见[表名迁移](database.md#表名规范化迁移-0028)及部署说明；此步不混跑旧代码消费者。
6. 重建/更新全部后端消费者及前端/Nginx，再启动API、worker和唯一Beat。Compose migrate服务必须成功；核对showmigrations、服务健康和日志。本地开发同样先migrate再重启各入口。
7. 从关闭状态决定是否启用播放：设置NASSAV_PLAYBACK_ENABLED，审核真实媒体CDN的NASSAV_PLAYBACK_ALLOWED_HOSTS及代理可信目标条件，并让所有后端入口配置一致。不开播放也必须完成数据库迁移。配置参考[播放架构](online-playback-architecture.md#配置与部署)，不以来源网页域名代替实际媒体域名。
8. 做目标环境验收，再开放任务和播放入口：登录/CSRF、资源查询/添加、热缓存复用、任务控制、worker状态、来源播放/本地Range、拖动/刷新、个人续播/多标签/清除，以及关闭后的容量归零。localhost HTTP开发与远程同源HTTPS的Cookie配置分别遵循配置契约。

本机命令（先确认配置指向目标数据库；维护窗口由操作者执行）：

```bash
cd django_backend
uv run python manage.py showmigrations nassav
uv run python manage.py migrate --plan
uv run python manage.py migrate
uv run python manage.py showmigrations nassav
```

Compose使用现有[部署入口](compose-deployment.md)，保持声明的SQLite/PostgreSQL模式。新安装按README完整链启动；已有实例须先停旧消费者，再由新镜像的migrate服务应用迁移，不能把以上宿主机命令直接当作容器数据库入口。

## 回退

优先修复或前向发布。必须回退时关闭入口、停止新消费者、备份新增数据，用新代码逆向迁移至旧消费者对应叶节点，再切换旧镜像与同版本前端/Nginx。

0032回退删除个人进度；0031回退删除media_kind，尚存local会话不能按source解释，应先撤销/清理播放会话。0029回退删除播放会话，0027回退删除缓存；0028须用可逆迁移恢复旧表名。回到2.4.5通常以0026为目标，须核对实际旧版本迁移图，不能只回退0032后启动旧代码。正式视频/图片不由这些迁移搬迁或删除，数据库/文件整体恢复仍须一致。

进度清除是个人历史清除，不删除正式资源；资源删除保留进度与事实缓存。原站签名地址可能过期，升级/回退不保证旧m3u8仍可用。

## 证据与发布门槛

截至实现提交9c0eb83（2026-10-12），已有离线后端946 passed / 28 skipped；独立PostgreSQL16进度/迁移/任务协议29 passed；前端91项测试、lint/build和全量pre-commit通过。SQLite/PostgreSQL验证0031→0032→0031→0032，最终恢复全部迁移叶节点。表名迁移另有历史SQLite/PostgreSQL17证据，不能把这些不同专项混成一次全量PostgreSQL验证。

Chrome/Firefox通过真实隔离Django/SQLite/Redis和合成MP4的首帧、seek、刷新续播、完成重置、写入权转让、清除撤销、移动深色布局、进度503降级；合成TS/fMP4与模拟来源会话另验证续播确认和一次刷新。早期真实Jable/MissAV worker与容量检查见[播放验收](online-playback-acceptance.md)。正式HTTPS/真机已按用户要求跳过，长时验收未完成，Firefox历史真实来源间歇超时仍保留，均不得记为已通过。

本次仅版本/文档发布准备，执行`pre-commit run -a`、前端`pnpm run check`、后端`uv lock --check --offline`及版本/本地文档链接一致性检查；不重新宣称全套后端/真实浏览器/正式部署验收。发布后需要维护者记录实际环境的迁移、配置、服务版本和验收结论。

发布准备验证（2026-10-13，分支chore/release-v2.5.0，提交见Git历史）：三个项目版本均为2.5.0；`uv lock --check --offline`通过、依赖版本未升级；`pnpm run check`为91 passed / 0 failed，lint/build通过；修改文档的180个本地链接/锚点检查通过，2.4.5及更早变更日志原文保持；完整`pre-commit run -a`通过。本轮未重跑全量后端或真实浏览器验收，相关946/29项及浏览器记录属于实现阶段证据。
