# 前端模块布局与维护边界

本轮目录重构采用业务就近放置；组件、状态、副作用各有所有者。组件数量或文件行数不是拆分标准，职责、生命周期和消费者能力才是。公开交互与状态约束见[开发契约](development-contracts.md)，通用原则见[仓库开发规范](../../AGENTS.md)。

## 目录与入口

| 位置                         | 内容与入口                                                                                                                                                 |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| src/views                    | 路由装配、导航和必要的跨模块协调；不另写查询或任务协议                                                                                                     |
| src/app                      | router、Navbar、WebSocket 连接及事件分发                                                                                                                   |
| src/shared                   | ui（按钮、菜单、复选框、封面等）、useDialog、请求版本工具、logger、toast；不依赖业务模块                                                                   |
| src/features/resources       | ResourceCard、添加结果、批量交互、useResourceSubmission、useResourceAdds；resource facade、resourceList 查询、downloadQueue 兼容队列；标题与资源操作纯函数 |
| src/features/catalog         | 演员/类别目录与详情组件；directoryStore 和实体适配 store                                                                                                   |
| src/features/external-search | ExternalSearchPanel、结果卡片、能力/任务组合函数；手动搜索与带令牌快照生命周期                                                                             |
| src/features/tasks           | TaskDetailsPanel、TaskTimeline、taskJobs、历史刮削兼容状态/反馈及展示适配函数                                                                              |
| src/features/recommendations | 偏好/指标/种子/黑名单组件；推荐查询与视图偏好状态                                                                                                          |
| src/features/cookies         | Cookie 管理面板、弹窗及状态展示；来源 API 读写                                                                                                             |
| src/features/settings        | 用户设置 store、设置面板与字体配置                                                                                                                         |
| src/features/auth            | 会话状态，启动/失效和应用装配协作                                                                                                                          |
| src/api                      | client.js 唯一 HTTP 实例；领域 API 文件；index.js 保留原有具名导出入口                                                                                     |
| src/styles/main.css          | 全局主题 token、层级与 Tailwind 入口                                                                                                                       |

子模块通过明确的组件 props/emits、store 方法或纯函数入口协作。shared 不导入 features、views、app 或领域 API；请求 guard 和展示组件不能读取资源/任务 store。不要增加会同时加载 Vue 组件和所有 store 的领域大 barrel，避免循环依赖并保留纯函数的 Node 测试能力。

现有跨业务协作是明确的：资源模块提交任务并读取标题设置；目录装配资源卡片与外部搜索面板；推荐模块消费资源添加能力；app 连接分发任务提示。不要为了消除这些真实依赖复制状态；新增依赖先确认状态所有者和公开契约。

## 状态与生命周期

推荐查询/错误/loading 属于 recommendations store，页面偏好属于 recommendationViewState，黑名单读写/缓存属于自身组件。外部搜索面板拥有来源选择、查询、部分结果和会话缓存，目录页只负责本地资源与协调事件；实体切换和卸载使旧查询失效。任务原始快照属于 taskJobs，展示派生字段属于任务适配器；资源添加按稳定 job_id 匹配批次，恢复 attempt 变化不得丢失任务归属。

useResourceSubmission 接收 resourceStore、resourceApi、toastStore 显式依赖，负责提交与批次摘要；SubmissionResults 只呈现 result/preferredTitle 并发出 view。RecommendationPreferences 通过具名 v-model 同步偏好；Metrics 接收 metrics/loading 并发出 refresh；Seeds 只展示传入种子组。ExternalSearchPanel 的协调入口与事件见开发契约。

AppCheckbox 保留原生 checkbox、标签、禁用与半选语义。ActionMenu 使用实例 ref 管理开关、键盘导航和焦点，不按 AVID 查询全局 DOM。ResourceCard 的 delete/deleteFile 事件表示操作已成功，父级只刷新列表，不能再次发出删除请求。

## API 与样式

api/client.js 独占 Axios 实例、envelope 转换、CSRF 与登录失效监听。领域 API 复用该实例，保留原有请求路径、字段、超时和错误语义；api/index.js 仅 re-export 原有具名对象和 onUnauthorized。新增接口放入对应领域文件，不能在组件中创建客户端或重新解释响应包络。

公共 UI 样式随组件。添加与推荐页面的既有视觉样式归对应 feature/styles，使用 .add-view / .recommendations-view 命名空间覆盖拆出的展示子组件；不得添加无前缀全局规则或将业务样式混入主题。主题新增值仍集中到 main.css。

## 验证

pnpm run check 包含 lint、单元测试、构建。模块布局回归检查 shared 无业务依赖、唯一 HTTP 实例及 API barrel 与领域对象同一身份。目录调整同步源码链接和浏览器样例 import；执行 pnpm run test:browser 以及根目录 pre-commit run -a。浏览器套件使用模拟 API/WS，不代表真实 worker 或生产环境验收。

InfoDialog 位于 shared/ui，管理通用信息弹窗，不读取业务 store。TaskDetailsPanel 的 information 插槽供页面装配跟踪说明。RemoteResourceActions 位于 features/resources/components，供外部搜索和推荐卡片共用操作展示；推荐反馈与理由保留在推荐模块。

推荐与外部搜索共用 features/resources/composables/useResourceAdds.js，消费提交能力和授权任务快照；旧 features/recommendations/composables/useRecommendationAdds.js 仅兼容 re-export。添加状态由返回 job_id 与最新 version 管理，保存确认后禁用，不等待所属翻译结束；未保存的失败/取消可重试，卸载与迟到响应不得影响新请求。RecommendationInformation 装配历史信息、刷新和重置弹窗；RecommendationContext 装配页内紧凑核验/种子摘要。页面持有偏好与推荐查询，借 RecommendationBlacklist 的 preferences 插槽装配联合偏好/黑名单弹窗。

