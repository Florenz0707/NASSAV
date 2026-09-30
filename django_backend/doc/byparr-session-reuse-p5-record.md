# Byparr 会话复用 P5 验证记录

日期：2026-09-30。状态：**Jable 首批准入 NO-GO；未切换运行策略，未启动 24 小时灰度。** 对应[执行计划](byparr-session-reuse-execution-plan.md)。本记录只包含脱敏状态、时段和指标；52 条逐项结果见[现场证据 JSONL](byparr-session-reuse-p5-field-evidence.jsonl)，不含 Cookie、完整 UA、代理 URL、出口 IP 或完整页面。

## 环境与代码核对

- 工作树从 `idle` 的 `a0768a5` 创建。API 容器的 Jable、MissAV、页面服务与刷新协调源码 SHA-256 均与该工作树一致；正式 `nassav-byparr-1` 镜像 digest 为 `sha256:874f719518f617d03a60e03411fc5d090647e1a877041e81f8dc965927c7deb6`。未使用名称相似的独立试验容器。
- 从 API 容器读取的有效配置：PostgreSQL、Byparr 和代理启用；`BrowserFetch.session_reuse_enabled=false`；Jable 为 `browser_first`，MissAV 配置为 `direct_first`，因全局开关关闭，目前也按 `browser_first` 执行。**未来若打开开关，须先同时将 MissAV 改为 `browser_first`**，再仅把 Jable 改为 `direct_first`；配置变更后重启 API 和持有 Source 实例的 worker。
- 现场探测均由正式 `nassav-api-1` 容器发起。出口查询服务返回的直连纯文本与 Byparr HTML 内容经解析为有效 IP 后，3 组配对 **3/3 相同**，IP 本身未记录。首次直接比较整段 HTML 得到 0/3 是格式误报，已纠正；该检查仍不能证明不同目标域名或未来时段不会轮换出口。
- 没有修改正式配置、`SourceCookie`、Redis 锁或任务队列，也未部署此分支。下述预筛脚本只在进程内保存 Cookie+UA，页面请求不走正式 API/worker 的共享会话写入路径；因此不能把预筛结果当作协调链路灰度通过。

## 隔离验证

| 项目             | 环境                                                                                                                          | 结果                                                            |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| SQLite 全套      | Python 3.12、`config/config.example.yaml`、隔离 `.env`/数据库/资源目录，`uv run pytest tests/ -v`                             | 395 passed、13 skipped；跳过项包括显式 opt-in 的在线测试        |
| 空 PostgreSQL    | `/tmp` 下 PostgreSQL 16 独立实例与空库，`uv run python manage.py migrate --noinput`                                           | 全部迁移成功，含 `nassav.0021_sourcecookie_session_metadata`    |
| 旧 Cookie 与并发 | 隔离 PostgreSQL 测试库，运行 `test_source_cookie_session.py`、`test_browser_session_reuse.py`、`test_session_coordination.py` | 43 passed；其中旧行从 0020 升到 0021 后 Cookie 不变、新字段为空 |
| Redis 租约       | `/tmp` 下独立 Redis 端口与库，运行真实 `RedisRefreshStore`                                                                    | 占锁、续租、错误 owner 禁止释放、结果和不可复用标记检查通过     |
| 配置样例路径     | 最新提交将 `template-config.yaml` 改为 `config.example.yaml`；本分支修正测试和说明，并补齐 pyright 所需开发类型桩             | 相关 20 项通过；干净虚拟环境 `pyright` 通过                     |
| 仓库检查         | 仓库根目录 `pre-commit run -a`                                                                                                | 全部检查通过，包含 pyright、后端编译及前端构建/检查             |

上述旧行是测试生成的样本，不是正式 PostgreSQL 数据副本。正式数据副本恢复/迁移、真实 Redis 跨进程联调和 worker 并发验收没有执行；首批门槛已失败，因此不进行生产切换。

## Jable 两时段只读预筛

探针先用 Byparr 验证 `/latest-updates/` 页面，从中得到 24 个当前详情链接；每窗口取得一组通过同页、同站点、非挑战和 Jable 业务结构校验的浏览器 Cookie+UA，且必须在 3 秒内对种子页直连 HTTP 200。之后用同一会话在 20 个不同详情页先直连，失败才以 Byparr 取回并重新校验页面。每个页面结果均无缓存命中，浏览器内容有效；所有失败的直连为 HTTP 403。脚本不读写 Cookie 表。W2 前两个有效浏览器种子页的 Cookie+UA 同页探测均为 403，第三个种子才通过。

| 时段（北京时间） | 有效详情 | 暖会话直连有效 | 403→Byparr 有效 | 浏览器次数 | 暖请求 P95 | 回退 Byparr 中位数 |
| ---------------- | -------: | -------------: | --------------: | ---------: | ---------: | -----------------: |
| W1，09:32–09:37  |    20/20 |   10/20（50%） |           10/10 |         10 |  33.394 秒 |          23.664 秒 |
| W2，09:40–09:47  |    20/20 |   12/20（60%） |             8/8 |          8 |  62.709 秒 |          30.232 秒 |

首批门槛要求暖会话有效页率至少 95%、暖请求 P95 小于 5 秒且低于同环境 Byparr 中位数的 25%。两个窗口的有效率和 P95 均不达标。没有观察到挑战或错误页误判成功，但不能据此推断所有反向场景都安全。另取一个不存在详情和一个无匹配搜索作为在线反向样本，Byparr 提供方均返回 200，业务校验均报 `page_mismatch`，未将其算作有效页；Byparr 不提供可靠目标 HTTP 状态，不能将提供方 200 写成目标 404。403、200 挑战、错域、结构变化等分类另有离线契约测试。

## 判定与后续门槛

**NO-GO：保持 Jable `browser_first`，复用开关继续关闭；MissAV 不切换。** 现阶段无需为此开启 24 小时灰度、并发 2 的正式 worker 或正式数据恢复演练。若将来代理/站点条件变化，先重做相同的两窗口预筛；只有达到计划中的 95% 有效页率、零错误页误判、双重 P95 阈值，以及更新后 10 个不同页面至多一次 Byparr 刷新，才准备备份和配置变更，再进行 API/worker 并发、任务/下载/WebSocket 回归及至少 24 小时观察。回滚时关闭开关、恢复 `browser_first`、重启 API/worker，保留 Cookie 表和新增可空列。
