# NASSAV 前端（Vue 3 + Vite）

将资源库、多源发现、个性化推荐和持久任务控制集中在一个界面。支持资源检索、批量添加与刮削、下载暂停/恢复/终止，并提供清晰的进度、翻译状态和失败反馈。基于 Vue 3、Vite、Pinia 与 Vue Router 构建，默认通过
`/nassav` 代理与后端交互。

全栈容器部署通过仓库根目录 `compose.yaml` 提供 nginx 网关，详见 [Compose 部署说明](../django_backend/doc/compose-deployment.md)。

后续开发遵循[仓库开发规范](../AGENTS.md)、[前端开发契约](doc/development-contracts.md)及 [AGENT.md](AGENT.md)；阶段验证证据见[语义重构记录](doc/semantic-refactoring-progress.md)和[UX 改进记录](doc/ux-neutral-progress.md)。

## 功能概览（含页面与预览图）

当前版本为2.5.1；以下预览生成于2026-10-08，展示当时的真实页面组件，尚未覆盖随后新增的个人中心、播放页和进度恢复提示。资源、演员、封面和任务均使用示例数据，截图不代表真实站点或 worker 联调验收；默认展示浅色主题，另附深色任务界面。

- 首页（品牌与功能入口）
  - 功能：展示品牌、下载与刮削能力介绍，提供添加资源和浏览资源库快捷入口；品牌标识与导航共用橙色渐变，背景使用彩色柔光。
  - 路由：`/`
  - 预览：

    ![Home](public/preview/home.jpg)

- 资源库（搜索/过滤/排序/批量操作）
  - 功能：支持按
    AVID/标题/来源搜索；按状态（已下载/未下载）过滤；按日期/编号/来源排序；批量操作（下载、刷新、删除）；支持按演员、类别分类浏览；卡片操作（下载、刷新、删除资源、删除视频文件）；一键刷新列表悬浮按钮。
  - 路由：`/resources`
  - 预览：

    ![Resources](public/preview/resource.jpg)

- 演员库（按演员聚合浏览）
  - 功能：展示所有演员及其作品数；支持搜索演员名称；按作品数或名称排序；分页浏览；点击演员卡片查看该演员的所有作品。
  - 路由：`/resources/actors`
  - 预览：

    ![Actors](public/preview/actors.jpg)

- 类别库（按类别聚合浏览）
  - 功能：展示所有类别及其作品数；支持搜索类别名称；按作品数或名称排序；分页浏览；点击类别卡片查看该类别的所有作品。
  - 路由：`/resources/genres`
  - 预览：

    ![类别库：五列卡片与筛选](public/preview/genres.jpg)

- 演员详情（特定演员的作品列表）
  - 功能：展示该演员的所有作品；支持搜索、排序、过滤；支持批量操作。
  - 路由：`/actors/:actorId`

- 类别详情（特定类别的作品列表）
  - 功能：展示该类别的所有作品；支持搜索、排序、过滤；支持批量操作。
  - 路由：`/genres/:genreId`

- 资源详情（元数据与操作）
  - 功能：展示封面、标题、发行日期、时长、来源、文件大小、演员、类别等；提交下载、复制本地文件路径、新标签页在线播放和刷新元信息。在线播放需后端开启且支持当前来源/编码。
  - 路由：`/resource/:avid`
  - 预览：

    ![Resource Detail](public/preview/resourceDetail.jpg)

- 添加资源（支持选择下载源与 Cookie 设置）
  - 功能：输入 AVID 并选择下载源（或自动），提交后回显封面下载/元数据保存/信息刮削状态；支持继续添加/查看详情；提供 Cookie
    设置弹窗（用于部分源需要认证）。
  - 路由：`/add`
  - 预览：

    ![批量添加资源与下载源选择](public/preview/addResource.jpg)

    ![添加资源页的 Cookie 设置弹窗](public/preview/cookies.jpg)

- 任务详情（持久下载与刮削任务，兼容历史队列）
  - 功能：列表/详情、类型和整体状态筛选、创建/更新时间降序、资源名称与封面、包含翻译的活动时间线；支持单条/批量暂停、恢复、终止和本浏览器隐藏已结束任务。控制能力由服务器快照决定，清理状态独立展示；说明文字旁的 info 弹窗区分当前跟踪、已加载隐藏数与服务端总数，本地隐藏不改变后台任务；列表不再提供独立刷新按钮。
  - 路由：`/downloads`
  - 预览：

    ![任务详情：下载和刮削列表、进度及活动时间线](public/preview/downloads.jpg)

    ![深色主题任务详情](public/preview/tasksDark.jpg)