useRecommendationElapsed 位于推荐 composables，仅负责当前查询本地计时与清理；成功批次用时和缓存恢复由 RecommendationsView 持有，RecommendationContext 仅展示该用时与授权核验统计。

features/playback 独占在线播放会话及播放引擎生命周期；ResourceDetailView 只打开 `/play/:avid` 新标签页；PlaybackView 仅装配 PlaybackPage（标题与播放器装配），PlaybackPlayer 拥有媒体/会话生命周期，详情页不拥有播放会话。领域传输位于 api/playback.js，复用唯一客户端，不向资源 store 混入媒体状态。hls.js 动态导入，MSE 可用时优先 hls.js；否则使用 video 的原生 HLS 能力。

播放路由的 meta.layout=playback 由 App 装配居中主区域及 Navbar.logoOnly，Navbar 复用既有 Logo，不复制品牌样式。PlaybackPlayer 拥有固定16:9播放区域及其中的加载、缓冲、错误/重试展示，状态切换不改变区域大小。

播放进度模块位于features/playback/lib：playbackProgress拥有事件/写入队列/归属，progressDrafts仅管理有界个人兜底。App作为装配层在匿名状态清理兜底；auth业务模块不反向依赖播放模块。媒体引擎与API不维护个人状态，详细契约见[播放进度](development-contracts.md#播放进度记忆)。

个人资源标记和备注归 `features/resources/components/PersonalResourcePanel.vue` 与 `features/resources/lib/personalResourceEditor.js`；前者展示，后者拥有编辑/版本/归属生命周期。用户通用偏好继续归 `features/settings/stores/settings.js`，持久化由后端UserPreferences拥有；App装配登出和用户切换时的reset，shared组件不依赖个人状态服务。

观看列表由features/viewing/components/ViewingLibrary负责读取、分页、刷新与移除，views/ViewingView仅装配，生产入口位于个人中心，旧独立路由保持兼容。HTTP归api/viewing.js并由api/index.js导出；播放历史事件归features/playback/lib/viewingRecorder.js，独立于进度写入权。

个人中心由features/personal管理功能导航与退出，复用features/viewing的列表、features/settings的PersonalSettings；views仅装配。个人状态单一editor留在PersonalResourcePanel，PersonalResourceActions展示图标状态，noteDialog负责草稿退出决定，页面slot只负责左右布局。

观看查询缓存归features/viewing/stores/viewing，组件只管理选择/页码/展示guard；App登录身份变化重置。shared/lib/personalDataEvents只传递无载荷失效信号，API写成功时发布，shared不导入领域API/store。个人中心KeepAlive保留最多四个面板，停用/卸载生命周期仍须明确；缓存现状与下一步见[方案](personal-cache-plan.md)。

features/library/lib/membershipLookup.js管理本人关系缓存与请求护栏；stores/memberships.js仅装配Pinia和api/library.js。其revision是前端失效信号，后端entry_id/version仍是持有命令的CAS依据，不引入全局库版本或推断他人库存。

DownloadsView按会话能力装配tasks/components/UserOperationsPage或LegacyDownloadsPage（兼容/DEBUG）；公共TaskDetailsPanel仅展示。tasks/composables/operationTracking.js拥有本人请求读取、排序、版本与命令归属，stores/userOperations.js装配API和关系失效，lib/operationDetails.js只转换显示。App启动/停止跟踪，WebSocket仅转发本人版本提示，不把全局队列混入共享用户页面。

features/library/lib/libraryCommands.js维护命令幂等、持有CAS、结果归属和有界批量；stores/commands.js只装配依赖并拥有来源选择弹窗意图。components/LibraryOperationDialog.vue复用公共弹窗/下拉/按钮，App作为装配入口。resource store按会话能力调用共享库命令或旧兼容API，不将operation改名为job；共享入口不直删全局资源或视频。

features/library/components/RemoteLibraryActions.vue是推荐/外部搜索按钮的本人状态装配层；resources/components/RemoteResourceActions.vue保留纯展示。成员store维护挂载项与唯一刷新计时器，membershipLookup管理合批、缓存和归属。App装配封面缓存身份失效，api/resources保留HTTP与object URL生命周期，卡片自身只持有当前图片展示代次。

LibraryMembershipsDialog拥有管理弹窗/选择/确认装配；library/lib/membershipList.js拥有有界查询与迟到响应guard，lib/batchResults.js只归纳请求内的部分成功。列表HTTP归libraryApi，移出复用既有命令核心。资源与目录页面共用批量结果归纳，不在目录保留共享模式删除视频入口。

features/admin拥有管理中心及独立账号/审计模块；views/ManagementView只按会话能力装配。api/admin.js复用统一HTTP客户端，公开adminApi同一对象导出。lib/adminRead.js管理有归属的查询，accountAdministration.js管理编辑/命令/草稿，组件仅展示与输入。管理页面不复用个人设置缓存，不持久化管理数据或密码；后续来源/GC页面作为独立业务区块加入管理中心。

管理中心的系统来源凭证位于features/admin/components/AdminSourceCredentials、SystemCredentialEditor，审计写入状态归lib/systemCredentials，复用adminRead读取与api/admin的既有来源API委托。个人凭证仍归features/cookies，不让普通入口承担系统审计命令或共享Cookie语义。

共享资源与回收记录复用AdminResources（jobs属性区分协议），确认交互由ResourceAdminDialog展示；lib/resourceAdministration负责版本/预览归属与命令重试，api/admin/resourceAdminApi负责端点装配。组件不执行文件操作或直接调用worker。
