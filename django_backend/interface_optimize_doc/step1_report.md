Step1 报告：文档与路由/视图不一致清单

概述
- 我已比对 `doc/interfaces.md`、`nassav/urls.py` 与 `nassav/views.py`。以下列出发现的不一致点、说明与建议修正。

主要不一致项

1. POST 下载接口的路径与参数位置不一致
- 文档：在 `doc/interfaces.md` 中，提交下载任务示例使用 `POST /nassav/api/downloads`，请求体为 `{ "avid": "SSIS-469" }`。
- 实现：在 `nassav/urls.py` 与 `nassav/views.py` 中，`DownloadView` 注册为 `path('api/downloads/<str:avid>', ...)`，实现要求 `avid` 为路径参数（`POST /api/downloads/{avid}`）。
- 建议：统一为其中一种方案。
  - 推荐：改文档为 `POST /nassav/api/downloads/{avid}`（更 RESTful 且与当前实现一致），或如果要保留 body 形式，则调整 `urls.py` 与 `views.DownloadView.post` 接收 body。

2. `ResourceMetadataView` 的 docstring/注释错误
- 实现（视图类注释）：`ResourceMetadataView` 的类注释写作 `GET /api/resource/downloads/metadata?avid=`，这明显包含多余的 `downloads`。
- 实际路由：`nassav/urls.py` 注册为 `path('api/resource/metadata', ...)`。
- 建议：修正视图注释为 `GET /api/resource/metadata?avid=`，并确保文档 `doc/interfaces.md` 的描述与实现一致（目前文档是正确的）。

3. Downloads 列表视图的注释错误
- 实现视图注释（`DownloadsListView`）写作 `GET /api/resource/downloads/list`（错误），而路由为 `api/downloads/list`，文档也为 `GET /nassav/api/downloads/list`。
- 建议：修正 `DownloadsListView` 的 docstring 注释为 `GET /api/downloads/list`。

4. Resource 创建端点文档中存在 `resource/new` 的引用差异
- 文档：若干地方（如在刷新失败提示中）建议调用 `/api/resource/new` 添加资源。
- 实现：`urls.py` 使用 `path('api/resource', views.ResourceView.as_view(), name='resource-new')`（即实际路径为 `/api/resource`）。
- 建议：统一为 `/api/resource`，并将所有文档及视图注释统一，或将路由改为 `/api/resource/new`（不推荐）。

5. 视图返回说明 vs 实际行为的细微差异
- `ResourceCoverView` 在视图实现中直接返回 `FileResponse`（image stream），而文档统一响应格式为 JSON envelope。文档在该端点说明为“图片文件 (image/jpeg)”，但未说明异常时返回 JSON。实现中异常返回 JSON（正确），建议在文档中明确说明成功时为二进制流，失败时为 JSON envelope。
- `DownloadAbspathView` 返回绝对路径（prefixed），文档已有说明，但需在文档中额外标注安全风险（会泄露主机路径），或改变实现以返回受限/相对路径。

6. 注释/文档用词不统一
- 文档中使用 `/nassav` 前缀（正确），`urls.py` 中注释多为 `/api/...`（省略前缀）。建议统一文档和注释均写完整前缀 `/nassav/api/...`，以减少混淆。

建议修正清单（优先级）

高优先级
- 将 `doc/interfaces.md` 中关于 `POST /api/downloads` 的示例改为使用路径参数：`POST /nassav/api/downloads/{avid}`，并更新示例请求/响应（匹配 `DownloadView.post`）。
- 修正 `nassav/views.py` 中的错误 docstring（`ResourceMetadataView`、`DownloadsListView` 等），确保视图注释准确反映路由。
- 在 `doc/interfaces.md` 中对 `ResourceCoverView` 明确成功返回为图片流，错误返回为 JSON envelope；对 `DownloadAbspathView` 增加安全警告。

中优先级
- 统一文档与注释中的路径前缀写法（全部使用 `/nassav/api/...`）。
- 将 `doc/interfaces.md` 中提及的 `/api/resource/new` 的所有引用改为 `/api/resource` 或在文档中说明别名及兼容期。

低优先级
- 逐条检查文档示例的 HTTP 状态码与视图实现一致性（例如 201/202/409 等），并统一用例。

下一步计划
- 我将把这些修正生成为具体的补丁清单（文件 + 修改位置）并写入 `0001_plan_patch.md`，作为 Step3 设计前的准备工作。
- 同时把 `step1_report.md` 放入版本库（已写入）。

参考文件
- [doc/interfaces.md](doc/interfaces.md)
- [nassav/urls.py](nassav/urls.py)
- [nassav/views.py](nassav/views.py)

生成时间：2025-12-31
