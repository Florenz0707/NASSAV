# NASSAV - AV 资源管理系统

基于 Django、Celery 和 Vue 的资源管理系统，提供多源获取、元数据刮削、异步下载、推荐和实时任务进度。项目基于 [Satoing/NASSAV](https://github.com/Satoing/NASSAV) 重构；历史参考代码已从当前仓库移除。

## 功能与入口

- 资源浏览、搜索、添加、刷新、下载与批量操作；按演员和类别聚合。
- 三个 Celery 队列分别处理默认任务、刮削和下载；任务状态由 API 与 WebSocket 提供。
- 单用户 Django 会话保护业务 API 和任务 WebSocket；登录后使用浏览器 Cookie 与 CSRF 令牌。
- [前端页面与本地开发](vue_frontend/README.md) · [后端本地开发](django_backend/README.md) · [后端接口](django_backend/doc/interface.md) · [数据库说明](django_backend/doc/database.md)
- [重构原则与持续开发约束](docs/development-principles.md) · [后端模块边界](django_backend/doc/p5-domain-boundaries.md) · [前端开发契约](vue_frontend/doc/development-contracts.md) · [Agent 规范](AGENTS.md)

## 快速开始

默认 Compose 使用 SQLite，包含前端网关、API、Redis、Byparr 和三个 worker。所有后端服务统一使用 `.env` 的 `NASSAV_UID:NASSAV_GID`（默认 1000:1000），首次部署或切换 root 旧实例前按部署说明准备绑定目录权限。首次部署按[全栈 Compose 部署说明](django_backend/doc/compose-deployment.md)准备 `.env`、配置文件和数据目录，然后从仓库根目录运行：

```bash
python3 scripts/compose_stack.py --mode sqlite init
python3 scripts/compose_stack.py --mode sqlite config --quiet
python3 scripts/compose_stack.py --mode sqlite up -d --build
python3 scripts/compose_stack.py --mode sqlite exec api python manage.py createsuperuser --username nassav
```

账号密码由 `createsuperuser` 的交互提示设置。若修改 `NASSAV_OPERATOR_USERNAME`，用户名须与其一致。默认页面仅监听 `127.0.0.1:9780`；远程访问需同源 HTTPS 反向代理，并按部署说明配置 Host、CSRF 和安全 Cookie。Beat 在 `scheduler` profile 中启用且全系统只运行一个实例。

PostgreSQL 模式连接外部数据库，需密码 secret 和 `compose.postgres.yaml` 覆盖文件；具体命令与回滚步骤见[部署说明](django_backend/doc/compose-deployment.md#外部-postgresql可选)。**开发库的数据已导入，业务回归、备份恢复验收及正式切换尚未完成**。默认 Compose 仍使用 SQLite；首次启动需声明数据目录的数据库模式，后续 `up`、`ps`、`logs`、`exec`、`down` 使用相同模式的部署入口。直接误用基础 Compose 时，应用会在连接数据库前拒绝模式冲突；不要仅修改 `.env` 的 `DB_ENGINE` 来切换。数据库行为见[数据库模式与备份说明](django_backend/doc/database.md)；开发导入与正式切换的边界见[验证状态](django_backend/doc/validation-status.md)。

本机开发分别参照[后端说明](django_backend/README.md#快速开始)和[前端说明](vue_frontend/README.md#本地开发)；Vite 开发页的 API 和 WebSocket 使用同源代理。启动检查、代理路由和数据目录的细节统一记录在[配置契约](django_backend/doc/configuration-contract.md)、[代理路由](django_backend/doc/proxy-routing.md)和[Compose 部署说明](django_backend/doc/compose-deployment.md)。

## 当前功能与验证状态

资源添加/刷新通过异步任务执行；演员和类别外部搜索支持来源选择、渐进结果、取消和终态补查。下载和批量翻译的 owner/异常收尾修复、资源/下载/翻译/推荐用例分层已实现；消费者 URL、响应字段和 Celery 任务名保持。

隔离测试、目标环境接受和正式发布分别记录。重构基线的历史离线门槛为 539 passed、24 skipped；真实 PostgreSQL 恢复、另一设备 HTTPS/WSS、外站抓取/下载及混合版本 worker 不由这个结果覆盖。当前边界和待验收证据见[验证状态](django_backend/doc/validation-status.md)。

## 文档导航

- 本地开发：[后端](django_backend/README.md)、[前端](vue_frontend/README.md)
- 消费者与数据：[接口与权限](django_backend/doc/interface.md)、[数据库与备份](django_backend/doc/database.md)、[推荐系统](django_backend/doc/recommendation.md)
- 架构与配置：[模块边界](django_backend/doc/p5-domain-boundaries.md)、[配置契约](django_backend/doc/configuration-contract.md)、[代理路由](django_backend/doc/proxy-routing.md)
- 运行与复验：[Compose 部署](django_backend/doc/compose-deployment.md)、[进程管理](django_backend/doc/host-processes.md)、[脚本](django_backend/scripts/README.md)、[测试](django_backend/tests/README.md)、[验证状态](django_backend/doc/validation-status.md)

## 版本更新

### v2.4.0（2026-09-28）

#### 🆕 新增

- **单用户访问边界**：业务 API 和任务 WebSocket 使用登录会话；浏览器写入请求校验 CSRF，WebSocket 校验 Origin，前端处理会话过期。

#### 🔧 优化

- **部署与启动配置**：明确 SQLite 与外部 PostgreSQL 的 Compose 模式、三队列 Worker 和唯一 Beat；无效配置在启动时给出明确错误。
- **实时任务与模块边界**：开发环境的 HTTP/WebSocket 使用同源代理，断线后补查任务状态；按资源、下载、推荐职责拆分后端和前端状态逻辑。
- **主题样式**：相关卡片和搜索框使用统一设计变量，调整深浅主题的文字对比度。

#### 🐛 修复

- 修复 WebSocket 异常关闭后会话核对与重连、首次连接失败时的轮询补偿，以及不一致数据库配置可能造成的启动歧义。

#### 🧹 清理

- 删除未使用的辅助代码和一次性迁移脚本；移除 `origin_project/` 历史参考代码，当前构建与运行入口保持在根目录及前后端项目中。

#### 📚 文档

- 将此前的项目质量阶段实施过程归档为[验证边界与历史记录](django_backend/doc/validation-status.md)；未完成的职责收口与目标环境验收见[验证边界与历史记录](django_backend/doc/validation-status.md)。PostgreSQL、Byparr 和异步刮削的独立验收计划继续保留。

### v2.3.0（2026-09-28）

#### 🆕 新增

- **异步资源刮削**：新增资源刮削任务及状态查询接口；添加、刷新资源时可跟踪刮削阶段，前端通过现有任务更新通道展示进度，并在完成或失败时显示通知。
- **完整 Compose 部署**：新增包含前后端、Redis、Byparr 和独立 scrape、download、default Worker 的部署入口；Ollama 可通过可选 profile 启动，并提供 GPU 覆盖配置。
- **PostgreSQL 可选配置与备份**：支持本地 `config.yaml` 和 Compose 覆盖文件连接外部 PostgreSQL，按数据库引擎执行备份，并提供 PostgreSQL 空库恢复命令。默认 Compose 仍使用 SQLite；开发库数据已导入，业务回归、备份恢复验收与正式切换尚未完成。

#### 🔧 优化

- **代理路由**：下载代理与页面抓取代理分开配置，Byparr 浏览器请求可使用项目配置的代理。
- **本地启动**：新增后端服务快捷命令及启动参数，可按需运行 API、各队列 Worker 和 Beat。

#### 🐛 修复

- 修复查询 Celery 队列时阻塞 WebSocket 握手的问题。
- 扩大 `translated_title` 字段长度，以容纳 PostgreSQL 导入时发现的较长标题。

#### 📚 文档

- 补充异步刮削、Compose 部署、代理路由和 PostgreSQL 迁移说明；当时新增的质量执行计划已在 v2.4.0 归档，当前结论见[验证边界与历史记录](django_backend/doc/validation-status.md)。

### v2.2.0（2026-09-26）

### Byparr 页面抓取迁移

- 使用固定 digest 的 Byparr 3.0.4 Compose 服务，宿主机控制地址为 `http://127.0.0.1:8192`；新增 `BrowserFetch` 配置及逐源请求顺序。
- 新增统一的浏览器页面获取层。MissAV 默认浏览器优先，Jable 默认直连优先；两条路径共用业务页面校验，拒绝挑战页、异常重定向和无效详情页。
- MissAV 自动获取的 Cookie 经现有 Repository 保存并更新运行时缓存；Cookie API 的请求和响应结构、数据库表结构均未改变。
- 将在线抓取测试改为显式启用，补充协议、配置、回退、搜索缓存及 Cookie 回归测试。本地开发已验证两个详情样本；生产验收范围与剩余项见 [验证边界与历史记录](django_backend/doc/validation-status.md)。

### v2.1.0（2026-04-17）

#### 🆕 新增

- **外部搜索详情能力（首期 Jable）**：新增演员详情与类别详情的外部搜索聚合接口，支持多源扩展架构（Jable 已实现，其他源保留占位）。
- **开放 API 文档**：新增 OpenAPI Schema 与文档页，可通过 docs 页面直接查看和调试接口。
- **外部搜索缓存层**：在 Jable 搜索与推荐召回链路加入页面级缓存，详情页与推荐页共享收益，降低重复抓取开销。

#### 🔧 优化

- **路径规范统一**：推荐、演员、类别等核心接口统一为无尾斜杠主路径，并保持兼容路径，前后端调用同步更新。
- **外部结果字段精简**：详情外部搜索结果聚焦核心展示字段，新增 in_library 标记用于快速判断是否已在本地库。
- **单用户 NAS 场景适配**：缓存策略收敛为低复杂度单层方案，默认可控、易维护，并支持强制刷新重新抓取。
- **推荐链路联动刷新**：推荐接口支持强制绕过外部缓存，前端推荐页与详情页提供“刷新外部结果”触发入口。

#### 🎨 前端体验

- **详情页外部搜索增强**：演员详情页与类别详情页支持外部结果排序切换、分页浏览与手动刷新。
- **推荐页交互增强**：推荐页新增外部刷新入口，保留个性化参数面板并优化结果续推行为。

#### 🐛 修复

- 修复外部搜索与推荐链路中因接口参数/路径不一致导致的联调问题。
- 修复 OpenAPI 在部分 APIView 上无法推断 serializer 的文档生成告警。
- 修复推荐与外部搜索相关测试桩签名不一致导致的回归风险。

#### 📚 文档

- 更新根 README 与接口文档，补充 v2.1.0 能力说明、外部搜索参数与缓存刷新语义。

### v2.0.0（2026-03-29）

#### 🆕 新增

- **推荐系统主链路**：新增基于本地高频演员/类别与 Jable 搜索结果的 demo 推荐系统
  - 后端新增 `RecommenderManager`、`RecommendationStrategy`、`AbstractRecommender` 等分层结构
  - 当前提供 `jable_search` recommender 与 `local_preference` strategy，可继续扩展更多推荐器与策略
  - `Jable.search()` 已支持直接解析站内搜索结果页，输出统一候选结构
- **推荐接口**：新增推荐相关 REST API
  - `GET /api/recommendations/`
  - `GET /api/recommendations/options`
  - `GET /api/recommendations/cover`
  - `GET /api/recommendations/demo`
- **推荐页前端界面**：新增独立推荐页与导航入口
  - 支持选择 recommender / strategy / 返回数量
  - 支持手动触发推荐、查看推荐理由、直接加入资源库
  - 已对“当前会话已添加资源”做前端隐藏处理
- **推荐封面代理缓存**：新增后端推荐封面代理与缓存，避免前端直接请求 Jable 资源导致在中国大陆无法加载

#### 🔧 优化

- **推荐结果过滤**：推荐请求默认过滤本地已存在资源，并将 `exclude_existing` 暴露为显式请求参数
- **推荐信息说明**：推荐接口返回 recommender / strategy 的名称与说明，前端可直接渲染说明文本
- **前端交互收敛**：推荐页改为手动触发请求，合并重复的选择与展示区，卡片中的评分与理由展示更紧凑
- **视觉细节调整**：补充浅色模式颜色修正，并优化推荐页选择区对齐

#### 🐛 修复

- 修复定时清理任务未正确清理过期日志文件的问题

#### 📚 文档

- 新增推荐系统设计文档：`django_backend/doc/recommendation.md`
- 更新根 README、接口文档与 REST API 端点列表，补充推荐系统相关说明

### v1.4.0（2026-02-25）

#### 🆕 新增

- **移动端适配**：全面支持小屏幕设备
  - Navbar 新增汉堡菜单，移动端下折叠为抽屉式导航，路由切换自动关闭
  - BatchControls、ResourceSearchBar、ResourcePagination 均改为自动换行布局，避免溢出
  - 演员详情页、类别详情页新增返回按钮，样式与资源详情页保持一致
- **无障碍支持（Accessibility）**
  - 刷新/删除等图标按钮补充 `aria-label`、`aria-haspopup`、`aria-expanded`
  - 下拉菜单添加 `role="menu"` / `role="menuitem"` 语义
  - ConfirmDialog 添加 `role="dialog"`、`aria-modal`、`aria-labelledby`、`aria-describedby`
  - Toast 通知容器添加 `aria-live="polite"`，错误类型使用 `role="alert"`
  - 下拉菜单与对话框支持 Esc 键关闭

#### 🔧 优化

- **下载按钮 Loading 状态**：点击下载后按钮立即显示旋转 spinner 及"下载中"文字，视频就绪后自动重置
- **批量选中高亮**：批量模式下选中的资源卡片显示高亮边框与外发光效果
- **下拉菜单智能定位**：刷新/删除下拉菜单在靠近视口顶部时自动向下翻转，避免被裁剪
- **Navbar 滚动阴影**：页面滚动超过 10px 时 Navbar 底部平滑出现阴影
- **演员头像懒加载**：ActorGroupCard 头像图片添加 `loading="lazy"`，减少初始加载开销
- **资源列表骨架屏**：切换筛选条件时以 shimmer 骨架屏替代 LoadingSpinner，消除内容闪烁

#### ♻️ 重构

- **颜色系统统一**：将所有 Views 层残留的硬编码 hex 颜色（`#ef4444`、`#4ecdc4` 等）全部替换为 CSS 变量
- **图标规范化**：将 Unicode 字符图标（◉ ◷ ✓ ✕ ⚠ ℹ）全部替换为 SVG 图标

---

### v1.3.8（2026-02-20）

#### 🆕 新增

- **批量添加错误详情展示**：批量添加资源时，失败的资源现在会直接在标签内显示具体错误码（如 `ABC-123:404`），并根据错误类型使用不同颜色标识（404-橙色、403-紫色、502-黄色、500-深红色）

#### 🔧 优化

- **简化操作流程**：移除添加资源结果页面的"继续添加"按钮，简化用户操作流程

---

### v1.3.7（2026-02-09）

#### 🆕 新增

- **字体选择功能**：在设置页面新增字体样式选择，支持 Mplus2、TheWriteRight、ZenKakuGothicNew 三种字体，提供实时预览功能
- **后端搜索功能**：将搜索功能从前端移至后端，支持对 `original_title`、`source_title`、`translated_title` 三个标题字段进行模糊搜索，提升搜索性能和准确性

#### 🔧 修复

- **时间字段更新bug**：修复刷新资源时错误更新 `metadata_created_at` 字段的问题，确保创建时间只在资源首次创建时设置
- **测试环境隔离**：修复测试运行时覆盖生产环境 `user_settings.ini` 配置文件的问题，测试现在使用独立的临时配置文件
- **导航栏高亮bug**：修复资源库下拉菜单中"全部资源"选项始终高亮的问题，现在只在当前页面时才高亮

#### ⚡ 改进

- **搜索图标优化**：将搜索栏中的搜索图标从 Unicode 字符替换为 SVG 图标，尺寸放大并优化垂直居中显示

---

### v1.3.5（2026-01-10）

#### 🆕 新增

- **观看和收藏状态管理**：为资源添加 `watched`（已观看）和 `is_favorite`（已收藏）字段
- **状态切换功能**：资源详情页新增收藏和观看状态按钮，支持一键切换
- **状态过滤**：资源列表支持按观看状态和收藏状态过滤（已观看/未观看/已收藏）
- **状态更新接口**：新增 `PATCH /api/resource/{avid}/status` 接口用于更新资源状态

#### 🔧 修复

- **时间字段语义修正**：
  - 将 `metadata_saved_at` 重命名为 `metadata_updated_at`（元数据最后更新时间）
  - 新增 `metadata_created_at` 字段（元数据首次创建时间）
  - 修复了时间字段语义不清的问题
- **状态显示修复**：修复资源详情页初始状态不随后端数据更新的问题
- **遗留字段清理**：清理所有代码中对旧字段 `metadata_saved_at` 的引用

#### ⚡ 改进

- **排序功能增强**：
  - 资源列表支持按元数据创建时间排序
  - 资源列表支持按元数据更新时间排序
- **UI 优化**：
  - 收藏和观看按钮移至封面下方，使用 `justify-between` 布局
  - 按钮显示文字标签和图标，状态更直观
  - 激活状态有背景色高亮（收藏：红色，观看：绿色）
- **文档更新**：更新接口文档，补充新字段和过滤参数说明

---

### v1.3.2（2026-01-05）

#### 🆕 新增

- 添加定时备份任务（`backup-database-daily` / `backup-avid-list-daily` / 同步任务支持）
- 配置项调整：将 `UrlPrefix` 重命名为 `FilePathPrefix`，新增 `BackupPath` 用于 `sync_backups` 命令目标目录
- 将批量删除操作拆分为 `delete-video` 与 `delete-all`，以便更精细的删除控制

#### 🐛 Bug 修复

- 修复前端 Cookie 显示错误和后端未正确设置 Cookie 的问题，同时为部分请求添加 `Referer` 头以提升来源兼容性
- 删除资源时同时清理缩略图（修复遗漏的缩略图删除逻辑）
- 移除 GET 资源接口的 `search` 查询参数（由前端的模糊搜索逻辑替代）

#### ⚡ 改进

- 启用 SQLite 的 WAL 模式以提升可恢复性与并发表现
- 新增数据库、AVID 列表与资源一致性检查的定时任务，并统一日志持久化与 30 天保留策略

---

### v1.3.0（2026-01-03）

#### 🆕 新功能

**系统设置页面：**

- ⚙️ **设置页面**：新增独立设置页（`/settings`），集中管理 Cookie 和系统配置
- 🍪 **Cookie 管理模块**：查看、设置、自动获取、删除下载源 Cookie，实时显示状态
- 📝 **用户设置持久化**：通过 `/api/setting` 接口将前端配置保存到后端 `user_settings.ini`
- 🎨 **通用设置**：支持控制女优头像显示、选择标题显示字段（原始/源站/翻译）

**女优头像功能：**

- 🖼️ **Javbus 头像集成**：自动从 Javbus 获取女优头像并保存到本地
- 👤 **头像显示**：演员列表和详情页支持显示女优头像（可通过设置开关）
- 🔍 **头像筛选**：演员列表支持 `has_avatar` 参数按头像状态筛选
- 🎯 **智能降级**：无头像时显示文字占位符

**封面与标题优化：**

- 📷 **Javbus 封面优先**：优先使用 Javbus 封面（质量更稳定），403 错误时自动回退到源站封面
- 🏷️ **多标题支持**：后端同时返回原始标题、源站标题、翻译标题，前端可选显示

#### 🐛 Bug 修复

- 🔧 修复 Javbus 女优名解析问题：正确处理带括号的女优名（如"めぐり（藤浦めぐ）"）
- 🔧 修复视频时间排序接口返回未下载资源：`sort_by=video_create_time` 时自动过滤
- 🔧 修复后端女优头像处理逻辑，确保头像正确保存和 API 返回
- 🔧 过滤无作品的演员，避免空数据显示

#### ⚡ 优化改进

- 🔍 女优名解析增强：改进正则表达式以支持复杂括号内容和特殊字符
- 🎯 封面下载鲁棒性：添加 HTTP 403 错误处理和自动重试机制
- 📊 API 增强：女优列表接口支持更多筛选条件
- 🧹 接口整合：移除冗余的 Cookie 设置功能，统一到设置页管理

---

### v1.2.0（2026-01-02）

#### 🎯 核心功能增强

**后端新特性：**

- ✨ **细粒度刷新控制**：支持独立刷新 m3u8、元数据、翻译（3个开关互不干扰）
- 🔄 **批量操作接口**：支持批量添加、刷新、删除资源，批量提交下载任务
- 🌐 **AI 智能翻译系统**：基于 Ollama 的日译中标题翻译，支持批量翻译和异步任务
- 🗂️ **source_title 规范化**：统一 AVID 格式（大写 + 前缀），保证数据一致性
- 📝 **DisplayTitle 配置**：支持通过配置文件选择显示标题类型（source_title/translated_title/title）
- 🎛️ **Translator 配置系统**：支持多翻译器配置，可通过 config.yaml 激活不同模型

**前端新特性：**

- ✨ **批量添加资源**：支持一次性输入多个 AVID（换行、逗号或空格分隔），自动去重和格式化
- 🎨 **刷新操作多选项**：刷新元数据时可选择刷新方式（仅本地、Ollama、DeepL、ChatGPT等）
- 🏠 **首页美化**：采用渐变配色、浮动动画背景、现代化卡片设计
- 🎭 **类别标签优化**：以 hashtag 形式展示资源类别，更直观
- 🧭 **导航菜单增强**：资源库新增下拉菜单，可快速导航至"按演员"和"按类别"视图
- ↩️ **返回逻辑优化**：返回按钮跳转至来源页面而非固定路由

#### 🐛 Bug 修复

- 🔧 **下载队列显示修复**：修复任务队列显示 Bug（任务数量和状态显示错误）
- 🔄 **WebSocket 连接优化**：改进 WebSocket 连接和 HTTP 轮询逻辑
- 🏷️ **任务状态同步**：改进任务状态同步机制，添加 AVID-名称缓存，减少重复请求

#### ⚡ 性能优化

- 🖼️ **封面加载优化**：优先使用后端提供的 thumbnail_url，减少 Blob 下载
- 💾 **智能缓存策略**：AVID-名称映射缓存，避免重复请求元数据
- 🧹 **翻译质量提升**：添加翻译结果清洗机制（10+ 清洗规则），移除前缀、注释、格式标记
- 🔄 **条件请求优化**：元数据和封面接口支持 ETag/Last-Modified，减少带宽占用

#### 📊 数据库与架构

- 📑 **数据库全面迁移**：所有元数据从文件系统迁移至 SQLite，统一通过 ORM 访问
- 🏷️ **演员类别聚合**：新增演员列表、类别列表 API，支持按作品数排序和搜索
- 🖼️ **智能缩略图生成**：按需生成多尺寸封面（small/medium/large），支持 ETag 缓存

#### 💻 代码质量提升

- ✅ **ESLint 代码检查**：配置 ESLint 9.39.2 + Vue 插件，添加 `pnpm lint` 和 `pnpm lint:fix` 命令
- 🧹 **代码清理**：移除未使用的变量、导入和函数，修复空 catch 块，添加缺失的 emits 声明
- 🔧 **代码优化**：移除无用的 try-catch 包装，修复模板变量遮蔽问题
- 🧪 **完整测试覆盖**：新增翻译清洗、序列化器、API 端点等测试用例

#### 📝 文档更新

- 📖 更新 API 文档，新增细粒度刷新、批量操作接口说明
- 📚 完善配置文档，添加翻译器和 DisplayTitle 配置说明
- 🗂️ 新增数据库迁移和规范化脚本文档

---

### v1.1.0

**新增功能：**

- ✨ **演员聚合浏览**：新增演员库页面，按演员分类浏览资源，支持搜索和排序
- ✨ **类别聚合浏览**：新增类别库页面（前端待完善），按类别分类浏览资源
- ✨ **演员/类别详情页**：点击演员/类别卡片可查看该演员/类别的所有作品
- ✨ **批量操作组件化**：封装统一的批量操作控件，支持批量下载、刷新、删除
- ✨ **实时进度追踪**：WebSocket 实时推送下载进度，支持百分比和速度显示
- 🔧 **后端 API 增强**：
  - `GET /api/actors/` - 演员列表及作品数统计
  - `GET /api/genres/` - 类别列表及作品数统计
  - `GET /api/resources/?actor=<id|name>` - 按演员过滤资源
  - `GET /api/resources/?genre=<id|name>` - 按类别过滤资源
  - `ws://host/nassav/ws/tasks/` - WebSocket 实时通知
- 🎨 **UI/UX 优化**：统一的卡片设计风格，更流畅的交互体验

**改进：**

- 📊 数据库结构优化：添加索引提升查询性能
- 🔒 增强的去重机制：多层去重保证任务唯一性
- 🚀 缩略图支持：封面支持多尺寸（small/medium/large）按需生成
- 📝 完善的文档：更新 API 文档和数据库文档

---

### v1.0.0

- 🎬 多源资源获取（8+ 下载源）
- 🔍 元数据刮削（JavBus 等）
- 📥 异步下载队列（Celery）
- 🖥️ 现代化前端界面（Vue 3 + Vite）
- 📁 统一资源管理

## 许可证

本项目基于原仓库 [Satoing/NASSAV](https://github.com/Satoing/NASSAV) 重构开发，遵循相同的许可证。

## 致谢

感谢 [Satoing/NASSAV](https://github.com/Satoing/NASSAV) 原项目的启发和基础代码。
