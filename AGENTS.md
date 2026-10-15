# 仓库级开发规范（FOR AGENT）

本文件是仓库级总规范，用于约束在 `NASSAV` 仓库中的通用开发行为。

更细粒度的子项目规范以各自目录下的 `AGENT.md` 为准：

- 后端开发前，先阅读 [django_backend/AGENT.md](django_backend/AGENT.md)
- 前端开发前，先阅读 [vue_frontend/AGENT.md](vue_frontend/AGENT.md)

如果根规范与子项目规范冲突，优先遵守更贴近目标目录的规范。

## 项目结构

- `django_backend/`
  - Django 后端
  - 核心代码位于 `django_backend/nassav/`
  - 项目配置位于 `django_backend/django_project/`
  - 后端文档位于 `django_backend/doc/`

- `vue_frontend/`
  - Vue 3 + Vite 前端
  - 页面位于 `vue_frontend/src/views/`
  - 业务组件与状态位于 `vue_frontend/src/features/<业务>/`
  - 无业务依赖的 UI、组合函数及工具位于 `vue_frontend/src/shared/`
  - 路由、导航及全局事件连接位于 `vue_frontend/src/app/`
  - API 封装位于 `vue_frontend/src/api/`

## 开发前

- 先确认本次修改影响的是后端、前端，还是两者都有
- 在进行后端开发之前，先阅读 `django_backend/AGENT.md`
- 在进行前端开发之前，先阅读 `vue_frontend/AGENT.md`
- 修改前先阅读相关代码和文档，避免直接跳到实现
- 核对本规范及目标模块架构文档中的公开契约与状态所有者
- 如涉及接口、数据结构、脚本、配置或架构变更，评估是否需要同步更新文档

## 开发时

- 优先保持现有架构分层，不要把调度逻辑、抓取逻辑、API 逻辑和数据对象混在一起
- 尽量复用已有抽象，而不是平行复制一套相似实现
- 新增模块时优先考虑：
  - 职责是否单一
  - 抽象边界是否清晰
  - 后续是否容易替换或扩展
- 不要在未确认上下文的情况下重构无关代码
- 面向消费者能力定义接口，核心接受显式依赖，生产默认实现由装配层提供；不为纯函数、数据对象和简单框架入口强制增加抽象基类
- 按单一职责划分状态与副作用，通过注册、工厂、策略或 hook 扩展；不在通用流程堆叠来源/实体分支，也不为假想需求创建框架
- 结构重构保持 URL、任务名、数据字段、缓存与副作用顺序；行为修复单独说明新旧差异并覆盖失败、取消、部分成功及终态
- 异步操作检查结果归属；旧响应、迟到事件和失租执行不得覆盖新状态或发布成功副作用

## 前端页面设计规范

在修改前后端页面与组件（如 `vue_frontend/` 目录下的代码）时，除遵循 `vue_frontend/AGENT.md` 外，必须保证以下 UI 规范：

### 1. 颜色的统一与语义一致性

- **禁止硬编码颜色**：独立组件不得新增十六进制、rgb/rgba 等颜色字面量；主题值集中定义于 `src/styles/main.css`，使用 `tailwind.config.js` 映射的语义工具类或已有 CSS token。新增 token 同时覆盖深浅主题，保留入口的显式 `@config` 并验证生成样式。
- **背景与文本**：
  - 背景统一使用 `bg-primary`（应用主背景）与 `bg-secondary`（侧边栏、卡片、浮层背景）。
  - 文本统一根据权重使用 `text-primary`（常用于正文/标题）、`text-secondary`（副文本）与 `text-muted`（提示/占位文本）。
- **强调与交互（Accent）**：使用 `accent-primary`（主要交互/高亮）、`accent-secondary`、`accent-tertiary` 来处理按钮和重要点缀。
- **语义一致性**：相同语义（如危险/删除动作、确认动作、链接等）在全站的色彩应当保持唯一且一致。

### 2. SVG 图标与 Unicode 图标使用规范

