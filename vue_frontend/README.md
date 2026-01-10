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

## 常见问题（FAQ）

- 生产环境 404（刷新页面丢失）
    - 需配置 SPA 回退到 `index.html`（见上方 Nginx 配置）。
- 接口 404 或跨域
    - 确认生产反向代理 `/nassav` 指向正确后端；或开启后端 CORS 并调整前端 API 地址。
- 端口冲突（开发）
    - 修改 [vite.config.js](vite.config.js) 中的 `server.port`，或释放 8080 端口。
