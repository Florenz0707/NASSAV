"""Application authorization independent of Django staff/superuser shortcuts."""

from django.db.models import Q

from nassav.account_models import UserAccount
from nassav.library_models import UserLibraryEntry


def account(user):
    if not user or not user.is_authenticated or not user.is_active:
        return None
    return UserAccount.objects.filter(user_id=user.pk).first()


def is_app_admin(user):
    row = account(user)
    return bool(row and row.role == "admin")


def is_legacy_operator(user):
    from nassav.access import is_operator

    return is_operator(user) and account(user) is None


def can_admin_tasks(user):
    return is_app_admin(user) or (is_legacy_operator(user) and user.is_superuser)


def execution_epoch(user_id):
    return (
        UserAccount.objects.filter(user_id=user_id)
        .values_list("version", flat=True)
        .first()
        or 0
    )


def own_resource_ids(user_id):
    return (
        UserLibraryEntry.objects.filter(
            user_id=user_id,
            state="active",
            pool__resource__isnull=False,
            pool__state__in=["ready", "preparing"],
            pool__is_available=True,
        )
        .filter(Q(access_scope="public") | Q(access_scope=f"legacy:operator:{user_id}"))
        .values_list("pool__resource_id", flat=True)
    )


def catalog_resource_filter(user_id):
    if user_id is not None and UserAccount.objects.filter(user_id=user_id).exists():
        return Q(resources__pk__in=own_resource_ids(user_id))
    return Q()


def can_read_resource(user, avid, *, administrative=False):
    from nassav.models import AVResource
    from nassav.library_models import ResourcePoolEntry

    if not user or not user.is_authenticated or not user.is_active:
        return False
    if ResourcePoolEntry.objects.filter(
        canonical_avid=avid, is_available=False
    ).exists():
        return False
    if is_legacy_operator(user):
        return True  # Restricted compatibility path; ordinary login stays closed.
    resource = AVResource.objects.filter(avid=avid).first()
    if resource is None:
        return False
    if AVResource.objects.filter(
        pk=resource.pk, pk__in=own_resource_ids(user.pk)
    ).exists():
        return True
    if administrative and is_app_admin(user):
        # Admin is not a universal private-media credential.
        return UserLibraryEntry.objects.filter(
            pool__resource=resource,
            state="active",
            access_scope="public",
            pool__state="ready",
            pool__is_available=True,
        ).exists()
    return False


def grant_playback(user_id, resource):
    """Caller holds user fence; lock the pool before creating a session."""
    from nassav.library_models import ResourcePoolEntry

    if ResourcePoolEntry.objects.filter(resource=resource, is_available=False).exists():
        raise PermissionError("Resource downlisted")
    if not UserAccount.objects.filter(user_id=user_id).exists():
        return {}
    pool = (
        ResourcePoolEntry.objects.select_for_update()
        .filter(resource=resource, is_available=True)
        .first()
    )
    if pool is None or pool.state not in {"ready", "preparing"}:
        raise PermissionError("Resource not available")
    own = UserLibraryEntry.objects.filter(
        user_id=user_id,
        pool=pool,
        state="active",
        access_scope__in=["public", f"legacy:operator:{user_id}"],
    ).first()
    if own:
        scope = own.access_scope
    elif (
        UserAccount.objects.filter(user_id=user_id, role="admin").exists()
        and pool.memberships.filter(state="active", access_scope="public").exists()
    ):
        scope = "public"
    else:
        raise PermissionError("Resource scope not available")
    return {"pool_id": str(pool.pk), "resource_id": resource.pk, "scope": scope}


def can_read_playback(user, session):
    """A pre-authorized grant may drain after ordinary release, never after downlist."""
    from nassav.library_models import ResourcePoolEntry

    if ResourcePoolEntry.objects.filter(
        resource=session.resource, is_available=False
    ).exists():
        return False
    if is_legacy_operator(user):
        return True
    if account(user) is None:
        return False
    grant = session.library_grant
    if not grant:
        return can_read_resource(user, session.resource.avid)
    if grant.get("resource_id") != session.resource.pk or grant.get("scope") not in {
        "public",
        f"legacy:operator:{user.pk}",
    }:
        return False
    from nassav.library_models import ResourcePoolEntry

    try:
        return ResourcePoolEntry.objects.filter(
            pk=grant.get("pool_id"),
            resource=session.resource,
            is_available=True,
            state__in=["preparing", "ready", "pending_gc"],
        ).exists()
    except (ValueError, TypeError):
        return False


