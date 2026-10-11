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

详情页只打开独立路由 `/play/:avid` 的新标签页（noopener/noreferrer），URL 仅包含 AVID。PlaybackView 装配 features/playback/components/PlaybackPage；后者查询展示标题并装配 PlaybackPlayer，播放器拥有同源在线播放的状态与生命周期。下载与本地路径操作保留，详情操作依次为刷新、下载/本地播放、在线播放、删除，使用等高等宽响应式网格。playbackSession 拥有提交/版本快照/轮询/关闭；mediaPlayer 拥有按需加载 hls.js（MSE 可用时优先）或原生 HLS、有限缓冲和引擎销毁。仅接受同源受控媒体入口，签名地址不进入浏览器持久存储或日志。关闭、实体切换、卸载使旧响应失效；关闭后的迟到提交仍补发关闭，版本冲突重读后以同一命令 UUID 有界重试。pagehide 尽力关闭，服务端 TTL 兜底。

播放器不强制自动播放；原生 controls 提供播放、暂停、音量及拖动。准备超过一秒展示平缓 loading，失败提供重试；同资源本次播放页内保存位置，换资源清零。独立播放页不使用弹窗焦点锁或 Escape 关闭；原详情标签页关闭不停止播放。停止/重新播放控制本页会话，关闭播放标签页的 pagehide 尽力关闭、TTL 兜底。浏览器套件 playback.cjs 使用 ffmpeg 临时合成 TS/fMP4 H.264/AAC 并通过真实 video/hls.js 解码，不将模拟会话 API 作为正式 worker 验收。

P4 的 refresh 由 playbackSession 单航班和一次上限控制，服务器仍是次数、版本和 generation 的所有者。只针对网关来源拒绝读取的 410 自动尝试，不能以任意网络错误无限重刮削；后端兼容失败不恢复位置，用户显式重新开始会清零。原生 HLS 失败保留手动重试。pagehide 的同源 CSRF keepalive 请求归 api/playback.js，不能声称必达；TTL 继续兜底。授权状态更新不得用新的签名 URL 重建同代次播放器。
