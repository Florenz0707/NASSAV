# 多用户升级、归属导入与恢复

本文是长期维护手册；版本差异与本次验证见[v2.5.3发布检查](release-2.5.3.md)。所有命令先在目标配置下查看--help及只读预览，不复制历史实例的数据量、用户名、开关状态或验收结果作为新实例结论。

## 结构迁移与业务数据分开

v2.5.1结构到0036，当前到0051：0037资源池/持有，0038–0039应用账号/授权，0040–0041加密凭证/密钥策略，0042–0043工作与个人操作，0044–0046不可变版本/发布指针/命令配额，0047本人目录，0048–0049持久历史/时钟，0050–0051回收账本/公平游标。已有正确应用到0051的实例不会因版本升级重复导入。

迁移是结构和显式数据迁移的集合，但migrate不会替操作者猜测旧资源与Cookie归属。数据库切换、旧数据导入和业务开关放行必须分别核查。尤其0050/0051不能只凭结构存在就允许物理回收。

## 维护窗口

1. 核对活动数据库、schema、数据目录声明、所有API/worker/Beat版本和当前任务/播放。停止旧写入者，确认下载子进程；不得混跑旧协议消费者。
2. 备份活动DB、原keyring及历史密钥、原Cookie配置和资产；恢复点同时涵盖数据库与文件，不只保留迁移号。PostgreSQL与SQLite升级/回退先在副本验证。
3. 同一配置应用migrate并核对迁移计划与表名。若迁移工具报告目标模式冲突先排查，不通过删除db模式声明或重建空库绕过。
4. 按下面的独立导入协议完成归属，再统一重建API、全部worker和已启用调度器。重建保留实际视频路径、原密钥及全部Compose覆盖文件。
5. 逐项验收本人库/图片/目录、双账号隔离、共享添加/刷新/取消、播放、下载停止与恢复、回收保护和失败恢复，再决定准入与GC是否放行。

## 旧数据归属与凭证

bootstrap_app_admin以配置operator显式引导首管理员；import_resource_library把旧资源绑定到指定原操作者；import_personal_data处理旧标记/设置；import_recommendation_data处理历史/种子/黑名单。命令各自有预览/确认语义，参数见[脚本说明](../scripts/README.md)及命令--help，不能把结构迁移视为归属确认。

推荐默认拒绝向已有个人数据合并。显式保留个人AVID黑名单选项仅补空历史/种子，拒绝旧AVID黑名单、已有历史/种子和活动job，并推进两侧generation拒绝旧writer。不能直接改owner绕过fence。

import_source_credentials要求显式分类，未知账号Cookie只隔离，不自动提升公共凭证。新模式只使用专用加密keyring，不能退回SECRET_KEY或生成新密钥掩盖旧密文不可读。轮换必须保留旧密钥，完成DB policy核查和所有消费者重启。

## 部署与放行

NASSAV_SCOPED_SOURCE_CREDENTIALS、NASSAV_SHARED_LIBRARY_ENABLED、NASSAV_MULTI_USER_ENABLED与NASSAV_RESOURCE_GC_ENABLED默认false；多用户依赖共享库和范围凭证，GC依赖共享库。实例实际值以当前配置为准，文档清理与版本准备不替操作者改开关。

显式-f的Docker部署必须持续携带compose.credentials.yaml及原数据库/GPU文件；根.env分别填写宿主机HOST_FILE和容器FILE。restart不应用新增挂载。服务健康检查成功仍须用原密钥加载/解密及本人来源绑定验证，见[部署说明](compose-deployment.md#独立来源-keyring-挂载)。

公共来源验收不代表私人账号网站验收；私人凭证与数据不能因管理员角色变为公开。HTTPS、真机、长时和历史Firefox超时的边界随版本检查单维护。

## 恢复

先停新写入者和媒体会话，再恢复匹配的DB、资产及完整keyring；不要只回退Python/Vue代码。已产生新持有、版本、历史或GC删除后，旧代码/旧schema可能无法解释数据，须从恢复点回退。禁止在线删除锁文件、清空.tasks、依据租约超时宣称writer已停止。清理失败保留日志与墓碑，按[回收协议](resource-gc-architecture.md)和[任务协议](task-control-architecture.md)处理。
