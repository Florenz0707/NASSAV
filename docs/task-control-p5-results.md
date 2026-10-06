# 任务控制 P5：关联翻译与整体终态

2026-10-06；分支 `feat/scrape-translation-control`；基线 `bd1a1a7`；提交标题 `[Feat] Fence scrape translation children and persistent controls`。

## 实现与行为变化

新增刮削从登录入口绑定操作者并创建 TaskJob/Attempt，broker 发布失败保留 pending；原 task 名称和资源提交 URL 保留。旧带签名的 task_id 查询可以定位持久 job，恢复后仍返回最新快照；稳定 job_id 的授权查询与控制不依赖旧 Redis TTL。仅有读 token 不获得写控制权限。无 job_id 的已发布旧消息继续兼容，需要版本切换前排空。

资源保存后，在同一提交中记录翻译基线：资源 ID、翻译 generation/owner 和实际选用标题。主执行将独立 translation attempt 持久化后交接，释放 scrape worker；翻译在原 default 队列运行，整条任务保留活动去重名额。暂停/终止作用于当前子执行；排队消息被失效，运行请求协作退出后才确认停止。恢复生成新 attempt，已保存资源与事件不重复执行。worker 领取同时校验 job kind/attempt role，错路由或旧消息不能误领。

翻译请求使用新建的 TranslatorManager/TranslatorBase 实例，原活动翻译器、提示词和固定词处理不变。TaskNetworkControl 总阶段预算 180 秒，可用性探测最多 5 秒，单请求最多配置 timeout 与 60 秒的较小值；内容回调检查控制，重试前再次检查。暂停保留旧译文和资源，终止不删除已提交资源；尚未完成的资源翻译状态回到 pending，父任务另记 paused/cancelled。

AVResource 新增 translation_generation 和 translation_owner（迁移 0025）。元数据保存、重新翻译请求和领取都更新归属；元数据及归属失效在同一个 ORM 事务内，防止新标题短暂继承旧翻译 writer。新单条派发携带 expected_generation，过时的排队消息不调用翻译器；批量任务可接收 expected_generations，实际执行的单条/批量结果和异常收尾都受 owner/generation 校验。未带版本的历史消息不具备派发时归属证据，必须遵守排空要求。

手动/批量更新不会被父刮削的暂停、终止、迟到成功或迟到异常覆盖。父翻译被替代时整体 failed/TRANSLATION_SUPERSEDED，已保存资源及新译文保留。已提交的翻译完成后到达暂停，恢复直接收尾，不再翻译。翻译失败参与整体 failed；资源仍显示已保存。仅重翻译的 refresh 不获取来源、下载图片或重写元数据；刷新默认不请求翻译，add 维持取得元数据才自动翻译的原规则。

task_presentation 集中裁剪公共快照，移除完整检查点、私有路径、播放 URL 和归属信息；HTTP/Celery Adapter 共用该接口。全局 WS 只发送 job/version 提示。父子时间线由 DB 记录，持久任务整体状态不再依赖读取 Celery SUCCESS 后临时推导；旧任务继续原只读展示。

## 验证与限制

```bash
cd django_backend
uv run pytest tests/ --ds=django_project.refactoring_test_settings -v
PYTHONPATH=/tmp/nassav-task-control-p1-pg:. uv run pytest \
  tests/test_controlled_translation.py tests/test_controlled_scrape.py \
  tests/test_controlled_download.py tests/test_persistent_scrape_http.py \
  tests/test_task_records.py tests/test_task_assets.py \
  tests/test_batch_translation_state.py tests/test_http_contracts.py \
  tests/test_task_control_http.py --ds=task_control_pg_settings -v
uv run python manage.py makemigrations --check --dry-run \
  --settings=django_project.refactoring_test_settings
# 根目录
pre-commit run -a
```

验证包含父子交接、排队/运行期间暂停终止、恢复不重做保存、完成竞争、旧 success/error 收尾、新手动请求、派发前版本变化、HTTP 权限/去重/发布失败与仅重翻译路径。生产库未执行迁移，来源/翻译响应为能力替身；真实 worker 与网络故障联调在 P7。

PostgreSQL 扩展检查单独复现了既有封面测试中 response.close 触发 request_finished、关闭 pytest 回滚事务内连接的问题；该用例改用 transaction=True，真实提交/响应关闭后连接可重新建立。生产 HTTP 实现不变。原批量保存失败注入移至 Repository.save，保留“第二项保存失败、第一项 completed、其余本批 failed”的原断言，以适配受控条件更新而非绕过回归。

最终完整后端 680 passed、26 skipped；临时 PostgreSQL 专项 123 passed，含现有下载和文件/HTTP 回归。模型迁移一致性检查和 pre-commit 全部通过后提交。无生产迁移、服务切换或正式文件清理。
