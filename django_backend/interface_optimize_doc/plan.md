执行计划：接口审查与整合（Step1, Step3, Step4, Step6）

目标
- 对齐文档与路由，消除命名不一致（Step1）。
- 合并重复的资源列表端点，提供统一的分页/过滤/排序（Step3）。
- 统一序列化器与响应格式，复用 `ResourceSerializer`，引入标准 JSON envelope（Step4）。
- 生成 OpenAPI 文档并补充测试覆盖（Step6）。

总原则
- 最小破坏：先引入新接口与兼容层，再逐步标记旧接口废弃。
- 安全优先：对写、删、任务相关接口在后续实现中强制鉴权（本计划列出需求，但鉴权实现单独 PR）。
- 可回退：每个功能拆为小变更（文档→模型→序列化器→视图），便于回退与 CI 验证。

交付物
- `step1_report.md`：文档与路由不一致清单与建议修正（Step1 输出）。
- `0001_plan_patch.md`：分步补丁清单（Step3/4 的具体改动文件列表及代码片段）。
- 新增序列化器文件/修改视图的代码补丁（以 PR 提交）。
- OpenAPI 生成文件 `openapi.yaml`（Step6），以及测试骨架 `tests/test_api.py`。

细分步骤与验收标准

1) Step1 — 校准接口文档（时长估计：0.5 - 1 天）
- 操作：扫描并比对 [doc/interfaces.md](doc/interfaces.md)、`nassav/urls.py`、`nassav/views.py`；记录差异（路径、方法、参数、返回结构）；在 `step1_report.md` 给出建议（修改文档或修改路由/视图）。
- 验收：`step1_report.md` 包含完整差异表和优先级（高/中/低），并列出需修改的具体文件与建议变更行范围。

2) Step3 — 合并资源列表（时长估计：1 - 2 天）
- 目标接口：新增 `GET /nassav/api/resources/`（或 `/api/resources/`）
- 支持的查询参数：`page`, `page_size`, `ordering` (e.g., `-video_create_time`), `file_exists` (true/false), `source`。
- 实现要点：在 `nassav/serializers.py` 新增或复用 `ResourceSummarySerializer`，在 `nassav/views.py` 新增基于 DRF 的 `ResourceListView`（或 ViewSet），并将现有 `/resource/list` 与 `/downloads/list` 逐步指向该实现（兼容重定向或标记废弃）。
- 验收：新接口返回 DRF 风格分页响应并通过单元测试；旧接口至少返回相同字段或 301/410（按迁移策略）。

3) Step4 — 统一序列化器与响应信封（时长估计：1 - 2 天）
- 操作：
  - 在 `nassav/serializers.py` 中定义 `ResourceSerializer`（包含 metadata 字段）、`ResourceCreateSerializer`（继承并限定必填字段）；
  - 在项目共享模块（如 `nassav/utils.py` 或 `nassav/serializers.py` 顶部）定义 `build_response(code:int, message:str, data:any)` 工具并在视图中统一使用；
  - 修改 `ResourceMetadataView`、`ResourceView`、`RefreshResourceView` 等使用新序列化器并保持返回格式一致（JSON envelope + 合理 HTTP 状态码）。
- 验收：关键视图的行为在单元测试下保持一致或改进（更合理的 HTTP 状态码），并且序列化器复用率提高（避免重复字段定义）。

4) Step6 — 文档与测试（时长估计：1 - 2 天，与实现并行）
- 操作：使用 DRF 的 schema 生成或 `drf-yasg` / `drf-spectacular` 生成 `openapi.yaml`；在 `tests/` 下添加接口测试（至少覆盖合并后的资源列表、metadata、创建、下载入队的关键路径）；为 WebSocket 消息写简单集成测试（可用 Channels 测试客户端）。
- 验收：`openapi.yaml` 能覆盖主要端点；CI 能运行 tests 并通过（本地先运行）。

开发与提交流程
- 分支策略：每一步一个 PR（例：`refactor/interface-step1-docsync`、`refactor/interface-step3-resources` 等）。
- 代码风格：遵循现有项目风格，尽量不变动公共 API 名称，先添加兼容层再逐步清理。

运行与验证（本地快速命令示例）
- 安装依赖并运行测试：
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest tests/ -q
```

后续计划
- 我将先执行 Step1（扫描并生成 `step1_report.md`），然后返回差异报告并开始 Step3 的设计。
