from django.urls import path

from . import views

app_name = 'nassav'

urlpatterns = [
    # GET /api/source/list - 获取可用的下载源列表
    path('api/source/list', views.SourceListView.as_view(), name='source-list'),

    # GET /api/resource/list - 获取所有已保存资源
    path('api/resource/list', views.ResourceListView.as_view(), name='resource-list'),

    # GET /api/resource/cover?avid= - 根据avid获取封面图片
    path('api/resource/cover', views.ResourceCoverView.as_view(), name='resource-cover'),

    # POST /api/resource/new - 通过avid获取资源信息（可指定source）
    path('api/resource/new', views.NewResourceView.as_view(), name='resource-new'),

    # POST /api/resource/refresh - 刷新已有资源的元数据和m3u8链接
    path('api/resource/refresh', views.RefreshResourceView.as_view(), name='resource-refresh'),

    # GET /api/downloads/list - 获取已下载的所有视频的avid
    path('api/downloads/list', views.DownloadsListView.as_view(), name='downloads-list'),

    # GET /api/downloads/metadata?avid= - 根据avid获取视频元数据
    path('api/downloads/metadata', views.DownloadsMetadataView.as_view(), name='downloads-metadata'),

    # POST /api/downloads/new - 通过avid下载视频
    path('api/downloads/new', views.NewDownloadView.as_view(), name='downloads-new'),
]
