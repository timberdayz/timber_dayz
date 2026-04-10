from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from modules.apps.collection_center.popup_handler import UniversalPopupHandler


@dataclass
class OverlayGuard:
    """Thin compatibility wrapper around the shared safe-notice popup handler."""

    async def run(self, page: Any, *, label: Optional[str] = None) -> int:
        if label:
            print(label)
        return await UniversalPopupHandler().close_safe_notices(
            page,
            platform="miaoshou",
        )
