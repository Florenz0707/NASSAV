from django.urls import path
from . import views

app_name = 'nassav'

urlpatterns = [
    # GET /api/resource/list - 获取数据库中的所有(avid, title)
    path('api/resource/list', views.ResourceListView.as_view(), name='resource-list'),

    # GET /api/resource/cover?avid= - 根据avid获取封面图片
    path('api/resource/cover', views.ResourceCoverView.as_view(), name='resource-cover'),

    # GET /api/resource/downloads/list - 获取已下载的所有视频的avid
    path('api/resource/downloads/list', views.DownloadsListView.as_view(), name='downloads-list'),

    # GET /api/resource/downloads/metadata?avid= - 根据avid获取视频元数据
    path('api/resource/downloads/metadata', views.DownloadsMetadataView.as_view(), name='downloads-metadata'),

    # POST /api/resource/new - 通过avid获取title并下载cover
    path('api/resource/new', views.NewResourceView.as_view(), name='resource-new'),

    # POST /api/resource/downloads/new - 通过avid下载视频
    path('api/resource/downloads/new', views.NewDownloadView.as_view(), name='downloads-new'),
]
