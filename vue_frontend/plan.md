# 接口优化计划（面向个人 NAS 项目 — 无 CDN 前提）

前提说明
- 项目为个人 NAS 部署，不能/不需要配置 CDN、外部对象存储或复杂生产级反向代理。
- 目标：在有限硬件与本地网络条件下，减少带宽与磁盘 I/O、降低前端延迟、提升用户体验并保持简单可维护性。

总体策略（要点）
- 把过滤、排序、分页、搜索的责任移交给后端，前端只负责展示与轻量内页过滤。
- 使用统一的 envelope 响应格式并规范 pagination 字段，减少前端多处兼容代码。
- 在 NAS 场景下优先靠本地缓存（ETag/Last-Modified）和小尺寸缩略图，避免频繁下载完整二进制封面。
- 支持批量操作与增量更新，避免对大数组的全量刷新。
- 使用轻量推送（WebSocket/SSE）在需要时传输任务/队列/进度变化；如不方便可用短轮询 + 条件请求代替。

接口建议（后端）
1) 统一响应 envelope
- 规范：{ code: number, message: string, data: any, pagination?: { total, page, page_size, pages } }
- 约定：code === 0 表示成功；HTTP 状态码仍保持语义（404/409/500 等）。

2) 列表与查询接口（核心）
- GET /resources
  - Query: `search`, `status` (all|downloaded|pending), `sort_by`, `order`, `page`, `page_size`, `source`，可扩展过滤字段
  - 返回：envelope + pagination
- 目的：前端将搜索/分页/过滤参数传入后端，后端返回当前页已过滤结果，避免拉取全量数据。

3) 详情与预览
- GET /resource/:avid
  - 返回 metadata（支持 ETag / Last-Modified）
- GET /resource/:avid/preview
  - 返回 { metadata, thumbnail_url }（thumbnail 为可缓存 URL 或小尺寸二进制），用于详情首屏预览
- 说明：缩略图保存在 NAS 的 thumbnails 目录或由后端按需生成并缓存，避免每次传输大封面 blob。

4) 封面与缩略图策略（针对无 CDN）
- 提供多尺寸缩略图接口：GET /resource/cover?avid=...&size=small|medium|large
- 尽量返回带 Cache-Control（长缓存）并在文件名/URL 中带版本号（如 ?v=hash）以便强缓存失效控制
- 对于需 blob 的场景，仍保留二进制下载接口，但默认优先返回可直接作为 img src 的 URL

5) 批量与局部更新
- POST /resources/batch  — 批量添加/删除/刷新（body 指定 actions）
- POST /downloads/batch_submit — 批量提交下载任务
- 单点操作尽量返回该资源的最新对象，便于前端局部替换而非整表刷新

6) 文件路径与播放
- GET /downloads/abspath?avid=... 返回 { abspath, url?, file_exists }，若仅本地播放可返回 `abspath`，同时提供 `file_url`（file:/// 或 http local server）方便复制/播放
- 不依赖 pre-signed URL 或 CDN，直接返回服务器可访问路径或本地文件路径

7) 任务与状态推送
- 提供 WebSocket 或 SSE 事件：task_update { avid, task_type, status, progress }。
- 如果后端无法长期维护连接，可采用短轮询（例如 /tasks/queue/status 支持 If-None-Match）

8) Cache / 条件请求（重要）
- 所有可以静态或半静态的数据（metadata、thumbnail）支持 ETag/Last-Modified
- 前端使用 If-None-Match / If-Modified-Since，以 304 减少传输

前端改进点（代码层面建议）
1) 将查询参数传给后端
- 在 `fetchResources` 中传入 search、status、sort_by、order、page、page_size 并由服务端返回已过滤分页数据。
- 从 `ResourcesView.vue` 中去掉对大量 client-side filter 的依赖，仅进行当前页内的局部筛选（例如快速排序或 highlight）。

2) 搜索防抖
- 给搜索框添加 200~400ms 防抖，减小请求频率（尤其在 LAN 下用户习惯快速输字符）。

3) 批量操作和局部刷新
- UI 支持多选并调用 `/resources/batch` 或 `/downloads/batch_submit`，后端返回批量结果并携带修改后的资源对象数组，前端用这些对象做局部合并更新，避免调用 `fetchResources()` 全表刷新。

4) 避免不必要的二进制下载
- 继续使用 `resourceApi.getCoverObjectUrl` 的缓存策略，但优先使用 `thumbnail_url`（img src 直接加载），仅在需要 blob 操作（如导出）时才下载二进制。

5) 统一错误/响应处理
- 简化 `src/api/index.js` 的响应拦截器：始终返回规范的 { code, message, data, pagination } 或抛出统一错误对象，组件侧仅依赖该格式。

6) 进度与状态显示
- 使用现有的 `src/stores/websocket.js`（项目已有 websocket store）订阅后端任务事件，ResourceCard/ResourceDetail 订阅并局部更新 `has_video`、`video_create_time` 或下载进度。

优先级（推荐执行顺序）
1. 服务端：实现 GET /resources 支持搜索/筛选/分页/排序 + 统一 pagination（高影响，优先）。
2. 前端：把 `fetchResources` 参数化（search/status/sort/order/page/page_size）并实现搜索防抖（中高）。
3. 服务端：返回单项操作结果（添加/删除/刷新）时包含该资源对象，便于前端局部更新（中）。
4. 服务端：提供 thumbnails（小尺寸）与 `GET /resource/:avid/preview`（加速详情首屏）（中）。
5. 前端：实现批量操作 UI 与调用 `/batch` 端点（中）。
6. 服务端：支持 ETag/Last-Modified，前端实现条件请求缓存（低中）。
7. 服务端/前端：实现 WebSocket 任务推送（如果可行，优先用于实时进度显示；否则用短轮询机制替代）（中）。

示例：接口样例与返回
- 列表
  - 请求: `GET /resources?search=abc&status=pending&sort_by=metadata_create_time&order=desc&page=1&page_size=18`
  - 返回:
    ```json
    {
      "code": 0,
      "message": "ok",
      "data": [{ "avid": "ABC-123", "title": "...", "has_video": false, ... }],
      "pagination": { "total": 120, "page": 1, "page_size": 18, "pages": 7 }
    }
    ```

- 添加资源（返回新对象）
  - 请求: `POST /resource` body { "avid":"ABC-123","source":"any" }
  - 返回: `{ code:0, data: { resource: { avid: "ABC-123", title: "..." } } }`
  - 前端动作: 将返回的 `resource` 插入当前资源列表或请求第一页以刷新展示。

- 详情预览
  - 请求: `GET /resource/ABC-123/preview`
  - 返回: `{ code:0, data: { metadata: {...}, thumbnail_url: "/resource/cover?avid=ABC-123&size=small&v=hash" } }`

实施注意事项（NAS 特有）
- 缩略图生成：在后端做异步生成并缓存到本地 thumbnails 目录，避免每次访问都用 CPU 重新生成大图片。
- 权限与路径：对于返回 `abspath` 的接口，确保前端展示/复制行为仅限受信任的本地客户端，避免误用导致安全问题。
- 资源版本：为 metadata/thumbnail 添加版本字段或在 URL 上添加 `?v=`，便于强缓存失效。
