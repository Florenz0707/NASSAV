# 前端开发契约

本轮 F1–F6 后的持续开发约束。共同设计原则见[重构原则](../../docs/development-principles.md)，阶段结果见[执行记录](refactoring-progress.md)，命令和浏览器环境见[前端 README](../README.md)。

## 职责与复用入口

| 入口                                                              | 职责与约束                                                                            |
| ----------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| views、DirectoryView、EntityDetailView                            | 路由装配与页面展示；演员/类别复用目录和详情模块，以实体适配保留差异                   |
| directoryStore、resourceList                                      | 查询、分页、加载和错误；页面取消或卸载时使旧查询失效                                  |
| api/index.js                                                      | 统一 HTTP 客户端、响应 envelope、CSRF 和登录失效；页面不重复创建客户端                |
| downloadQueue、resource store                                     | 下载队列状态和原始标题元数据；resource 保留消费者 facade，新增列表状态归 resourceList |
| websocket、scrapeJobState、scrapeJobFeedback                      | 分别管理连接/事件、资源任务快照、短时提示；不向连接模块添加展示规则                   |
| useExternalSearchTask、useExternalSearchSources                   | 外部搜索生命周期、来源能力与选择；页面复用既有任务协议                                |
| recommendations、RecommendationBlacklist、recommendationViewState | 推荐数据、黑名单自身读写/缓存/生命周期、视图偏好；黑名单操作不散落到父页              |
| utils/resourceTitle.js                                            | 唯一标题选择规则；消费者使用 resolveResourceTitle，队列保留原始字段以响应标题偏好变化 |

目录/详情公共模块的实体类型在生命周期内固定，同类型 ID 变化由路由监听处理。新增实体优先检查适配能力；不能仅为少数展示差异复制查询和任务流程，也不能用单一组件吞并所有无关页面。

## 视觉与交互

主题值定义在 `src/styles/main.css`，Tailwind 映射定义在 `tailwind.config.js`，入口保留显式 `@config`。独立组件不得新增十六进制、rgb/rgba 等颜色字面量；使用语义工具类或已定义 CSS token。新增 token 同时提供深浅主题并检查生成的类和实际样式，不能仅凭类名判断生效。

- 背景为 `bg-primary`、`bg-secondary`；文字为 `text-primary`、`text-secondary`、`text-muted`，不得混用背景和文字的 primary 映射。
- ResourceCard 的 AVID 徽标使用主强调色文字和淡强调色背景；不套用实心主强调背景的浅色文字规则。
- 主强调背景上的文字与头像开关圆点使用固定浅色 `on-accent` token（对应深色主题正文色），不随浅色主题变暗。
- 交互使用 accent 系列；危险、成功、警告和信息分别使用对应语义 token。边框使用 `--border-color` 对应默认 `border`，浅表面使用 `surface-subtle`，阴影复用预设；不新建固定白色边框或独立状态色。
- 操作按钮优先使用 `AppButton` 的 `primary`、`neutral`、`danger` 及 loading/disabled 状态；搜索、分页、下拉和确认复用 `SearchInput`、`ResourcePagination`、`CustomSelect`、`ConfirmDialog`。
- 入口 main.js 必须先加载 main.css，其层级顺序为 theme / base / components / utilities；避免全局组件先定义 components 后被 preflight 覆盖。公共组件基础样式放在合适的 CSS layer，让 Tailwind 显示、尺寸等工具类正常覆盖；新增交互同时检查移动布局与禁用状态。
- 核心图标复用 `AppIcon` 或内联 SVG，以 currentColor 跟随语义颜色并明确尺寸；不使用 Emoji 或 HTML 字符串表示功能图标。导航使用真实链接，动作使用按钮。

弹窗复用 `useDialog`：初始可见、嵌套、关闭和卸载均处理焦点、滚动锁及清理；仅最顶层响应 Escape/Tab。下拉保持键盘导航、禁用项跳过与交互属性传递。无文本按钮提供可访问名称，表单提供关联标签。设置子面板通过事件更新父状态，保持即时预览与手动保存的区别。

演员库和资源库默认每页 15 项，类别目录默认每页 18 项；桌面资源库每行三项，演员和类别目录每行五项，小屏响应式；请求 page_size、URL 默认值和占位布局同步维护。Cookie 管理入口位于添加资源表单的提交按钮右侧，使用带饼干 SVG 图标的圆角矩形按钮（保留可访问名称）；仅在弹窗打开时加载，来源共享会话的后端作用范围保持不变。

