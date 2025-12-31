## 给前端的适配要点

- **统一响应包裹（envelope）**：后端现在使用统一响应结构，格式为：

  ```json
  {
    "code": 0,
    "message": "ok",
    "data": { ... }
  }
  ```

  - 前端应以 `data` 为主要载体读取实际资源，`code`/`message` 用于通用错误/状态显示。

- **资源列表（新接口）**：`GET /api/resources/`
  - 支持查询参数：`page`（默认1）、`page_size`、`source`、`file_exists`（0/1）、`ordering` 等。
  - 返回的 `data` 中包含 `results`（对象数组）和 `pagination`（页码、总数、page_size 等）。前端应使用 `pagination` 渲染翻页控件。

- **旧接口仍兼容**：很多老接口仍保留（如 `/api/resource`、`/api/downloads/<avid>`），但推荐优先使用 `/api/resources/` 作为统一列表入口。

- **封面/文件响应**：`GET /api/resource/cover?avid=...` 返回的是 `FileResponse`（直接二进制流），并非 JSON。前端请求时请不要尝试按 JSON 解析，而应以 `blob`/`arraybuffer` 或直接通过浏览器 `<img src>` 加载。

- **下载路径与 abspath**：`/api/downloads/abspath?avid=...` 返回的路径包含 `config.UrlPrefix` 前缀（供前端拼接访问），但后端文档已标注不要暴露真实文件系统路径到用户端。前端应仅用于构建下载/播放 URL，不要展示为文件系统路径。

- **创建/刷新资源**：`POST /api/resource`（或旧的 `POST /api/resource/new` 行为）用于创建或获取资源信息；`POST /api/resource/refresh/{avid}` 用于刷新元数据。注意这些端点可能是异步操作，前端应轮询任务状态或订阅 WebSocket（若已实现）以获取进度。

- **分页与排序**：`/api/resources/` 支持 `ordering` 参数（例如 `-created_at`），并在 `pagination` 中返回 `total`、`page`、`page_size`。前端应在构建表格/列表时为用户提供排序控件并将其映射到 `ordering`。


- **错误处理约定**：统一使用 `code` 字段——`0` 表示成功，非 0 为业务错误；HTTP 状态码仍然遵循 REST（例如 404、400、500）。前端应该同时检查 HTTP 状态和响应内的 `code`。

- **建议前端变更优先级**：
  - 高：使用 `/api/resources/` 替换散落的列表调用；切换到解析 `data` 字段并读取 `pagination`。
  - 中：调整封面加载（区分 FileResponse 与 JSON）；准备认证头部。
