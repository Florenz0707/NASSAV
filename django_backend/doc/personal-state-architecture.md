# 个人资源状态与数据库设置

## 所有者与授权

UserResourceState以(user,resource)唯一持有收藏、已观看、稍后再看、备注、version和更新时间；未建行按默认状态投影。UserPreferences以user一对一持有JSON preferences、created_at和updated_at，不包含legacy_imported_at。播放进度、观看历史和原站事实缓存独立；播放结束不自动标记已观看，不做评分。

HTTP从request.user确定身份，不接受请求指定owner。共享模式写入在user fence内重新核查本人持有，列表批量投影，避免逐卡查询；个人备注或偏好不能通过共享任务事件泄露。个人状态保存使用expected_version，冲突保留前端草稿，不自动覆盖服务器新版。

## JSON设置与0034（当前实现）

preference_definitions是当前键、类型、默认值与校验的唯一入口，业务读取有效配置，不直接消费原JSON。PostgreSQL的JSONField使用JSONB；SQLite仍支持同一JSONField接口，不增加专属JSONB依赖。

GET只读合并合法默认值，缺少键不写回、不创建用户行；不返回已废弃键。PUT只合并明确提交的合法键，校验整次提交，不顺手删除未知存储键。空更新/同值不推进更新时间；前端只提交改动字段，不把其他设置分区草稿带入保存。

新增配置先加定义与默认值，已有JSON缺键即可读取默认值；配置删除、重命名或类型变化必须新增数据迁移，保留历史迁移并处理旧值冲突。禁止靠浏览器清理废弃键。播放数值允许JSON整数/小数，不接受布尔或数值字符串；既有字符串类型保持契约。

## 迁移与导入

0033建立个人状态/偏好，0034把原六项配置列搬入JSON并删除旧列。旧AVResource标记、INI和推荐数据的归属由操作者显式确认；import_personal_data只读旧源、幂等创建缺失行，不把旧状态复制给所有账号，不重新以INI持有设置。共享库归属导入、角色引导和推荐补导入各走独立命令，结构迁移不自动决定归属，见[切换手册](multi-user-cutover.md)。

代理、缓存TTL、服务器来源开关及专用keyring不是用户偏好。Cookie通过[范围凭证](source-credential-architecture.md)盲写，不放JSON偏好、浏览器存储或日志。

## 前端职责

PersonalResourcePanel及personalResourceEditor负责标记、备注草稿与版本冲突；settings store持有JSON设置草稿与服务器基线。App在登录身份变化时重置；旧用户/旧资源响应不能改写当前内容。个人中心KeepAlive只保留界面状态，数据新鲜度仍由领域查询缓存和失效事件管理，见[前端缓存](../../vue_frontend/doc/cache-architecture.md)。
