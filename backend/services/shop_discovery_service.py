from __future__ import annotations


class ShopDiscoveryService:
    async def run_current_discovery(
        self,
        db,  # noqa: ANN001
        *,
        platform: str,
        main_account_id: str,
        request,  # noqa: ANN001
    ):
        raise NotImplementedError("current shop discovery is not implemented yet")


_shop_discovery_service: ShopDiscoveryService | None = None


def get_shop_discovery_service() -> ShopDiscoveryService:
    global _shop_discovery_service
    if _shop_discovery_service is None:
        _shop_discovery_service = ShopDiscoveryService()
    return _shop_discovery_service
