# 前端开发契约

本轮 F1–F6 后的持续开发约束。共同设计原则见[仓库开发规范](../../AGENTS.md)，阶段结果见[执行记录](refactoring-progress.md)，命令和浏览器环境见[前端 README](../README.md)。

## 职责与复用入口

| 入口                                                              | 职责与约束                                                                            |
| ----------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| views、DirectoryView、EntityDetailView                            | 路由装配与页面展示；演员/类别复用目录和详情模块，以实体适配保留差异                   |
| directoryStore、resourceList                                      | 查询、分页、加载和错误；页面取消或卸载时使旧查询失效                                  |
| api/client.js、api/index.js                                       | client 唯一 HTTP 实例及 envelope/CSRF/登录失效；index 保留领域 API 导出               |
| downloadQueue、resource store                                     | 下载队列状态和原始标题元数据；resource 保留消费者 facade，新增列表状态归 resourceList |
| websocket、scrapeJobState、scrapeJobFeedback                      | 分别管理连接/事件、资源任务快照、短时提示；不向连接模块添加展示规则                   |
| useExternalSearchTask、useExternalSearchSources                   | 外部搜索生命周期、来源能力与选择；页面复用既有任务协议                                |
| recommendations、RecommendationBlacklist、recommendationViewState | 推荐数据、黑名单自身读写/缓存/生命周期、视图偏好；黑名单操作不散落到父页              |
| features/resources/lib/resourceTitle.js                           | 唯一标题选择规则；消费者使用 resolveResourceTitle，队列保留原始字段以响应标题偏好变化 |

目录/详情公共模块的实体类型在生命周期内固定，同类型 ID 变化由路由监听处理。新增实体优先检查适配能力；不能仅为少数展示差异复制查询和任务流程，也不能用单一组件吞并所有无关页面。

## 视觉与交互

主题值定义在 `src/styles/main.css`，Tailwind 映射定义在 `tailwind.config.js`，入口保留显式 `@config`。独立组件不得新增十六进制、rgb/rgba 等颜色字面量；使用语义工具类或已定义 CSS token。新增 token 同时提供深浅主题并检查生成的类和实际样式，不能仅凭类名判断生效。

- 背景为 `bg-primary`、`bg-secondary`；文字为 `text-primary`、`text-secondary`、`text-muted`，不得混用背景和文字的 primary 映射。
- ResourceCard 的 AVID 徽标使用主强调色文字和淡强调色背景；不套用实心主强调背景的浅色文字规则。
- 详情操作使用 coral 下载、teal 播放（包括已下载资源的路径入口），保持等宽等高；coral/teal 的 hover、pressed 由公共主题 token 提供更深的填充，不用页面样式覆盖 loading/disabled。
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

全局通知模块与开发预览已移除，Navbar 不提供通知入口。任务活动时间线归任务快照及 taskDetails 展示适配器，TaskTimeline 显示每次状态 / 阶段进入时间并右对齐；缺失时间明确显示未记录。共享任务 toast 由 userOperations 接受的本人版本快照驱动：命令提交显式标记 submitted，提示排队或当前结果；已知任务后续状态变化提示执行、成功、失败或本人撤销，首次历史载入保持安静，同状态阶段推进、重复与旧版本不重复提示。taskTimeline 统一共享请求、持久任务与历史刮削的阶段中文映射；区分下载/刮削的开始与本人请求撤销，未知阶段使用中文状态或“正在处理”，不直接展示原始英文代码，不改写事件顺序和服务器时间。

任务页以包含翻译的整体状态筛选、统计和清理：资源已保存但翻译仍排队 / 运行 / 暂不可读时继续执行中，翻译完成后已完成，翻译失败时失败，跳过或未请求翻译允许结束；历史 Redis 刮削 state 仍只表示资源保存结果；持久 TaskJob.state 是包含所属翻译的整体状态，resource_saved 独立记录资源保存结果。列表任务列只展示 AVID，全部任务视图增加类型列，以彩色 badge 标注 scrape / download；同类型筛选隐藏类型列，资源图片与名称放在详情。自定义 TaskCheckbox 保留原生键盘与半选语义，表头与行使用同一列宽和对齐方式。单条“不再跟踪”位于列表操作列，批量已结束包括已完成和失败；详情仅保留重点色“查看资源”。持久任务的单条 / 批量结束任务调用 cancel 控制 API；仅历史无 job_id 的任务不支持控制，按钮禁用并说明原因。

## 异步、缓存与失败

所有能重入的查询明确结果归属，复用 `createRequestGuard` 或当前模块等效的版本/令牌机制。旧响应不能覆盖当前数据、错误、loading 或缓存；路由变化、实体切换、注销连接及卸载均使旧操作失效。只清除 loading 或只调用 AbortController 不能替代归属检查。

外部搜索初始居中展示开始搜索按钮，右侧设置图标打开来源弹窗；不重复展示中央标题和图标。外部搜索由按钮手动触发，进入页面、来源或排序变化不自动创建任务。取消使用后端 cancel 接口；离开页面仅清理客户端时，不能声称后台任务已取消。来源和排序来自能力接口，部分结果、失败和取消明确展示；部分结果不写入完整成功缓存，保持原实体/来源/排序缓存隔离。

外部结果默认每页 15 项，同一带令牌任务可读取不同展示页；运行时不得禁止浏览已获取结果，翻页不重启任务。源站抓取页数与展示总页数分别计算，失败和取消保留已获取结果。

HTTP 202 表示入队，成功由终态快照确认；WebSocket 是通知渠道，按现有令牌/版本查询和轮询补偿恢复状态。避免重复终态通知，并覆盖断线、迟到事件与登录失效。具体字段和后台状态以[接口文档](../../django_backend/doc/interface.md)为准。

标题优先使用用户设置的有效字段，缺失时依次回退 translated_title、source_title、original_title、title、AVID；不得在卡片、队列和推荐页分别复制回退逻辑。黑名单实体切换时，旧读写操作不得修改新列表。

## 检查与维护

### 编辑器与提交格式化

从仓库根目录打开 VS Code，安装 Prettier 扩展并先执行 `cd vue_frontend && pnpm install --frozen-lockfile`。仓库提交的 `.vscode/settings.json` 为 Vue 显式指定 `esbenp.prettier-vscode`，覆盖个人设置中的 Volar 格式化器；Volar 仍可提供 Vue 语言服务。编辑器与 pre-commit 均使用 `vue_frontend/node_modules/prettier` 和根 `.prettierrc`，版本由前端锁文件统一管理，不再单独安装镜像钩子的 Prettier。其他 VS Code 本地文件保持忽略。

保留现有规则：无分号、单引号、100 列、2 空格和 ES5 尾逗号。钩子继续检查全部文本文件并跳过无法识别的格式；在仓库根目录执行 `pre-commit run prettier -a` 可单独验证。修改规则或升级 Prettier 时同时验证编辑器与提交输出，避免使用两种格式化器轮流修改 Vue 模板。

改动后执行 `pnpm run check` 和根目录 `pre-commit run -a`；不使用 `build | tail` 掩盖退出码。异步或状态改动覆盖乱序响应、失败、失效和终态；视觉与公共组件改动执行相关浏览器套件。模拟套件和真实验收分别记录。新增公开 props、事件、状态方法或缓存语义时同步本文，真实协议变更同时更新后端接口说明。