- **首选 SVG 图标**：用于表达功能、操作、核心元素的图标应统统使用内联 `<svg>`。并通过 `fill="currentColor"` 或 `stroke="currentColor"` 让图标颜色跟随上下文的文字颜色变化。
- **尺寸与对齐**：所有的 SVG 图标必须显式通过 Tailwind 类定义宽高（例：`w-5 h-5` 或 `w-4 h-4`），并结合 Flex 布局（`flex items-center gap-2` 等）保证它与相邻文本精确的垂直居中对齐。
- **限制 Unicode 表意符**：严禁使用复杂的 Unicode 符号或 Emoji 代替核心功能图标（例如不要用 ⚙️、❌ 代替设置或关闭），避免在不同设备和操作系统上发生渲染差异。Unicode 图标仅限用于少量纯文本占位符或极简列表符（如 `·` 或箭头 `→`）。

### 3. 组件一致性（按钮、下拉菜单等）

- **公共组件首选**：优先复用 `AppButton`、`CustomSelect`、`ConfirmDialog`、`SearchInput`、`ResourcePagination` 等已有组件；目录与演员/类别详情复用公共模块，不复制同语义的查询和任务生命周期。
- **交互状态一致**：
  - 按钮使用公共 variant、尺寸与 loading/disabled 状态；基础样式使用合适的 CSS layer，使工具类可以覆盖显示和布局。
  - 下拉与浮窗使用 `bg-secondary`、默认语义边框（`--border-color`）、预设阴影与圆角，保证深浅主题一致。
  - 弹窗复用 `useDialog`，检查初始打开、嵌套、焦点循环/恢复和卸载清理；下拉支持键盘操作与禁用项跳过。
- **结构与留白**：区块（Card）、表单内外间距必须统一使用 Tailwind 标准间距尺码（如 `p-4`, `gap-3`, `mt-6`），同一层级应保持视觉一致，避免生硬和跳跃的排版。

## 验证要求

`pre-commit` 是必须项，不是可选项。

完成代码或文档修改后，至少执行：

- `pre-commit run -a`

如果任务只涉及后端，还应优先补充：

- `cd django_backend && uv run pytest tests/ --ds=django_project.refactoring_test_settings -v`

前端代码修改执行 `cd vue_frontend && pnpm run check`；主题、布局、键盘和弹窗生命周期修改另执行相关浏览器检查。命令必须保留退出码，不通过输出截断掩盖失败。后端隔离设置、在线 opt-in 和测试依赖见[测试说明](django_backend/tests/README.md)。

如果 `pre-commit run -a` 失败：

- 必须先修复失败项，再结束任务
- 不要在存在已知 lint、format、type check 或 compile check 错误的情况下宣称完成
- 质量门槛无法达成时说明失败证据，暂停依赖该门槛的合并并与用户沟通
- 分别报告已实现、隔离验证与目标环境验收，不把模拟 API、eager task 或构建通过当作真实服务联调

## 文档要求

- 发布版本同时更新`django_backend/pyproject.toml`、`django_backend/uv.lock`中的项目版本与`vue_frontend/package.json`，检查锁文件一致性；发布文档区分制品准备、远端发布和正式部署，不把历史迁移快照或隔离测试当作当前实例验收。
- 版本变更日志统一写入根目录 [CHANGES.md](CHANGES.md)，按版本倒序排列并沿用现有分类；README 仅保留入口，不再追加版本记录
- 后端相关改动，需要检查 `django_backend/doc/` 下文档是否需要同步更新
- 新增接口时，应更新接口文档
- 新增或调整数据库相关行为时，应更新数据库文档
- 新增脚本、推荐链路、服务编排或其他非显然行为时，应补充设计说明文档
- 后端职责维护于[任务架构与职责](django_backend/doc/task-control-architecture.md)，前端职责与组件约束维护于[开发契约](vue_frontend/doc/development-contracts.md)与[模块布局](vue_frontend/doc/module-layout.md)；执行记录注明提交、命令和验证范围

## 提交约定

- 提交信息沿用仓库既有前缀风格：
  - `[Feat]`
  - `[Fix]`
  - `[Chore]`
  - `[Enhancement]`
  - `[Doc]`
- 一次提交应尽量聚焦一个明确目标
- 未获提交授权时主动询问并给出提交信息；用户已授权分阶段提交和合并时直接执行，不重复询问
- 本轮已授权流程：仅在 `/tmp/nassav-agent-worktree` 使用独立阶段分支，通过质量门槛后提交并合并 `idle`，结束保持工作树干净且位于 `idle`；默认工作树保留给用户使用