任务详情保留 `/downloads` 路径。持久任务的原始快照由 taskJobs store 按稳定 job_id/version 管理，App 登录启动、登出/卸载失效并停止轮询；WebSocket 只分发版本提示，重连及可见性恢复补取快照，轮询兜底不依赖页面打开。新刮削提交委托 taskJobs，resource store 的签名快照跟踪只服务历史任务。DownloadsView 装配持久列表和旧队列兼容，TaskDetailsPanel 仅拥有筛选/选择并发出 dismiss/control；taskDetails 统一展示字段，不修改原始任务。恢复的新 attempt 不改变列表身份，旧版本响应不覆盖新快照，隐藏 ID 按登录用户保存、迟到响应不得恢复显示。

任务页显示已加载/服务器总数，加载更多；筛选及批量作用于已加载任务，不宣称所有历史均已读取。单条/批量 pause/resume/cancel 使用服务器 allowed_actions、版本和幂等 UUID，批量分组最多 100 项，冲突快照更新且逐项提示失败。网络结果未确认保留请求 UUID 重试；命令返回 pausing/cancelling 时仍等待执行器确认。终止先确认删除未提交文件、保留已提交资源；cleanup_state 与终态独立，失败可重试。已结束包含成功/失败/终止，普通批量隐藏排除清理未完成任务。不再跟踪只隐藏本浏览器列表，不等于停止后台任务；历史任务按钮禁用并说明无法控制。

DEBUG_MODE 使用独立内存样例，控制模拟过渡和停止确认，不调用真实控制 API，定时器卸载清理。深浅主题、checkbox 选择数、状态筛选最小宽度、活动时间线右对齐和列表/详情布局沿用公共组件。资源链接只在已保存/已存在资源时提供，未保存标题仍可由公开检查点摘要显示。

全局通知模块与开发预览已移除，Navbar 不提供通知入口。任务活动时间线归任务快照及 taskDetails 展示适配器，TaskTimeline 显示每次状态 / 阶段进入时间并右对齐；缺失时间明确显示未记录。普通 toast 保留既有行为。

任务页以包含翻译的整体状态筛选、统计和清理：资源已保存但翻译仍排队 / 运行 / 暂不可读时继续执行中，翻译完成后已完成，翻译失败时失败，跳过或未请求翻译允许结束；历史 Redis 刮削 state 仍只表示资源保存结果；持久 TaskJob.state 是包含所属翻译的整体状态，resource_saved 独立记录资源保存结果。列表任务列只展示 AVID，全部任务视图增加类型列，以彩色 badge 标注 scrape / download；同类型筛选隐藏类型列，资源图片与名称放在详情。自定义 TaskCheckbox 保留原生键盘与半选语义，表头与行使用同一列宽和对齐方式。单条“不再跟踪”位于列表操作列，批量已结束包括已完成和失败；详情仅保留重点色“查看资源”。持久任务的单条 / 批量结束任务调用 cancel 控制 API；仅历史无 job_id 的任务不支持控制，按钮禁用并说明原因。

## 异步、缓存与失败

所有能重入的查询明确结果归属，复用 `createRequestGuard` 或当前模块等效的版本/令牌机制。旧响应不能覆盖当前数据、错误、loading 或缓存；路由变化、实体切换、注销连接及卸载均使旧操作失效。只清除 loading 或只调用 AbortController 不能替代归属检查。

外部搜索初始居中展示开始搜索按钮，右侧设置图标打开来源弹窗；不重复展示中央标题和图标。外部搜索由按钮手动触发，进入页面、来源或排序变化不自动创建任务。取消使用后端 cancel 接口；离开页面仅清理客户端时，不能声称后台任务已取消。来源和排序来自能力接口，部分结果、失败和取消明确展示；部分结果不写入完整成功缓存，保持原实体/来源/排序缓存隔离。

外部结果默认每页 15 项，同一带令牌任务可读取不同展示页；运行时不得禁止浏览已获取结果，翻页不重启任务。源站抓取页数与展示总页数分别计算，失败和取消保留已获取结果。

