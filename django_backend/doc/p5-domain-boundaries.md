# 后端用例与基础设施边界

本文记录 R0–R7 收敛后的职责，用于维护后端分层。历史抽象评估和隔离验收见[验证边界与历史记录](validation-status.md)。

| 模块                              | 责任                                           | 允许依赖                                    |
| --------------------------------- | ---------------------------------------------- | ------------------------------------------- |
| http 与 tasks                     | 输入/权限/响应映射、任务 ID/重试适配与默认装配 | 用例、composition、框架                     |
| resource_workflow                 | 新增/刷新资源及副作用时序                      | resource_contracts、resource_data、展示函数 |
| download_workflow                 | 下载/模拟执行、失败/重试/进度与清理编排        | download_contracts                          |
| translation_workflow              | 共享标题选择、单条/批量状态转换与异常收尾      | translation_contracts                       |
| recommendation.base/workflow      | 推荐流水线与协调，输入执行副本                 | 推荐 contracts/entities/策略                |
| source 与 external search Adapter | 来源网络/解析/排序/缓存/封面能力               | 页面/会话能力与来源实现                     |
| Django/Redis/文件/CLI Adapter     | 数据库、队列、资产、事件、进程副作用           | 基础设施与对应能力契约                      |
| composition                       | 默认工厂、配置和生产 Adapter 装配              | 具体实现                                    |

核心用例不导入 HTTP 视图、Celery task 对象或 composition 默认实例。生产 facade 可装配并导出既有同步实例，但不能从核心反向引用；有实际消费者的 facade 保留，无消费者的 wrapper 删除。测试替身与生产 Adapter 使用同一 canonical ABC；旧 HTTP/Celery envelope 由入口继续保持。

资源 HTML/来源关系解析位于持久化前；推荐查询批量执行，纯算法不逐候选读 ORM；下载租约校验保护 Redis 写入和后续成功副作用。正常成功/部分失败时序按既有行为冻结，改变事务/事件语义应独立实施。

隔离测试通过不代表真实站点、PostgreSQL、混合版本 worker 或生产部署接受。备份引擎、简单 ORM 查询及纯函数不为假想扩展建立新的业务继承层。