## 默认收尾清单

除非任务明确说明不需要，完成修改后默认执行以下检查：

1. 运行与改动直接相关的测试
2. 清理相关临时文件
3. 运行 `pre-commit run -a`
4. 确认必要文档已更新
5. 再输出最终结论

## 持久任务开发约束

涉及下载、刮削、所属翻译、任务控制或文件清理时，先阅读[任务控制架构](django_backend/doc/task-control-architecture.md)。DB 是持久业务状态所有者；恢复使用新 attempt/generation，旧执行不得提交。暂停/终止须确认写入者停止，终态不等于清理完成；不得在线删除锁文件、手动清空 `.tasks` 或以 Celery revoke 代替控制协议。发布、回滚与删除复用共享资源/目标锁及资产日志；网络、复制和大文件哈希不得放入短 DB 提交回调。前端按 job_id/version 合并授权快照，以 allowed_actions 决定操作。

## 推荐开发约束

修改推荐、反馈或历史重置前阅读[推荐架构](django_backend/doc/recommendation-architecture.md)。
推荐 job 由 DB 持有，Celery 仅运输；成功检查历史 generation、执行 UUID 和 deadline。
网络不进入短提交事务；取消/重置后的旧执行不得保存 snapshot。
推荐来源与浏览器出口共用全局 Proxy.url，Byparr 控制直连，不混用下载代理。
详情失败消耗共享预算，启用 seed 黑名单时排除未核验候选并告知数量；
推荐上下文、历史、反馈和三类黑名单按当前用户显式绑定；Item/Feedback沿snapshot归属，无owner兼容实例只访问待导入旧行。重置只取消本用户job，反馈先取得本用户历史写入fence，再读取旧值和更新计数。离线映射不默认自动运行。

代理服务器并发能力统一由 `ProxyServer` 提供，不以 Byparr 等具体 provider 决定业务调度；
来源实例、会话和网络控制按并发操作隔离，结果、预算与提交由协调线程持有，
跨 worker 容量和开发约束见[代理并发架构](django_backend/doc/proxy-concurrency.md)。

## 抓取缓存开发约束

原站事实、短期播放缓存与正式资源独立，迁移/流程遵循[持久抓取缓存](django_backend/doc/resource-cache-architecture.md)。命中仍执行当前黑名单与业务判断；不得混入翻译/用户状态或把旧来源地址当永久有效。网络在事务外，缓存提交检查执行归属、租约和代次；定期清理有界且只清理缓存记录。

## 数据库表名约束

业务模型显式声明 Meta.db_table；表名全小写，单词之间用下划线，AV/AVID 等缩写作为整体。改名使用新增可逆迁移，保留既有历史迁移与模型身份；自动多对多表随主表检查，固定已有索引名称避免附带结构变更。迁移验证覆盖 SQLite/PostgreSQL 的升级、回退、再次升级与业务/关系数据保持；正式切换前核对活动数据库、备份与所有消费者版本，按维护窗口停止写入，不混跑旧表名消费者。

## 播放与个人进度约束

修改播放/进度先阅读[播放架构](django_backend/doc/online-playback-architecture.md)和[个人进度](django_backend/doc/playback-progress-architecture.md)。会话是短期授权，进度是用户持久状态，不混入AVResource.watched或原站缓存。媒体身份由服务端决定；来源账本键不代表字节相同，新会话续播须确认，不按AVID跨来源/本地模式套位置。保存/清除核查写入代次、序号和版本；旧页面不自动抢回写入权，清除保留墓碑防止token复用。离页合并保存和关闭，不依赖销毁后的JS回调，未送达由现有TTL兜底；浏览器模拟不代替真实媒体/数据库联调。

多用户能力属于[路线规划](django_backend/doc/multi-user-roadmap.md)，未开放登录权限。开放前明确共享资源与个人状态的权限矩阵，迁移旧收藏/观看/推荐数据的归属，并对HTTP、WebSocket、任务与媒体统一用户隔离，禁止仅取消operator用户名限制。

## 个人状态与设置约束

