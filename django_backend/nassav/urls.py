from django.urls import path

from . import auth_views
from .http import (
    catalog_views,
    media_views,
    recommendation_views,
    resource_views,
    settings_views,
    source_views,
    task_views,
)
from .search_job_views import (
    SearchJobCancelView,
    SearchJobSubmitView,
    SearchJobStatusView,
)

app_name = "nassav"

urlpatterns = [
    path("api/search/jobs", SearchJobSubmitView.as_view(), name="search-job-submit"),
    path(
        "api/search/jobs/<uuid:task_id>",
        SearchJobStatusView.as_view(),
        name="search-job-status",
    ),
    path(
        "api/search/jobs/<uuid:task_id>/cancel",
        SearchJobCancelView.as_view(),
        name="search-job-cancel",
    ),
    path("api/auth/session", auth_views.session_view, name="auth-session"),
    path("api/auth/login", auth_views.login_view, name="auth-login"),
    path("api/auth/logout", auth_views.logout_view, name="auth-logout"),
    # GET /api/source/list - 获取可用的下载源列表
    path(
        "api/source/search-capabilities",
        source_views.SourceSearchCapabilitiesView.as_view(),
        name="source-search-capabilities",
    ),
    path("api/source/list", source_views.SourceListView.as_view(), name="source-list"),
    # GET/POST/DELETE /api/source/cookie - 源Cookie管理
    path(
        "api/source/cookie",
        source_views.SourceCookieView.as_view(),
        name="source-cookie",
    ),
    # GET/PUT /api/setting - 用户设置管理
    path("api/setting", settings_views.UserSettingView.as_view(), name="user-setting"),
    # GET /api/resources - 统一资源列表（过滤/分页）
    path(
        "api/resources",
        resource_views.ResourcesListView.as_view(),
        name="resources-list",
    ),
    # backward compatibility for legacy trailing slash path
    path("api/resources/", resource_views.ResourcesListView.as_view()),
    # GET /api/recommendations - 推荐结果
    path(
        "api/recommendations",
        recommendation_views.RecommendationsView.as_view(),
        name="recommendations",
    ),
    # backward compatibility for legacy trailing slash path
    path("api/recommendations/", recommendation_views.RecommendationsView.as_view()),
    # GET /api/recommendations/options - 推荐器与策略选项
    path(
        "api/recommendations/options",
        recommendation_views.RecommendationOptionsView.as_view(),
        name="recommendations-options",
    ),
    # GET /api/recommendations/metrics - 推荐效果与状态概览
    path(
        "api/recommendations/metrics",
        recommendation_views.RecommendationMetricsView.as_view(),
        name="recommendations-metrics",
    ),
    # POST /api/recommendations/feedback - 记录推荐反馈
    path(
        "api/recommendations/feedback",
        recommendation_views.RecommendationFeedbackView.as_view(),
        name="recommendations-feedback",
    ),
    # POST/DELETE /api/recommendations/seed-block - 手动屏蔽或取消屏蔽 actor/genre
    path(
        "api/recommendations/seed-block",
        recommendation_views.RecommendationSeedBlockView.as_view(),
        name="recommendations-seed-block",
    ),
    # GET/POST/DELETE /api/recommendations/avid-blocklist - 手动管理资源黑名单
    path(
        "api/recommendations/avid-blocklist",
        recommendation_views.RecommendationAvidBlocklistView.as_view(),
        name="recommendations-avid-blocklist",
    ),
    # POST /api/recommendations/reset - 清空推荐状态
    path(
        "api/recommendations/reset",
        recommendation_views.RecommendationResetView.as_view(),
        name="recommendations-reset",
    ),
    # GET /api/recommendations/cover - 推荐封面代理缓存
    path(
        "api/recommendations/cover",
        recommendation_views.RecommendationCoverView.as_view(),
        name="recommendations-cover",
    ),
    # GET /api/recommendations/demo - demo 推荐结果
    path(
        "api/recommendations/demo",
        recommendation_views.RecommendationsDemoView.as_view(),
        name="recommendations-demo",
    ),
    # GET /api/actors - 演员列表及作品数（分页）
    path("api/actors", catalog_views.ActorsListView.as_view(), name="actors-list"),
    # backward compatibility for legacy trailing slash path
    path("api/actors/", catalog_views.ActorsListView.as_view()),
    # GET /api/actors/<int:actor_id>/detail - 获取演员详情与外部搜索结果
    path(
        "api/actors/<int:actor_id>/detail",
        catalog_views.ActorDetailView.as_view(),
        name="actor-detail",
    ),
    # GET /api/actors/<int:actor_id>/avatar - 获取演员头像图片
    path(
        "api/actors/<int:actor_id>/avatar",
        media_views.ActorAvatarView.as_view(),
        name="actor-avatar",
    ),
    # GET /api/genres - 类别列表及作品数（分页）
    path("api/genres", catalog_views.GenresListView.as_view(), name="genres-list"),
    # backward compatibility for legacy trailing slash path
    path("api/genres/", catalog_views.GenresListView.as_view()),
    # GET /api/genres/<int:genre_id>/detail - 获取类别详情与外部搜索结果
    path(
        "api/genres/<int:genre_id>/detail",
        catalog_views.GenreDetailView.as_view(),
        name="genre-detail",
    ),
    # GET /api/resource/cover?avid= - 根据avid获取封面图片
    path(
        "api/resource/cover",
        media_views.ResourceCoverView.as_view(),
        name="resource-cover",
    ),
    # GET /api/resource/{avid}/preview - 详情首屏预览（metadata + thumbnail_url）
    path(
        "api/resource/<str:avid>/preview",
        media_views.ResourcePreviewView.as_view(),
        name="resource-preview",
    ),
    # POST /api/resources/batch - 批量资源操作（add/delete/refresh）
    path(
        "api/resources/batch",
        resource_views.ResourcesBatchView.as_view(),
        name="resources-batch",
    ),
    # POST /api/downloads/batch_submit - 批量提交下载任务
    path(
        "api/downloads/batch_submit",
        task_views.DownloadsBatchSubmitView.as_view(),
        name="downloads-batch-submit",
    ),
    # GET /api/resource/metadata?avid= - 根据avid获取视频元数据
    path(
        "api/resource/metadata",
        media_views.ResourceMetadataView.as_view(),
        name="resource-metadata",
    ),
    # Async resource jobs leave the legacy synchronous endpoints unchanged.
    path(
        "api/resource/jobs",
        resource_views.ResourceJobView.as_view(),
        name="resource-jobs",
    ),
    path(
        "api/resource/jobs/batch",
        resource_views.ResourceJobBatchView.as_view(),
        name="resource-jobs-batch",
    ),
    path(
        "api/resource/jobs/<uuid:task_id>",
        resource_views.ResourceJobStatusView.as_view(),
        name="resource-job-status",
    ),
    # POST /api/resource/new - 通过avid获取资源信息（可指定source）
    path("api/resource", resource_views.ResourceView.as_view(), name="resource-new"),
    # POST /api/resource/refresh/{avid} - 刷新已有资源的元数据和m3u8链接
    path(
        "api/resource/refresh/<str:avid>",
        resource_views.RefreshResourceView.as_view(),
        name="resource-refresh",
    ),
    # DELETE /api/resource/{avid} - 删除整个资源目录
    path(
        "api/resource/<str:avid>",
        resource_views.DeleteResourceView.as_view(),
        name="resource-delete",
    ),
    # PATCH /api/resource/{avid}/status - 更新资源的观看状态和收藏状态
    path(
        "api/resource/<str:avid>/status",
        resource_views.ResourceStatusView.as_view(),
        name="resource-status",
    ),
    # GET /api/downloads/abspath?avid= - 返回视频文件的绝对路径，前面拼接 config.FilePathPrefix
    path(
        "api/downloads/abspath",
        media_views.DownloadAbspathView.as_view(),
        name="downloads-abspath",
    ),
    # POST /api/downloads/{avid} - 通过avid下载视频
    path(
        "api/downloads/<str:avid>",
        task_views.DownloadView.as_view(),
        name="downloads-new",
    ),
    # DELETE /api/downloads/{avid} - 删除已下载的视频
    path(
        "api/downloads/<str:avid>",
        task_views.DownloadView.as_view(),
        name="downloads-delete",
    ),
    # POST /api/downloads/mock/{avid} - 模拟下载任务（仅 DEBUG 模式）
    path(
        "api/downloads/mock/<str:avid>",
        task_views.MockDownloadView.as_view(),
        name="downloads-mock",
    ),
    # GET /api/tasks/queue/status - 获取任务队列状态
    path(
        "api/tasks/queue/status",
        task_views.TaskQueueStatusView.as_view(),
        name="task-queue-status",
    ),
    # Schema endpoints for OpenAPI (drf-spectacular)
]
