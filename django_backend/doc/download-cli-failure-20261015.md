# 下载器退出零但无输出的定位与修复（2026-10-15）

## 真实症状与原因边界

P8完整下载使用用户指定的新下载备选Jable MIMK-079，独立PostgreSQL/资源副本、真实HTTP/原生Celery和来源；不写实际实例，不重启用户服务。此前DASS-839只读本地播放已经通过，不把旧视频当新共享发布证据。

原失败job `6637aa8a-7ea1-48eb-9032-0c1954490977`暂停恢复后报告“未找到输出文件”。另一次完整重放job `548245c2-86ea-4db2-929a-bdf5e1f5e1ed`在专用临时包装器保留私有CLI输出后确认：CDN多次HTTP 428，1437个分片仅取得1241个，CLI报告Segment count check not pass/Failed，却仍退出0。没有进入合并、全量媒体校验或版本发布；任务正确失败并清理。原日志丢弃CLI行使诊断退化，不能据“未找到输出”推断是命名或合并问题。

HTTP 428本身不证明限流。仅将分片并发从32改4的实际对照未再记录428，并取得全部分片、进入合并及完整校验；本地可控“四请求上限”也能用32稳定失败、4通过。该证据支持采用较保守默认值，不保证所有CDN/网络窗口行为相同。

离线曾构造1437分片/1024句柄的另一种同症状：FFmpeg合并报Too many open files而CLI退出0；不符合本次真实分片失败阶段，不将它误认根因，也没有为此切换合并协议或修改宿主机ulimit。

## 行为变化

- 默认分片并发32→4，旧VideoDownloadService移除固定32；显式thread_count参数仍有效。未新增运行配置、修改用户.env、代理或凭证，不改变全局下载槽位和Celery数量。
- 检测CLI内部的分片校验失败/明确Failed标记，即使退出0且存在旧输出也拒绝成功。受控调用抛出安全RuntimeError，进入既有失败/停止/清理协议；旧兼容调用返回false。
- 诊断不保存原始CLI行，只解析最多8个HTTP状态码、有限长度的分片数量及固定系统错误类别。本次诊断日志与安全任务错误不含源URL、Cookie、User-Agent、命令行或原站响应。
- 不跳过分片完整性、不自动换来源/凭证/代理、不增加无限重试。媒体仍须通过现有轨道/时长/完整解码校验后发布；暂停/取消、generation及writer停止条件不变。

## 回归与验证

分支`fix/shared-download-output-diagnostics`，基线45348ae；用户授权独立定位修复再继续P8。四项隔离回归在修复前失败，覆盖退出零/缺分片、旧输出及受控/兼容结果，修复后通过。

```bash
cd django_backend
uv run pytest tests/test_download_cli_diagnostics.py tests/test_download_cli_cancellation.py tests/test_download_proxy_isolation.py tests/test_n_m3u8dl_re_progress.py --ds=django_project.refactoring_test_settings -q
NASSAV_LOCAL_DOWNLOAD_BINARY=/absolute/path/to/pinned/N_m3u8DL-RE uv run pytest tests/test_download_cli_diagnostics.py tests/test_local_cli_task_control.py tests/test_download_proxy_isolation.py tests/test_download_cli_cancellation.py tests/test_n_m3u8dl_re_progress.py --ds=django_project.refactoring_test_settings -q
uv run pytest tests/ --ds=django_project.refactoring_test_settings -v
```

固定原有v0.5.1-beta二进制专项22 passed（92.17秒），只使用本地生成HLS与临时文件/数据库，涵盖实际HTTP 428诊断、四并发限制和明文/AES暂停恢复；未把它当真实CDN或目标库验收。完整隔离后端1345 passed、30 skipped（415.04秒）；其中两项新增原生CLI用例默认跳过，另以固定二进制22项组合显式通过。完整pre-commit全部通过，最终文档收尾后再次执行。最终P8默认调用重验另记，不能以参数包装器对照替代。

真实源重放与并发对照使用私有验收副本；原始CLI仅保留在0700目录/0600文件，不提交到Git，持久keyring只读且不复制到证据目录。最终服务与文件清理、实际默认调用重验按P8记录单列。

并发4真实对照job `6aa7def7-4085-407c-8cf8-cc8ebb6d80f6`完整下载、暂停恢复、全量解码、共享视频版本发布及固定版本本地HTTP 206全部通过，454.0秒，峰值1,781,908,581字节，未触及5 GiB预算。两个账号指向同一视频版本。副本及服务已停止/清理，私有证据`django_backend/backup/p8-real-source-20261015T134405Z/`保存失败/成功对照和原CLI诊断，不保存大视频。该对照通过包装器仅改变并发，随后正式默认重验同样通过：全新副本、原固定二进制、无包装器，446.2秒，完整下载/暂停恢复/全量解码/共享发布/本地206及真实视频GC完成。最新范围和清理见[P8验收](multi-user-p8-public-acceptance-20261015.md)。
