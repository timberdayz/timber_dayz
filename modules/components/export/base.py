from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional
from pathlib import Path

from modules.components.base import ComponentBase, ResultBase


class ExportMode(str, Enum):
    STANDARD = "standard"
    RECORD = "record"
    COMPARE = "compare"


@dataclass
class ExportResult(ResultBase):
    file_path: Optional[str] = None


def build_standard_output_root(
    ctx, data_type: str, granularity: str, *, subtype: str | None = None
) -> Path:
    """Compute the unified output directory for any exporter.

    Path shape:
      temp/outputs/<platform>/<account>/<shop>[__shop_id]/<data_type>/<subtype?>/<granularity>

    Notes:
    - include_shop_id is read from config and defaults to True in new architecture
    - Resolves account_label/shop_name/shop_id using robust fallbacks
    """
    # Local imports to avoid side-effects at import time
    from modules.core.config import get_config_value
    from modules.utils.path_sanitizer import build_output_path

    account = (ctx.account or {}) if hasattr(ctx, "account") else {}
    cfg = (ctx.config or {}) if hasattr(ctx, "config") else {}

    account_label = (
        account.get("label")
        or account.get("store_name")
        or account.get("username")
        or "unknown"
    )
    # 优先使用运行上下文的 shop_name（来自店铺选择器），其后才回退到账号级别名称
    shop_name = (
        cfg.get("shop_name")
        or account.get("menu_display_name")
        or account.get("menu_name")
        or account.get("selected_shop_name")
        or account.get("display_shop_name")
        or account.get("display_name")
        or account.get("store_name")
        or "unknown_shop"
    )
    shop_id = (
        cfg.get("shop_id")
        or account.get("shop_id")
        or account.get("cnsc_shop_id")
    )
    # 平台特例：TikTok 仅在明确识别到店铺代码时才追加 shop_id；不要回退到 account_id，避免出现“__账号标签”
    platform_name = str(getattr(ctx, "platform", "")).lower()
    if not shop_id and platform_name != "tiktok":
        shop_id = account.get("account_id")
    include_shop_id = get_config_value(
        "data_collection", "path_options.include_shop_id", True
    )

    return build_output_path(
        root=Path("temp/outputs"),
        platform=getattr(ctx, "platform", "unknown"),
        account_label=account_label,
        shop_name=shop_name,
        data_type=data_type,
        granularity=granularity,
        shop_id=shop_id,
        include_shop_id=include_shop_id,
        subtype=subtype,
    )


class ExportComponent(ComponentBase):
    def run(self, page: Any, mode: ExportMode = ExportMode.STANDARD) -> ExportResult:  # type: ignore[override]
        raise NotImplementedError

