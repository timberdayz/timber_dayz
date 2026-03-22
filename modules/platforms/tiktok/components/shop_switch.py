from __future__ import annotations

"""Canonical shop switch entry for TikTok platform components.

This file exists to align the user-facing logical component name with the
current collection rules (`shop_switch`) while retaining compatibility with the
existing `shop_selector` implementation.
"""

from modules.platforms.tiktok.components.shop_selector import TiktokShopSelector


class TiktokShopSwitch(TiktokShopSelector):
    """Canonical compatibility wrapper over the existing TikTok shop selector."""

    platform = "tiktok"
    component_type = "shop_switch"
    data_domain = None
