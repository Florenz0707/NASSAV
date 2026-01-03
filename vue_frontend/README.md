# NASSAV 前端（Vue 3 + Vite）

一个用于管理视频资源的前端应用，包含资源检索、信息刮削、下载管理等功能。基于 Vue 3、Vite、Pinia 与 Vue Router 构建，默认通过
`/nassav` 代理与后端交互。

## 功能概览（含页面与预览图）

- 首页（概览与最近添加）
    - 功能：展示资源总览统计（总数/已下载/待下载），最近添加资源，快捷入口（添加资源/浏览资源库）。
    - 路由：`/`
    - 预览：

      ![Home](public/preview/home.png)

- 资源库（搜索/过滤/排序/批量操作）
    - 功能：支持按
      AVID/标题/来源搜索；按状态（已下载/未下载）过滤；按日期/编号/来源排序；批量操作（下载、刷新、删除）；支持按演员、类别分类浏览；卡片操作（下载、刷新、删除资源、删除视频文件）；一键刷新列表悬浮按钮。
    - 路由：`/resources`
    - 预览：

      ![Resources](public/preview/resource.png)

- 演员库（按演员聚合浏览）
    - 功能：展示所有演员及其作品数；支持搜索演员名称；按作品数或名称排序；分页浏览；点击演员卡片查看该演员的所有作品。
    - 路由：`/resources/actors`
    - 预览：

      ![Actors](public/preview/actors.png)

- 类别库（按类别聚合浏览）
    - 功能：展示所有类别及其作品数；支持搜索类别名称；按作品数或名称排序；分页浏览；点击类别卡片查看该类别的所有作品。
    - 路由：`/resources/genres`
    - 预览：（与演员库界面类似，采用统一的卡片设计）

- 演员详情（特定演员的作品列表）
    - 功能：展示该演员的所有作品；支持搜索、排序、过滤；支持批量操作。
    - 路由：`/actors/:actorId`

- 类别详情（特定类别的作品列表）
    - 功能：展示该类别的所有作品；支持搜索、排序、过滤；支持批量操作。
    - 路由：`/genres/:genreId`

- 资源详情（元数据与操作）
    - 功能：展示封面、标题、发行日期、时长、来源、文件大小、演员、类别等；提交下载、复制本地文件路径用于播放、刷新元信息。
    - 路由：`/resource/:avid`
    - 预览：

      ![Resource Detail](public/preview/resourceDetail.png)

- 添加资源（支持选择下载源与 Cookie 设置）
    - 功能：输入 AVID 并选择下载源（或自动），提交后回显封面下载/元数据保存/信息刮削状态；支持继续添加/查看详情；提供 Cookie
      设置弹窗（用于部分源需要认证）。
    - 路由：`/add`
    - 预览：

      ![Add Resource](public/preview/addResource.png)

- 下载管理（已下载清单）
    - 功能：统计已下载与待下载数量；展示已下载列表，支持跳转到资源详情。
    - 路由：`/downloads`
    - 预览：

      ![Downloads](public/preview/downloads.png)

## 技术栈

- Vue 3、Vite 5（`@vitejs/plugin-vue`）
- 状态管理：Pinia
- 路由：Vue Router
- 网络请求：Axios

## 本地开发

> 要求 Node.js ≥ 18（Vite 5）。包管理器推荐 pnpm。

1) 安装依赖

```bash
pnpm install
```

2) 启动开发服务器（默认端口 8080）

```bash
pnpm dev
```

- 开发代理：参见 [vite.config.js](vite.config.js)，`/nassav` 将被代理到 `http://localhost:8000`。请确保后端在本地 8000
  端口可用，或按需修改配置。

3) 生产构建与本地预览

```bash
pnpm build
pnpm preview
```

- 构建产物输出目录：`dist/`

## 部署说明

本项目为纯前端单页应用（SPA），可作为静态资源部署到任意静态托管环境（Nginx、Apache、OSS/CDN、Vercel、Netlify、GitHub Pages 等）。

关键点：

- 需开启 HTML5 History 路由回退（所有未命中路径回退到 `index.html`）。
- 需将前端的 API 前缀 `/nassav` 反向代理到后端服务（默认 `http://localhost:8000`，生产按需替换）。

### Nginx 示例

```nginx
server {
  listen 80;
  server_name your-domain.com;

  root /var/www/nassav-frontend/dist;
  index index.html;

  # 前端路由回退
  location / {
    try_files $uri $uri/ /index.html;
  }

  # API 反向代理（与开发时保持一致的前缀）
  location /nassav/ {
    proxy_pass http://127.0.0.1:8000/;  # 替换为你的后端地址
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
  }
}
```

### Vercel / Netlify / GitHub Pages

- 将 `dist/` 作为发布目录。
- 设置单页应用重写规则（将所有路径重写到 `/index.html`）。
- 若平台支持反向代理/重写，将 `/nassav` 指向后端服务；若不支持，可改为由后端允许跨域（CORS），并在前端将 API 基址改为后端直连地址。

## 配置与约定

- 开发代理与别名：见 [vite.config.js](vite.config.js)
    - `server.port = 8080`
    - `server.proxy['/nassav'] -> http://localhost:8000`
    - `resolve.alias['@'] = '/src'`
- 主要代码结构：
    - 视图：`src/views/`（首页、资源库、演员库、类别库、详情、添加、下载）
    - 组件：`src/components/`（包括资源卡片、演员卡片、类别卡片、批处理控件等）
    - 路由：`src/router/index.js`
    - 状态：`src/stores/`（资源、演员、类别等状态管理）
    - 接口封装：`src/api/`

## 最近更新日志

### v1.3.0 (2026-01-03)

#### 新功能

