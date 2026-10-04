"""Temporary compatibility exports; URLs migrate to concrete HTTP modules in R7."""

from nassav.http_base import (
    SchemaAPIView as SchemaAPIView,
    EmptySchemaSerializer as EmptySchemaSerializer,
)
from nassav.http.source_views import (
    SourceListView as SourceListView,
    SourceSearchCapabilitiesView as SourceSearchCapabilitiesView,
    SourceCookieView as SourceCookieView,
)
from nassav.http.settings_views import UserSettingView as UserSettingView
from nassav.http.catalog_views import (
    ActorsListView as ActorsListView,
    ActorDetailView as ActorDetailView,
    GenresListView as GenresListView,
    GenreDetailView as GenreDetailView,
)
from nassav.http.recommendation_views import (
    RecommendationsDemoView as RecommendationsDemoView,
    RecommendationsView as RecommendationsView,
    RecommendationOptionsView as RecommendationOptionsView,
    RecommendationMetricsView as RecommendationMetricsView,
    RecommendationFeedbackView as RecommendationFeedbackView,
    RecommendationSeedBlockView as RecommendationSeedBlockView,
    RecommendationAvidBlocklistView as RecommendationAvidBlocklistView,
    RecommendationResetView as RecommendationResetView,
    RecommendationCoverView as RecommendationCoverView,
)
from nassav.http.media_views import (
    ActorAvatarView as ActorAvatarView,
    ResourceCoverView as ResourceCoverView,
    ResourcePreviewView as ResourcePreviewView,
    DownloadAbspathView as DownloadAbspathView,
    ResourceMetadataView as ResourceMetadataView,
)
from nassav.http.task_views import (
    DownloadView as DownloadView,
    TaskQueueStatusView as TaskQueueStatusView,
    DownloadsBatchSubmitView as DownloadsBatchSubmitView,
    MockDownloadView as MockDownloadView,
)
from nassav.http.resource_views import (
    ResourcesListView as ResourcesListView,
    ResourceView as ResourceView,
    RefreshResourceView as RefreshResourceView,
    DeleteResourceView as DeleteResourceView,
    ResourcesBatchView as ResourcesBatchView,
    ResourceStatusView as ResourceStatusView,
    ResourceJobView as ResourceJobView,
    ResourceJobStatusView as ResourceJobStatusView,
    ResourceJobBatchView as ResourceJobBatchView,
)
