from __future__ import annotations

from typing import Dict


_ALIASES: dict[tuple[str, str, str], dict[str, str]] = {}


def get_header_alias_mapping(platform: str, data_domain: str, granularity: str) -> Dict[str, str]:
    key = (
        str(platform or "").strip().lower(),
        str(data_domain or "").strip().lower(),
        str(granularity or "").strip().lower(),
    )
    return dict(_ALIASES.get(key, {}))