任务操作列使用 eye-off SVG 表示不再跟踪，close SVG 表示结束任务，并保留可访问名称和悬停提示；批量入口使用图标加文本。复选框未选中时使用主题副文本色的加粗边框，在深浅主题中保持清晰轮廓；选中和半选继续使用主强调色。

任务状态筛选最小宽度为 8rem，切换短标签不收缩。批量操作按钮不显示选择数，计数统一放在全选复选框右侧，表头与行保持对齐。空列表使用 EmptyState 的 compact 模式（不添加内部留白），在首屏扣除应用主容器上下留白后的剩余区域居中；无 action 插槽时不保留空操作间距。阶段列仅显示统一阶段，不再附加独立翻译状态行，详情和整体任务状态继续保留翻译结果。

资源卡片、资源详情及任务详情复用 ResourceCover 的空 URL/加载失败占位，卡片懒加载观察本组件根元素，避免同 AVID 的多个卡片共用全局 DOM 查询。任务明细按稳定 job/task ID 选择，缺少深链参数时不主动选择任务；同 AVID 的历史任务可分别查看。任务列表支持创建时间和最近更新时间降序，store 管理排序及分页，旧排序响应不能覆盖新列表；展示层保留原始时间字段排序。

持久任务协议与后端状态所有权见[任务控制架构](../../django_backend/doc/task-control-architecture.md)。列表选择以 job_id 为准，task_id 仅标识当前执行；排序先由服务器执行再分页，不按已加载页面冒充全量排序。新增控制不得以浏览器隐藏、取消 HTTP 请求或 WebSocket 断开代替后台停止确认。

## HTML 语义与页面焦点

表单标签关联控件 id，CustomSelect 的 id/ARIA 传到内部按钮；分页提供导航名称和唯一输入 id。目录卡片使用 RouterLink 和 to，保留来源查询，动作继续使用按钮。页面实体名称是 h1，子区块按层级组织标题；展开导航使用普通链接列表，不冒用 ARIA menu。App 提供跳过导航入口，路径导航完成后恢复 main 焦点，查询参数变化不抢焦点；弹窗继续由 useDialog 管理。

## 资源交互与查询归属

ActionMenu 按实例 ref 管理菜单、方向键、Escape、外部关闭和触发器焦点恢复；不得以 AVID 全局查询 DOM。AppCheckbox 是资源/批量/任务复选框的共同基础，TaskCheckbox 保留兼容入口。资源删除由 resource.removeAsset 执行，卡片 delete/deleteFile 事件表示请求成功后的事实；父列表仅刷新/同步，不重复删除。刷新/删除选项来自 resourceActions。添加批次按 job_id 匹配当前快照，旧任务才按 task_id；推荐查询 loading/error/结果归 recommendations，旧响应及页面清空、卸载后的结果失效。

## 页面模块装配

EntityDetailView 管理实体信息与本地资源；ExternalSearchPanel 独占外部展示页缓存、签名任务生命周期与来源选择，通过 initialize/restoreCache/reset/syncLibraryStatus 及 detail/resource-saved 事件协调，隐藏不销毁后台控制语义。useResourceSubmission 接受显式资源/API/toast 依赖并拥有添加批次状态，SubmissionResults 只展示快照并发出 view。RecommendationPreferences 使用四个模型，Metrics/Seeds 消费展示输入，不发送业务请求。提取的添加/推荐样式分别以 .add-view/.recommendations-view 限定，公共主题仍在 main.css，不跨域污染；不因文件长度继续拆纯展示样式。

## 模块归档与依赖

代码位置遵循[模块布局](module-layout.md)。资源封面占位使用 shared/ui/ResourceCover；TaskCheckbox 是 AppCheckbox 的任务兼容包装。不要恢复 components/stores/utils 大杂烩目录；跨模块通过明确的组件、store 或纯函数入口协作，不穿透子组件 DOM 或内部状态。领域 API 文件复用 api/client.js，禁止自行创建第二个 Axios 实例。目录迁移保持 URL、请求方法/字段、任务协议和存储键。

资源详情的完整封面使用 ResourceCover naturalSize 模式，在最大可用尺寸内按原比例居中，图片自身有圆角，成功加载时不显示底色框；失败仍保留原占位。ActionMenu 通过 triggerClass 接收触发按钮布局类，尺寸不传给菜单容器；资源卡片操作按内容定宽（刷新显示短文案且保留可访问名称），详情操作共用固定宽高，加载/禁用状态不改变布局。

ActionMenu 的 compact 模式用于卡片，buttonText 区分短文案与可访问名称；菜单保留居中选项、主题浮层及柔和底色，键盘/禁用/焦点契约不变。外部搜索初始入口按首屏剩余高度居中并响应窗口和可见性变化；已搜索后重新搜索与设置位于分页下方，重新搜索清除当前查询页缓存并从第一页开始，不另提供刷新外部结果按钮。

## 中性色控件与反馈

页面沿用重构前首页的中性底色与珊瑚红、橙色、青绿色柔光渐变，背景装饰统一由 App 装配，避免页面重复叠加。卡片、输入框与浮层保持中性色，辅助表面区分层级；重点色用于当前主要动作和状态，单处工具操作允许少量暖色点缀。60/30/10 是视觉层级目标，不按资源图片像素强制配比。深浅主题保持相同按钮尺寸和字重；深色主题降低重点色亮度及阴影，避免视觉重量明显增大。

AppButton 的 primary、neutral、danger 共用默认、悬浮、按下、禁用、加载五态；loading 保留原插槽占位，loadingText 提供可访问的忙碌说明，禁止重复提交。调用方仅覆盖布局，不用旧按钮类或内联背景覆盖状态颜色。危险动作使用独立的浅底和高对比文字。

AppInput 支持 label/id、placeholder、error、multiline、disabled、clearable 与 modelValue；输入和清空均发出 update:modelValue，清空另发出 clear 并恢复输入焦点。外部标签关联 id；错误文本通过 aria-describedby/aria-invalid 关联。class/style 用于外层布局，其余原生属性传入控件。SearchInput 复用它并保留公开模型契约。

LoadingSpinner 使用单层 1.5 秒连续旋转，避免多层动画和文字闪烁；减少动态效果偏好下停止动画。加载元素保持稳定，不通过高频重建 DOM 制造闪烁。

PageLoad 只拥有挂载后一秒的展示计时器，卸载清理；资源/目录/详情使用与内容形状对应的骨架，设置与任务等场景使用单层 loading。原查询 store 继续拥有 loading/error/结果。刷新保留已有内容，空状态只在请求结束且没有错误时出现；RequestError 通过 retry 事件交回原操作，不自行请求 API。骨架使用 3.2 秒低幅度呼吸，不频繁重建节点；减少动态效果偏好下静止。详情元数据按路由与请求版本合并，旧响应不能改写新页。

强调色背景与文字分别使用 --accent-primary 和 --accent-primary-text；text-accent-primary 映射前景 token，不能把深色按钮底色直接用于小字。分页与卡片的次要操作使用 neutral；全页主要动作少量使用 primary。确认删除复用 danger，不借用通用主按钮或低对比反色。

