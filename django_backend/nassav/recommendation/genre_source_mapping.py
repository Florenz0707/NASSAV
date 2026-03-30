from nassav.models import GenreSourceMapping


class GenreSourceMappingService:
    def get_genre_source_mappings(
        self,
        *,
        genre_ids: list[int],
        source_name: str,
        active_only: bool = True,
    ) -> dict[int, GenreSourceMapping]:
        normalized_source = str(source_name or "").strip().lower()
        if not genre_ids or not normalized_source:
            return {}

        queryset = GenreSourceMapping.objects.filter(
            genre_id__in=genre_ids,
            source_name=normalized_source,
        )
        if active_only:
            queryset = queryset.filter(is_active=True)

        output: dict[int, GenreSourceMapping] = {}
        for mapping in queryset:
            genre_pk = getattr(mapping, "genre_id", None)
            if genre_pk is None:
                continue
            output[int(genre_pk)] = mapping
        return output


genre_source_mapping_service = GenreSourceMappingService()
