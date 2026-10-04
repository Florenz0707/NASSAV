# R4 翻译质量门槛：批量任务的既有标题字段错误

记录日期：2026-10-04。下载 owner 独立修复已在 `fix/backend-download-lock-ownership` 提交为 `c4ea2a5` 并合并 `idle`；子进程取消补充修复 `6b6825a` 也已通过门槛并合并。R4 下载结构迁移另行验证；本记录不将翻译与 R5–R7 标为完成。

## 已复现的失败

在未修改翻译任务的代码上，创建仅含 `original_title` 的临时资源，注入离线翻译替身，执行原注册任务 `nassav.tasks.batch_translate_titles_task`。预期选择该资源并返回成功，实际返回 `success: false`，错误为 `Cannot resolve keyword 'title' into field`。

`AVResource` 实际字段为 `original_title` 和 `source_title`。单条任务使用这两个字段选择标题；批量任务的 ORM 筛选却使用不存在的 `title` 字段，因此会在调用翻译器之前失败。这一缺陷存在于下载重构之前，与锁修复及模块迁移无关。

## 证据与隔离方式

- 独立复现脚本：`/tmp/test_nassav_batch_translation_gate.py`。
- 日志：`/tmp/nassav-r4-translation-baseline-proof.log`。
- 最终有效复现结果：**1 failed，0.40 秒**；断言输出包含完整错误 envelope。
- 使用 `django_project.refactoring_test_settings`、临时 SQLite、离线网络守卫和翻译替身。未读取生产数据、调用真实翻译服务或发送任务到 worker。
- 恢复后的 R4 下载分支中，单条和批量翻译任务 AST 与已复现 baseline `c4ea2a5` 完全相同，未修改翻译行为。
- 原全套缺少该业务路径的回归，因此原有全套通过不能作为批量翻译可用的证据。

从工作树 `django_backend/` 可复现：

```bash
PYTHONPATH=/tmp/nassav-agent-worktree/django_backend/tests:/tmp/nassav-agent-worktree/django_backend \
UV_CACHE_DIR=/tmp/nassav-audit-uv \
uv run --no-sync pytest /tmp/test_nassav_batch_translation_gate.py \
  --ds=django_project.refactoring_test_settings -v --tb=short
```

脚本通过 `pytest_plugins = ["conftest"]` 显式加载仓库隔离 fixture。上述命令预期失败；它是门槛失败证据，不是通过记录。

## 所需范围决定

计划第 2 节要求行为修复与结构迁移分开记录。用户本次新增授权明确为锁所有权和失租处理；批量任务从必然失败变为成功属于另一项行为修复，用户已授权独立修复并继续后续阶段，修复已通过七项回归及全套 515 passed、24 skipped。

建议独立分支 `fix/backend-batch-translation-state`：

1. 筛选实际标题字段，保留 AVID 选择及 `skip_existing` 行为。
2. 验收翻译器异常、空结果和结果数量不匹配，避免资源停留在 `translating`。
3. 单条与批量共享标题/状态规则，保持原任务名和结果 envelope；行为修复先单独提交，结构迁移在 R4 后续分支完成。
4. 新增回归、全套隔离后端测试、`pre-commit run -a` 通过后合并 `idle`，然后继续 R4–R7。

本门槛已解除；本文保留原始缺陷证据，当前正常回归见 tests/test_batch_translation_state.py。
