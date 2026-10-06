# 旧正式资源权限兼容修复（2026-10-06）

## 定位与变更

分支 `fix/legacy-resource-publication-permissions`，基线 `346d758`，提交标题 `[Fix] Back up legacy read-only assets before publication`。

实际 scraper 已以 UID1000 运行，资源目录 1000:1000 755，但 SNOS-317.html 仍是 root:root 644。箭头式报错来自 os.link 创建回滚备份，而不是符号链接挂载或 os.replace。真实 Docker fixture 复现 protected_hardlinks=1 时 UID1000 对 root 属主只读旧文件硬链接返回 EPERM；[Linux 官方说明](https://docs.kernel.org/admin-guide/sysctl/fs.html#protected-hardlinks)解释非属主且没有读写权限的限制。

上次修复仅覆盖运行目录与私有文件，遗漏了正式文件与覆盖旧文件的验收；保留该记录的历史范围，本次补齐。可以继续使用 deploy-data/resource 指向 django_backend/resource 的符号链接，权限修复工具传入人工核对的 realpath。

TaskAssets 在持久 journal 准备后、DB write fence 外创建旧文件备份：先尝试硬链接，仅对 EPERM/EACCES/EXDEV/EOPNOTSUPP 使用独立复制，O_NOFOLLOW 打开文件，分块检查控制/归属，校验 SHA 并原子发布备份。复制中的临时文件不是有效备份，失败/暂停删除临时副本，正式文件与已校验新私有资产保持；备份已完成但发布未开始时，不以独立副本替换原正式 inode；磁盘错误不静默回退。自身硬链接产生 ctime 变化后更新短提交的 fingerprint，仍检查 inode/大小/mtime/checksum 和最终归属。正式替换及 DB 回调仍在 fence 内，DB 失败使用已校验备份回滚。

权限工具增加显式 include-published 迁移选项，默认检查范围保持；整批离线迁移仍要求操作者确认所有写入者停止，不跟随链接、不改变文件内容或 inode、不修改 Redis/Ollama 卷或密码文件。

## 验证

测试先复现硬链接备份失败，再验证修复。专项覆盖发布、DB 失败回滚、复制中暂停、磁盘失败、正式文件 opt-in 迁移和链接拒绝。真实 Docker UID1000、network none、临时 SQLite/root:root 644 文件使用完整 TaskAssets 流程，最终复验以与用户相同的符号链接为挂载源，实际内核三次 EPERM 后发布、失败回滚及发布前暂停保留原 inode 均通过，不仅是 mock。

完整门槛从后端执行 `uv run pytest tests/ --ds=django_project.refactoring_test_settings -v`，根目录执行 `pre-commit run -a`；专项 40 通过，完整隔离回归 743 通过、28 跳过（85.14s），pre-commit 全通过；数字与状态见[验证状态](../django_backend/doc/validation-status.md)。隔离 fixture 不属于真实外站抓取或正式发布验收。

## 现场处理

实际目录有 110 个 root 属主、nlink=1 的正式文件：cover 中 10 个 HTML/封面、video 中 1 个视频、recommendation_cover 中 99 个封面。通过当前镜像的公共 resource_file_locks，在每个资源锁及与 TaskAssets 相同的目标路径 SHA 锁中逐个修复属主和 owner 读写权限；以 UID1000 创建锁，升权仅用于既有文件 chown/chmod。修改前重查 inode/属主/普通文件/nlink，修改后确认 inode、大小、mtime 保持，未写入、复制或删除任何正式媒体。此次按锁限定现场操作，不是对离线权限工具作虚假的 writers-stopped 断言。

SNOS-317.html 与同类文件已为 1000:1000，当前应用可读写；所有服务继续运行，未重启、未改任务状态、未自动重新抓取失败任务。未来更新镜像后才应用兼容备份代码；失败任务需重新提交，不能把仅权限变更当作正式刮削已成功。
