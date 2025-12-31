Step4 设计文档：序列化器统一与响应封装

目标
- 统一资源元数据的序列化器：`ResourceSerializer`（完整元数据）与 `ResourceSummarySerializer`（列表/简要）。
- 提供创建/输入校验序列化器：`ResourceCreateSerializer`。
- 引入统一的 JSON envelope 构建工具 `build_response(code, message, data, http_status=None)` 以便视图统一返回格式并正确设置 HTTP 状态码。
- 最小化现有视图改动：按需替换序列化器/返回逻辑，但确保旧端点行为兼容。

设计细节

1) 序列化器（文件：`nassav/serializers.py`）
- 定义：
  - `ResourceSummarySerializer`：用于列表视图，字段：`avid, title, source, release_date, has_video, metadata_create_time, video_create_time, file_size`。
  - `ResourceSerializer`：用于 metadata/detail，字段：`avid, title, m3u8, source, release_date, duration, director, studio, label, series, actors, genres, file_size, file_exists`（优先使用 DB 中 `metadata` 字段，如存在则直接传递）。
  - `ResourceCreateSerializer`：用于 `POST /api/resource`，字段：`avid`（required, uppercase validated）, `source`（optional, choices 或字符串）。

- 示例实现片段：

  - `ResourceSummarySerializer`（示例）

    from rest_framework import serializers
    from .models import AVResource

    class ResourceSummarySerializer(serializers.ModelSerializer):
        has_video = serializers.BooleanField(source='file_exists')
        metadata_create_time = serializers.SerializerMethodField()
        video_create_time = serializers.SerializerMethodField()

        class Meta:
            model = AVResource
            fields = ('avid','title','source','release_date','has_video','metadata_create_time','video_create_time','file_size')

        def get_metadata_create_time(self, obj):
            return obj.metadata_saved_at.timestamp() if obj.metadata_saved_at else None

        def get_video_create_time(self, obj):
            return obj.video_saved_at.timestamp() if obj.video_saved_at else None

  - `ResourceSerializer`（示例）

    class ResourceSerializer(serializers.Serializer):
        avid = serializers.CharField()
        title = serializers.CharField(allow_blank=True)
        m3u8 = serializers.CharField(allow_blank=True, allow_null=True)
        source = serializers.CharField(allow_blank=True)
        release_date = serializers.CharField(allow_blank=True)
        duration = serializers.IntegerField(allow_null=True)
        director = serializers.CharField(allow_blank=True)
        studio = serializers.CharField(allow_blank=True)
        label = serializers.CharField(allow_blank=True)
        series = serializers.CharField(allow_blank=True)
        actors = serializers.ListField(child=serializers.CharField(), allow_empty=True)
        genres = serializers.ListField(child=serializers.CharField(), allow_empty=True)
        file_size = serializers.IntegerField(allow_null=True)
        file_exists = serializers.BooleanField()

    # 用法：当 AVResource.metadata 有内容时，直接传 metadata dict 给此序列化器进行校验/输出；否则基于 model fields 构建 dict

2) Response Envelope（文件建议：`nassav/utils.py` 或 `nassav/api_utils.py`）
- 定义 `build_response(code:int, message:str, data:any=None)`：返回 `Response` 对象并设置正确 `status`（映射：200->HTTP_200_OK, 201->201_CREATED, 202->202_ACCEPTED, 400->400_BAD_REQUEST, 404->404_NOT_FOUND, 409->409_CONFLICT, 500->500_INTERNAL_SERVER_ERROR, 502->502_BAD_GATEWAY）
- 视图改造建议：所有 APIView 返回使用 `return build_response(code, message, data)` 代替直接 `Response({...})`。对于返回文件流（`FileResponse`），保持原样（不包裹），但在文档中声明该端点特殊处理。

