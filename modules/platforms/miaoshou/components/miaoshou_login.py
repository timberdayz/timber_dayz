from __future__ import annotations

"""Compatibility wrapper for legacy recorder-era Miaoshou login imports."""

from modules.platforms.miaoshou.components.login import MiaoshouLogin


class MiaoshouMiaoshouLogin(MiaoshouLogin):
    """Legacy compatibility alias over the canonical V2 Miaoshou login."""

    pass
