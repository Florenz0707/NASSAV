# P5 业务边界与兼容约束

本次拆分保留现有 URL、响应 envelope、Celery 任务名、数据库 schema、资源路径和 WebSocket 消息字段。按资源、下载、推荐三个域分别提交。

## 资源添加与刷新

`ResourceJobView` / `ResourceJobBatchView` 验证请求并映射 202、400、404、409、503；`scrape_jobs.submit_resource_job` 去重、排队并保存任务快照；`ResourceService.add_resource` / `refresh_resource` 组合源查询、刮削、封面、数据库和翻译；`DjangoResourcePersistence.save` 写入 AVResource、演员、类别与来源映射。输入为编号、来源及刷新选项，输出为任务快照和最终资源结果。业务异常在视图映射为原有状态码，队列异常映射为 503。资源服务会写入封面/HTML/头像，触发资源信号并提交翻译任务。

前端 `resourceApi` 发起请求，`resource` store 维护任务快照和轮询，`scrapeJobState` 按版本合并快照，`scrapeJobNotifications` 负责 UI 提示。收到较旧的 WebSocket 事件时仍忽略；刷新页面后仍用保存的状态令牌查询终态。

## 资源删除与旧批量兼容

`DeleteResourceView`、`DownloadsView.delete` 和 `ResourcesBatchView` 只校验输入并映射响应；`ResourceDeletionService` 在同一 AVID 文件锁下定位封面、缩略图、视频、备份文件，并经 `DjangoResourceDeletionRepository` 删除资源行或清除视频状态。单条与批量全删共用该操作。文件先于数据库删除；任一步失败报告阶段和已确认删除的文件名，调用方可重试，且不会把部分完成报告为成功。空状态返回 404。锁文件位于封面目录的同级 `.nassav-delete-locks`，由 API 实例共享资源挂载。

旧 `/resources/batch` 的 `add`、`refresh` 仍是同步兼容入口，流程由 `legacy_batch` 操作类承载，保留逐项响应；前端正常新增/刷新走异步任务入口。原有固定 2 秒等待缺少来源限流依据，已移除；兼容入口去留待外部调用方核对。

## 下载

下载 API 验证编号并通过 `submit_download_task` 去重入队；`nassav.tasks.download_video_task` 持有全局锁、更新 Redis 队列和进度、发送原有 WebSocket 事件并处理重试；`video_download_service` 执行网络下载并写入 MP4；`DjangoDownloadPersistence` 按 MP4 是否存在更新 AVResource 的文件大小、存在状态和保存时间。任务输入为编号，输出仍为原有成功/失败字典。下载或持久化异常仍按任务已有重试/告警路径处理，锁和进度在 finally 中清理。文件路径仍是 `VIDEO_DIR/<AVID>.mp4`；失败标记只清除 `file_exists`，保留之前的文件大小字段。针对性测试覆盖文件存在、文件缺失和失败状态。

## 推荐

推荐 API 视图校验参数并映射响应；`recommender_manager` 执行推荐策略，现有反馈与种子 profile 仓库写入学习状态；`DjangoAvidBlocklistRepository` 查询、分页、写入和删除资源黑名单及关联资源标题。`RecommendationCoverCacheService` 仍管理封面代理与文件缓存。输入为筛选参数、快照编号/反馈类型或屏蔽编号，输出保持原有推荐结果、分页及反馈 envelope；无效参数和不存在的屏蔽记录仍返回 400/404。

前端 `recommendations` store 拥有结果、种子、指标、反馈和屏蔽状态，集中调用现有 API；页面保留筛选项、展示、路由、会话存储和 UI 提示。追加推荐按 AVID 去重，反馈提交后更新本地状态；页面销毁时保存视图状态，重新进入时仍恢复推荐项和滚动位置。推荐接口与页面状态测试覆盖批次合并、反馈、重置和屏蔽列表。
