"""Canonical provider registration and origin defaults; no network construction."""

from typing import TYPE_CHECKING, TypedDict, cast

from nassav.source_credentials import origin_host

if TYPE_CHECKING:
    from nassav.source.SourceBase import SourceBase
    from nassav.source.Jable import Jable
    from nassav.source.MissAV import MissAV
    from nassav.source.Memo import Memo


class SourceProviders(TypedDict):
    missav: "type[MissAV]"
    jable: "type[Jable]"
    memo: "type[Memo]"


def source_provider_types() -> SourceProviders:
    from nassav.source.Jable import Jable
    from nassav.source.Memo import Memo
    from nassav.source.MissAV import MissAV

    return {"missav": MissAV, "jable": Jable, "memo": Memo}


def configured_source_origins(config):
    return {
        name: origin_host(
            config.get(name, {}).get(
                "domain", cast("type[SourceBase]", provider).DEFAULT_DOMAIN
            )
        )
        for name, provider in source_provider_types().items()
    }
