# MissAV 会话复用 P5 单独验证

日期：2026-09-30。状态：现场采样待完成；Docker Desktop Linux Engine 当前不可连接。本文对应 [P5 执行计划](byparr-session-reuse-execution-plan.md) 与 [Jable P5 记录](byparr-session-reuse-p5-record.md)。MissAV 必须单独判定，不能继承 Jable 的结论。

## 验证方法

在正式 API 容器及其有效代理配置下，以只读探针 `scripts/probe_p5_missav.py` 从 MissAV 首页发现当前详情页。每个时段先用 Byparr 验证至少 5 个不同详情页，并从有效页面中取得 Cookie+UA；候选会话只保留在探针进程内，须通过同页 3 秒直连验证。然后对至少 20 个不同、业务结构有效的详情页分别测无 Cookie 直连、Cookie+UA 直连及必要的 Byparr 回退。两个时段分别记录有效页分母、HTTP 状态、业务校验、P95、Byparr 中位数、浏览器调用率和缓存命中。逐请求 JSONL 只保留番号、状态、失败分类及耗时，不记录 Cookie、UA、完整 URL、代理地址、出口 IP 或 HTML。

历史 P0 的六个 MissAV 详情样本中，无 Cookie/默认 UA 直连的业务内容为 6/6 有效，与 Cookie+UA 的 6/6 相同，尚不能证明会话复用有额外收益。当时生产挑战检测误判内嵌脚本；该逻辑已修正并有离线回归，但仍需在现场复测。验证前不切换正式配置；未来若启用全局复用开关，须先确保 MissAV 的策略为 `browser_first`。

## 现场结果与判定

隔离配置下 `uv run pytest tests/ -v`：396 passed、13 skipped；`pre-commit run -a` 全部通过。Windows `docker.exe ps` 无法连接 `dockerDesktopLinuxEngine` 命名管道；`docker desktop restart` 因 WSL 进程仍运行而超时，未恢复引擎。因此没有启动 W1/W2 在线请求，也没有现场有效率或耗时数据。等待 API 与 Byparr 容器恢复后填写。未取得两时段有效样本前，MissAV 保持 `browser_first`，不放行策略切换，也不宣称请求链路已由会话复用提速。
