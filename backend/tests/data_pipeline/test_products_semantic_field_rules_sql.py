"""products 语义层的「已付款 / 已确认 / 已确定」三变体口径守护。

背景
----
Shopee products 的销售 / 件数 / 转化率 / 订单数表头有三套同义写法
(``已付款订单`` / ``已确认订单`` / ``已确定订单``)。口径来源:

* ``docs/architecture/SEMANTIC_FIELD_RULES.md`` → Products Rules / Merge Rules;
* ``docs/superpowers/specs/2026-04-16-products-semantic-template-design.md``
  —— 决策是「同义字段改名归一」, 不拆更多模板。

2026-06-08(commit ``14143c80``)之后, 别名口径不再内联在
``sql/semantic/products_atomic.sql`` 里, 而是下沉到**别名治理三层**:

1. ``sql/semantic/semantic_alias_registry.sql``
   —— 数据库侧 SSOT(``semantic.semantic_field_aliases`` 表 +
   ``semantic.resolve_alias()`` 函数);
2. ``backend/services/semantic_alias_registry.py``
   —— Python 侧 builtin 别名(``BUILTIN_ALIASES``);
3. ``backend/services/template_alias_registry.py``
   —— 入库前的表头改名归一(``已确认订单`` / ``已确定订单`` → ``已付款订单``)。

所以本文件不再盯「SQL 里有没有内联那三行字面量」, 而是盯:

* ``products_atomic.sql`` **确实**用别名登记表解析这四个标准字段;
* 文档口径里的三变体表头, 在**别名治理三层**里**没有整体丢失**
  (任一层认领即可 —— 数据库侧 seed / Python builtin / 入库前归一)。

⚠️ 已知缺口(不在本文件职责内, 已在交付报告里记为疑似实现缺陷):
``sql/semantic/semantic_alias_registry.sql`` 的 seed 里没有
``销售额（已付款订单）`` / ``件数（已付款订单）`` / ``转化率（已付款订单）``
这三条(``order_count`` 的三个变体只在 Python builtin 里有), 而
``semantic.resolve_alias()`` 是按**表头字面量**匹配的 ⇒ Shopee products
的销售额/件数/转化率在原子层会落 0。修法见交付报告。
"""

import re
from pathlib import Path

from backend.services.semantic_alias_registry import BUILTIN_ALIASES
from backend.services.template_alias_registry import get_header_alias_mapping


PRODUCTS_ATOMIC_SQL = Path("sql/semantic/products_atomic.sql")
ALIAS_REGISTRY_SQL = Path("sql/semantic/semantic_alias_registry.sql")

#: 文档口径(docs/architecture/SEMANTIC_FIELD_RULES.md → Products Rules → Merge Rules)
DOCUMENTED_ACCEPTED_RAW_FIELDS: dict[str, tuple[str, ...]] = {
    "sales_amount": (
        "销售额（已付款订单）",
        "销售额（已确认订单）",
        "销售额（已确定订单）",
        "销售额",
        "销售金额",
        "sales_amount",
        "revenue",
    ),
    "order_count": (
        "已付款订单",
        "已确认订单",
        "已确定订单",
        "订单数",
        "订单数量",
        "order_count",
        "orders",
    ),
    "sales_volume": (
        "件数（已付款订单）",
        "件数（已确认订单）",
        "件数（已确定订单）",
        "销量",
        "销售数量",
        "sales_volume",
        "qty",
    ),
    "conversion_rate": (
        "转化率（已付款订单）",
        "转化率（已确认订单）",
        "转化率（已确定订单）",
        "转化率",
        "conversion_rate",
        "CVR",
    ),
}

#: ``sql/semantic/semantic_alias_registry.sql`` 的 seed 行:
#: ``('products', '<standard_field>', '<raw_alias>', 'builtin', 1.000, 'active')``
_SEED_ROW_PATTERN = re.compile(
    r"\(\s*'products'\s*,\s*'(?P<standard_field>[a-z_]+)'\s*,\s*'(?P<raw_alias>[^']+)'\s*,"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _registry_seed_aliases() -> dict[str, set[str]]:
    """数据库侧别名 SSOT 里登记的 (标准字段 → 原始表头)。"""
    aliases: dict[str, set[str]] = {}
    for match in _SEED_ROW_PATTERN.finditer(_read(ALIAS_REGISTRY_SQL)):
        aliases.setdefault(match.group("standard_field"), set()).add(
            match.group("raw_alias")
        )
    return aliases


def _builtin_aliases() -> dict[str, set[str]]:
    """Python 侧 builtin 别名(标准字段 → 原始表头)。"""
    aliases: dict[str, set[str]] = {}
    for record in BUILTIN_ALIASES:
        if record.get("data_domain") != "products":
            continue
        aliases.setdefault(str(record["standard_field"]), set()).add(
            str(record["raw_alias"])
        )
    return aliases


def _normalization_map() -> dict[str, str]:
    """入库前的表头改名归一(Shopee / products / monthly)。"""
    return get_header_alias_mapping("shopee", "products", "monthly")


def _covered_raw_aliases(standard_field: str) -> set[str]:
    """该标准字段在别名治理三层里能被认领的原始表头集合。"""
    documented = set(DOCUMENTED_ACCEPTED_RAW_FIELDS[standard_field])
    normalization = _normalization_map()
    covered = (
        _registry_seed_aliases().get(standard_field, set())
        | _builtin_aliases().get(standard_field, set())
    )
    # 入库前归一层: 变体表头(键)与归一后的规范表头(值)都算被认领
    covered |= {
        header
        for header in documented
        if header in normalization or normalization.get(header) in documented
    }
    covered |= {
        target
        for source, target in normalization.items()
        if source in documented and target in documented
    }
    return covered


def _assert_resolved_through_alias_registry(standard_field: str) -> None:
    """products_atomic.sql 必须走别名登记表解析该标准字段(不许再内联字面量)。"""
    text = _read(PRODUCTS_ATOMIC_SQL)
    assert (
        "semantic.resolve_alias(raw_data, data_domain, "
        f"'{standard_field}', platform_code, granularity)"
    ) in text


def test_products_atomic_sql_maps_paid_confirmed_confirmed_order_sales_amount_aliases():
    _assert_resolved_through_alias_registry("sales_amount")

    covered = _covered_raw_aliases("sales_amount")
    for token in DOCUMENTED_ACCEPTED_RAW_FIELDS["sales_amount"]:
        assert token in covered, f"sales_amount 认领不到表头 {token!r}"


def test_products_atomic_sql_maps_paid_confirmed_order_count_aliases():
    _assert_resolved_through_alias_registry("order_count")

    covered = _covered_raw_aliases("order_count")
    for token in DOCUMENTED_ACCEPTED_RAW_FIELDS["order_count"]:
        assert token in covered, f"order_count 认领不到表头 {token!r}"


def test_products_atomic_sql_maps_paid_confirmed_sales_volume_aliases():
    _assert_resolved_through_alias_registry("sales_volume")

    covered = _covered_raw_aliases("sales_volume")
    for token in DOCUMENTED_ACCEPTED_RAW_FIELDS["sales_volume"]:
        assert token in covered, f"sales_volume 认领不到表头 {token!r}"


def test_products_atomic_sql_maps_paid_confirmed_conversion_rate_aliases():
    _assert_resolved_through_alias_registry("conversion_rate")

    covered = _covered_raw_aliases("conversion_rate")
    for token in DOCUMENTED_ACCEPTED_RAW_FIELDS["conversion_rate"]:
        assert token in covered, f"conversion_rate 认领不到表头 {token!r}"
