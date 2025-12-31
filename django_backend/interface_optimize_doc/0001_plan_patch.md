0001 - Patch 计划（Step3：合并资源列表）

目标
- 在 `nassav` 中新增统一资源列表端点：`GET /nassav/api/resources/`，替代或兼容现有的 `/api/resource/list` 与 `/api/downloads/list`。
- 支持过滤、排序与分页：`file_exists`、`source`、`ordering`（支持按字段及倒序，如 `-video_saved_at`）、`page`、`page_size`。
- 使用 DRF 的分页与视图（`ListAPIView` 或 `ViewSet`），并复用通用的 `ResourceSummarySerializer`。

设计原则
- 向后兼容：先新增新接口并保持旧接口可用（给旧接口调用新查询函数）；后续标注旧接口废弃并移除。
- 高效查询：基于 `AVResource` 模型进行查询，利用索引字段 `file_exists`, `source`, `metadata_saved_at`, `video_saved_at`。
- 分层职责：将查询逻辑放入 `nassav/services.py`（新函数 `list_resources(query_params)`) 以便复用与单元测试。

模型字段（参考 `nassav/models.py`）
- 主字段：`avid`, `title`, `source`, `release_date`, `file_exists`, `file_size`, `metadata_saved_at`, `video_saved_at`。

查询参数
- `file_exists` (optional): true/false（字符串 'true'/'false' 或 '1'/'0'）
- `source` (optional): 精确匹配或逗号分隔多个来源
- `ordering` (optional): 支持字段名或以 `-` 前缀表示降序；允许字段：`avid`, `metadata_saved_at`, `video_saved_at`, `source`, `title`
- `page` / `page_size` (optional): DRF 标准分页参数

接口示例
- 请求：`GET /nassav/api/resources/?file_exists=true&source=Jable&ordering=-video_saved_at&page=1&page_size=20`
- 响应（DRF 风格 + project envelope）：
```
{
  "code": 200,
  "message": "success",
  "data": [
    {"avid":"SSIS-469","title":"...","source":"Jable","release_date":"...","has_video":true,"metadata_create_time":...,"video_create_time":...,"file_size":123456},
    ...
  ],
  "pagination": {"total": 100, "page":1, "page_size":20, "pages":5}
}
```

实现变更清单（文件级）
1. `nassav/serializers.py`
   - 新增 `ResourceSummarySerializer`：包含 `avid`, `title`, `source`, `release_date`, `has_video`（映射 `file_exists`）, `metadata_create_time`（来自 `metadata_saved_at.timestamp()`）, `video_create_time`（来自 `video_saved_at.timestamp()`）, `file_size`。
2. `nassav/services.py`
   - 新增函数 `list_resources(params: dict) -> (queryset, total)` 或 `list_resources` 返回 `data, pagination`；封装过滤/ordering/pagination逻辑，便于旧接口复用。
3. `nassav/views.py`
   - 新增 `ResourcesListView`（DRF `APIView` 或 `GenericAPIView` + `ListModelMixin` / `ListAPIView`）：
     - 使用 `list_resources` 获取 queryset 或结果。
     - 返回标准 `code/message/data/pagination`。
   - 修改 `ResourceListView.get` 与 `DownloadsListView.get`：将内部查询替换为调用 `list_resources`（保持行为一致），并在响应中调用统一序列化器（临时保持这两个旧端点以兼容）。
4. `nassav/urls.py`
   - 添加路由 `path('api/resources/', views.ResourcesListView.as_view(), name='resources-list')`。
5. `tests/test_resources_list.py`
   - 新增测试：
     - 无过滤时返回分页结果
     - `file_exists=true` 仅返回已下载项
     - `source` 过滤
     - `ordering` 的正确性

代码草案

- `nassav/serializers.py`（增量示例）
```
from rest_framework import serializers
from .models import AVResource

class ResourceSummarySerializer(serializers.Serializer):
    avid = serializers.CharField()
    title = serializers.CharField()
    source = serializers.CharField()
    release_date = serializers.CharField(allow_blank=True)
    has_video = serializers.BooleanField(source='file_exists')
    metadata_create_time = serializers.SerializerMethodField()
    video_create_time = serializers.SerializerMethodField()
    file_size = serializers.IntegerField(allow_null=True)

    def get_metadata_create_time(self, obj):
        return obj.metadata_saved_at.timestamp() if obj.metadata_saved_at else None

    def get_video_create_time(self, obj):
        return obj.video_saved_at.timestamp() if obj.video_saved_at else None
```

- `nassav/services.py`（新增函数草案）
```
from django.core.paginator import Paginator
from .models import AVResource

def list_resources(params):
    qs = AVResource.objects.all()
    fe = params.get('file_exists')
    if fe is not None:
        if str(fe).lower() in ('1','true','yes'):
            qs = qs.filter(file_exists=True)
        else:
            qs = qs.filter(file_exists=False)
    source = params.get('source')
    if source:
        sources = [s.strip() for s in source.split(',') if s.strip()]
        qs = qs.filter(source__in=sources)

    ordering = params.get('ordering')
    if ordering:
        qs = qs.order_by(ordering)

    # pagination
    page = max(int(params.get('page', 1)), 1)
    page_size = max(int(params.get('page_size', 20)), 1)
    paginator = Paginator(qs, page_size)
    page_obj = paginator.get_page(page)
    return page_obj.object_list, {'total': paginator.count, 'page': page, 'page_size': page_size, 'pages': paginator.num_pages}
```

- `nassav/views.py`（新增视图草案）
```
from rest_framework.views import APIView
from rest_framework.response import Response
from .services import list_resources
from .serializers import ResourceSummarySerializer

class ResourcesListView(APIView):
    def get(self, request):
        objs, pagination = list_resources(request.query_params)
        serializer = ResourceSummarySerializer(objs, many=True)
        return Response({'code':200,'message':'success','data':serializer.data,'pagination':pagination})
```

迁移与兼容策略
- 第一阶段（当前 PR）：新增接口 `api/resources/`，在 `ResourceListView` 与 `DownloadsListView` 中调用 `list_resources` 以移除重复逻辑。
- 第二阶段（后续 PR）：将客户端指向新接口并在文档中标注旧接口废弃；在 1 个发布周期后移除旧路由。

验收标准
- 新增 `ResourcesListView` 可正确返回带过滤/排序/分页的结果（单元测试覆盖）。
- 旧端点不改变外部行为（除非文档化的迁移），并在内部复用 `list_resources` 实现。
- 代码提交包含相应的单元测试并在本地 `pytest` 通过。

后续建议（与 Step4 联动）
- 在 Step4 中将 `ResourceSummarySerializer` 抽象为 `ResourceSerializer` 的子集，并统一 `ResponseEnvelope` 的构建函数（如 `nassav/utils.py: build_response`），以便所有视图使用一致返回格式与 HTTP 状态码。

文件已生成：
- [interface_optimize_doc/0001_plan_patch.md](interface_optimize_doc/0001_plan_patch.md)
