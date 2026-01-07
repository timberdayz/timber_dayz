from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional
import re
import unicodedata

__all__ = [
    "safe_slug",
    "build_output_path",
    "build_filename",
]


def safe_slug(s: str) -> str:
    """Normalize a string for filesystem-safe usage.

    Rules:
    - NFKD decompose and strip diacritics
    - NFKC normalize (half/full width unify)
    - lowercase
    - keep letters/digits and "-_."; others -> "_"
    - collapse multiple underscores
    - strip leading/trailing dots/underscores
    """
    s_norm = unicodedata.normalize("NFKD", s or "")
    s_noacc = "".join(c for c in s_norm if not unicodedata.combining(c))
    s_kc = unicodedata.normalize("NFKC", s_noacc)
    s_lower = s_kc.lower()
    mapped = [c if (c.isalnum() or c in "-_.") else "_" for c in s_lower]
    slug = "".join(mapped)
    slug = re.sub(r"_+", "_", slug)
    slug = slug.strip("._")
    return slug or "unknown"


def build_output_path(
    root: Path | str,
    platform: str,
    account_label: str,
    shop_name: str,
    data_type: str,
    granularity: str,
    shop_id: Optional[str] = None,
    include_shop_id: bool = False,
    subtype: Optional[str] = None,
) -> Path:
    """构建输出路径

    目录层级：
      <root>/<platform>/<account>/<shop>[__shop_id]/<data_type>/<subtype?>/<granularity>

    Args:
        root: 根目录
        platform: 平台名称
        account_label: 账号标签
        shop_name: 店铺名称
        data_type: 数据类型
        granularity: 粒度
        shop_id: 店铺ID（可选）
        include_shop_id: 是否在路径中包含shop_id（默认False，保持向后兼容）
        subtype: 子数据类型（如 services 下的 ai_assistant/agent），默认不添加该层
    """
    root_path = Path(root)

    # 构建店铺目录名：如果启用shop_id且提供了shop_id，则追加到店铺名后（两侧均做 slug 规范化）
    if include_shop_id and shop_id:
        shop_dir = f"{safe_slug(shop_name)}__{safe_slug(str(shop_id))}"
    else:
        shop_dir = safe_slug(shop_name)

    path = (
        root_path
        / platform
        / safe_slug(account_label)
        / shop_dir
        / data_type
    )
    if subtype:
        path = path / safe_slug(subtype)
    path = path / granularity
    return path


def build_filename(
    ts: Optional[str],
    account_label: str,
    shop_name: str,
    data_type: str,
    granularity: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    suffix: str = ".xlsx",
) -> str:
    """Build unified, Windows-safe filename.

    Format:
      {TS}__{account}__{shop}__{data_type}__{granularity}[__{start}_{end}]{suffix}

    Notes:
    - start_date/end_date may contain spaces/colons; normalize to YYYY-MM-DD_HHMMSS to be Windows-safe
    """
    ts_val = ts or datetime.now().strftime("%Y%m%d_%H%M%S")

    def _norm_date(s: Optional[str]) -> Optional[str]:
        if not s:
            return None
        # keep digits and dashes, convert space to underscore, drop colons/other
        s2 = s.replace(" ", "_").replace(":", "")
        return s2

    s_norm = _norm_date(start_date)
    e_norm = _norm_date(end_date)
    date_suffix = f"__{s_norm}_{e_norm}" if s_norm and e_norm else ""

    return (
        f"{ts_val}__{safe_slug(account_label)}__{safe_slug(shop_name)}__"
        f"{data_type}__{granularity}{date_suffix}{suffix}"
    )

