# 前端模块布局与维护边界

本轮目录重构采用业务就近放置；组件、状态、副作用各有所有者。组件数量或文件行数不是拆分标准，职责、生命周期和消费者能力才是。公开交互与状态约束见[开发契约](development-contracts.md)，通用原则见[重构原则](../../docs/development-principles.md)。

## 目录与入口

| 位置                         | 内容与入口                                                                                                                                |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| src/views                    | 路由装配、导航和必要的跨模块协调；不另写查询或任务协议                                                                                    |
| src/app                      | router、Navbar、WebSocket 连接及事件分发                                                                                                  |
| src/shared                   | ui（按钮、菜单、复选框、封面等）、useDialog、请求版本工具、logger、toast；不依赖业务模块                                                  |
| src/features/resources       | ResourceCard、添加结果、批量交互、useResourceSubmission；resource facade、resourceList 查询、downloadQueue 兼容队列；标题与资源操作纯函数 |
| src/features/catalog         | 演员/类别目录与详情组件；directoryStore 和实体适配 store                                                                                  |
| src/features/external-search | ExternalSearchPanel、结果卡片、能力/任务组合函数；手动搜索与带令牌快照生命周期                                                            |
| src/features/tasks           | TaskDetailsPanel、TaskTimeline、taskJobs、历史刮削兼容状态/反馈及展示适配函数                                                             |
| src/features/recommendations | 偏好/指标/种子/黑名单组件；推荐查询与视图偏好状态                                                                                         |
| src/features/cookies         | Cookie 管理面板、弹窗及状态展示；来源 API 读写                                                                                            |
| src/features/settings        | 用户设置 store、设置面板与字体配置                                                                                                        |
| src/features/auth            | 会话状态，启动/失效和应用装配协作                                                                                                         |
| src/api                      | client.js 唯一 HTTP 实例；领域 API 文件；index.js 保留原有具名导出入口                                                                    |
| src/styles/main.css          | 全局主题 token、层级与 Tailwind 入口                                                                                                      |

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
