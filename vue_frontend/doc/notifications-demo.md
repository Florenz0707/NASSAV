# 通知设计 Demo

本轮只实现开发预览，不建设正式通知历史、未读同步或推送能力。初始设想见[通知时间线提案](notification-timeline-concept.md)。

从前端目录运行：

```bash
pnpm demo:notifications
```

沿用现有 `/downloads` 页面、应用导航和登录流程，通过开发环境预览参数进入：

- `/downloads?demo=notifications&variant=panel`：A，铃铛入口打开侧栏时间线，小屏全宽。
- `/downloads?demo=notifications&variant=timeline`：B，通知中心按今天、昨天排列时间线。
- `/downloads?demo=notifications&variant=grouped`：C，按需要处理和完成消息分组。

底部按钮或左右方向键切换，URL 保留选项；输入框及弹窗中不拦截方向键。支持全部 / 未读 / 需要处理筛选、单条及全部已读、批量失败展开、关联详情演示和重置。标为已读不会把失败改为已解决。

四条事件全部是虚构样例，时间和 AVID 也只用于演示。查看任务 / 资源 / 批次仅选中本页关联详情，不操作或跳转真实任务。状态保存在组件内存，不写 localStorage、store 或后端；离开预览会清空状态。通知侧栏复用 useDialog，支持 Escape、焦点循环与恢复、滚动锁和卸载清理。

Demo 动态组件仅在 `import.meta.env.DEV` 加载，生产构建不含 NotificationsDemo、NotificationDemoTimeline 或 PrototypeSwitcher。生产环境即使带上述参数，仍呈现正式任务页。预览期间 DownloadsView 停止自身下载队列读取 / 轮询；退出预览恢复正常读取，并拒绝迟到响应。应用原有全局 WebSocket、刮削跟踪不因预览而改变。

本 Demo 用于确定通知入口和消息密度；真实事件来源、历史保存、用户归属、已读同步、失败后恢复及批次聚合仍需后续设计。模拟消息不能用作真实下载、刮削或翻译已完成的证据。
