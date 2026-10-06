# 下载原生续传修复（2026-10-06）

## 问题与行为变化

分支 `fix/native-download-resume`，基线 `53d0e92`。重新部署后只读核查确认 60 秒请求期限已生效，但任务仍在 resume_validation：151 个缓存分片、2214 个清单分片，持续约七分钟且心跳正常。原流程在启动 CLI 前串行重新下载所有已缓存分片，上次增加超时仅改善失败收尾，没有消除重复传输。

恢复现在请求当前播放列表及 AES 密钥，保留清单/轨道/密钥身份比较；随后仅校验已登记本地完整分片的 SHA-256，删除损坏、未登记和未完成缓存，沿用稳定 job 工作区、保存名称及轨道目录，由 N_m3u8DL-RE 下载缺失分片。逐文件检查控制请求，保留暂停/终止优先级和进程退出证明。路径与 64 MiB 限制保留，清单身份变化及不支持的缓存仍要求显式终止后重新下载。视频提交前的 ffprobe、全量解码和执行归属检查保持。

依据部署版本 [v0.5.1-beta 源码](https://github.com/nilaoda/N_m3u8DL-RE/blob/v0.5.1-beta/src/N_m3u8DL-RE/Downloader/SimpleDownloader.cs#L79-L100)，原生下载器按完整文件存在复用；无需额外 resume 参数。完整本地缓存哈希检查仍由项目负责。

## 明确的安全边界

本地哈希保证缓存与暂停检查点一致，不能证明服务器在相同 URL 下未替换字节。当播放列表、轨道映射和密钥都不变时，该替换无法检出；最终解码也不能证明内容未发生替换。本修复采用已授权的身份加本地校验方案，没有增加严格远端校验开关，不承诺直播、独立音轨、fMP4、byterange 或未知加密续传。

## 验证与部署

专项回归覆盖 320 个缓存分片零远程请求、损坏/缺失/未知/未完成分片、AES 密钥变化和本地校验暂停。真实 CLI 验收从正在运行的 Docker worker 只读复制 0.5.1 二进制到临时目录，使用本地合成明文/AES HLS、隔离数据库及 loopback HTTP，核对缓存请求计数和恢复后全量解码 hash。

复验命令（后端目录）：

```bash
uv run pytest tests/ --ds=django_project.refactoring_test_settings -v
NASSAV_LOCAL_DOWNLOAD_BINARY=/绝对路径/N_m3u8DL-RE uv run pytest tests/test_local_cli_task_control.py --ds=django_project.refactoring_test_settings -q
uv run python scripts/accept_hls_validation_timeout.py
```

根目录执行 `pre-commit run -a`。完整隔离回归 726 通过、28 跳过；真实 CLI 四项通过（84.85s），恢复前至少 151 个缓存分片的请求数不增加，最终解码 hash 一致；curl 超时探针通过。较大 CLI 测试改用临时文件 SQLite，避免默认共享内存 SQLite 的并发表锁。质量门槛与范围详见[验证状态](../django_backend/doc/validation-status.md#原生下载续传修复2026-10-06)。

本地 CLI 不代表真实外站或 Docker 正式任务恢复已验收。本轮不修改正式任务、配置或服务；部署时更新后端镜像并按 Compose 文档切换 download worker。已有暂停任务的检查点字段兼容；身份一致时可直接恢复，无需删除任务或缓存。正在运行的旧执行须先暂停并确认停止，再切换版本。
