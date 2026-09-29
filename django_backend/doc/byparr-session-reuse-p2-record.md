# Byparr 会话复用 P2 验证记录

P2 实现直连目标状态与失败分类、统一的页面验证、浏览器 Cookie+UA 候选筛选及短直连探测。MissAV 详情与 Jable 详情、搜索、列表、推荐沿用原有候选 URL 和业务校验入口。所有自动写入仍使用 P1 的 `updated_at` 比较；站点级 Redis 刷新协调属于 P3。

## 离线验收

`tests/test_browser_session_reuse.py` 覆盖 `browser_first`、`direct_first`、`direct_only`，以及冷会话 403 回退、暖会话不调用 Byparr、目标 404 不刷新、HTTP 200 挑战页、浏览器错域和结构错误、Cookie 域名/路径/过期/同名歧义、无 UA、无已确认代理路线、失败探测、人工写入晚到及首次探测后幂等重放。P1 的迁移和并发测试继续回归。

SQLite 后端全量测试：`373 passed, 13 skipped`；隔离 PostgreSQL 中 P2 与 P1 专项测试：`29 passed`；`pre-commit run -a` 为提交前必需检查。测试默认不访问外站或生产数据库。PostgreSQL 验证使用独立测试容器；正式站点的代理出口、有效页面率和耗时阈值须在 P5 灰度阶段另行验收。两源配置仍保持 `browser_first`，本阶段不切换生产策略。

## 行为边界

仅通过 Byparr 取得并完成页面校验的候选可以自动保存。浏览器候选需包含适用于目标页的 Cookie 与 UA；直连探测预算为 3 秒，并要求目标 HTTP 200、同站点、非挑战且站点业务结构有效。候选无效或探测失败时不替换已有会话，本次有效浏览器页面仍可用于业务。已存储的配套会话在 `direct_first` 下可直接使用；旧 Cookie 仍以默认 UA 进行有限直连。媒体下载路径未改动。
