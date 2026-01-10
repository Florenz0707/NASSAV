from django.urls import path

from . import views

app_name = "nassav"

urlpatterns = [
    # GET /api/source/list - 获取可用的下载源列表
    path("api/source/list", views.SourceListView.as_view(), name="source-list"),
    # GET/POST/DELETE /api/source/cookie - 源Cookie管理
    path("api/source/cookie", views.SourceCookieView.as_view(), name="source-cookie"),
    # GET/PUT /api/setting - 用户设置管理
    path("api/setting", views.UserSettingView.as_view(), name="user-setting"),
    # GET /api/resources/ - 统一资源列表（过滤/分页）
    path("api/resources/", views.ResourcesListView.as_view(), name="resources-list"),
    # GET /api/actors/ - 演员列表及作品数（分页）
    path("api/actors/", views.ActorsListView.as_view(), name="actors-list"),
    # GET /api/actors/<int:actor_id>/avatar - 获取演员头像图片
    path(
        "api/actors/<int:actor_id>/avatar",
        views.ActorAvatarView.as_view(),
        name="actor-avatar",
    ),
    # GET /api/genres/ - 类别列表及作品数（分页）
    path("api/genres/", views.GenresListView.as_view(), name="genres-list"),
    # GET /api/resource/cover?avid= - 根据avid获取封面图片
    path(
        "api/resource/cover", views.ResourceCoverView.as_view(), name="resource-cover"
    ),
    # GET /api/resource/{avid}/preview - 详情首屏预览（metadata + thumbnail_url）
    path(
        "api/resource/<str:avid>/preview",
        views.ResourcePreviewView.as_view(),
        name="resource-preview",
    ),
    # POST /api/resources/batch - 批量资源操作（add/delete/refresh）
    path(
        "api/resources/batch",
        views.ResourcesBatchView.as_view(),
        name="resources-batch",
    ),
    # POST /api/downloads/batch_submit - 批量提交下载任务
    path(
        "api/downloads/batch_submit",
        views.DownloadsBatchSubmitView.as_view(),
        name="downloads-batch-submit",
    ),
    # GET /api/resource/metadata?avid= - 根据avid获取视频元数据
    path(
        "api/resource/metadata",
        views.ResourceMetadataView.as_view(),
        name="resource-metadata",
    ),
    # POST /api/resource/new - 通过avid获取资源信息（可指定source）
    path("api/resource", views.ResourceView.as_view(), name="resource-new"),
    # POST /api/resource/refresh/{avid} - 刷新已有资源的元数据和m3u8链接
    path(
        "api/resource/refresh/<str:avid>",
        views.RefreshResourceView.as_view(),
        name="resource-refresh",
    ),
    # DELETE /api/resource/{avid} - 删除整个资源目录
    path(
        "api/resource/<str:avid>",
        views.DeleteResourceView.as_view(),
        name="resource-delete",
    ),
    # PATCH /api/resource/{avid}/status - 更新资源的观看状态和收藏状态
    path(
        "api/resource/<str:avid>/status",
        views.ResourceStatusView.as_view(),
        name="resource-status",
    ),
    # GET /api/downloads/abspath?avid= - 返回视频文件的绝对路径，前面拼接 config.FilePathPrefix
    path(
        "api/downloads/abspath",
        views.DownloadAbspathView.as_view(),
        name="downloads-abspath",
    ),
    # POST /api/downloads/{avid} - 通过avid下载视频
    path(
        "api/downloads/<str:avid>", views.DownloadView.as_view(), name="downloads-new"
    ),
    # DELETE /api/downloads/{avid} - 删除已下载的视频
    path(
        "api/downloads/<str:avid>",
        views.DownloadView.as_view(),
        name="downloads-delete",
    ),
    # POST /api/downloads/mock/{avid} - 模拟下载任务（仅 DEBUG 模式）
    path(
        "api/downloads/mock/<str:avid>",
        views.MockDownloadView.as_view(),
        name="downloads-mock",
    ),
    # GET /api/tasks/queue/status - 获取任务队列状态
    path(
        "api/tasks/queue/status",
        views.TaskQueueStatusView.as_view(),
        name="task-queue-status",
    ),
    # Schema endpoints for OpenAPI (drf-spectacular)
]
