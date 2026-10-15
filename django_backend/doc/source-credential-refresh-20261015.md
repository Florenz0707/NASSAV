# 系统来源凭证刷新记录（2026-10-15）

## 范围与结果

用户授权获取新的有效凭证并验证后刷新。本轮更新目标为既有 PostgreSQL `127.0.0.1:5432/dbb`、schema `nassav` 中的两份系统来源凭证；不修改资源详情、旧 `SourceCookie` 或运行配置，不重启现有服务。

独立分支 `chore/source-credential-refresh-validation`，基线 `efe37c2`。两份记录沿原 ID，由隔离的未知旧 Cookie 替换为新获取且经过验证的公共访问挑战凭证；使用管理员盲写协议、`expected_version=1`、独立 request UUID 和 `maintenance` 原因，提交后均为 `active / clearance / version=2`。只读复核确认各有一条对应审计和幂等回执，版本均为 2。

| 来源   | 真实详情样本 | 浏览器获取耗时 | 候选直接重放       | 数据库更新后的范围工厂重放 |
| ------ | ------------ | -------------- | ------------------ | -------------------------- |
| Jable  | ADN-495      | 34331 ms       | HTTP 200 / 1137 ms | HTTP 200 / 778 ms          |
| MissAV | SNOS-116     | 27413 ms       | HTTP 200 / 883 ms  | HTTP 200 / 698 ms          |

耗时是本轮单次观测，不是稳定性保证。两阶段重放均确认最终地址属于配置原站、页面不是挑战页，且 `parse_source_facts` 能解析匹配的资源编号及播放信息；MissAV 的播放列表解析亦成功。此记录不代表浏览器长时间播放或真实 Celery 刮削任务已验收。

## 获取、验证与提交边界

1. 使用既有 `ProxyServer` 和全局 `Proxy.url` 获取公共详情页；沿 Redis 跨进程容量协议，不增加面向具体浏览器 provider 的业务调度。
2. 获取过程显式使用公共页面，不读取隔离的未知旧 Cookie。只保留 `cf_clearance`、`__cf_bm`、`__cflb` 白名单中的适用条目，验证域名、路径、有效期和配套 User-Agent。账户 Cookie 不升级为公共凭证。
3. 通过同一全局代理，以候选 Cookie 和配套 UA 直接重放原站详情页；要求 HTTP 200、三秒内完成、原站 HTTPS 默认端口、无挑战，并验证业务内容。提交前再次重放，拒绝超过十分钟、过期、出口变化或记录版本变化的候选。
4. 网络在事务外；管理员写入协议负责当前角色、密钥策略、CAS、审计、幂等回执及旧快照失效。没有直接翻转隔离行状态或绕过凭证协议写表。
5. 提交后仅在验证进程内开启范围消费者，通过生产 `source_factories` 从数据库重新读取版本 2，确认公共范围后再次重放、解析。旧 Cookie 保存回调明确禁止写入。

本次公共挑战验证不能证明私人账户、付费内容或 Cookie 跨出口重放有效；后续过期仍须遵守正常刷新及失败协议。这里是管理员获取、验证后替换凭证的运维操作，不是新增自动刷新调度或公开 API。

## 恢复点与秘密处理

提交前生成完整 PostgreSQL 自定义格式备份，保存于 Git 忽略的私有目录：

`/tmp/nassav-agent-worktree/django_backend/backup/source-refresh-20261015T094244Z/`

其中 `before-credential-refresh.dump`、`backup.sha256` 是操作前恢复点；候选文件只含加密载荷及非敏感验证证据，另留运维脚本和脱敏结果。目录 0700、文件 0600，未写入日志或版本库。该目录位于 `/tmp`，应在清理或重启前另行安全留存。

持久 keyring 继续使用 `/home/florenz/NASSAV/secrets/source-credentials.json`，恢复副本为同目录 `source-credentials.recovery.json`；两者不与数据库备份同放。本轮没有更换密钥。旧明文兼容记录及历史备份不因本轮刷新自动清除。

## 验证与后续运行切换

- 凭证和范围运行隔离回归：`cd django_backend && uv run pytest tests/test_source_credentials.py tests/test_scoped_source_runtime.py --ds=django_project.refactoring_test_settings -q`，36 passed。
- 目标证据：上述两来源真实获取、直接重放、持久写入及生产范围工厂复验；只读确认两份新版本、审计及回执。
- 文档提交根目录 `pre-commit run -a` 全部通过。本轮无生产代码或 schema 变更，未重新运行全量后端；此前 1335 passed / 28 skipped 属于 `efe37c2` 基线证据。

本凭证刷新阶段未更改旧 Cookie 运行模式或持久配置；凭证仓库更新不等于现有 API/worker 自动使用新记录。用户随后另行授权[统一服务切换](source-service-cutover-20261015.md)，已开启范围凭证/共享库、配置 keyring 并优雅重启 API/三个 worker。普通登录和自动 GC 继续关闭；真实共享任务发布、挂载及故障恢复门槛仍需后续受控验收。