收藏、已观看、备注和通用显示/搜索设置遵循[个人状态与设置](django_backend/doc/personal-state-architecture.md)，由UserResourceState/UserPreferences按用户持有，不写旧AVResource标记、不读写用户INI、不混入共享抓取缓存或任务事件。HTTP以request.user确定身份，列表批量投影避免逐卡查询；备注版本冲突保留前端草稿，禁止旧资源/旧用户响应改写当前状态。原数据通过指定操作者的只读、幂等导入命令迁移，不能复制给所有账号。开放多账号登录仍须完成统一权限和推荐隔离。

UserPreferences以JSON覆盖值保存通用设置；当前键/类型/默认值/校验集中在preference_definitions，业务通过有效配置入口读取，不直接消费原JSON。GET合并默认值且不写回，PUT校验后只合并提交项，不顺手删除未知存储键；前端只提交改动字段。配置删除/改名/类型演进使用新增数据迁移，保留历史迁移；旧数据导入仅创建缺失行，不再持有导入时间标记。

## 个人设置与跨设备进度

用户设置由UserPreferences JSON持有，合法键/默认值/类型以preference_definitions为准；GET只读补齐且不返回废弃键，PUT仅合并合法提交项，不接受用户指定owner。删/改键需明确数据迁移，不能依靠前端清理。新增播放数值设置接受JSON整数/小数，禁止布尔和数值字符串；原有设置类型保持契约。

跨设备共享user进度，session控制仍绑定具体登录。继续观看只投影本用户的最新ledger及仍存在/身份匹配的资源，不返回源站链接或凭证，不抓取来源。打开页面不抢占保存权；明确接续先读最新快照，再CAS领取，并使用claim返回的位置。旧writer的409只读，不自动抢回；零位置清除tombstone不能被旧请求复活。不因个人表已隔离就移除is_operator或开放共享资产控制权限。

## 观看列表约束

观看历史与稍后观看遵循[个人观看列表](django_backend/doc/viewing-architecture.md)。历史唯一(user,pool)，展示快照只保留当时本人授权标题/AVID/来源；真实播放/恢复更新队首，play之后的playing才上报；缓冲、读取、准备、claim和重试不新增事件。按会话generation/sequence拒绝旧执行或幂等去重，不绑定进度writer，只读播放同样记录。稍后观看沿用个人状态version与手动移除，不自动标记已观看或删队列；资源回收保留历史快照且不授予封面/播放权限，稍后观看仍随资源删除清理，播放进度按原规则保留。查询绑定request.user，不持久化个人列表到浏览器存储，不据旧进度推测回填历史。

## 应用角色与共享池（开发中）

修改角色、持有、管理、配额或账号撤销前阅读[共享池](django_backend/doc/resource-pool-architecture.md)与[账号策略](django_backend/doc/account-policy-architecture.md)。UserAccount才是应用角色所有者，不从Django标志推导管理权限；普通账号登录仍关闭。未引导operator兼容路径不属于新角色授权，禁止用它绕过后续凭证/共享工作协议。管理命令必须版本/幂等/理由代码/审计，管理fence在排序user→pool→work/session之前，普通业务不反向取得它。审计清理不删除持久命令receipt；配额释放不以writer超时为证明。停用/移出先撤销本人共享订阅；他人仍有需求时不得终止共享job，旧单owner任务另走原停止协议。图片/媒体先授权再响应304/206，播放grant不代替P5读取占用与不可变版本。

## 来源凭证开发约束

新增加密凭证和刷新快照遵循[凭证架构](django_backend/doc/source-credential-architecture.md)。专用keyring不可回退SECRET_KEY或明文；HTTP只返回元信息，禁止秘密进入日志、审计、任务参数或公共缓存。来源host由服务端配置决定，个人凭证不自动提升公共。刷新须检查凭证version、快照context、owner/generation/lease及执行归属，人工更新/撤销使旧结果失效；只释放本人租约。旧Cookie显式分类导入，未知账号Cookie隔离，不双写或自动清除。新模式默认关闭，启用时全部消费者统一重启，不混跑旧Cookie写入者。ProxyServer声明会话能力，私人请求不得将匿名HTML视为成功；原站Cookie禁止跟随重定向或发往CDN。DB缓存和推荐终态先取得key policy/actor/credential fence，再进入既有短提交；Redis仅用失效版本命名空间，不持DB锁调用Redis。旧active key writer不得绕过DB key policy，轮换保留历史密钥且CAS预检。共享正式媒体当前只用system，私人资产待P4/P5。

