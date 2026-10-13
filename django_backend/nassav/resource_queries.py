"""Django resource listing query and pagination."""

from django.core.paginator import Paginator
from django.db.models import Q


def list_resources(params, *, user_id=None):
    """Return (objects, pagination) for resources list based on params dict/querydict.

    Supported params: file_exists (true/false), source (comma separated), ordering,
    page, page_size.
    """
    from nassav.models import AVResource

    from nassav.personal_state import project_personal_state

    qs = project_personal_state(AVResource.objects.all(), user_id)

    # 优化查询：预加载关联对象，避免 N+1 查询问题
    qs = qs.prefetch_related("genres")

    # support status: downloaded/pending/all (alias to file_exists)
    status = params.get("status")
    if status:
        s = str(status).lower()
        if s == "downloaded":
            qs = qs.filter(file_exists=True)
        elif s == "pending":
            qs = qs.filter(file_exists=False)

    # legacy/file_exists parameter (boolean-like)
    fe = params.get("file_exists")
    if fe is not None:
        if str(fe).lower() in ("1", "true", "yes"):
            qs = qs.filter(file_exists=True)
        else:
            qs = qs.filter(file_exists=False)

    source = params.get("source")
    if source:
        sources = [s.strip() for s in str(source).split(",") if s.strip()]
        qs = qs.filter(source__in=sources)

    # filter by actor (accept actor id or name fragment)
    actor = params.get("actor")
    if actor:
        try:
            aid = int(actor)
            qs = qs.filter(actors__id=aid)
        except Exception:
            a = str(actor).strip()
            if a:
                qs = qs.filter(actors__name__icontains=a)
        qs = qs.distinct()

    # filter by genre (accept genre id or name fragment)
    genre = params.get("genre")
    if genre:
        try:
            gid = int(genre)
            qs = qs.filter(genres__id=gid)
        except Exception:
            g = str(genre).strip()
            if g:
                qs = qs.filter(genres__name__icontains=g)
        qs = qs.distinct()

    # filter by watched status
    watched = params.get("watched")
    if watched is not None:
        if str(watched).lower() in ("1", "true", "yes"):
            qs = qs.filter(personal_watched=True)
        elif str(watched).lower() in ("0", "false", "no"):
            qs = qs.filter(personal_watched=False)

    # filter by favorite status
    is_favorite = params.get("is_favorite")
    if is_favorite is not None:
        if str(is_favorite).lower() in ("1", "true", "yes"):
            qs = qs.filter(personal_is_favorite=True)
        elif str(is_favorite).lower() in ("0", "false", "no"):
            qs = qs.filter(personal_is_favorite=False)

    # search in title fields (original_title, source_title, translated_title)
    search = params.get("search")
    if search:
        search_term = str(search).strip()
        if search_term:
            # 使用Q对象进行多字段搜索，不区分大小写
            qs = qs.filter(
                Q(original_title__icontains=search_term)
                | Q(source_title__icontains=search_term)
                | Q(translated_title__icontains=search_term)
            )

    ordering = params.get("ordering")
    if ordering:
        # 当按 video_saved_at 排序时，只返回已下载的视频
        # 避免返回 video_saved_at 为 NULL 的未下载资源
        if "video_saved_at" in ordering:
            qs = qs.filter(file_exists=True, video_saved_at__isnull=False)
        qs = qs.order_by(ordering)

    # pagination
    try:
        page = int(params.get("page", 1))
    except Exception:
        page = 1
    try:
        page_size = int(params.get("page_size", 20))
    except Exception:
        page_size = 20

    paginator = Paginator(qs, page_size)
    page_obj = paginator.get_page(page)

    return page_obj.object_list, {
        "total": paginator.count,
        "page": page_obj.number,
        "page_size": page_size,
        "pages": paginator.num_pages,
    }