AppButton 的 tone="coral" 与 tone="teal" 分别用于资源库刷新和资源卡片下载，使用更鲜明的语义底色并保留固定浅色文字及完整五态；Cookie 设置恢复 neutral。导航栏透明并保留背景模糊，菜单浮层继续使用不透明表面。首页大标题与导航品牌共用 --brand-gradient 的橙色渐变；三个功能图标继续使用珊瑚红、青绿和紫色。深色组件底色采用较深的中性色，悬浮与按下表面保持可辨层级。tone="warm" 保留兼容：primary 使用橙色实底，neutral 使用暖色浅底，默认/悬浮/按下/禁用/加载仍由公共组件管理；danger 继续使用危险语义色。主题值与渐变统一归 main.css。CustomSelect 外层负责布局，内部按钮拥有边框，不给外层套原生输入框样式。

任务详情 info 弹窗中的当前跟踪数来自 taskJobs.visible，已隐藏数来自已加载缓存与可见列表之差，服务端总数独立展示；隐藏仅影响本浏览器，不改变服务端分页和持久任务。资源卡片批量复选框由独立绝对定位容器覆盖封面，不能占据封面正常文档流。

## 推荐任务生命周期

推荐页由用户按钮启动 `POST /recommendations/jobs`，不再等待同步 GET 抓取。
业务轮询位于 `features/recommendations/lib/recommendationJob.js`，API 仅负责传输；
store 拥有当前 job ID、AbortController、查询版本和结果。只合并同 job 且更高版本的
快照，成功沿用 items/seeds/meta。失败展示原因和重试，取消不伪装为空成功。

“取消推荐”先确认后端取消，再停止客户端；确认失败继续轮询并允许重试。
卸载和替换查询使旧响应失效，并尽力请求后端取消；尚未返回 ID 的提交继续等待响应，
拿到 ID 后取消，避免创建无人跟踪的后台工作。仅停止轮询不表示服务端已停止。
异常响应及旧结果不得更新当前错误、loading 或缓存。

推荐 job 的版本快照新增 progress：由当前查询 store 持有，页面展示召回/详情阶段、
候选与核验数量及用时，取消或替换查询后清空，旧响应不得覆盖。进度不是最终资源列表，
不提供历史反馈操作；资源仍以 succeeded 的 result 为准。网络预算内收尾的部分成功
通过 meta.partial/returned_count/requested_count 明确提示，保留合格资源。
已确认 failed/succeeded/cancelled 时不再发送防御性取消；断网或协议异常仍尝试取消，
保持主动取消、离开页面和迟到提交的后台清理语义。

推荐核验统计由 RecommendationVerification 统一展示运行 progress 与成功结果
verification_context，分别标记详情获取成功、黑名单排除、未核验和合格候选，
详情尝试数独立说明。缺失旧字段显示“—”，不把缺失数据当作零；旧未核验字段保留回退。
召回数量不能作为通过率分母，未核验不能展示为失败，合格候选与最终返回数分开。

### 页面辅助信息与远程资源操作

任务页副标题右侧的 InfoDialog 展示当前跟踪、已加载隐藏数和服务端总数；移除手动刷新按钮，保留自动跟踪、错误重试和加载更多。导航栏在 scrollY 为 0 时边框透明，滚动后显示语义边框，并在挂载时同步当前位置。

推荐页优先展示结果。历史信息、刷新指标与重置历史保留在推荐信息弹窗；核验与种子以默认折叠的紧凑摘要显示在卡片上方。清空页面位于页头，推荐偏好与黑名单共用一个弹窗，桌面左右排列、移动端上下排列。失败原因仅以底部继续推荐按钮下方的灰色小字展示，继续推荐负责重试。InfoDialog 使用 AppButton 五态与 useDialog 的焦点循环、Escape、滚动锁、焦点恢复及卸载清理，不自行复制弹窗生命周期。

推荐和外部搜索卡片复用 RemoteResourceActions 的加入资源库、跳转来源/查看详情按钮；公共组件仅管理展示与事件，添加请求、去重和状态归属由各业务消费者持有。库内资源仍使用原有下载、刷新和删除动作。

推荐添加由 useRecommendationAdds 跟踪本次提交的 job_id（旧任务兼容 task_id），不得按 AVID 匹配其他任务。202 接受后保持加载，授权快照 resource_saved/resource_avid 确认已保存即标记已添加；整体翻译失败不能重新开放已保存资源的添加。未保存的失败或取消释放加载，409 标记已存在；处理状态早于提交响应的情况，卸载后的迟到响应不得反馈成功。

RecommendationInformation 仅装配历史信息、指标刷新和历史重置；RecommendationContext 展示可展开的本轮核验与推荐依据，缺失数据不撑开空区域。统计与种子使用响应式网格、空组占位和长文本换行，不以页面宽度规则强制弹窗列数。回到顶部按钮只定义定位与尺寸，颜色和悬浮/按下等状态归 AppButton。

推荐页面在初始化恢复完成后、每轮查询结束及相关结果/偏好/反馈变更后，将完整合并列表保存至既有 sessionStorage key；pagehide 和路由卸载补保存滚动位置，不依赖 Vue 卸载来处理网页刷新。初始化完成前不启动新查询，卸载后的设置响应不得重新恢复旧状态或注册监听器。继续推荐保留跨轮 AVID 去重；失败追加保留已有成功批次，清空与历史重置同步持久化，刷新不会自动提交新任务。

RecommendationBlacklist 保留 show/close/invalidate 生命周期接口，新增 title 与 preferences 插槽用于联合弹窗；黑名单缓存、查询护栏和类型切换仍由自身持有。推荐卡片屏蔽动作移至喜欢/不喜欢右侧，保留取消屏蔽、禁用及原后端反馈契约。

推荐历史标题左对齐，指标刷新/历史重置在右侧成组，resetHistory 事件经 RecommendationInformation 转发到页面；重置在推荐或指标加载时禁用。个性化弹窗的偏好标签与选择框增加标准间距，桌面两列之间使用主题分割线，黑名单选项位于标题右侧并使用 AppButton 的选中、加载/禁用与五态。SettingsModal 仅在提供 footer 插槽时渲染页脚，避免留下空白区。

useRecommendationElapsed 使用前端单调时钟从查询 loading 开始计时，不等待 progress；每轮重置，完成后冻结，卸载清理 interval。成功批次用时随页面缓存恢复，未知旧缓存显示“—”；失败/取消不覆盖已有成功批次用时。核验摘要显示 verified_count/qualified_count 与 recalled_count/candidate_count 及前端用时，不重复展示上方旧进度文案。演员种子底色使用 coral-fill，类别使用 teal-fill，文字使用 on-accent；屏蔽按钮复用反馈按钮的圆角。

个性化弹窗采用受视口约束的高度。SettingsModal 的可选 contentClass 只控制内容区布局，默认不改变其他消费者；黑名单在桌面填满剩余高度并独立滚动，偏好列可独立滚动，窄屏内容区整体滚动。列表条目不收缩，不再使用固定 13rem 上限，标题与关闭按钮保持可访问。

外部搜索与推荐的添加动作复用 resources/composables/useResourceAdds，以提交返回的 job_id（兼容 task_id）跟踪授权快照；入队后保持 loading，resource_saved/resource_avid 或保存成功即禁用添加，不等待所属翻译。失败/取消但未保存时允许重试，同番号其他任务不决定本次添加。外部搜索同步当前结果与页缓存的库存投影，删除事件清除本地已添加标记。推荐依据的演员/类别标签只将 coral/teal 背景设为 80% 不透明，文字保持原有不透明度；继续推荐与结果之间保留 3rem 间距。

## 在线播放器（P3）

