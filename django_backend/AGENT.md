# 后端开发规范（FOR AGENT）

## 开发前

- 阅读[仓库规范](../AGENTS.md)、[重构原则](../docs/development-principles.md)和[模块边界](doc/p5-domain-boundaries.md)，核对目标用例与消费者。
- 使用 `uv` 管理环境和运行 Python；配置变更同步 `config/config.example.yaml`，容器默认配置受影响时同步对应示例。
- 接口、数据、推荐与运行行为分别核对 doc 下对应文档；脚本参数写入脚本说明和 [scripts/README.md](scripts/README.md)，测试入口维护于 [tests/README.md](tests/README.md)。

## 接口与职责

- workflow 编排业务，HTTP 负责权限/输入/响应，Celery 负责任务上下文/重试，Adapter 负责 ORM、文件、Redis、CLI 等实现；生产默认依赖仅在 composition 装配。
- 核心不导入 views、Celery task 对象或 composition 默认实例；新核心直接消费独立 workflow/contract，既有 facade 保留消费者兼容。
- 消费能力以 canonical contracts 为唯一入口，必要的可替换业务能力使用现有 ABC；数据类、纯函数、简单框架入口不强制继承。调用公开接口，不调用未声明的子类方法或遍历实现私有容器。
- 新来源/列表能力、推荐器与因子按模块边界中的注册、工厂及 hook 扩展；不在通用流程加入源名分支，不复制推荐主流水线，不让算法直接读取全局 ORM。
- 持久化消费已解析的数据输入，不接收 HTML 或来源对象，不修改调用方输入；存在性查询按候选集合批量处理，避免逐项 ORM 请求。

## 状态与行为兼容

- 结构调整保留 URL/字段、任务名/路由/重试、Redis key/TTL、文件路径、关系规则和副作用顺序；行为修复须说明新旧差异并提供回归，契约快照不因失败自动重建。
- 下载锁按 owner 原子续租和释放，不能无条件删锁；失租中止执行与 CLI 后代进程，抑制成功副作用。混合版本 worker 的切换按[部署说明](doc/compose-deployment.md#下载-worker-版本切换)执行。
- 批量翻译按实际标题字段选择，本批失败仅收尾本批仍 translating 的记录，保留已完成结果和旧译文；禁止全局重置异常状态。
- 区分旧兼容路径与受控任务：旧成功副作用顺序保持；受控任务按[任务控制架构](doc/task-control-architecture.md)执行代次 fencing、资产日志补偿和事件出箱。文件/DB 不承诺全局原子性，不得把旧下载的告警语义带入受控提交。
- 外部搜索显式拒绝不支持能力，保留版本快照、部分结果与后台取消契约；来源会话与代理策略保持已有验证边界。

## 验证与文档

从后端目录执行离线集成门槛：

```bash
uv run pytest tests/ --ds=django_project.refactoring_test_settings -v
```

默认 pytest 配置使用实例设置，不能省略 `--ds` 后声称隔离验证。复用能力替身和临时 SQLite/Redis fixture，覆盖异常、失租、幂等、终态和调用次数；在线测试显式 opt-in，不连接正式数据验证重构。根目录执行 `pre-commit run -a`，失败项修复后再提交/合并。

按变更更新接口、数据、模块边界或运行说明；纯文档变更检查链接与命令并执行 pre-commit。报告提交、命令、通过/跳过及范围，目标环境验收按[验证状态](doc/validation-status.md)维护。

## 持久任务开发约束

涉及下载、刮削、所属翻译、任务控制或文件清理时，先阅读[任务控制架构](doc/task-control-architecture.md)。DB 是持久业务状态所有者；恢复使用新 attempt/generation，旧执行不得提交。暂停/终止须确认写入者停止，终态不等于清理完成；不得在线删除锁文件、手动清空 `.tasks` 或以 Celery revoke 代替控制协议。发布、回滚与删除复用共享资源/目标锁及资产日志；网络、复制和大文件哈希不得放入短 DB 提交回调。前端按 job_id/version 合并授权快照，以 allowed_actions 决定操作。
