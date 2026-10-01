# Jable 自动 Cookie 500 修复验证

日期：2026-10-01。关联：[候选方案第四步验收](byparr-candidate-acceptance-record.md)。

## 原因与修改

旧自动获取入口继承 `SourceBase.set_cookie_auto`，仅 HTTP 请求首页。现场首页 403 后返回 500，Byparr 调用为 0。

Jable 新增自动获取实现，调用已配置浏览器，校验首页后复用 `accept_browser_session` 的 Cookie 筛选、配套 UA、同代理同页直连验证及原子写入。现有管理入口的刷新租约和版本保护保持生效。禁用浏览器时保留旧流程；无新增配置或迁移。

## 验证

- 修复前接口回归实际返回 500；修复后返回 200。
- 11 项回归覆盖成功、挑战页、跨站跳转、缺 UA/Cookie、直连 403/超时、并发手动更新/清空、租约失效及已有 Cookie 的非强制加载。
- 隔离 Docker API + Redis + SQLite，使用示例配置、无凭据代理地址及现有 Byparr 服务，真实请求 Jable；自动入口返回 200，耗时 17.374 秒，Cookie、UA、出口信息均存在。
- 现场 `session_reuse_enabled=false`；显式自动获取仍成功。没有修改正式配置、正式数据库或重启正式服务。
- 临时 API/Redis 容器及验证文件在验收证据归档后删除。没有归档实际 Cookie、UA 或敏感配置。

本修复解决第四步的自动 Cookie 阻塞项；媒体、回滚与 24 小时连续观察仍需后续验收，不代表第四步整体通过。

## 仓库检查

全量后端 `uv run pytest tests/ -v`：431 passed、13 skipped（103.92 秒）。`pre-commit run -a` 全部通过，包含格式、类型、编译及前端构建/测试检查。
