from __future__ import annotations

from typing import Dict


_ALIASES: dict[tuple[str, str, str], dict[str, str]] = {
    ("tiktok", "orders", "monthly"): {
        "TikTok Shop平台佣金": "TikTok 平台佣金",
        "TikTok Shop平台佣金(RMB)": "TikTok 平台佣金(RMB)",
        "TikTok Shop平台折扣": "TikTok 平台折扣",
        "TikTok Shop平台折扣(RMB)": "TikTok 平台折扣(RMB)",
        "TikTok Shop 运费折扣": "TikTok 运费折扣",
        "TikTok Shop 运费折扣(RMB)": "TikTok 运费折扣(RMB)",
        "马来西亚税费SST": "SST",
        "马来西亚税费SST(RMB)": "SST(RMB)",
    }
}


def get_header_alias_mapping(platform: str, data_domain: str, granularity: str) -> Dict[str, str]:
    key = (
        str(platform or "").strip().lower(),
        str(data_domain or "").strip().lower(),
        str(granularity or "").strip().lower(),
    )
    return dict(_ALIASES.get(key, {}))
