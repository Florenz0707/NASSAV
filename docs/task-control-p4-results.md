# 任务控制 P4：刮削检查点与安全提交

2026-10-06；分支 `feat/scrape-pause-cancel`；基线 `191ca04`；提交标题 `[Feat] Checkpoint scraping and fence resource publication`。

## 行为与边界

ControlledScrape 分阶段保存来源解析输入、元数据、封面与逐个头像的检查点。图片和 HTML 都先写 `.tasks/{job_id}`；恢复校验已登记文件 checksum，复用已完成的产物。来源与刮削器每次执行新建，控制上下文不安装到共享单例，也不修改既有来源策略及代理配置。同步资源接口及未带 job_id 的旧 Celery 消息保持旧流程。

TaskNetworkControl 约束总传输时间、响应大小和分块写入。来源阶段预算 180 秒，元数据 60 秒，封面和单个头像各 45 秒；直接请求沿用最多 15 秒，浏览器控制调用最多 75 秒、provider maxTimeout 不超过 60 秒。curl 内容回调检查停止；无响应时等待有界请求退出，保持 pausing/cancelling，不宣称立即停止。浏览器侧正在执行的只读页面访问可能在调用方断开后继续到 provider 期限，不再触达本任务的文件或 DB 写入。

封面失败仍允许元数据部分成功；已有合法共享头像不重复下载；不合法头像只在成功暂存并受控提交后替换。演员名中的路径分隔符和控制字符不进入文件路径，DB 显示名称不因此改写。资源/关系和文件在同一受控提交中落地，事件出箱也在该事务登记；失败按 P2 日志补偿。该顺序是新受控任务的显式行为变化，旧同步流程没有切换。

刷新基线记录资源 ID、元数据更新时间及内容摘要；提交前重新核对，暂停期间被其他操作更新时拒绝覆盖。版本摘要不包括视频和翻译字段，允许独立下载/翻译更新。资源已提交后收到停止请求不撤销提交；恢复不会重做资源保存。

迁移 0024 新增 TaskEvent 和 TaskEventReceipt。事件按 job/event 唯一，在派发失败后保留 pending；重试携带相同 event UUID。现有资源日志消费者按 UUID 收件去重。该机制不承诺跨任意网络消费者的 exactly-once；后续消费者必须实现自身幂等收件，日志本身也不承担业务交付证明。自动重试扫描在 P7 接入。

本阶段修复一个共同清理边界：取消时即使所有资产均 committed，也需要清理仍存在的私有目录或回滚备份。正式资源、原有视频和共享头像仍保留。清理失败独立展示，不复活任务。

run_resource_job 保留任务名和旧参数，新增可选 job_id 供内部受控执行。用户刮削提交及 HTTP 控制仍未切换：必须在 P5 接好关联翻译后才能宣称整条刮削流程可控制。

## 验证入口

```bash
cd django_backend
uv run pytest tests/ --ds=django_project.refactoring_test_settings -v
PYTHONPATH=/tmp/nassav-task-control-p1-pg:. uv run pytest \
  tests/test_controlled_scrape.py tests/test_task_network.py \
  tests/test_task_assets.py tests/test_task_records.py \
  --ds=task_control_pg_settings -v
uv run python manage.py makemigrations --check --dry-run \
  --settings=django_project.refactoring_test_settings
# 根目录
pre-commit run -a
```

测试覆盖来源、元数据、封面、两个头像、提交前与提交后停止，暂停复用、原刷新资源保留、旧快照冲突、坏文件、部分图片失败、DB/文件补偿、稳定事件重试及 callback 内停止。完整后端 659 passed、26 skipped；临时 PostgreSQL 专项 70 passed；模型迁移一致性检查通过。pre-commit 全部通过后提交。来源和图片响应使用显式替身，DB/文件为真实隔离资源；不属于真实来源或非 eager worker 验收。生产库未运行迁移。