HTTP 202 表示入队，成功由终态快照确认；WebSocket 是通知渠道，按现有令牌/版本查询和轮询补偿恢复状态。避免重复终态通知，并覆盖断线、迟到事件与登录失效。具体字段和后台状态以[接口文档](../../django_backend/doc/interface.md)为准。

标题优先使用用户设置的有效字段，缺失时依次回退 translated_title、source_title、original_title、title、AVID；不得在卡片、队列和推荐页分别复制回退逻辑。黑名单实体切换时，旧读写操作不得修改新列表。

## 检查与维护

改动后执行 `pnpm run check` 和根目录 `pre-commit run -a`；不使用 `build | tail` 掩盖退出码。异步或状态改动覆盖乱序响应、失败、失效和终态；视觉与公共组件改动执行相关浏览器套件。模拟套件和真实验收分别记录。新增公开 props、事件、状态方法或缓存语义时同步本文，真实协议变更同时更新后端接口说明。

任务操作列使用 eye-off SVG 表示不再跟踪，close SVG 表示结束任务，并保留可访问名称和悬停提示；批量入口使用图标加文本。复选框未选中时使用主题副文本色的加粗边框，在深浅主题中保持清晰轮廓；选中和半选继续使用主强调色。

任务状态筛选最小宽度为 8rem，切换短标签不收缩。批量操作按钮不显示选择数，计数统一放在全选复选框右侧，表头与行保持对齐。空列表使用 EmptyState 的 compact 模式（不添加内部留白），在首屏扣除应用主容器上下留白后的剩余区域居中；无 action 插槽时不保留空操作间距。阶段列仅显示统一阶段，不再附加独立翻译状态行，详情和整体任务状态继续保留翻译结果。

资源卡片、资源详情及任务详情复用 TaskResourceCover 的空 URL/加载失败占位，卡片懒加载观察本组件根元素，避免同 AVID 的多个卡片共用全局 DOM 查询。任务明细按稳定 job/task ID 选择，缺少深链参数时不主动选择任务；同 AVID 的历史任务可分别查看。任务列表支持创建时间和最近更新时间降序，store 管理排序及分页，旧排序响应不能覆盖新列表；展示层保留原始时间字段排序。

持久任务协议与后端状态所有权见[任务控制架构](../../django_backend/doc/task-control-architecture.md)。列表选择以 job_id 为准，task_id 仅标识当前执行；排序先由服务器执行再分页，不按已加载页面冒充全量排序。新增控制不得以浏览器隐藏、取消 HTTP 请求或 WebSocket 断开代替后台停止确认。

## HTML 语义与页面焦点

表单标签关联控件 id，CustomSelect 的 id/ARIA 传到内部按钮；分页提供导航名称和唯一输入 id。目录卡片使用 RouterLink 和 to，保留来源查询，动作继续使用按钮。页面实体名称是 h1，子区块按层级组织标题；展开导航使用普通链接列表，不冒用 ARIA menu。App 提供跳过导航入口，路径导航完成后恢复 main 焦点，查询参数变化不抢焦点；弹窗继续由 useDialog 管理。

## 资源交互与查询归属

ActionMenu 按实例 ref 管理菜单、方向键、Escape、外部关闭和触发器焦点恢复；不得以 AVID 全局查询 DOM。AppCheckbox 是资源/批量/任务复选框的共同基础，TaskCheckbox 保留兼容入口。资源删除由 resource.removeAsset 执行，卡片 delete/deleteFile 事件表示请求成功后的事实；父列表仅刷新/同步，不重复删除。刷新/删除选项来自 resourceActions。添加批次按 job_id 匹配当前快照，旧任务才按 task_id；推荐查询 loading/error/结果归 recommendations，旧响应及页面清空、卸载后的结果失效。

## 页面模块装配

EntityDetailView 管理实体信息与本地资源；ExternalSearchPanel 独占外部展示页缓存、签名任务生命周期与来源选择，通过 initialize/restoreCache/reset/syncLibraryStatus 及 detail/resource-saved 事件协调，隐藏不销毁后台控制语义。useResourceSubmission 接受显式资源/API/toast 依赖并拥有添加批次状态，SubmissionResults 只展示快照并发出 view。RecommendationPreferences 使用四个模型，Metrics/Seeds 消费展示输入，不发送业务请求。提取的添加/推荐样式分别以 .add-view/.recommendations-view 限定，公共主题仍在 main.css，不跨域污染；不因文件长度继续拆纯展示样式。
