# 任务控制 P0：下载停止与恢复能力验证

2026-10-06；分支 `spike/task-stop-resume-capabilities`，提交标题 `[Chore] Validate task download stop and resume capabilities`。设计见[执行计划](task-pause-cancel-design.md)。本阶段新增可重复探针与输入保护测试，不修改生产任务、数据库、Hook 配置或真实资源。

## 样例与工具归属

从本机已有构建验证镜像 `nassav-api-build-check:20261005` 的 `/app/tools/N_m3u8DL-RE` 复制二进制到临时目录。提取容器无网络、无应用挂载、未运行应用，提取后删除。镜像 ID 为 `sha256:5c7465f935a6081d808efd318ab7380241706c185f05196d91cb55de0d473185`。

- 版本：`0.5.1+c1f6db5639397dde362c31b31eebd88c796c90da`，CLI 日期 20251029。
- 二进制 SHA256：`d2fa5b4b79f243320c509a85835327a520d8c160c600d99921e764bfc519fec7`。探针拒绝其他二进制。
- ffmpeg 生成 24 秒、12 个分片的本地 HLS，另生成分片内容不同但播放列表文字相同的样例。
- HTTP 只监听回环地址，移除下载器继承的代理并禁用更新检查；无来源站点、Cookie、正式 DB/Redis 或实际视频参与。
- CLI 串行下载，服务端记录分片请求；重启结果使用严格 ffmpeg 解码和视频像素 SHA256，与完整下载基线比较。
- 停止使用当前 Adapter 的 POSIX TERM/wait/KILL 进程组序列，检查 `/proc` 中同组非僵尸进程，不把父进程退出当作后代退出。

两轮最终有效样例保存在 [第一轮](task-control-probes/p0-first.json)和[第二轮](task-control-probes/p0-second.json)。这些报告使用合成媒体，仅证明当前工具在该受控环境的能力。

## 结论

| 检查                    | 结果及实施要求                                                                                                  |
| ----------------------- | --------------------------------------------------------------------------------------------------------------- |
| 下载途中停止            | 确认无存活 writer，已完成分片保留；停止耗时见逐项 JSON，不作为线上 SLA                                          |
| 相同内容重启            | 至少 4 个完整分片未再次请求，最终解码像素与基线相同                                                             |
| 播放列表 URL 更换 token | 受控相同内容仍复用至少 4 个分片；这不证明任意真实签名 URL 更新都安全                                            |
| 损坏缓存负向对照        | 原生按文件名复用会产生与基线不同的输出；CLI 成功退出不足以证明视频正确                                          |
| 校验后恢复              | 依据已记录 checksum 删除损坏的私有缓存分片，再下载得到基线一致的视频                                            |
| 内容变化负向对照        | 播放列表文字相同也可能对应不同视频；原目录复用会混入旧分片                                                      |
| 内容变化安全处理        | 使用新工作区重新下载，与新内容基线一致；身份不确定时禁止直接复用                                                |
| 合并中断                | ffmpeg 包装器在正式合并调用中写入未完成输出并阻塞，进程组停止后删除该私有未提交输出，再重启合并，结果与基线一致 |

恢复能力可继续进入 P1，但 P2/P3 必须实现分片清单、完整性检查、内容归属及未提交输出清理。禁止只把同一 tmp-dir 传给 CLI 就宣称安全续传。新播放列表的 URI、轨道、分片映射/长度/强校验信息变化或无法确认原内容时，保留暂停并提示需要从下载阶段重新开始；不得静默拼接。

探针里的 checksum 来自已知有效的合成分片，不能代替生产中首次建立可信检查点的协议。生产清单不得把“停止时文件存在”视为完整分片，需结合完成标志、媒体校验及可用来源校验信息。URL 更新的内容身份策略在 P3 接入来源时进一步验收。

## 刮削停止期限与扫描核对

当前来源/刮削 HTTP 的默认 timeout 为 15 秒，头像有 3 次重试；翻译默认 30 秒，可被配置覆盖。Byparr 控制请求使用 `(5, timeout_ms / 1000 + 10)`。`ScraperManager` 的 `cache.set(..., timeout=3600)` 是缓存有效期，已纠正设计文档误写。以上是源码核对值，并非实测停止 SLA；外部调用尚不接收任务控制。

同步阻塞请求只能在返回后检查控制；逐次请求 timeout 不等于全流程墙钟期限，慢流和重试须在 P4 添加阶段期限及分块检查。P0 没有调用真实 Byparr/翻译或来源，因此不宣称其目标环境停止时延已验收。

视频/资源一致性检查读取正式 AVID 文件或顶层 glob，`.tasks` 目录目前不会被这些规则当作视频；备份同步 `sync_backups.py` 的递归复制不会自动排除私有目录。P2 必须加入明确排除并覆盖测试，禁止将暂存产物同步成正式资源。

## 可重复命令与质量门槛

从 `django_backend` 运行，工作目录必须不存在；日志及生成媒体仅写入新建目录：

```bash
uv run python scripts/probe_task_download_control.py \
  --binary /tmp/nassav-task-control-p0/tools/N_m3u8DL-RE \
  --workspace /tmp/nassav-task-control-p0/new-run
uv run pytest tests/ --ds=django_project.refactoring_test_settings -v
uv run pytest tests/test_probe_task_download_control.py \
  --ds=django_project.refactoring_test_settings -v
# 仓库根目录
pre-commit run -a
```

全套后端隔离测试 561 passed、24 skipped；随后新增探针输入保护测试 2 passed。两轮本地 CLI 能力探针通过；第一轮 8 项、第二轮增加基线解码检查为 9 项。根目录 pre-commit 通过后提交。尚未进行非 eager worker 联调、生产数据迁移、真实来源下载或浏览器操作验收。

初始探索遇到零宽度输出窗口导致 Spectre.Console 崩溃，设置 `COLUMNS=120`、`LINES=40` 后探针可稳定运行；P3 需要相同的显式 CLI 输出环境。早期探针修正了输出扩展名与 ffmpeg 媒体信息/合并调用的区分，失败探索未计入最终有效样例。
