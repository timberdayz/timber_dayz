from pydantic import BaseModel


class ShopDirectoryItemResponse(BaseModel):
    platform_code: str
    shop_id: str
    shop_account_id: str
    main_account_id: str
    display_name: str
    canonical_name: str
    account_alias: str | None = None
    shop_region: str | None = None
    enabled: bool