- 外部搜索（演员/类别详情中的发现入口）
  - 功能：手动选择来源开始搜索，渐进展示结果，支持取消与分页；添加按钮跟随所属任务状态，保存后禁用，未保存的失败允许重试。
  - 路由：`/actors/:actorId?tab=external` 或 `/genres/:genreId?tab=external`
  - 预览：

    ![外部搜索结果与添加状态](public/preview/externalSearch.jpg)

- 推荐页
  - 路由：`/recommendations`；手动提交推荐 job，由 scrape worker 执行，支持进度、取消与失败重试；多轮结果追加并在当前浏览器标签页恢复。历史信息收进 info 弹窗，核验/依据默认折叠，偏好与黑名单集中在个性化弹窗；支持反馈、屏蔽及加入资源库。
  - 预览：

    ![推荐发现：核验摘要、依据与反馈卡片](public/preview/recommendations.jpg)

    ![个性化：推荐偏好与演员、类别、资源黑名单](public/preview/personalization.jpg)

- 设置页
  - 路由：`/settings`；按账号保存显示偏好与默认外部搜索源（数据库）；Cookie 设置由添加资源页按钮打开。
  - 预览：

    ![设置：主题、标题、头像及默认搜索源](public/preview/settings.jpg)

## 登录与外部搜索

应用使用单用户 Django 会话；未登录时展示登录界面，写请求携带 CSRF token，会话失效后回到登录流程。API 与 WebSocket 使用同源网关；DEBUG 不能绕过登录。权限和部署配置见[接口文档](../django_backend/doc/interface.md)。

演员/类别详情提供手动搜索入口；开始搜索与来源设置按钮在空白区域居中，来源由设置弹窗选择，重新搜索位于结果分页下方，不自动发起外部抓取。可用来源和排序以后端 search-capabilities 为准，当前支持启用的 Jable/MissAV；默认选择取持久化设置，不可用时回退到支持该搜索的源。MissAV 缺少映射时可能是关键词结果，页面明确提示，不能保证全部属于该演员/类别。

搜索使用后台任务，逐页展示 partial 结果；失败或取消保留已有结果并显示状态，不伪装成完整成功。用户可以取消任务；切源或离开页面终止旧请求/订阅，后台任务仍可能继续，过期响应不得覆盖新状态。WebSocket 通知触发带 token 的版本快照查询，1.5 秒轮询补偿断线。结果默认每页 15 项，翻页通过同一签名任务读取，不新建搜索；源站抓取进度与界面展示页数分别标注。添加结果时携带对应来源；部分结果不进入成功会话缓存。详细接口见[外部搜索契约](../django_backend/doc/interface.md)。

## 技术栈

- Vue 3、Vite 5（`@vitejs/plugin-vue`）
- 状态管理：Pinia
- 路由：Vue Router
- 网络请求：Axios

## 本地开发

> 要求 Node.js ≥ 18（Vite 5）。项目固定 pnpm 10.30.1（见 package.json 的 packageManager），使用与仓库配置兼容的 Node.js。

1. 安装依赖

```bash
pnpm install
```

1. 启动开发服务器（默认仅监听 `127.0.0.1:9780`）

```bash
pnpm dev
```

- 开发代理：`/nassav/api/` 与 `/nassav/ws/` 默认转发到 `http://127.0.0.1:9790`。后端不在该地址时，在启动 Vite 前设置 `NASSAV_VITE_BACKEND_URL=http://后端主机:端口`。这是 Vite 服务端连接地址；浏览器仍使用页面的 Host、Cookie 和 Origin。
- 仅在可信局域网跨设备调试时使用 `NASSAV_VITE_HOST=0.0.0.0 pnpm dev`，然后从另一设备打开 `http://开发机局域网地址:9780`。后端 `ALLOWED_HOSTS` 须包含浏览器访问的主机名或 IP；若要在该入口登录，还须将 `http://开发机局域网地址:9780` 加入 `CSRF_TRUSTED_ORIGINS`。不要将开发服务器直接暴露到公网。

1. 生产构建与本地预览

```bash
pnpm build
pnpm preview
```

- 构建产物输出目录：`dist/`

## 部署说明

