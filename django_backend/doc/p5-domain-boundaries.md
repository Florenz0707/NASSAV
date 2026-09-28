# P5 业务边界与兼容约束

本次拆分保留现有 URL、响应 envelope、Celery 任务名、数据库 schema、资源路径和 WebSocket 消息字段。按资源、下载、推荐三个域分别提交。

## 资源添加与刷新

`ResourceJobView` / `ResourceJobBatchView` 验证请求并映射 202、400、404、409、503；`scrape_jobs.submit_resource_job` 去重、排队并保存任务快照；`ResourceService.add_resource` / `refresh_resource` 组合源查询、刮削、封面、数据库和翻译；`DjangoResourcePersistence.save` 写入 AVResource、演员、类别与来源映射。输入为编号、来源及刷新选项，输出为任务快照和最终资源结果。业务异常在视图映射为原有状态码，队列异常映射为 503。资源服务会写入封面/HTML/头像，触发资源信号并提交翻译任务。

前端 `resourceApi` 发起请求，`resource` store 维护任务快照和轮询，`scrapeJobState` 按版本合并快照，`scrapeJobNotifications` 负责 UI 提示。收到较旧的 WebSocket 事件时仍忽略；刷新页面后仍用保存的状态令牌查询终态。

## 下载

待本域提交时补充实际边界与验证结果。

## 推荐

待本域提交时补充实际边界与验证结果。
