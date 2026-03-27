from __future__ import annotations

"""Stable runtime wrapper for Miaoshou login v1.0.3."""

from modules.platforms.miaoshou.components.login import MiaoshouLogin as CanonicalMiaoshouLogin


class MiaoshouLogin(CanonicalMiaoshouLogin):
    """Versioned runtime alias over the canonical V2 Miaoshou login."""

    pass