共享请求遵循[共享工作](django_backend/doc/shared-work-architecture.md)。UserOperation与SharedWork/TaskJob身份、版本、权限分开；默认旧执行器不得派发/领取shared_work。状态按本人游标投影，不广播内部诊断；成功必须由P5发布证据激活，取消/失代次不得复活持有。user→pool→work→task锁顺序不变，禁止pool持锁后遍历取得其他user锁；提示在事务后仅发送operation_id/version。

版本/占用遵循[资源版本](django_backend/doc/resource-version-architecture.md)。元数据与视频指针分离，已发布数据不可原地改写；公开版本owner为空，其他范围仅所属用户，不授予管理员私人媒体权。读取固定version/登录/账号epoch，移出仅允许已有合法播放grant在原期限续读，不能新授权或延长；GC同时检查占用和仍可续读的播放session，不能用lease超时替代writer停止。当前发布/网关接入未完成，不在旧流程直接启共享执行。

共享版本发布复用TaskAssets日志/文件锁及DjangoSharedExecutionRecords来源→pool→work→task fence；public工作上下文actor必须为空，不能绑定最初提交人。新目标限定对应versions/UUID，禁止旧AVID/头像全局路径。指针同时核对父版本/revision，未完成翻译和源链接不写正式展示snapshot；旧token与仍owned的来源失效区分收尾，不留下running ghost。成功激活需发布证据，私人数据不能写共享AVResource列；目录/推荐/媒体消费须显式投影版本。

共享执行器只运输job/attempt身份并关闭结果存储，禁止把checkpoint/源链接复制到Celery结果。NASSAV_SHARED_LIBRARY_ENABLED默认false且依赖范围凭证；当前HTTP/配额/正式读取未完成不得用于开放普通用户。刮削翻译在正式不可变提交之前完成、失败保留旧版；下载复用现有媒体验证与停止证明，按job隔离租约/投影且保留全局槽位。恢复键从DB job身份推导，不信任保存的任意Redis key；网络实例fork与transport关闭由装配统一管理。

共享库命令必须使用当前user、持久request_id回执和expected_entry_version；旧DELETE重放不得删除重添关系。意图按元数据/视频kind分代次，旧成功不覆盖最新需求；先附新订阅再撤本人旧订阅，不杀B。配额按本人video版本完整逻辑字节，未知大小保守预留，最终grant在user fence核查，超额只拒绝本人并退款。public/personal明确选择，个人凭证缺失不得回退；幂等重试先查意图账本再加载来源。source/quality/scope/credential/context与ready证据不符不得复用文件。

共享模式资源展示走本人持有版本投影，不将私有标题/演员/图片复制到AVResource等全局列。版本图片使用授权入口及短读取占用，根下目录/文件NOFOLLOW且核查manifest/marker/内容，不以opaque URL代替权限；个人状态写入在user fence内重新核查持有。

共享模式本地播放在创建事务核查descriptor与本人video_version相同，session固定版本和账号epoch；授权读取占用不能以Redis容量代替。坏版本不回退旧AVID文件，旧会话不得跟随当前指针切换，原播放宽限与下架即时撤销保持区分。

版本化来源播放使用本人元数据版本的冻结凭证引用与source_name，密钥可用性在创建事务外检查，创建/worker/媒体读取再次核查范围/账号代次。不得凭空共享私有引用、初始化无范围来源来替代检查，或以新Cookie复活旧元数据授权。新source进度key隔离scope/context，provider账本仍不证明字节相同。

用户演员/类别目录以UserCatalogTerm/UserCatalogLink投影本人当前元数据持有，成功grant在user→pool事务批量同步；link不代表额外持有。不得用全局Actor/Genre的资源锚点关系代替版本事实，私有名称不全局提升；目录整数ID只是用户投影，外部搜索/推荐不得误当旧全局Actor/Genre ID。

共享目录整数ID属于本人term，不当作旧全局Actor/Genre映射ID；外部搜索使用命名实体和独立cache/job namespace。推荐本地种子沿本人当前关系聚合，新lookup_payload不得冒充全局actor_id触发学习；名称黑名单按本人历史fence更新。旧目录句柄/账户epoch失效须在网络前终止。
