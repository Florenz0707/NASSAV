"""Pure source title normalization shared by lookup and persistence."""


def normalize_source_title(avid: str, source_title: str) -> str:
    """规范化 source_title，确保以 AVID 开头

    Args:
        avid: 资源编号
        source_title: 原始标题

    Returns:
        规范化后的标题（以 AVID 开头）
    """
    if not source_title:
        return source_title

    avid_upper = avid.upper()
    # 检查标题是否已经以 AVID 开头（不区分大小写）
    if not source_title.upper().startswith(avid_upper):
        return f"{avid_upper} {source_title}"
    return source_title
