# 范围来源与共享库服务切换（2026-10-15）

## 授权与运行目标

在[新凭证刷新](source-credential-refresh-20261015.md)完成后，用户明确授权继续切换当前服务，普通多用户登录和 GC 仍关闭。

独立分支 `chore/scoped-source-service-cutover`，基线 `dfedb06`。运行服务来自 `/home/florenz/NASSAV/django_backend` 的 dev 提交 `37a16bc`，其生产后端代码与 idle 一致；默认工作树的用户前端改动保留。本轮只更改已忽略的宿主机 `.env` 运行配置，开发文档仍在独立 worktree 完成，不改用户源码或分支。

实际目标继续为 PostgreSQL `127.0.0.1:5432/dbb`、schema `nassav`，使用原全局代理、浏览器服务和 Redis。找到一个 `nassav-api` 及 default/scrape/download 三个 worker，无 Beat 实例。本轮保持该进程组成，不额外启动 Beat。

## 停止、配置与启动

停止前同时核对 DB 和执行器：TaskJob 为 24 succeeded、3 failed、2 cancelled；TaskAttempt 为 24 succeeded、3 failed、18 stopped；没有推荐 job，播放会话只有一份 closed。三个 worker 的 active/reserved 均为空，三个队列长度均为 0。

先保存一致性 PostgreSQL 备份及原 `.env`，再优雅停止 API、撤销旧 worker 对队列的消费并重核空闲，向 worker 主进程发送 SIGTERM 等待退出。旧 API/三个 worker 均确认停止，没有强杀、revoke、删除任务记录、锁文件或任务目录。

随后统一持久配置：

```dotenv
NASSAV_SCOPED_SOURCE_CREDENTIALS=true
NASSAV_SHARED_LIBRARY_ENABLED=true
NASSAV_SOURCE_CREDENTIAL_KEYRING_FILE=/home/florenz/NASSAV/secrets/source-credentials.json
NASSAV_MULTI_USER_ENABLED=false
NASSAV_RESOURCE_GC_ENABLED=false
```

使用原来的 `uv run nassav-worker-default`、`uv run nassav-worker-scrape`、`uv run nassav-worker-download` 和 `uv run nassav-api` 入口启动。新进程以独立会话运行、输出写入私有日志，不再依赖原终端；今后手动启动这些入口仍读取同一 `.env`。没有更换数据库、代理或 keyring，没有新增用户，也没有执行资源刷新、下载或回收。

## 目标环境验证

- 检查新 API 启动进程、三个 worker 主进程及各自子进程的配置白名单，确认上述五项一致；三个真实 worker 均经 broker 返回 pong。
- 匿名 `GET /nassav/api/auth/session` 为 200 且未登录。
- 临时原操作者登录会话的真实 HTTP session 为 200，能力为共享库、个人来源凭证及应用管理员；普通登录、GC、旧资产控制均为 false。临时会话在检查后删除，不修改密码或原登录。
- 系统凭证元信息 HTTP 200，两来源均 active/clearance/version 2，响应无密文、Cookie 或 User-Agent。
- 旧 Cookie 接口 HTTP 403：已引导的应用管理员被权限层拒绝，不进入兼容处理器。处理器本身在范围模式返回 410；两者都不读写旧 Cookie。验收脚本最初误期待 410，核对权限契约后改为实际要求的 403 并通过，没有修改生产权限。
- 本人库及资源列表均 HTTP 200，第一页各 15 条，本人持有仍为 693 份。
- 全新验证进程只读取持久配置，不使用测试开关覆盖；生产来源工厂绑定公共版本 2。Jable ADN-495 重放 HTTP 200 / 840 ms，MissAV SNOS-116 重放 HTTP 200 / 635 ms，均解析到正确编号及播放信息。未将结果写入正式资源。
- 新 API/三个 worker 的私有启动日志无 ERROR、CRITICAL 或 traceback；这只是本轮观察窗口，不是长时稳定性结论。

启动配置隔离回归：`cd django_backend && uv run pytest tests/test_startup_config.py --ds=django_project.refactoring_test_settings -q`，43 passed。前一阶段凭证/范围回归为 36 passed；本轮无生产代码或 schema 变更。文档另运行完整 `pre-commit run -a`，通过后提交合并 idle。

此轮证明统一配置、真实 API 读取、broker 连接和来源直接重放，不把 worker ping 当成真实来源任务发布成功。真实共享刮削/版本文件发布、私人账户隔离、挂载故障及 GC 删除仍按[切换手册](multi-user-cutover.md)逐项受控验收；普通多用户准入及 GC 未开放。

## 私有恢复点

`/tmp/nassav-agent-worktree/django_backend/backup/service-cutover-20261015T095645Z/`

目录 0700、文件 0600，包含 `before-service-cutover.dump`、`backup.sha256`、`before.env`、运维脚本、脱敏 HTTP 结果及服务日志。含秘密的原配置和数据库备份不得提交 Git；日志也按私有文件处理。`/tmp` 可能被清理，恢复点须另行安全留存。持久 keyring 及恢复副本仍位于宿主机 `secrets/`，没有放入该目录。

回退需先停止新提交及当前消费者，重新核对任务、版本和资产，再决定配置/数据恢复；不能在线覆盖数据库或在新模式已产生资产后直接打开旧写入者。普通登录和 GC 应继续显式保持 false。