- 示例：

    from rest_framework.response import Response
    from rest_framework import status

    STATUS_MAP = {200: status.HTTP_200_OK, 201: status.HTTP_201_CREATED, 202: status.HTTP_202_ACCEPTED, 400: status.HTTP_400_BAD_REQUEST, 404: status.HTTP_404_NOT_FOUND, 409: status.HTTP_409_CONFLICT, 500: status.HTTP_500_INTERNAL_SERVER_ERROR, 502: status.HTTP_502_BAD_GATEWAY}

    def build_response(code: int, message: str, data=None):
        http_status = STATUS_MAP.get(code, status.HTTP_200_OK)
        return Response({'code': code, 'message': message, 'data': data}, status=http_status)

3) 视图改造建议（文件：`nassav/views.py`）
- 受改造影响的视图：`ResourceMetadataView`, `ResourceView`, `RefreshResourceView`, `ResourceListView`, `DownloadsListView`。
- 改造原则：
  - 在逻辑层（服务函数）构造好 dict 或 model instances，然后使用序列化器序列化成 `data`；最后通过 `build_response` 返回。
  - 保持行为兼容：不要在第一次改造中改变返回字段名或错误语义，优先替换内部生成/格式化逻辑。

- 示例修改片段（`ResourceMetadataView.get`）：

    # 伪代码
    resource = AVResource.objects.filter(avid=avid).first()
    if resource is None:
        return build_response(404, f'资源 {avid} 的元数据不存在', None)

    # 优先使用 metadata json
    metadata = resource.metadata if resource.metadata else {
        'avid': resource.avid,
        'title': resource.title,
        'm3u8': resource.m3u8,
        'source': resource.source,
        ...
    }

    serializer = ResourceSerializer(metadata)
    return build_response(200, 'success', serializer.data)

4) 校验与输入
- `ResourceCreateSerializer` 负责对 `POST /api/resource` 的 `avid` 做最低限度校验（非空，格式化为大写）。对 `source` 可选项，建议在 serializer 的 `validate_source` 中校验是否存在于 `source_manager.sources`。

5) Tests（文件夹：`tests/`）
- 新增：`tests/test_serializers.py`：验证 `ResourceSerializer` 在 metadata dict 与 AVResource instance 两种输入下的行为一致。
- `tests/test_views_resource.py`：使用 Django `APIClient` 测试 `ResourceMetadataView`, `ResourceView (POST)`, `RefreshResourceView`，断言 `code` 字段和 HTTP status 映射一致。
- 使用 fixtures 或工厂（如 `pytest-django` + `model_bakery`）快速创建 AVResource 实例。

6) 兼容与迁移策略
- 先在代码中引入新序列化器与 `build_response`，把关键视图替换为使用这些组件，旧外部接口保持不变（字段/状态码兼容）。
- 后续可统一将所有视图迁移到 `build_response`，并在新版本中调整返回 envelope 或 HTTP 状态策略。

7) 文件与 PR 列表（建议拆分为多个 PR）
- PR 1（小）：添加 `ResourceSummarySerializer`, `ResourceSerializer` 与 `ResourceCreateSerializer`，并新增测试 `tests/test_serializers.py`。
- PR 2：添加 `build_response` 到 `nassav/utils.py`，并把 `ResourceMetadataView` 与 `ResourceView` 中的返回改造为 `build_response`。附单元测试。
- PR 3：修改其余视图（`DownloadView`, `RefreshResourceView`, 列表视图）复用 `ResourceSummarySerializer` / `build_response` 并补齐测试。

验收标准
- `tests/` 中序列化器测试通过；对 `ResourceMetadataView` 的 API 测试显示 `code` 与 HTTP 状态码一致。
- 新的序列化器已复用并添加到 `nassav/serializers.py`，并在 `nassav/views.py` 中被使用。
- 文档 `doc/interfaces.md` 保持或更新以反映任何有意改变（例如，明确 FileResponse 不使用 envelope）。

时间估算
- 设计与实现（分 PR）：约 1-2 天（视测试覆盖程度与回归修复而定）。

已生成文件
- [interface_optimize_doc/0002_step4_design.md](interface_optimize_doc/0002_step4_design.md)

下一步
- 如果你确认设计，我将开始 PR 1：实现序列化器与基础测试，并在本地运行 `pytest` 验证。