##### 1. 系统设置页面
- **新增设置页面**（`/settings`）：集中管理系统配置，包含通用设置和 Cookie 管理两个模块
- **通用设置**：
  - 显示女优头像开关：控制演员列表和详情页是否渲染女优头像图片
  - 标题显示字段选择：支持在原始标题、源站标题、翻译标题间切换
- **Cookie 管理**：
  - 查看已设置的下载源 Cookie 及其状态
  - 手动设置或一键自动获取 Cookie
  - 删除 Cookie 配置（带二次确认）
  - 实时显示 Cookie 更新时间和设置状态
- **后端持久化**：所有设置通过 `/api/setting` 接口保存到后端 `user_settings.ini`，支持多浏览器同步

##### 2. 女优头像功能
- **头像显示**：演员列表卡片和详情页支持显示女优头像
- **Javbus 集成**：自动从 Javbus 获取女优头像图片
- **灵活控制**：通过设置页开关控制是否显示头像，关闭时显示文字头像
- **后端支持**：新增演员头像 API（`/api/actors/:id/avatar`）

##### 3. 标题显示优化
- **多标题支持**：后端同时返回 `original_title`（原始日语）、`source_title`（源站标题）、`translated_title`（翻译标题）
- **用户可选**：通过设置页下拉菜单选择在资源列表中显示哪种标题
- **智能降级**：首选标题字段不存在时自动使用备用标题，确保始终有内容显示

#### 优化改进

##### 4. 封面下载优化
- **Javbus 封面优先**：优先使用 Javbus 封面，相比其他源质量更高
- **403 错误修复**：解决封面下载时遇到的 403 Forbidden 错误

##### 5. 接口整合优化
- 移除 AddResourceView 中冗余的 Cookie 设置功能
- 统一在设置页集中管理所有 Cookie 配置
- 优化前后端接口对齐，修复头像 API 返回问题

#### Bug 修复

##### 6. 数据处理修复
- **演员名解析**：修复日语演员名在特定情况下被截断的问题
- **演员过滤**：过滤掉无作品的演员，避免在列表中显示空数据
- **排序修复**：修复按视频下载时间排序时错误返回未下载资源的问题

### v1.2.0 (2026-01-02)

#### 代码质量提升
- **启用 ESLint 代码检查**：配置 ESLint 9.39.2 + Vue 插件，添加 `pnpm lint` 和 `pnpm lint:fix` 命令
- **代码清理**：移除未使用的变量、导入和函数，修复空 catch 块，添加缺失的 emits 声明
- **代码优化**：移除无用的 try-catch 包装，修复模板变量遮蔽问题

#### 核心功能增强

##### 1. 批量添加资源（AddResourceView）
- 支持一次性输入多个 AVID（换行、逗号或空格分隔）
- 自动去重和格式化
- 批量结果分类展示：成功、已存在、失败
- 保持单个资源添加时的详细信息展示

##### 2. 刷新操作多选项（ResourceCard）
- 刷新元数据时可选择刷新方式
- 提供"仅本地"和多种翻译器选项（Ollama、DeepL、ChatGPT 等）
- 通过下拉菜单选择，提升操作灵活性

##### 3. 下载队列优化（DownloadsView）
- 修复任务队列显示 Bug（任务数量和状态显示错误）
- 优化 WebSocket 连接和 HTTP 轮询逻辑
- 改进任务状态同步机制
- 添加 AVID-名称缓存，减少重复请求

##### 4. UI/UX 改进
- **首页美化**：采用渐变配色、浮动动画背景、现代化卡片设计
- **资源卡片样式优化**：改进封面加载、卡片布局和交互效果
- **类别标签**：以 hashtag 形式展示资源类别
- **导航菜单增强**：资源库新增下拉菜单，可快速导航至"按演员"和"按类别"视图
- **返回逻辑优化**：返回按钮跳转至来源页面而非固定路由

##### 5. 性能优化
- 封面加载优化：优先使用后端提供的 thumbnail_url，减少 Blob 下载
- 改进缓存策略：AVID-名称映射缓存
- 减少不必要的 API 请求

### v1.1

#### 演员与类别聚合浏览

- **演员库**（`/resources/actors`）：展示所有演员及其作品数，支持搜索、排序（按名称/作品数）、分页浏览
- **类别库**（`/resources/genres`）：展示所有类别及其作品数，支持搜索、排序（按名称/作品数）、分页浏览
- **演员详情**（`/actors/:actorId`）：查看特定演员的所有作品，支持完整的搜索、排序、过滤和批量操作
- **类别详情**（`/genres/:genreId`）：查看特定类别的所有作品，支持完整的搜索、排序、过滤和批量操作

#### 批处理操作组件化

- 将批处理控件封装为独立的 `BatchControls` 组件，实现代码复用
- 统一的蓝色系配色风格
- 支持批量刷新、批量下载、批量删除操作
- 在资源库、演员详情、类别详情页面中均可使用

#### 后端 API 支持

- `GET /nassav/api/actors/` - 获取演员列表，支持分页、搜索、排序
- `GET /nassav/api/genres/` - 获取类别列表，支持分页、搜索、排序
- `GET /nassav/api/resources/?actor=<id|name>` - 按演员过滤资源
- `GET /nassav/api/resources/?genre=<id|name>` - 按类别过滤资源

## 常见问题（FAQ）

- 生产环境 404（刷新页面丢失）
    - 需配置 SPA 回退到 `index.html`（见上方 Nginx 配置）。
- 接口 404 或跨域
    - 确认生产反向代理 `/nassav` 指向正确后端；或开启后端 CORS 并调整前端 API 地址。
- 端口冲突（开发）
    - 修改 [vite.config.js](vite.config.js) 中的 `server.port`，或释放 8080 端口。
