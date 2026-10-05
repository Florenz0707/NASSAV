# 前端开发契约

本轮 F1–F6 后的持续开发约束。共同设计原则见[重构原则](../../docs/development-principles.md)，阶段结果见[执行记录](refactoring-progress.md)，命令和浏览器环境见[前端 README](../README.md)。

## 职责与复用入口

| 入口                                                              | 职责与约束                                                                            |
| ----------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| views、DirectoryView、EntityDetailView                            | 路由装配与页面展示；演员/类别复用目录和详情模块，以实体适配保留差异                   |
| directoryStore、resourceList                                      | 查询、分页、加载和错误；页面取消或卸载时使旧查询失效                                  |
| api/index.js                                                      | 统一 HTTP 客户端、响应 envelope、CSRF 和登录失效；页面不重复创建客户端                |
| downloadQueue、resource store                                     | 下载队列状态和原始标题元数据；resource 保留消费者 facade，新增列表状态归 resourceList |
| websocket、scrapeJobState、scrapeJobNotifications                 | 分别管理连接/事件、资源任务快照、通知；不向连接模块添加展示规则                       |
| useExternalSearchTask、useExternalSearchSources                   | 外部搜索生命周期、来源能力与选择；页面复用既有任务协议                                |
| recommendations、RecommendationBlacklist、recommendationViewState | 推荐数据、黑名单自身读写/缓存/生命周期、视图偏好；黑名单操作不散落到父页              |
| utils/resourceTitle.js                                            | 唯一标题选择规则；消费者使用 resolveResourceTitle，队列保留原始字段以响应标题偏好变化 |

目录/详情公共模块的实体类型在生命周期内固定，同类型 ID 变化由路由监听处理。新增实体优先检查适配能力；不能仅为少数展示差异复制查询和任务流程，也不能用单一组件吞并所有无关页面。

## 视觉与交互

主题值定义在 `src/styles/main.css`，Tailwind 映射定义在 `tailwind.config.js`，入口保留显式 `@config`。独立组件不得新增十六进制、rgb/rgba 等颜色字面量；使用语义工具类或已定义 CSS token。新增 token 同时提供深浅主题并检查生成的类和实际样式，不能仅凭类名判断生效。

- 背景为 `bg-primary`、`bg-secondary`；文字为 `text-primary`、`text-secondary`、`text-muted`，不得混用背景和文字的 primary 映射。
- 主强调背景上的文字与头像开关圆点使用固定浅色 `on-accent` token（对应深色主题正文色），不随浅色主题变暗。
- 交互使用 accent 系列；危险、成功、警告和信息分别使用对应语义 token。边框使用 `--border-color` 对应默认 `border`，浅表面使用 `surface-subtle`，阴影复用预设；不新建固定白色边框或独立状态色。
- 操作按钮优先使用 `AppButton` 的 `primary`、`neutral`、`danger` 及 loading/disabled 状态；搜索、分页、下拉和确认复用 `SearchInput`、`ResourcePagination`、`CustomSelect`、`ConfirmDialog`。
- 公共组件基础样式放在合适的 CSS layer，让 Tailwind 显示、尺寸等工具类正常覆盖；新增交互同时检查移动布局与禁用状态。
- 核心图标复用 `AppIcon` 或内联 SVG，以 currentColor 跟随语义颜色并明确尺寸；不使用 Emoji 或 HTML 字符串表示功能图标。导航使用真实链接，动作使用按钮。

弹窗复用 `useDialog`：初始可见、嵌套、关闭和卸载均处理焦点、滚动锁及清理；仅最顶层响应 Escape/Tab。下拉保持键盘导航、禁用项跳过与交互属性传递。无文本按钮提供可访问名称，表单提供关联标签。设置子面板通过事件更新父状态，保持即时预览与手动保存的区别。

演员库和资源库默认每页 15 项，类别目录默认每页 18 项；桌面资源库每行三项，演员和类别目录每行五项，小屏响应式；请求 page_size、URL 默认值和占位布局同步维护。Cookie 管理仅在添加资源页按钮弹窗打开时加载，来源共享会话的后端作用范围保持不变。

## 异步、缓存与失败

所有能重入的查询明确结果归属，复用 `createRequestGuard` 或当前模块等效的版本/令牌机制。旧响应不能覆盖当前数据、错误、loading 或缓存；路由变化、实体切换、注销连接及卸载均使旧操作失效。只清除 loading 或只调用 AbortController 不能替代归属检查。

外部搜索初始居中展示开始搜索按钮，右侧设置图标打开来源弹窗；不重复展示中央标题和图标。外部搜索由按钮手动触发，进入页面、来源或排序变化不自动创建任务。取消使用后端 cancel 接口；离开页面仅清理客户端时，不能声称后台任务已取消。来源和排序来自能力接口，部分结果、失败和取消明确展示；部分结果不写入完整成功缓存，保持原实体/来源/排序缓存隔离。

外部结果默认每页 15 项，同一带令牌任务可读取不同展示页；运行时不得禁止浏览已获取结果，翻页不重启任务。源站抓取页数与展示总页数分别计算，失败和取消保留已获取结果。

HTTP 202 表示入队，成功由终态快照确认；WebSocket 是通知渠道，按现有令牌/版本查询和轮询补偿恢复状态。避免重复终态通知，并覆盖断线、迟到事件与登录失效。具体字段和后台状态以[接口文档](../../django_backend/doc/interface.md)为准。

标题优先使用用户设置的有效字段，缺失时依次回退 translated_title、source_title、original_title、title、AVID；不得在卡片、队列和推荐页分别复制回退逻辑。黑名单实体切换时，旧读写操作不得修改新列表。

## 检查与维护

改动后执行 `pnpm run check` 和根目录 `pre-commit run -a`；不使用 `build | tail` 掩盖退出码。异步或状态改动覆盖乱序响应、失败、失效和终态；视觉与公共组件改动执行相关浏览器套件。模拟套件和真实验收分别记录。新增公开 props、事件、状态方法或缓存语义时同步本文，真实协议变更同时更新后端接口说明。
