from __future__ import annotations

from typing import Dict, Optional, Tuple


_SHOPEE_PRODUCTS_STATUS_ALIASES = {
    "销售额（已确认订单）": "销售额（已付款订单）",
    "销售额（已确定订单）": "销售额（已付款订单）",
    "订单转化率（已确认订单）": "订单转化率（已付款订单）",
    "订单转化率（已确定订单）": "订单转化率（已付款订单）",
    "已确认订单": "已付款订单",
    "已确定订单": "已付款订单",
    "件数（已确认订单）": "件数（已付款订单）",
    "件数（已确定订单）": "件数（已付款订单）",
    "买家数（已确认订单）": "买家数（已付款订单）",
    "买家数（已确定订单）": "买家数（已付款订单）",
    "转化率（已确认订单）": "转化率（已付款订单）",
    "转化率（已确定订单）": "转化率（已付款订单）",
    "每笔订单销售额（已确认订单）": "每笔订单销售额（已付款订单）",
    "每笔订单销售额（已确定订单）": "每笔订单销售额（已付款订单）",
    "订单复购率（已确认订单）": "订单复购率（已付款订单）",
    "订单复购率（已确定订单）": "订单复购率（已付款订单）",
    "订单复购的平均天数（已确认订单）": "订单复购的平均天数（已付款订单）",
    "订单复购的平均天数（已确定订单）": "订单复购的平均天数（已付款订单）",
}


# 别名登记表
# -------------
# 键 = (platform, data_domain, granularity) 或 (platform, data_domain, granularity, account)
#
# 用途: 不同地区/店铺的导出报表, 同一个业务指标可能用不同表头
# (例如 A 地区叫「销售额」, B 地区叫「销售金额」)。
# 登记别名后, 表头比对前会先做一次改名归一 —— 这样**不必**为每个地区发一版模板,
# 文件就能正常入库(判定为 alias_only, 不提示更新模板)。
#
# 账号维度(account)的别名优先级高于通用别名:
# 先应用通用别名, 再应用账号专属别名(后者覆盖前者)。
_ALIASES: Dict[Tuple[str, ...], Dict[str, str]] = {
    ("shopee", "products", "daily"): dict(_SHOPEE_PRODUCTS_STATUS_ALIASES),
    ("shopee", "products", "weekly"): dict(_SHOPEE_PRODUCTS_STATUS_ALIASES),
    ("shopee", "products", "monthly"): dict(_SHOPEE_PRODUCTS_STATUS_ALIASES),
}


def _normalize(value: Optional[str]) -> str:
    return str(value or "").strip().lower()


def get_header_alias_mapping(
    platform: str,
    data_domain: str,
    granularity: str,
    account: Optional[str] = None,
) -> Dict[str, str]:
    """取表头别名映射。

    Args:
        platform: 平台代码
        data_domain: 数据域
        granularity: 粒度
        account: 账号/地区维度(可选)。给出时会**叠加**账号专属别名,
            覆盖同名的通用别名 —— 不同地区的表头差异可以被单独登记。
    """
    base = (
        _normalize(platform),
        _normalize(data_domain),
        _normalize(granularity),
    )
    mapping: Dict[str, str] = dict(_ALIASES.get(base, {}))

    normalized_account = _normalize(account)
    if normalized_account:
        scoped = _ALIASES.get((*base, normalized_account))
        if scoped:
            mapping.update(scoped)

    return mapping