详情页只打开独立路由 `/play/:avid` 的新标签页（noopener/noreferrer），URL 包含 AVID及可选mode=local，不包含上游地址或凭证。PlaybackView 装配 features/playback/components/PlaybackPage；后者查询展示标题并装配 PlaybackPlayer，播放器拥有同源在线播放的状态与生命周期。播放路由通过 meta.layout=playback 使用居中布局，Navbar 的 logoOnly 仅保留品牌链接，普通页面继续完整导航。已下载资源的“点击播放”打开本地MP4模式；默认及“在线播放”仍走来源，文件错误不自动回退。详情操作依次为刷新、下载/本地播放、在线播放、删除，使用等高等宽响应式网格。playbackSession 拥有提交/版本快照/轮询/关闭；mediaPlayer 拥有按需加载 hls.js（MSE 可用时优先）或原生 HLS、有限缓冲和引擎销毁。mediaPlayer按公开media_type选择MP4原生video或HLS引擎；本地不导入hls.js、不刷新来源，同代次轮询保留原media_url，AVID/模式变化清空本页位置，本地重试从头。仅接受同源受控媒体入口，签名地址不进入浏览器持久存储或日志。关闭、实体切换、卸载使旧响应失效；关闭后的迟到提交仍补发关闭，版本冲突重读后以同一命令 UUID 有界重试。pagehide 尽力关闭，服务端 TTL 兜底。

播放器不强制自动播放；原生 controls 提供播放、暂停、音量及拖动。准备超过一秒展示平缓 loading，失败提供重试；同资源本次播放页内保存位置，换资源清零。独立播放页不使用弹窗焦点锁或 Escape 关闭；原详情标签页关闭不停止播放。页面不提供停止/重新播放或查看资源详情按钮；退出路由、关闭或刷新标签页使旧执行失效并清理，pagehide 尽力关闭、TTL 兜底。播放器维持 max-w-5xl 宽度，加载/错误/视频共用 16:9（1280:720）区域；video 填满边框内部并 object-contain，不拉伸不同画幅。无外围 padding 或底部说明，缓冲/错误提示在区域内显示。浏览器套件 playback.cjs 使用 ffmpeg 临时合成 TS/fMP4 H.264/AAC 并通过真实 video/hls.js 解码，不将模拟会话 API 作为正式 worker 验收。

P4 的 refresh 由 playbackSession 单航班和一次上限控制，服务器仍是次数、版本和 generation 的所有者。只针对网关来源拒绝读取的 410 自动尝试，不能以任意网络错误无限重刮削；后端兼容失败不恢复位置，用户显式重新开始会清零。原生 HLS 失败保留手动重试。pagehide 的同源 CSRF keepalive 请求归 api/playback.js，不能声称必达；TTL 继续兜底。授权状态更新不得用新的签名 URL 重建同代次播放器。

## 播放进度记忆

playbackProgress 拥有 video 事件、短期写入token、单请求保存队列、恢复提示与卸载清理；api/playback只处理HTTP与CSRF keepalive。组件装配提示和AppButton，媒体引擎不承担持久化。

读取进度不领取写入权，不发送初始化0秒。用户开始播放时claim；每15秒timeupdate节流，pause/seeked/ended/页面隐藏补存。一次仅一个保存请求，合并待发最新位置；响应丢失重试原payload成功后发送新位置。409/401/404/410停止保存，不自动抢回写入权，播放可以继续。

有效非完成位置>5秒、距结尾>5秒、时长差<=max(2秒,1%)提供“继续上次/从头播放”；本地文件版本必须精确匹配，来源新会话提示用户确认，不自动跨模式恢复。同会话HLS受控刷新沿用本页位置并重新绑定generation，不重复弹恢复提示。完成后重新打开默认从头，不修改共享watched。

player销毁前捕获位置并解绑监听，再尽力保存；pagehide有写入token且无在途保存时，同步发起带CSRF keepalive的close_after_save请求，在后端短事务保存并关闭，不依赖页面销毁后的JS回调。无token/在途保存/失去写入权时立即走既有close；捕获有界兜底，服务端TTL兜底。保存失败时离页末次位置可能缺失；不并发开启两个进度保存请求。离页末次请求不承诺必达。路由/会话更换后旧响应不得修改新UI。

progressDrafts是可选localStorage兜底，仅存账本摘要、秒数、完成/版本/代次/序号及写入时间，最多20条、7天；不保存AVID、用户名、视频路径、签名/来源URL或Cookie。取得当前授权服务端快照后，只有账本、version与writer_generation相符才作为恢复候选，不能直接重放旧请求。版本变化/清除/其他页面领取后旧兜底失效；确认匿名/退出登录时App装配层清理，存储不可用不影响播放。

Node专项playbackProgress.test.js验证节流、重复/丢包重试、单航班、回退、完成、归属冲突、迟到查询及兜底隔离。真实API浏览器专项playbackProgress.cjs需NASSAV_PROGRESS_STORAGE_STATE显式指定隔离helper生成的临时登录状态，无该变量跳过，不使用正式账号。Chrome/Firefox与本地合成MP4验证不等同真机/长时或生产容器验收。

## 个人资源状态与设置（多用户第二阶段）

资源详情装配 `features/resources/components/PersonalResourcePanel.vue`，输入resource快照，updated事件只表示当前资源/用户的成功或冲突快照。`personalResourceEditor`管理备注草稿、版本、保存错误及忙碌状态；所有状态写入带expected_version，冲突保留草稿且不自动重试。切换资源、用户、登出、卸载使旧响应失效，不发布旧toast或覆盖新实体。保存确认前不伪装成功；清空先修改草稿，保存后生效。备注最多5000字符，仅当文本处理，不使用v-html，不持久化本地草稿。收藏/已观看是个人手动标记，播放结束不自动修改。

settings store的reset清空通用、推荐和播放偏好及loaded/in-flight请求归属；App在status/username变化时调用，资源列表reset同时清空含个人标记的结果、分页和旧查询。saveSettings返回ignored时页面不展示成功提示。API身份由后端会话决定，不发送user_id，不将INI或localStorage作为个人设置所有者。主题/字体的即时预览与手动保存契约保持。

后端数据、迁移/导入及开放权限边界见[个人状态与设置](../../django_backend/doc/personal-state-architecture.md)。本阶段仍保留指定操作者登录，不把单项数据隔离当作全系统多用户访问已完成。