前端生产部署需要 HTML5 History 路由回退，以及 `/nassav/api/` 和 `/nassav/ws/` 的同源代理。登录、CSRF、HTTPS/WSS、Host 和 WebSocket Upgrade 的完整网关要求见[Compose 部署说明](../django_backend/doc/compose-deployment.md#服务和代理)。纯静态托管若无法代理 WebSocket，需另配同源网关。

## 配置与约定

- 开发代理与别名：见 [vite.config.js](vite.config.js)
  - `server.host = 127.0.0.1`、`server.port = 9780`；`NASSAV_VITE_HOST` 可调整监听地址
  - `server.proxy['/nassav/api']` 和 `server.proxy['/nassav/ws']` → `NASSAV_VITE_BACKEND_URL`（默认 `127.0.0.1:9790`）；WebSocket 随目标协议选择 ws/wss
  - `resolve.alias['@'] = '/src'`
- 主要代码结构：
  - 视图：`src/views/`（首页、资源库、演员/类别详情、添加、任务详情、推荐、个人中心、播放及旧设置兼容入口）
  - 业务模块：`src/features/`（resources、catalog、external-search、tasks、recommendations、cookies、settings、auth、personal、viewing、playback；组件与状态就近放置）
  - 公共能力：`src/shared/`（ui、composables、lib、stores，无业务依赖）
  - 应用装配：`src/app/`（路由、导航、WebSocket 连接）
  - 接口封装：`src/api/`（client.js 唯一客户端，按领域分文件，index.js 保留公开导出）

目录规则与状态所有者见[模块布局](doc/module-layout.md)，本轮证据见[语义与模块重构记录](doc/semantic-refactoring-progress.md)。

## 常见问题（FAQ）

- 生产环境 404（刷新页面丢失）
  - 需配置 SPA 回退到 `index.html`（见上方 Nginx 配置）。
- 接口 404 或跨域
  - 确认生产反向代理 `/nassav` 指向正确后端；并检查 Host、CSRF_TRUSTED_ORIGINS 和 WebSocket Upgrade。
- 端口冲突（开发）
  - 修改 [vite.config.js](vite.config.js) 中的 `server.port`，或释放 9780 端口。

## 异步资源任务反馈

资源添加、刷新和批量添加/刷新现在提交到后端 `/nassav/api/resource/jobs`，HTTP 202 仅表示入队。资源任务通过全局 toast 提示入队、开始、成功和失败；同一状态的阶段更新和重复 WebSocket 事件不会重复通知。WebSocket 状态事件触发带令牌的快照查询，只有快照确认 `succeeded` 后才提示成功并刷新资源数据。任务 ID 与查询令牌保存在浏览器本地存储，页面刷新或 WebSocket 重连后会重新查询未结束任务；定时查询作为断线时的补偿。重新提交失败任务会以新的任务 ID 提示“重试任务已排队”。批量删除和视频删除继续使用原接口。后端需另启监听 `scrape` 队列的 Celery worker；只启动默认 worker 无法处理资源任务。

前端无交互检查入口：

```bash
pnpm run check
```

该命令依次运行 lint、`pnpm run test` 和构建。测试覆盖资源任务从入队到终态的快照补齐、WebSocket URL、重连与会话失效，以及 Vite 的 HTTP/WebSocket 同源代理。WebSocket 连接失败时，下载页改用 API 轮询；资源任务继续通过带令牌的状态查询补齐终态。浏览器握手失败若只返回异常关闭码，前端会查询 HTTP 会话：登录已过期则停止重连，网络故障则继续重试。

## 公共组件浏览器验收

`tests/browser/components.cjs` 使用 Playwright 在独立页面挂载真实 Vue 组件，检查初始弹窗、焦点循环/恢复、嵌套滚动锁、卸载清理和下拉禁用项导航；不调用后端。普通 `pnpm run test` 不包括此浏览器检查。

在临时目录安装测试驱动，启动本地 Vite 后，在另一终端运行：

```bash
npm install --prefix /tmp/nassav-browser-audit --no-audit --no-fund playwright
# 可设置 PLAYWRIGHT_BROWSERS_PATH=/tmp/nassav-browsers 并安装 Chromium。
NODE_PATH=/tmp/nassav-browser-audit/node_modules node /tmp/nassav-browser-audit/node_modules/playwright/cli.js install chromium
pnpm exec vite --host 127.0.0.1 --port 4178
```

```bash
NODE_PATH=/tmp/nassav-browser-audit/node_modules pnpm run test:browser
```

有现成 Chromium 时设置 `NASSAV_CHROMIUM_PATH` 指向可执行文件；`NASSAV_BROWSER_ORIGIN` 可覆盖默认本地地址。重构阶段与验收边界见 [执行记录](doc/refactoring-progress.md)。

浏览器套件还检查深浅主题映射、目录分页/错误/竞态及移动布局、演员与类别的手动外部搜索/部分结果/取消、黑名单读写隔离和设置保存。必须使用 Vite 开发服务以编译组件样例；真实接口由 Playwright 拦截并模拟。

前端职责约定：路由页装配目录或实体详情模块；统一 HTTP 客户端处理 envelope、CSRF 和登录失效；资源列表查询由 resourceList 管理，下载队列和标题元数据由 downloadQueue 管理，WebSocket store 保持连接与事件分发。主题类由 tailwind.config.js 显式映射；公共按钮、搜索输入、下拉和弹窗供页面复用，标题选择集中在 features/resources/lib/resourceTitle.js。

目录和实体详情模块的实体类型在各自生命周期中保持固定；同一实体类型的 ID 变化由路由监听处理。浏览器套件同时截断 WebSocket 到真实后端的连接。

## 任务详情与调试

正式 `/downloads` 使用列表与详情布局，支持下载与刮削筛选。模拟效果由 `DownloadsView.vue` 的 `DEBUG_MODE` 开关启用，见[任务详情与调试说明](doc/development-contracts.md)。

全局通知模块已移除，任务的阶段时间在任务详情中查看；导航栏恢复原有布局。

## 控件与页面反馈

按钮统一五态，加载时保留尺寸且阻止重复提交。输入框提供占位、聚焦、就地错误与清空；空列表使用图标与短文案，失败显示简短原因和重试。请求超过一秒后显示骨架或 loading，刷新保留已有内容；动画使用平缓呼吸和单层旋转，支持减少动态效果偏好。深浅主题、公共组件和状态归属见[开发契约](doc/development-contracts.md)，目录职责见[模块布局](doc/module-layout.md)。

推荐异步任务浏览器验收入口：`tests/browser/recommendationJobs.cjs`。
它使用模拟任务 API 验证手动启动、轮询成功、失败、真实 cancel 请求、移动端布局和
离开页面清理；不能替代真实 Celery/代理部署验收。

## 推荐任务与页面恢复

开始推荐/继续推荐显式提交任务，前端每秒读取同 job_id 的递增版本快照；运行时只展示核验数量和本轮用时，资源卡片在成功后展示，不提供逐条资源流。后端达到网络预算时可返回已核验的部分结果，页面提示数量不足；失败原因显示在底部继续推荐按钮下方，重试不会清掉之前的成功批次。主动取消调用后端接口；离开页面会尝试取消当前任务，断网时仍由服务端期限收尾。

核验摘要的用时由前端单调时钟计算，与后端工作进度更新时间独立；成功批次用时与完整去重列表保存到 sessionStorage，刷新及同标签页路由往返可恢复，跨浏览器/新标签页不承诺恢复。未知历史字段显示“—”。清空页面只清除当前页面结果；重置历史操作会删除后端历史并取消未结束推荐任务，黑名单保留。

推荐信息仅保留历史统计、刷新和重置。个性化弹窗左侧推荐偏好，右侧黑名单；桌面两列独立滚动，移动端内容整体滚动，关闭按钮保持可访问。推荐依据按演员 coral/类别 teal 显示；资源卡片与外部搜索复用操作按钮，屏蔽位于反馈右侧。添加请求按返回 job_id 跟踪，授权快照确认资源已保存即禁用按钮，即使翻译尚未结束或失败也不重复添加。

回归入口为 `recommendationJobs.cjs`、`recommendationRestore.cjs`、`recommendationBlacklist.cjs`；配合公共 `components.cjs` 验证任务失败/取消/迟到响应、添加禁用、多批次刷新恢复、弹窗布局/滚动及焦点。模拟 API/WS 验收与真实来源/worker 验收分开记录，见[执行记录](doc/refactoring-progress.md)和[部署与验证边界](../django_backend/doc/compose-deployment.md#近期改动与验证边界)。

## 在线播放器验收

详情页“在线播放”使用同源授权会话、MSE/hls.js 优先、缺少 MSE 时回退原生 HLS，不保存视频文件。来源准备异步完成，独立 `/play/:avid` 页面顶部仅保留Logo，播放器居中并在加载/播放时保持16:9比例；支持拖动、暂停、错误重试、关闭标签页和卸载清理；关闭原详情页不影响播放；hls.js 对网关来源拒绝最多刷新一次，兼容检查成功才恢复位置。原生 HLS 错误无法可靠取得 HTTP 状态，使用显式重试。配置和上线条件见[后端验收](../django_backend/doc/online-playback-acceptance.md)。

已下载资源的“点击播放”使用`/play/:avid?mode=local`，由后端鉴权直传MP4、支持Range，不重新刮削或下载。新增个人进度会自动节流保存，在再次打开时提供“继续上次播放/从头播放”；来源续播要求确认，本地文件版本不同不自动套用。多标签/旧响应不能覆盖新状态，进度服务失败不阻塞播放，离页保存不保证必达。详细生命周期见[开发契约](doc/development-contracts.md#播放进度记忆)，前后端必须统一更新并迁移至0036，升级见[发布检查](../django_backend/doc/release-2.5.1.md)。

`tests/browser/playback.cjs` 默认离线，ffmpeg 生成临时 TS/fMP4 后真实解码，模拟 API 验证迟到提交、恢复、焦点和移动布局；不替代真实来源/worker。`scripts/verify-playback-live.cjs` 必须显式提供验收来源、两个已有 AVID 和临时 Playwright storage-state 文件；默认连续播放 30 秒，可选刷新，测试后尽力关闭会话，临时登录由提供者删除。驱动依赖沿用上面的 NODE_PATH，不将凭证提交到仓库。

```sh
NODE_PATH=/tmp/nassav-browser-audit/node_modules \
NASSAV_PLAYBACK_TEST_ORIGIN=https://你的验收域名 \
NASSAV_PLAYBACK_TEST_LOGIN=/tmp/临时登录.json \
NASSAV_PLAYBACK_TEST_AVIDS=已入库编号一,已入库编号二 \
NASSAV_PLAYBACK_TEST_SECONDS=30 \
NASSAV_PLAYBACK_TEST_REFRESH=true \
node scripts/verify-playback-live.cjs
```

此脚本会创建两个播放会话并允许短期播放缓存写入，不添加资源、不下载正式视频。正式实例仅在明确授权后执行；日志不展示 Cookie、能力 URL 或代理凭证。仅限 Chrome 的脚本成功不能代替真实 Safari/iOS/Android、HTTPS、自然签名到期和完整长时播放验收。

真实在线播放探针可用 `NASSAV_PLAYBACK_TEST_ENGINE=firefox` 选择已安装的 Playwright Firefox（默认 chromium）；浏览器目录由 `PLAYWRIGHT_BROWSERS_PATH` 指定。该探针有界等待播放启动，但短时通过不代表真机或长期验收。

私有 loopback HTTPS 验收可显式设置 `NASSAV_PLAYBACK_TEST_SELF_SIGNED=true`；仅允许localhost/回环HTTPS，例外只绕过一次性证书信任校验，不关闭Secure Cookie、CSRF或上游目标限制。正式证书验收保持默认false。

合成播放器回归可设置 `NASSAV_BROWSER_ENGINE=firefox`（默认chromium），配合Playwright浏览器目录运行 `node tests/browser/playback.cjs`。先等待MSE挂载再调用play；合成TS/fMP4与真实来源轮次分开记录，Firefox间歇超时不由一次通过掩盖。

合成与真实探针失败时会在清理前输出 `media_diagnostics`：当前媒体时间、帧数、缓冲区间和最近100条媒体事件，区分play拒绝、暂停、seek和等待缓冲；不包含URL、凭证或响应正文。真实探针的连续播放区间须解码新帧，且时间推进至少为观察时长的80%，避免只在开始播放过却被误报为连续播放通过。

独立进程重复合成回归（任一轮失败立即退出）：

```sh
for round in 1 2 3 4 5 6 7 8 9 10; do
  NODE_PATH=/tmp/nassav-browser-audit/node_modules \
  PLAYWRIGHT_BROWSERS_PATH=/tmp/nassav-browser-audit/browsers \
  NASSAV_BROWSER_ENGINE=firefox node tests/browser/playback.cjs || exit "$?"
done
```

正式HTTPS/真机/长时验收项目及未通过记录见[验收记录](../django_backend/doc/online-playback-acceptance.md)。

### 已下载 MP4 真实隔离浏览器验证

后端测试 helper 只在显式启用时启动，使用临时 SQLite、资源/用户/登录会话和 Unix socket Redis，生成90秒H.264/AAC MP4，不使用正式配置或资源。需要 ffmpeg、redis-server 和 Playwright；正常停止 helper 回收临时文件。

从仓库根目录进入后端：

```bash
cd django_backend
NASSAV_LOCAL_PLAYBACK_TEST_SERVER=1 PYTHONPATH=. uv run python tests/helpers/local_playback_server.py
```

另一个终端从前端目录启动 `NASSAV_VITE_BACKEND_URL=http://127.0.0.1:9791 pnpm run dev --host 127.0.0.1 --port 4178`，将 helper 输出的 ISOLATED_STORAGE_STATE 文件路径填到下列变量（不要使用正式登录状态）：

```bash
NASSAV_LOCAL_PLAYBACK_STORAGE_STATE=/tmp/nassav-local-playback-http-实际目录/storage-state.json \
  node tests/browser/localPlayback.cjs
```

可加 NASSAV_BROWSER_ENGINE=firefox；NASSAV_BROWSER_ORIGIN 只接受本机地址。验证真实会话/MP4 HTTP/Range、解码帧、拖动/暂停、移动尺寸、退出后 closed；仅全局 WebSocket 提示用替身。不提供隔离状态时该专项明确跳过。它不替代正式 Docker、实际下载文件编码或真机验收。

### 个人状态验收

详情页支持个人收藏、已观看和5000字符备注，冲突时保留草稿。`tests/browser/personalState.cjs` 为显式opt-in：先启动后端 `tests/helpers/local_playback_server.py` 的隔离fixture与Vite代理，再用 `NASSAV_PERSONAL_STORAGE_STATE` 指向该临时会话文件运行；`NASSAV_BROWSER_ENGINE=firefox` 可切换引擎。验证真实HTTP/SQLite、键盘保存、备注清空/刷新/冲突、筛选和设置持久化；WebSocket只隔离本轮无关连接，不代替任务/worker联调。勿使用正式会话文件。

播放偏好真实隔离API浏览器验收：先按既有local_playback_server说明启动临时服务，将Vite的NASSAV_VITE_BACKEND_URL设为该临时地址，再以`NASSAV_PROGRESS_STORAGE_STATE=<临时storage-state.json> node tests/browser/playbackPreferences.cjs`执行；支持NASSAV_BROWSER_ENGINE=firefox。脚本只接受本地临时fixture，写入的是临时账号偏好，不使用部署账号。

跨设备真实API验收：临时helper会输出两个不同登录的storage-state路径（均只含测试账号），以`NASSAV_PROGRESS_STORAGE_STATE=<第一份> NASSAV_PROGRESS_SECOND_STORAGE_STATE=<第二份> node tests/browser/crossDeviceContinuation.cjs`运行，支持Firefox。helper的NASSAV_LOCAL_PLAYBACK_TEST_PORT可设9791–9799，Vite后端地址同步指向该临时端口；不使用部署9790。Firefox多标签小屏检查先bringToFront再调整视口，测试有90秒上限、HTTP清理请求有界，避免浏览器后台resize无限等待。

个人中心本轮真实隔离验收可运行`tests/browser/personalState.cjs`和`tests/browser/viewingManagement.cjs`：使用local_playback_server的观看fixture及`NASSAV_PERSONAL_STORAGE_STATE`临时登录文件，另设`NASSAV_BROWSER_ENGINE=firefox`复核。前者会确认登出并使该临时登录失效，后者只修改临时观看状态/历史并关闭自建播放会话；两者不得指向正式实例。未提供临时状态时跳过，完整环境准备见上述播放验收说明。

## v2.5.1个人中心

导航入口“个人中心”集中稍后再看、观看历史、通用设置、播放设置与退出确认。历史按最近实际观看去重，卡片批量操作显式开启；列表删除不删资源或播放进度。详情图标管理收藏/观看/稍后再看，备注只读展示并弹窗编辑。观看查询缓存30秒、最多8项，设置按登录归属复用；后续缓存隔离改进见[方案](doc/personal-cache-plan.md)。前端实现与验收证据见[开发契约](doc/development-contracts.md)，正式升级及旧数据导入见[发布检查](../django_backend/doc/release-2.5.1.md)。

个人中心导航/音量布局专项为`tests/browser/personalLayout.cjs`，使用模拟API，不依赖正式账号。与上方4178 Vite示例配合运行时显式设置`NASSAV_BROWSER_ORIGIN=http://127.0.0.1:4178`；单独运行默认4180。可用`NASSAV_BROWSER_ENGINE=firefox`复核，覆盖面板过渡、弹窗滚动锁和四种视口下百分比位数变化。