ADMIN_VIEWS = frozenset(
    {
        "SourceCookieView",
        "DownloadAbspathView",
        "ResourceView",
        "RefreshResourceView",
        "DeleteResourceView",
        "ResourcesBatchView",
        "ResourceJobView",
        "ResourceJobBatchView",
        "DownloadView",
        "DownloadsBatchSubmitView",
        "MockDownloadView",
        "TaskQueueStatusView",
        "TaskControlView",
        "TaskBatchControlView",
        "TaskCleanupRetryView",
        "RecommendationsDemoView",
    }
)
RESOURCE_VIEWS = frozenset(
    {
        "ResourceCoverView",
        "ResourcePreviewView",
        "ResourceMetadataView",
        "ResourceStatusView",
        "PlaybackSubmitView",
        "PlaybackProgressClearView",
    }
)
READ_VIEWS = frozenset(
    {
        "ResourcesListView",
        "ActorsListView",
        "ActorDetailView",
        "ActorAvatarView",
        "GenresListView",
        "GenreDetailView",
        "SourceListView",
        "SourceSearchCapabilitiesView",
        "SearchJobSubmitView",
        "SearchJobStatusView",
        "SearchJobCancelView",
        "RecommendationsView",
        "RecommendationOptionsView",
        "RecommendationMetricsView",
        "RecommendationFeedbackView",
        "RecommendationSeedBlockView",
        "RecommendationAvidBlocklistView",
        "RecommendationResetView",
        "RecommendationCoverView",
        "RecommendationJobSubmitView",
        "RecommendationJobStatusView",
        "RecommendationJobCancelView",
        "UserSettingView",
        "TaskJobListView",
        "TaskJobStatusView",
        "ResourceJobStatusView",
        "PersonalHistoryView",
        "PersonalWatchLaterView",
        "PlaybackStatusView",
        "PlaybackRefreshView",
        "PlaybackCloseView",
        "PlaybackContinueView",
        "PlaybackProgressView",
        "PlaybackProgressClaimView",
        "PlaybackViewedView",
    }
)


def permit_business_view(request, view):
    """Fail closed for unknown views once an explicit application role is assigned."""
    user = request.user
    if is_legacy_operator(user):
        if type(view).__name__ in RESOURCE_VIEWS:
            avid = view.kwargs.get("avid") or request.query_params.get("avid", "")
            from nassav.library_models import ResourcePoolEntry
            from nassav.library_membership import LibraryNotFound

            if ResourcePoolEntry.objects.filter(
                canonical_avid=str(avid).strip().upper(), is_available=False
            ).exists():
                raise LibraryNotFound("Object not available")
        return True
    role = account(user)
    if role is None:
        return False
    name = type(view).__name__
    if name in ADMIN_VIEWS:
        if name in {
            "SourceCookieView",
            "ResourceView",
            "RefreshResourceView",
            "DeleteResourceView",
            "ResourcesBatchView",
            "ResourceJobView",
            "ResourceJobBatchView",
            "DownloadView",
            "DownloadsBatchSubmitView",
            "MockDownloadView",
        }:
            return False  # Managed writes wait for scoped credentials/shared-work protocols.
        return role.role == "admin"
    if name in RESOURCE_VIEWS:
        avid = view.kwargs.get("avid") or request.query_params.get("avid", "")
        if not can_read_resource(
            user,
            str(avid).strip().upper(),
            administrative=(name != "ResourceStatusView"),
        ):
            from nassav.library_membership import LibraryNotFound

            raise LibraryNotFound("Object not available")
        return True
    if name == "ActorAvatarView":
        from nassav.models import Actor
        from nassav.library_membership import LibraryNotFound

        actor = Actor.objects.filter(
            pk=view.kwargs.get("actor_id"), resources__pk__in=own_resource_ids(user.pk)
        ).first()
        if actor is None:
            raise LibraryNotFound("Avatar not available")
    if name == "ResourceJobStatusView":
        from nassav.task_models import TaskAttempt
        from nassav.library_membership import LibraryNotFound

        attempts = TaskAttempt.objects.filter(
            pk=view.kwargs.get("task_id"), job__kind="scrape"
        )
        if role.role != "admin":
            attempts = attempts.filter(job__owner_id=user.pk)
        if not attempts.exists():
            raise LibraryNotFound("Unowned legacy snapshot not available")
    if name in {"PlaybackProgressClaimView", "PlaybackRefreshView"}:
        from nassav.playback.models import PlaybackSession
        from nassav.library_membership import LibraryNotFound

        session = (
            PlaybackSession.objects.filter(
                pk=view.kwargs.get("session_id"), user_id=user.pk
            )
            .select_related("resource")
            .first()
        )
        if session is None or not can_read_resource(user, session.resource.avid):
            raise LibraryNotFound("Playback object not available")
    return name in READ_VIEWS
