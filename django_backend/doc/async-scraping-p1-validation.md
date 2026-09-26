# 异步资源任务 P1 验证记录

日期：2026-09-26。分支：`feat/async-resource-jobs`。本记录仅覆盖后端任务接口；前端反馈、进度通道评估和全栈 Compose 分别属于后续独立功能分支。

## P0 输入

- 本机 `x86_64`；Redis `PING` 返回 `PONG`；本地 SQLite 文件约 11 MiB。
- 固定 digest 的 Byparr 容器在宿主机端口 `127.0.0.1:8192` 运行，Docker 显示 `healthy`。详情页有效性与先前样本结果见 [Byparr 验收记录](byparr-rollout-validation.md)，不能用健康状态代替样本验收。
- 当前改动没有切换前端或容器部署。P0 计划中的同步 API 延迟、无结果样本、下载进度与 WebSocket、代理拓扑及目标机架构/下载器版本仍需在 P3/P4 联调前测量。

## P1 实现与边界

- 新的任务接口只做校验、Redis 占锁和 Celery 入队；资源查找、元数据、封面、保存及翻译提交留在 `scrape` worker 中。旧同步接口不变。
- 添加与刷新共用规范化 AVID 锁；相同编号重复提交返回已有任务。入队失败清理快照并释放自己的锁。worker 用现有 `ResourceService`，阶段回调只在真实业务边界触发；数据库/翻译调用不复制一套。
- 快照先落 Redis 后推送精简 WebSocket 事件。查询需提交响应中的签名令牌；前端可按版本处理乱序事件。没有自动重试；worker 失联后锁到期，查询转为失败并允许重提。资源添加重投时检查既有记录以避免二次写入。
- 当前 WebSocket 仍是全局广播；新事件不含 AVID、结果或错误文本。公开部署前仍需按原计划补齐访问控制和订阅范围。刷新与重新翻译在 worker 崩溃且任务被人为重提的情况下，还需联调验证副作用去重。

## 本阶段放行检查

- 离线任务测试：`uv run pytest tests/test_scrape_jobs.py -q`，10 项通过。
- 全量后端测试：在最后一个单条接口测试加入前，`uv run pytest tests/ -q` 为 257 项通过、13 项跳过。加入该测试后重跑为 257 项通过、1 项失败、13 项跳过；失败项是既有推荐排序断言 `test_recommendation_feedback_endpoint_accepts_like_and_dislike`，单独运行和整份推荐测试文件重跑分别为 1 项及 37 项通过。首次全量测试还发现 Jable 离线用例受本地启用的 Byparr 配置影响而触发真实网络回退；该测试文件现显式关闭浏览器回退，重跑后 13 项通过。
- 真实 Redis 临时键探测：去重锁、非持有者不能释放、持有者续期、快照读写通过；探测键已清理。
- Celery 路由核对：下载与模拟下载为 `download`，资源任务为 `scrape`，翻译为 `default`。
- 代码检查：根目录 `pre-commit run -a` 全部通过。
- 在线验收仍需同时启动 `scrape`、`download`、`default` worker，再测提交 P95、任务完成、重复提交、失败快照和下载不被刮削阻塞。P1 的本地单元检查不代替该验收。
