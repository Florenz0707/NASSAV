# R4 质量门槛阻塞：下载锁所有权

记录日期：2026-10-04。初次阻塞基线：`idle@383bd83`；当时 R4 下载草稿未提交或合并。现已通过独立锁修复 `c4ea2a5` 和 CLI 子进程取消补充修复 `6b6825a` 解除本记录中的下载阻塞。原计划及阶段结果见[执行计划](backend-refactoring-plan.md)和[执行记录](backend-refactoring-execution.md)。

## 决策与修复状态

用户已授权独立 `[Fix]` 分支修复下载锁所有权与失租处理，然后恢复 R4 并继续 R5–R7。独立修复全套 **499 passed、24 skipped**，全量 `pre-commit run -a` 通过；原下载 owner 阻塞已解除。

原计划第 2 节冻结“Redis key、TTL、锁所有权及旧任务兼容性”，第 4 节 R4 又要求通过“锁丢失”验收；第 2 节要求行为改善单独作为语义修复。现有下载锁不具有 owner 保护，纯结构迁移无法同时保持原行为和通过这项验收。用户另明确要求质量门槛不能达成时先沟通再决定下一步，因此已停止后续业务修改，未降低或跳过该验收。

## 已复现的问题

在 `idle@383bd83` 的 `nassav/tasks.py` 中：

- `acquire_global_download_lock`（437 行）执行 `SET key locked NX EX timeout`，所有任务使用同一个固定值。
- `release_global_download_lock`（453 行）无条件 `DEL key`，没有任务身份或 owner 校验。
- 默认 TTL 为 3600 秒，没有续租；超过 TTL 或租约丢失后，后来任务可以重新获得锁。

确定性竞争顺序：

| 步骤 | 动作                     | 必须保持的结果 | 实际结果         |
| ---- | ------------------------ | -------------- | ---------------- |
| 1    | 任务 A 获取全局下载锁    | A 持有锁       | 成功             |
| 2    | 模拟 A 的租约到期        | 原租约结束     | 删除临时测试 key |
| 3    | 任务 B 获取同名锁        | B 持有新锁     | 成功             |
| 4    | A 晚到的清理调用 release | B 的锁继续存在 | B 的锁被删除     |

这会使后续任务再次进入下载区间，破坏“同一时间只有一个下载任务”的约束。测试以删除临时 Redis key 模拟过期，不依赖实际等待时间；既没有使用生产 Redis，也没有下载真实媒体。

## 验证证据

- 原有下载/代理/输出解析/资源列表及 R0 时序测试：**22 passed**。
- 增加锁所有权验收后的定向结果：**22 passed、1 failed，1.98秒**。
- R4 草稿全套：**493 passed、24 skipped、1 failed，45.11秒**。唯一失败是 `test_expired_download_owner_cannot_delete_new_workers_lock`，断言消息 `Late cleanup removed the new worker's download lock`。
- 草稿 `pre-commit run -a` 采用格式化结果后复验全部通过；测试门槛失败，故不能提交合并该阶段。
- 将草稿保存后，在恢复的 `idle@383bd83` 上运行相同外部回归脚本，仍是 **1 failed，0.22秒**。三个锁函数的 AST 与草稿相同，证明是既有缺陷而不是本次代码迁移引入。
- Redis 使用独立临时目录、无凭证、`--port 0`、临时 Unix socket、禁用持久化；测试终止 Redis 并清理目录。无需公网、生产数据库或现有服务凭证。

本次仅验证了该竞争，不宣称已完成 CLI 失租中止、混合版本 worker、真实 Redis/PostgreSQL 部署或目标环境验收。

## 草稿保留与恢复

- 草稿分支：`enhancement/backend-refactor-r4-download-workflow`，基线 `383bd83`，没有未通过门槛的业务提交。
- Git stash：`30c12da1616fec8fab4c7f52ac1630be21878b13`，说明 `R4 download workflow WIP: blocked by lock ownership gate`。
- 完整可审阅补丁：`/tmp/nassav-refactor-r4-download-wip.patch`，包含未跟踪的新模块和失败回归测试。
- 已恢复的 baseline 复现脚本：`/tmp/test_nassav_r4_download_lock_ownership.py`。
- 草稿全套日志：`/tmp/nassav-refactor-r4-download-gate.log`；baseline 复现日志：`/tmp/nassav-refactor-r4-idle-lock-proof.log`。

草稿包括下载信息解析依赖、下载/模拟用例、任务传输 Adapter 与资源查询模块迁移。只有既有兼容测试通过，不计为 R4 完成。后续恢复应先将阶段分支快进到已通过门槛的 `idle`，再 `git stash apply 30c12da1616fec8fab4c7f52ac1630be21878b13`，保留 stash 至恢复和验证完成；不直接 `pop` 或把草稿并入 `idle`。

baseline 复现命令，从工作树 `django_backend/` 运行：

```bash
PYTHONPATH=/tmp/nassav-agent-worktree/django_backend/tests:/tmp/nassav-agent-worktree/django_backend \
UV_CACHE_DIR=/tmp/nassav-audit-uv \
uv run --no-sync pytest /tmp/test_nassav_r4_download_lock_ownership.py \
  --ds=django_project.refactoring_test_settings -v --tb=short
```

该脚本记录旧无 owner 接口的缺陷；修复后的验收使用 `tests/test_download_lock_ownership.py`，不再使用旧脚本作为正常门槛。

## 拟议独立修复范围

用户已授权独立修复并继续 R4–R7，使用新分支 `fix/backend-download-lock-ownership`，在恢复 R4 前完成下列工作：

1. 为每次执行生成唯一 owner token，避免重复投递或重试共享同一个 task ID 被误判为同一个租约。
2. 获取、续租和释放通过原子 owner 校验实现；旧 owner 不能删除或续租新 owner 的锁。保留 key 名和既有 TTL 默认值；明确任务锁及进度清理同样受所有权保护。
3. 定义并验证失租后的停止规则：不得继续将下载标记为成功；中止执行中的 CLI，并保留已确认的文件/状态结果。续租故障和清理异常应有有限等待与清晰失败返回。
4. 保持 HTTP、Celery 任务名、队列、下载代理及正常成功事件字段。锁所有权/续租/失租规则属于单独记录的行为变化，不能混入结构迁移提交。
5. 使用临时 Redis 验证竞争、过期、旧 owner、重复投递、失租、续租故障和清理异常；使用 CLI 替身确认中止行为。相关测试、全套隔离后端测试及 `pre-commit run -a` 全部通过后才提交并合并 `idle`。
6. 旧 worker 无条件删除锁，不能据此认定混合版本安全。实际部署需单独验证兼容路径或停止/排空旧 worker；本次授权不自动包含生产部署。

独立修复已实现执行级 UUID owner、原子续租/释放、任务进度与清理 fencing，以及静默 CLI 的失租中止。测试使用真实临时 Redis 和本地 Python 子进程；实际外站下载、混合版本 worker 与生产部署仍不在本次验收内。原失败脚本描述旧接口，现有回归见 `tests/test_download_lock_ownership.py`。