通用设置保存相对最近加载/成功保存的基线只提交改动字段，无改动不发PUT；不把GET补齐的默认值自动全部持久化。保存失败保留差异，保存期间新的编辑在后续提交，登出/用户切换或旧请求响应不得覆盖保存基线。JSON配置定义、缺失/废弃键与0034数据迁移遵循[后端配置规则](../../django_backend/doc/personal-state-architecture.md#json设置与0034当前实现)。

## 推荐个人状态

结果页面缓存按账号命名，旧未归属缓存不恢复；登出清空缓存与store，用户切换重新装配路由页。job/指标检查查询身份，反馈/黑名单写后投影检查登录代次，旧页不得持久化到新账号。偏好由settings store的recommendationPreferences读取用户JSON，“保存推荐偏好”只提交变更项；当前查询可使用尚未保存的选择，显式路由参数优先，缓存结果不覆盖个人数据库默认值。

## 播放偏好

PlaybackSettingsPanel仅发模型更新；settings store拥有个人JSON草稿、服务器基线和登录代次。playbackPreferenceWriter捕获登录代次，仅保存显式播放器变化，不提交无关设置。playbackPreferences绑定原生事件，初始化无写入、500ms合并、单请求串行，卸载移除监听；错误保持可重试草稿。设置defaultPlaybackRate防止换src时浏览器回到1倍速误写配置。播放路由auto依据个人默认模式与共享file_exists提示选模，明确local/source入口不被设置覆盖；最终播放授权和媒体身份在后端。字幕默认只作用于存在的字幕轨道。

## 跨设备接续

首页继续观看组件已移除；进度接续协议保持，入口由个人中心观看历史或资源详情提供。个人中心复用ViewingLibrary，历史与进度清除保持不同语义；播放在无opener的新标签页打开，通用入口遵循用户播放模式偏好。

进度模块消费writer_active/is_writer提示，打开页不claim；另一页持权则由用户明确接续、从头或只读播放。接续先重读DB，再CAS领取，位置以claim返回值为准；409不自动抢回，可显式重新接续。有效离线草稿仅在没有其他活跃writer且版本/代次匹配时恢复，claim版本已变则丢弃该兜底。卸载/换媒体仍停止监听并保留原串行保存队列；小屏16:9播放器内提示有自己的滚动区域，按钮完整可达。

## 观看历史与稍后观看

PersonalResourcePanel/personalResourceEditor增加watch_later，复用个人state_version冲突与草稿保护。ViewingLibrary拥有页码/列表/错误/移除状态，切换列表或用户及卸载使旧响应失效，窗口回到前台重新读取；不持久化个人列表到localStorage。移除过程中不启动分页查询，失败保留内容并提供重试，跨页冲突须刷新。

viewingRecorder仅在video的play后真实playing事件上报当前会话/代次/sequence；缓冲和重试保持sequence，暂停后重新播放增加sequence，播放器重绑同会话继承计数。事件记录与progress.claim/save独立，“仅播放不保存”仍记录历史；打开页面/loadedmetadata不记录。卸载解除play/playing监听，旧响应不改新播放器错误，失败可明确重试。不自动标记已观看或移除稍后观看。

## 个人中心与备注编辑

/personal/:section?由PersonalCenterView装配features/personal/PersonalCenter，section允许watch-later/history/general/playback，默认稍后再看。导航仅保留个人中心入口，退出按钮属于中心；原/settings和/resources/viewing地址保留兼容。ViewingLibrary支持embedded/initialKind，沿用原查询所有者和卸载护栏。PersonalSettings归features/settings，通用与播放设置分开装配，SettingsView仅为旧路由入口；后端配置/保存契约不变，卸载后的能力查询与设置响应不触发旧提示。

PersonalResourcePanel唯一持有个人editor，可用default作用域插槽(state/save)将图标操作置于封面下；备注展示在插槽后，宽度限制为页面内容。PersonalResourceActions只渲染state并emit change(changes,action)，选中variant primary、未选中neutral，aria-pressed/title/可访问名称说明状态，按钮图标不放长文字。

noteDialog统一处理关闭与导航离开的未保存决定，所有弹窗复用useDialog。清空只改草稿，保存成功后关闭，失败/409保留；关闭/Escape/换路由可继续编辑或放弃，标签页关闭用浏览器原生beforeunload提示（文案由浏览器决定）。账号/实体更换及卸载使待决导航和旧保存失效，解除监听；保存进行中拒绝关闭。备注仅文本展示，长词/多行换行，不写浏览器存储。

个人中心saveSettings(section)仅提交当前general/playback分区的差异，不保存另一分区或推荐草稿；缺省all维持旧调用契约。播放设置保存不应用隐藏的字体预览，未改动分区不发PUT。原/settings仍提供组合设置入口。

### 个人中心UI执行记录（2026-10-14）

基线313f764，独立分支feat/personal-center-ui；本轮仅改前端及文档，后端公开接口、状态与数据库保持。前端pnpm run check包括123单元测试、lint和构建；根pre-commit run -a完整通过。Chrome/Firefox使用临时真实Django/SQLite/Redis/同账号登录和合成封面验证个人中心入口、分区设置、退出、封面上缘对齐、图标状态、长备注、弹窗焦点/关闭/清空/保存/冲突和未保存导航提示及390px深浅主题。原settings.cjs模拟API回归通过；跨设备接续Chrome通过，入口改到个人中心观看历史，显式接续/旧writer409/清除进度仍保留历史验证通过。首次浏览器尝试强制点击被遮罩覆盖的链接并未触发路由，脚本改为显式触发RouterLink导航、等待确认层退出；同AVID新快照不再重置弹窗，409草稿保持。原生beforeunload监听检查不代表能自定义浏览器警告文案。

新备注关闭护栏只阻止打开的编辑器，收藏等后台保存不阻断关闭状态下的导航。提交与合并见该分支Git历史；正式服务、真实源站worker、实体设备与数据库迁移未执行，本轮不需要新增迁移。

### 个人中心缓存与列表操作（v2.5.1）

PersonalCenter使用最多4个KeepAlive面板，使用viewing:section/settings:section的独立缓存key保留状态、180ms淡入位移，尊重prefers-reduced-motion；登出须ConfirmDialog确认“是否要登出”。ViewingLibrary的查询缓存归features/viewing/stores/viewing，30秒/8项/同请求去重；App身份变化重置，缓存revision及请求guard双重检查旧响应。onDeactivated停止查询、关闭确认和解除操作展示状态，卸载解除focus/visibility监听。手动刷新和重试强刷，写入成功以shared/lib/personalDataEvents无载荷事件失效，不保存个人数据到浏览器持久存储。跨标签/设备仅有TTL恢复，详细现状与后续步骤见[缓存计划](personal-cache-plan.md)。

观看历史的选择限定当前页，单条/批量删除确认后提交列表queue_time，重新观看冲突保留并提示。稍后再看“移出已观看”作用于当前账号全队列的手动watched=true，不根据历史推断；列表移除不删媒体/进度。AppCheckbox新增disabled并透传原生input。ResourceCover新增squareBottom仅去除下缘圆角；原默认样式保持。详情图标操作为三等分布局，行宽贴合封面、上方间距1.2rem；备注编辑图标位于文本左侧，保持原弹窗和草稿护栏。

页面过渡完成的主内容焦点恢复不得抢走已打开的aria-modal弹窗焦点；App在恢复前检查可见弹窗，弹窗继续持有焦点循环。设置面板先读取已有个人设置，不等待来源能力接口完成才显示表单。

### 个人中心缓存与列表管理执行记录（2026-10-14）

基线e5622a3，独立分支feat/personal-center-cache-and-actions，功能提交e72493a。`pnpm run check`：125单元测试、lint和构建通过；`uv run pytest tests/ --ds=django_project.refactoring_test_settings -v`：1007通过、28在线跳过。Chrome/Firefox以临时真实API/SQLite/Redis/合成MP4和封面验证分区请求次数不增长、设置保存、登出确认与取消、封面下缘直角、历史单条/批量删除、移出已观看、390px深浅主题、图标布局/1.2rem间距及备注键盘/冲突护栏；两浏览器全部最终用例通过。历史接口测试覆盖用户隔离、幂等重试、重新观看冲突及独立条目部分成功，查询缓存测试覆盖TTL/容量/在途去重/旧账号与乱序响应。

首次Firefox焦点检查失败后，App增加过渡完成时已打开弹窗优先的焦点保护，复测通过；窄屏尺寸检查改为等待真实封面加载后同帧测量，并按14px小屏根字号计算1.2rem，避免加载/动画期间的错误采样。PersonalCenter原v-if/v-else共享key改为单个动态组件，viewing/settings缓存键分离；构建与实际切换通过。格式化钩子修改文件后重新暂存并执行完整pre-commit，不修改钩子配置。正式环境、外站worker及实体设备未验收，本轮无模型迁移；后端列表管理接口需与前端一起部署。执行提交见该分支Git历史；缓存规划中的外部搜索账号归属、blob回收、条件请求等后续项尚未实现。

### 观看卡片交互

观看历史默认隐藏多选控件，按下“批量操作”才在封面左上角叠加公共AppCheckbox，位置/样式沿用资源库；勾选不触发资源导航，也不改变封面或卡片高度。批量栏提供本页全选、已选计数和删除所选，退出批量、切换列表/身份或停用面板时清理选择；单条历史删除保持原确认与后端时间冲突保护。两个观看列表的卡片支持鼠标悬停轻微上浮、主题阴影及边框反馈，键盘focus-within显示边框，减少动态偏好下禁用位移与过渡；触屏不强制悬停位移。

本轮基线a1a10ac，独立分支enhancement/viewing-card-interactions。pnpm run check的125项单元测试、lint与构建通过；Chrome/Firefox使用临时真实Django/SQLite/Redis与合成媒体验证两类卡片深浅主题悬停、减少动态偏好、默认隐藏选择、左上角叠加位置、键盘Space/半选状态、选择不导航、退出后清空、卡片高度稳定、单条/批量删除及390px布局，截图已检查。根pre-commit完整门槛在格式化后重新执行，通过后提交合并idle；正式实例/实体设备不属于本轮验收范围。

### 个人中心布局稳定性

桌面个人中心导航固定12rem，内容列minmax(0,1fr)；导航按钮填满列宽，移动端仍自动换行。html预留scrollbar-gutter:stable，长短页和面板过渡期间滚动条出现/消失不改变内容的可用宽度，不强制在短页绘制滚动条。音量控件组最大17rem、可按容器缩小，百分比output固定3.5rem并使用tabular-nums，slider占剩余宽度，0/9/99/100%变化不影响位置；input提供对应百分比aria-valuetext，output关联slider。

本轮基线f3e05ca，独立分支fix/personal-center-layout-stability。原音量滑块在0%到100%间约20px水平位移已用Chrome/Firefox复现；隔离浏览器默认覆盖式滚动条下未复现导航位移，修复以固定导航列和稳定滚动条占位消除长短页宽度变化来源。pnpm run check含125单元测试、lint和构建；根pre-commit完整执行。personalLayout.cjs使用模拟API验证1440/1024/390/320px切换全过程导航位置/尺寸、弹窗滚动锁与取消恢复、0/9/10/99/100%滑块固定及无横向溢出，两浏览器通过后合并idle。布局截图已检查，不代表真实服务或实体设备验收。

## 共享模式接入：会话与缓存身份

登录和session响应携带cache_identity、account_epoch及显式capabilities；cache_identity仅为不含秘密的缓存命名空间，不是授权token。普通登录仍关闭，所有动作继续由后端核查。session store以请求代次拒绝旧初始化/recheck；统一client在发请求时同步捕获本地登录代次，拒绝旧成功/旧错误，旧401不得触发新会话登出。网络错误本身不证明登录失效。

App按status/identity重置资源、目录、设置、观看列表、推荐、下载队列和任务跟踪，重建WebSocket及路由组件；回到前台先recheck。推荐页面与外部搜索缓存按不透明identity命名；旧无归属缓存不恢复到新命名空间。生产刮削跟踪/旧下载隐藏ID采用v2身份命名，未装配会话的旧单元兼容入口不代表多用户准入。个人编辑器也以identity核查响应归属。

播放离线草稿按identity隔离，固定捕获owner且读/写/删除均核查仍属当前登录。同一登录刷新保留有效草稿；注销或已知身份切换清除旧草稿，旧播放器的迟到收尾不得重新写入。数据库仍持有个人进度。restoreScrapeJobs返回可等待的恢复批次，不能用固定微任务数量推测异步完成。

本子阶段仅接入身份与缓存基础，尚未切换共享库命令/用户operation界面或开放普通账号；P7其余界面和P8统一验收继续。真实浏览器使用临时HTTP/SQLite与同账号两个真实登录，延迟旧设置响应验证更换登录后的归属；不等同跨用户/源站/生产部署验收。

### 个人来源凭证与来源缓存域

CookieManagementDialog是模式装配入口：capabilities.personal_source_credentials为true时仅装配PersonalCredentialsDialog，否则保留独立LegacyCookieManagementDialog。usePersonalCredentials持有元信息/输入/加载与mutation归属，personalCredentialApi只用统一client；公共api/index新增对应同一对象导出。界面Cookie/UA不预填、不持久化、不显示服务端秘密；新协议两者配套必填，旧兼容界面的UA规则不变。409保留草稿，重载是用户明确读取新版本的动作，禁止自动重试覆盖。未保存关闭确认、卸载清空，消息和busy均核查当前owner与编辑代次。

session store额外持有sourceIdentity，从source_cache_identity读取；凭证写成功用其返回值立即更新，无需额外session请求。来源身份变化使推荐store/来源页面及其缓存失效，拒绝旧来源请求的结果/错误/清理动作；cache_identity保持时不重建添加表单及个人设置。外部搜索/推荐用sourceIdentity命名，所有对象授权仍归后端，字段不是token。普通登录仍关闭，公共/个人提交模式及共享库/管理页面继续实施。

个人凭证弹窗最大高度为视口减标准留白，内容是唯一滚动区，标题与关闭保留；复用SettingsModal/useDialog、ConfirmDialog、AppButton五态和CustomSelect键盘操作。加载超过1秒用公共spinner，失败可重试，空来源明确显示空状态；保存与撤销分别展示loading文案。

### 本人库状态缓存

features/library的membershipLookup只拥有请求归属及短期状态缓存，持有关系由DB拥有。统一libraryApi分批最多100项，重复批次共享请求，重叠批次按AVID请求序号拒绝旧发布；不完整响应不得部分写入。缓存30秒、常规最多500项；挂载中的卡片状态保留至卸载再裁剪，不落浏览器存储。App按登录身份重置，共享模式回到前台完成session核查后失效；revision供消费者重新核查。未查询/失败不能解读为未持有，列表恢复应显式刷新，命令成功或operation变化需失效。当前子阶段仅提供基础查询，卡片和命令消费者随后接入。

### 本人操作请求

共享模式DownloadsView装配UserOperationsPage；兼容与DEBUG模式装配LegacyDownloadsPage，调试开关仍位于DownloadsView。userOperations持有原始operation_id/version快照，不把共享job ID或attempt伪装成本人标识。WebSocket只提示本人operation/version，轮询与重连补查/my-operations；共享模式不读取旧全局队列、旧任务详情或恢复旧刮削句柄。

公共TaskDetailsPanel的operationMode只改变展示：隐藏暂停/恢复，取消文案为撤销本人请求；忙碌使用operationId，动作仍按allowed_actions。撤销逐项发送expected_version/request_id，结果不明时保留同一命令UUID，409补读但不自动重试，部分失败明确保留；取消不等于共享执行已停止，也不自动移出本人库。隐藏只是当前登录的本地展示偏好，快照不落本地存储。登出/身份变化使列表、提示、错误、busy和命令结果失效。

operationDetails仅投影任务展示字段；名称/封面可使用当前本人库已加载数据，不按AVID读取全局标题。不具备当前active关系时不展示查看资源入口。终态变化使本人持有状态缓存失效，命令与资源列表消费者继续接入。

### 共享库命令与来源选择

libraryCommands核心消费显式API、持有状态查询、本人operation发布和失效回调；HTTP归libraryApi，不平行使用旧资源写入口。每个命令在首次查询后固定entry UUID/version和request UUID，结果未知的重试先复用旧命令，不因关系已消失/变为pending重建意图；409只在用户再次明确操作时重新取CAS。身份变化清除命令/进行中请求，迟到成功、失败和清理不得发布至新用户。批量最多100项、逐项有界提交并保留部分失败，不把已接受等同工作已完成。

App装配LibraryOperationDialog；添加页直接显式选择来源和public/personal，其他入口通过统一弹窗选择。共享模式无自动any、无旧部分刷新选项，刷新重新获取完整来源/元数据；个人凭证缺失明确失败，不能回退系统凭证。提交失败保留表单与可重试命令；弹窗忙碌时不关闭，未提交关闭不发送请求。共享CAS冲突不能沿旧409语义标记已存在。

资源移出只释放本人持有/需求，卡片、详情、批量确认不能显示删除共享视频选项；文件由受控GC处理。本人operation状态和关系变更使列表重新投影，下载按钮按本人请求显示忙碌。SubmissionResults按operation_id合并，兼容job_id/task_id继续保留。推荐与外部搜索的已持有缓存覆盖随后接入，不能把缓存中全局存在标记当本人授权。

### 远程卡片的本人持有状态

RemoteLibraryActions装配会话、关系状态与路由，RemoteResourceActions保持纯展示。共享模式忽略推荐/搜索缓存及added集合中的旧库存标记；添加前的alreadyAdded能力也查询当前本人关系，不能出现按钮已恢复但旧集合阻止提交。准备中显示查看请求，查询失败提供重试，未知关系不能当作未持有。旧模式沿原有added语义。

卡片同一轮挂载通过schedule合并查询，每批最多100；成员store只维护一个30秒刷新计时器，隐藏页不发请求，最后卡片卸载或登录reset停止。页面前台核查和operation/命令失效通过revision重查；长列表保留已挂载项，卸载裁剪至常规500项上限。失效不清空可见项注册，身份reset清空，旧卸载句柄不能删除新注册。

封面object URL缓存在登录身份和关系revision变化时同步撤销；迟到成功、错误和URL回退均检查代次，显式撤销同样阻止进行中的旧请求发布。并发完成复用同一对象URL，LRU淘汰撤销对象。ResourceCard监听本人关系/资源版本/URL，组件卸载和新版本拒绝旧封面回填；封面缓存不授予媒体权限。

### 本人持有管理与移出CAS

资源库的管理持有弹窗查询独立/library/memberships，只显示本人的编号/关系状态/时间；正式资源列表继续过滤不可读产物。不可用和pending持有仍可移出，单项和当前页批量共用libraryCommands，部分失败保留说明，不触发直接文件删除。筛选只搜索编号，读取及卸载复用请求guard；嵌套确认遵循useDialog焦点/滚动协议。

移出可以提供渲染时的membership证据；卡片、资源详情、批量操作和持有管理均传entry_id/version。发出新命令前若权威关系与该证据不同，返回本地409要求刷新，禁止自动采纳重新添加的新关系后继续移出。结果未知的旧命令仍按原证据重放。本人移出与旧全局删除在演员/类别批量入口同样明确区分，批量成功计数不包含未请求的结果，缺失结果保留失败。

### 管理员账号与审计界面

个人中心按capabilities.app_admin显示管理中心入口；/manage页面再次检查能力，未授权不装配查询组件。能力仅控制UI，后端应用管理员权限仍是授权所有者，不以Django标记代替。普通多账号登录未开放时明确提示，创建账号不改变准入。

features/admin/lib/adminRead拥有管理查询的当前登录/请求代次；accountAdministration拥有账号编辑草稿、确认时冻结的目标version和幂等request UUID。配额、角色、启停仅提交实际变化项，避免仅改配额时顺带发送role并撤销会话。结果未知时保留原输入/命令，编辑才创建新UUID；409保留草稿但不自动采用新版本，最后管理员保护和用户名冲突分别解释。密码不预填、不写浏览器存储/日志，完成、放弃和身份变化立即清空；审计只展示白名单摘要，不展开原请求体。

账号弹窗复用公共控件与useDialog，子组件通过控制器方法更新字段，不直接写prop。确认和放弃未提交输入是独立嵌套弹窗，检查焦点/滚动恢复。分页有界1–100，读取刷新保留原列表，失败可重试；停用明确说明撤销凭证/持有，重新启用不自动恢复。

### 系统来源凭证管理

管理中心sources板块只读系统元信息，写入固定clearance类型并要求原因、目标版本与request UUID；个人账号Cookie不能通过此入口发布。systemCredentials控制器与个人凭证的盲写交互相同，但独立持有管理员审计命令：结果未知按原端点/版本/UUID重放，修改草稿才更换UUID，409保留输入且要求刷新重编辑。来源列表只限制新建，不隐藏已撤下来源的现有凭证及撤销入口。响应检查system范围/来源/ID后更新source_cache_identity，完成、丢弃、身份变化与卸载清空秘密，不落浏览器存储或审计内容。删除不直接操作文件或来源站点。

### 共享资源生命周期管理

管理中心resources/gc仅在共享库与app_admin能力下装配。AdminResources拥有当前分页的adminRead；resourceAdministration拥有确认时冻结的pool_version或job revision、原因与幂等UUID。下架/恢复访问、保留、回收排队和失败重试使用不同API，不能以移出关系代替物理删除或以排队响应宣称文件已清理。UI不读私密标题/持有者/路径，不修改后端执行开关。

回收预览有独立请求代次，核对pool UUID/version/generation和可选版本UUID；旧预览、来源输入变化、关闭与身份切换不能授权新请求。无阻塞预览不是删除保证，后台再次核查；RESOURCE_GC_ENABLED关闭时保留只读预览/保留操作，禁止排队及重试。未知结果重放相同命令，409保留原对象版本并提示刷新，保护条件逐项展示；完成后使本人关系/封面缓存失效。弹窗复用公共控件、唯一内容滚动及嵌套确认。

### 管理员全局执行控制

管理中心work复用既有/tasks/jobs审计协议，仅app_admin装配，不与本人operation跟踪混用。列表按job_id及服务端排序分页；按钮仅接受allowed_actions。workAdministration冻结任务版本、动作、审计原因和request UUID，结果未知使用原命令重试；409不采纳响应的新版本继续控制，须刷新后重新确认。动作期间及成功后的列表刷新均保持busy，迟到结果不能写入新登录。

全局暂停/恢复/终止及清理重试明确提示影响其他等待者；本人撤销仍在任务详情中。HTTP202仅表示登记，清理状态独立展示，不以cancelled宣称中间产物已删除。界面只显示执行编号/AVID/类型、阶段、清理状态和时间，不展开来源配置或凭证。清理重试复用cleanup/retry端点；未知动作在API层拒绝。

### 本人推荐/搜索图片句柄

推荐与外部卡片统一调用recommendationApi.getResultCoverUrl，范围模式只用服务器cover_handle，不因缓存缺少句柄回退cover_url/source请求。旧模式保持原URL代理。外部响应原thumbnail_url映射cover_url时保留句柄；图片失败或句柄缺失显示既有占位，不自动重新搜索。句柄不独立持久化或保活，随原结果缓存；服务端实时检查归属/范围/TTL。

### HTTP命令标识与跨设备关系刷新

所有任务、库、管理员及播放幂等命令使用shared/lib/requestId的安全UUID v4。安全上下文优先原生randomUUID，HTTP局域网缺失该API时使用WebCrypto.getRandomValues，不用Math.random或时间戳代替随机数；缺少安全随机能力明确报错。原有控制器仍拥有命令重放/新意图边界，工具替换不在重试时创建新UUID。

本人关系轮询只有已缓存快照的身份/版本/状态/可用性变化才增加领域revision，使现有资源列表与object URL失效；首次载入和相同快照不触发。先发布新快照再发revision，监听者复用新鲜缓存，禁止通过reset重查形成循环。旧登录或被替代请求不能增加当前revision。

### 多用户浏览器上下文

ordinary_login开启时session store拥有cache_identity，api/client仅持有X-NASSAV-Context预条件；409 browser_context_changed只读重查，不重放写入。旧响应/socket或销毁后的bootstrap不能改变新身份。原生封面/头像由API helper附加_context，keepalive带同头；本人结果图片仍用归属句柄。WS带任务/上下文两个subprotocol，旧4401先查当前Cookie，4409重查代次；上下文不替代业务owner/epoch。准入默认关闭，详见后端准入架构。

### 后端返回的普通图片地址与会话上下文

资源卡和任务详情不能将后端返回的普通AVID thumbnail_url/cover_url直接作为img src；它们可能不含_context。通过resourceApi.resolveCoverUrl在显示时为受保护的同API封面地址绑定当前登录上下文，保持size、v和fragment，替换旧_context并去重。纯任务投影显式接收解析回调，不导入API或持有会话；共享ResourceCover仍只展示传入地址。

外部图片、Blob、Entry图片和本人结果句柄不经此普通封面改写，不把会话上下文附到外站。后端缺失/旧上下文409及owner权限检查保持，不以取消校验修复图片。历史/稍后再看复用ResourceCard；会话变化仍沿现有identity重建、缓存清理及旧响应拒绝协议。

2026-10-16修复分支fix/resource-cover-browser-context：原API thumbnail_url绕过helper复现409；URL幂等/参数保持和两类任务投影有单元回归，浏览器使用生产Vue组件与模拟409/图片接口覆盖资源卡、共享任务详情及两个登录上下文。与后端准入隔离测试、当前部署验收分别报告。

2026-10-16资源卡尺寸修复：ResourceCard默认coverSize=medium，优先采用后端thumbnail_url时仍须显式将coverSize传给resolveCoverUrl(url, size)，不能让后端预览用size=small绕过组件尺寸。省略解析器size保留服务器提示；显式null/空字符串去掉size使用原图，ResourceCard的undefined仍触发Vue默认medium。只改写普通封面URL，保留_context/v/fragment，外部图与归属句柄不拼接尺寸。旧布局small/medium/large规格为200/600/1200，新版本图片仍按其既有正式资产协议读取，不因此生成新版本。

浏览器resourceCoverSize.cjs使用生产ResourceCard与模拟图片接口，修复前复现默认medium却实际naturalWidth=200，修复后验证600及运行中small/large/原图切换；Chrome/Firefox与上一轮图片上下文回归分开执行，不替代部署图片实测。

## 读取缓存

资源库和演员/类别目录以完整查询参数为键，内存缓存30秒、最多20项，并合并相同请求；过期页先恢复上次数据再后台更新。缓存读写深拷贝，展示层变更不污染缓存。`shared/lib/queryCache` 只持有缓存和请求归属，状态展示与错误仍由业务 store 持有；失败不缓存，reset/失效后旧请求不能回填。

资源详情缓存30秒、最多100项，来源列表/搜索能力缓存5分钟、最多8项；API缓存键包含登录/来源请求代次。身份变化清空个人展示状态，持有代次、资源写入及任务刷新失效关联缓存。手动刷新资源列表和详情绕过缓存，不把刷新按钮变成读取旧快照；资源库/目录内存缓存不持久化到浏览器存储。图片继续使用授权URL和浏览器条件缓存，不用旧AVID-only Blob缓存绕过每次授权。普通JSON响应策略仍由后端决定，客户端不再给所有请求附带禁止缓存的通用请求头。

阶段分支 `enhancement/frontend-query-cache`，执行 `pnpm run check`、`pre-commit run -a`，缓存回归覆盖翻页请求次数、请求合并、TTL、容量、手动刷新、对象隔离及旧账号响应拒绝；浏览器验证使用隔离API，不代表现有服务联调。

### 缓存寿命与精确失效

| 对象          | 新鲜期/边界                       | 失效与持久化                                                                                                     |
| ------------- | --------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| 通用/播放设置 | 5分钟，合并请求                   | 页面进入、可见恢复及可见页5分钟复核；同源页签保存通过无值storage信号提示失效，未保存草稿及新保存值不被旧GET覆盖  |
| 历史/稍后观看 | 30秒，8页                         | 各自代次与请求归属；真实播放只失效历史，清除已观看只失效稍后观看，备注不清空两列表；退出整体清理                 |
| 外搜结果      | 后端剩余有效期与1小时上限的较小值 | 按来源身份、实体、来源隔离，最多20个会话记录、每查询10页及6种排序，前缀总预算2MiB；部分/到期结果不复用，登出清除 |
| 推荐恢复状态  | 新一轮成功后的30分钟              | 页面保存和反馈不延长原结果绝对期限；最多4个身份记录，前缀总预算2MiB；到期/旧结构为缓存未命中                     |
| 黑名单查询    | 60秒，20种查询                    | 本页写入失效关联类型，退出/来源身份变化随页面重建                                                                |

`personalDataEvents` 只发送失效领域名，不携带备注、配置值、凭证或个人数据。共享请求提交和任务终态提示失效库投影；缓存不参与授权。会话存储不可用、内容损坏、配额不足时降级为不持久化，不能把成功搜索变成失败。通用设置的页签信号也不包含配置值，后续GET仍由当前登录与浏览器上下文授权。

阶段分支 `enhancement/cache-lifecycle`：运行 `pnpm run check`、`pre-commit run -a`、后端隔离 pytest。Chrome/Firefox 隔离浏览器覆盖真实 App 跨页签更新/草稿保护，以及真实外搜组件翻页缓存/过期拒绝；模拟接口不代表正式部署。

### 部署静态资源

nginx 对 `/assets/` 下带至少8位内容哈希的 JS/CSS 使用 `public, max-age=31536000, immutable`，缺失文件返回404，不回退HTML。固定路径字体使用 `public, max-age=0, must-revalidate`，入口HTML及SPA回退使用 `no-cache`；nginx原有ETag/Last-Modified继续提供条件请求。新加固定文件名资源不能套用 immutable，更新字体时无需等待一年缓存。开发模式 Vite 不等同生产 nginx，API、WS及媒体代理保持原策略。

阶段分支 `enhancement/static-asset-cache`，使用本地 nginx 镜像、当前构建产物与只读配置挂载，在隔离临时容器检查 `nginx -t`、真实响应缓存头、条件304和缺失文件404；另执行 `pnpm run check` 与 `pre-commit run -a`。临时容器验证不代表现有部署已更新，部署需同步前后端并重新构建。
