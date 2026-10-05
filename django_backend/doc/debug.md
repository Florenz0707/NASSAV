# 调试与链路验证

本地 API 默认 `http://127.0.0.1:9790`，Vite/Compose 网关默认 `http://127.0.0.1:9780`。浏览器始终通过页面同源 `/nassav/api/` 和 `/nassav/ws/` 请求，网关须转发 WebSocket Upgrade、Cookie、Host 与 Origin。配置和启动见[后端 README](../README.md)及[部署说明](compose-deployment.md)。

业务接口需要 operator 登录；写请求还需 CSRF。`DEBUG=true` 只控制调试功能，不绕过认证。开发账号、Host 和 CSRF_TRUSTED_ORIGINS 按[配置契约](configuration-contract.md)设置；正式环境不启用 DEBUG。

## 登录后使用 curl

以下从后端目录执行，只是操作示例，本轮文档检查不执行请求。使用本机 HTTP 入口；若使用 HTTPS 网关，替换 base 并保持同一 Host。账号例为默认 nassav；改过 NASSAV_OPERATOR_USERNAME 时同步修改。

```bash
set -e
umask 077
doc_base=http://127.0.0.1:9790/nassav
doc_cookie_jar=$(mktemp /tmp/nassav-debug-cookie.XXXXXX)
trap 'rm -f "$doc_cookie_jar"' EXIT

# 返回 JSON 只含登录状态；CSRF token 从 Set-Cookie 写入 cookie jar
curl --fail --silent --show-error --cookie-jar "$doc_cookie_jar" \
  "$doc_base/api/auth/session"

doc_read_csrf() {
  uv run python -c 'import http.cookiejar,sys; jar=http.cookiejar.MozillaCookieJar(sys.argv[1]); jar.load(ignore_discard=True,ignore_expires=True); print(next(c.value for c in jar if c.name=="csrftoken"))' "$doc_cookie_jar"
}
doc_csrf=$(doc_read_csrf)

# 密码交互输入，只通过 stdin 提交，不写入命令行或示例文件
uv run python -c 'import getpass,json; print(json.dumps({"username":"nassav","password":getpass.getpass("Operator password: ")}))' | \
  curl --fail --silent --show-error --cookie "$doc_cookie_jar" \
    --cookie-jar "$doc_cookie_jar" -H 'Content-Type: application/json' \
    -H "X-CSRFToken: $doc_csrf" -H "Origin: ${doc_base%/nassav}" \
    --data-binary @- "$doc_base/api/auth/login"

# 登录会轮换 CSRF cookie；后续写请求使用新 token
curl --fail --silent --show-error --cookie "$doc_cookie_jar" \
  --cookie-jar "$doc_cookie_jar" "$doc_base/api/auth/session"
doc_csrf=$(doc_read_csrf)
```

保留当前终端用于以下命令；退出时 cookie jar 自动删除。不要将真实 Cookie/密码放入仓库或输出到分享日志。

## 模拟下载

`POST /nassav/api/downloads/mock/{avid}` 要求已登录、DEBUG=true，且 AVID 已存在数据库。duration 为整数，默认 30，允许 1–300 秒。它会写任务队列/锁/进度并发送事件，不创建媒体文件，也不更新 file_exists；不能替代真实 CLI、媒体文件或全局下载并发验收。

```bash
curl --fail --silent --show-error --cookie "$doc_cookie_jar" \
  -H 'Content-Type: application/json' -H "X-CSRFToken: $doc_csrf" \
  -H "Origin: ${doc_base%/nassav}" -d '{"duration":10}' \
  "$doc_base/api/downloads/mock/EXISTING-AVID"

curl --fail --silent --show-error --cookie "$doc_cookie_jar" \
  "$doc_base/api/tasks/queue/status"
```

EXISTING-AVID 替换为当前隔离样本编号。成功返回 202 与 task_id/avid/status/duration/mock；这只是入队，不是终态。未登录为 401；无 DEBUG 为 403；无资源为 404；重复任务为 409；整数 duration 越界为 400。CSRF 校验失败为 403。任务需要监听 download 队列的 worker。

### 浏览器事件

在已经登录的应用页控制台运行；浏览器自动携带会话 Cookie，协议由页面决定，不通过 query 传登录凭证。

```javascript
const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
const socket = new WebSocket(`${protocol}//${location.host}/nassav/ws/tasks/`)
socket.onmessage = ({ data }) => {
  const event = JSON.parse(data)
  if (event.type === 'progress_update') {
    console.log(event.data.avid, event.data.percent, event.data.speed, event.data.eta)
  } else {
    console.log(event.type, event.data)
  }
}
```

progress_update 字段直接位于 data；任务事件还有 task_started/task_completed/task_failed/queue_status。下载页在连接失败时使用 API 轮询，其他任务的完整快照仍需独立 token 查询。关闭码与会话核对规则见[接口文档](interface.md)。

## 资源与外部搜索任务

前端已使用异步资源和外部搜索任务，旧同步接口继续保留。不要以 202 入队或 WebSocket 通知认定成功：

| 链路          | 提交                           | 查询与令牌                                                    | 终态与补偿                                                               |
| ------------- | ------------------------------ | ------------------------------------------------------------- | ------------------------------------------------------------------------ |
| 资源新增/刷新 | POST /nassav/api/resource/jobs | GET /nassav/api/resource/jobs/{task_id}，X-Resource-Job-Token | succeeded 后刷新库；scrape worker 执行，断线补查                         |
| 外部搜索      | POST /nassav/api/search/jobs   | GET /nassav/api/search/jobs/{task_id}，token query            | 按 version 合并阶段结果，failed/cancelled 保留 partial；默认 worker 执行 |

具体 body、取消、签名校验和 TTL 见[接口文档](interface.md)。阶段页或失败部分结果不写入成功缓存；切源/翻页后的旧请求不得覆盖新页面。真实 worker、队列和共享缓存联调在目标环境单独验收。

## 离线验证与在线探针

首选[测试说明](../tests/README.md)中的 refactoring_test_settings；它隔离数据库、资源和网络。离线会话模拟、临时 Redis 的真实 Lua 与实际浏览器/站点分别记录。

在线验证须显式 opt-in，并使用当前有效页面、源对应路线、独立库/Redis/文件目录（若探针需要写入）。参数和容器命令见[脚本说明](../scripts/README.md)，当前接受边界见[验证状态](validation-status.md)。Byparr /health 可能依赖外部连通性，HTTP 200、Cookie 存在和 TCP 成功均不能替代同站非挑战业务 HTML 校验。

日志 page_fetch 记录来源、路径类型、提供方、失败分类、浏览器次数、会话版本、锁等待与耗时；scrape_job 记录队列等待和任务耗时。task_id/request_id 用于关联同一执行，检查前确认日志未包含原始 Cookie、UA 或代理凭据。生产策略/等待候选不因本地调试结果自动放行。

## 排查顺序

1. 401/CSRF 403：先核对 operator 会话、登录后轮换的 token、请求 Host/Origin，再排查业务参数。
2. 已入队无进展：核对 default/scrape/download 的 worker 订阅与 Redis；不要同时启动两个 Beat。
3. 进度或快照迟到：按任务 version 和终态读取，不用旧事件覆盖完成/取消。
4. 下载失租：核对该执行日志与当前 owner；不要手工删除另一执行的锁，不将 Redis 故障改成成功。
5. 文件/DB 状态不一致：检查 VIDEO_DIR 与持久化告警，再在隔离副本使用一致性工具；成功通知可能先于 DB 写入。

更新日期：2026-10-05。
