#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数据域归一 SSOT（Single Source of Truth）

背景
----
`traffic` 域自 v4.10.0 起废弃并入 `analytics`，但仓库里一直散落着三套写法：

1. **白名单仍把 traffic 当合法域** —— `modules/core/validators.py`、
   `modules/core/file_naming.py` 各自维护一份字面量集合；
2. **配置字典里 traffic 与 analytics 各写一份** —— `data_standardizer.py`、
   `event_listeners.py`、`deduplication_fields_config.py` 三处都有两份条目，
   内容还互不相同（有的多一个字段、有的少两个刷新目标）；
3. **采集侧把 analytics 反向转回 traffic** —— `collection_center/app.py`
   里 `analytics -> traffic`，使新采集的文件又被写回已废弃的域名。

结果是同一个业务域在不同链路上被当成两个域：统计口径漂移、白名单与实际写入不一致、
`data_domain` 字段在库里出现历史遗留值。

本模块是数据域的唯一裁决点
--------------------------
- ``DataDomain``：canonical 域枚举
- ``CANONICAL_DATA_DOMAINS``：当前唯一合法的数据域集合（**白名单只允许用这个**）
- ``LEGACY_DATA_DOMAIN_ALIASES``：历史别名 → canonical 的映射
- ``normalize_data_domain()``：大小写归一 + 别名归一
- ``is_valid_data_domain()``：归一后是否落在 canonical 集合内

约定
----
- **写**只允许 canonical 值；
- **读**历史文件 / 历史库表时允许别名，归一后再用（生产环境磁盘上可能仍有
  ``__traffic__`` 命名的历史文件，不能因此拒绝登记）；
- 别名只增不删 —— 废弃一个域时把别名指向新域即可，历史数据自动被归一。
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, Final, FrozenSet, Optional

__all__ = [
    "DataDomain",
    "CANONICAL_DATA_DOMAINS",
    "LEGACY_DATA_DOMAIN_ALIASES",
    "normalize_data_domain",
    "canonicalize_data_domain",
    "is_valid_data_domain",
    "is_canonical_data_domain",
    "data_domain_tokens",
    "data_domain_tokens_for",
]


class DataDomain(str, Enum):
    """canonical 数据域枚举。

    使用 ``str`` 继承以便直接与字符串比较（历史代码大量用 ``== "analytics"`` 判断）。
    """

    ANALYTICS = "analytics"   # 流量/客流表现（v4.10.0 起吸收已废弃的 traffic 域）
    PRODUCTS = "products"     # 商品表现
    ORDERS = "orders"         # 订单表现
    SERVICES = "services"     # 服务表现
    FINANCE = "finance"       # 财务/结算表现
    INVENTORY = "inventory"   # 库存表现
    PURCHASE = "purchase"     # 采购单（v4.20.0+）

    def __str__(self) -> str:  # pragma: no cover - 仅便于日志输出
        return self.value


#: 当前唯一合法的数据域集合 —— 任何白名单都必须从这里取，不要再写字面量
CANONICAL_DATA_DOMAINS: Final[FrozenSet[str]] = frozenset(
    domain.value for domain in DataDomain
)

#: 历史别名 → canonical 域。只用于**读**历史数据的兼容，写入一律用 canonical 值。
LEGACY_DATA_DOMAIN_ALIASES: Final[Dict[str, str]] = {
    # v4.10.0：traffic 域废弃，统一并入 analytics
    "traffic": DataDomain.ANALYTICS.value,
}


def normalize_data_domain(domain: Optional[str]) -> str:
    """归一数据域：去空白 → 小写 → 别名映射。

    未知域**原样返回（小写）**，不抛错也不置空 —— 调用方通常还要用它做日志和
    「跳过无效数据域」的判断，抹成空串会丢诊断信息。是否合法由
    :func:`is_valid_data_domain` 判断。

    Examples
    --------
    >>> normalize_data_domain(" Traffic ")
    'analytics'
    >>> normalize_data_domain("ANALYTICS")
    'analytics'
    >>> normalize_data_domain("unknown_domain")
    'unknown_domain'
    >>> normalize_data_domain(None)
    ''
    """
    if not domain:
        return ""
    key = str(domain).strip().lower()
    if not key:
        return ""
    return LEGACY_DATA_DOMAIN_ALIASES.get(key, key)


def canonicalize_data_domain(domain: Optional[str]) -> Optional[str]:
    """归一数据域并要求结果必须是 canonical 域，否则返回 ``None``。

    与 :func:`normalize_data_domain` 的区别：未知域会被丢弃（返回 ``None``），
    适合「必须落库到合法域」的写入路径。
    """
    normalized = normalize_data_domain(domain)
    if normalized in CANONICAL_DATA_DOMAINS:
        return normalized
    return None


def is_valid_data_domain(domain: Optional[str]) -> bool:
    """判断数据域是否有效（先归一别名，再看是否落在 canonical 集合内）。

    ``is_valid_data_domain("traffic")`` 返回 ``True`` —— traffic 是 analytics 的
    历史别名，归一后是合法域；调用方应当使用 :func:`normalize_data_domain`
    取到的 canonical 值继续处理。
    """
    return normalize_data_domain(domain) in CANONICAL_DATA_DOMAINS


def is_canonical_data_domain(domain: Optional[str]) -> bool:
    """判断数据域**本身就是** canonical 域（不做别名归一）。

    用于「这个值已经是最终形态吗」的自检，例如校验新写入的数据。
    """
    if not domain:
        return False
    return str(domain).strip().lower() in CANONICAL_DATA_DOMAINS


def data_domain_tokens() -> tuple:
    """返回文件名 / 路径关键字匹配时可用的全部域 token（canonical + 历史别名）。

    扫描器需要在历史文件（``shopee_traffic_monthly_*.xlsx``）里认出域，
    但白名单只认 canonical —— 两者必须区分开，否则历史文件会被当成非法域丢弃。
    """
    return tuple(sorted(CANONICAL_DATA_DOMAINS | set(LEGACY_DATA_DOMAIN_ALIASES)))


def data_domain_tokens_for(domain: Optional[str]) -> tuple:
    """返回指定 canonical 域的全部可识别 token（自身 + 指向它的历史别名）。

    ``data_domain_tokens_for("analytics")`` → ``('analytics', 'traffic')``

    用于「从文件名/路径判断这个文件是不是某域」的兜底识别：既认新命名，
    也认历史别名，且不会把别的域的别名误算进来。
    """
    canonical = canonicalize_data_domain(domain)
    if canonical is None:
        return ()
    aliases = tuple(
        sorted(alias for alias, target in LEGACY_DATA_DOMAIN_ALIASES.items() if target == canonical)
    )
    return (canonical, *aliases)
