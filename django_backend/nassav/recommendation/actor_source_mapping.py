from nassav.models import ActorSourceMapping


class ActorSourceMappingService:
    def get_actor_source_mappings(
        self,
        *,
        actor_ids: list[int],
        source_name: str,
        active_only: bool = True,
    ) -> dict[int, ActorSourceMapping]:
        normalized_source = str(source_name or "").strip().lower()
        if not actor_ids or not normalized_source:
            return {}

        queryset = ActorSourceMapping.objects.filter(
            actor_id__in=actor_ids,
            source_name=normalized_source,
        )
        if active_only:
            queryset = queryset.filter(is_active=True)

        output: dict[int, ActorSourceMapping] = {}
        for mapping in queryset:
            actor_pk = getattr(mapping, "actor_id", None)
            if actor_pk is None:
                continue
            output[int(actor_pk)] = mapping
        return output


actor_source_mapping_service = ActorSourceMappingService()
