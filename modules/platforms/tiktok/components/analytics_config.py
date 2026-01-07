"""TikTok Analytics (traffic) selectors and deep-link paths.

- 仅维护路径与选择器常量，无副作用
- BASE_URL 统一从此处读取，业务层禁止硬编码域名
- 注意：TikTok 流量（Analytics）页面在深链接上不应附带 timeRange/shortcut；
  否则导出按钮可能不出现。应仅携带 shop_region，通过页面内日期控件选择时间。
"""
from __future__ import annotations

from typing import ClassVar, Sequence


class AnalyticsSelectors:
    """Selectors and paths for TikTok traffic overview page."""

    # Deep-link base
    BASE_URL: ClassVar[str] = "https://seller.tiktokshopglobalselling.com"

    # Path only; do not hardcode domain in business code
    TRAFFIC_PATH: ClassVar[str] = "/compass/data-overview"

    # Probes to confirm page ready (minimal; to be refined)
    DATA_READY_PROBES: ClassVar[Sequence[str]] = (
        "[data-testid*='traffic']",
        "[role='grid'], table",
    )

    # Primary export button candidates
    EXPORT_BUTTON_SELECTORS: ClassVar[Sequence[str]] = (
        "button:has-text('Export')",
        "button:has-text('导出')",
        "[data-testid*='export']",
    )

    # Latest-download candidates (if platform provides recent exports panel)
    DOWNLOAD_BUTTON_SELECTORS: ClassVar[Sequence[str]] = (
        "button:has-text('Download')",
        "button:has-text('下载')",
        "[data-testid*='download']",
    )

