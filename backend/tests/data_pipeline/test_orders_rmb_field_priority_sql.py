"""orders 域取数的「人民币口径优先」守护。

[*] 2026-11-08: 取数链已从**手写 COALESCE 链**改成
``semantic.resolve_alias(...)``(别名表是取数的单一事实源)。旧断言盯的是
「COALESCE 链里 (RMB) 排在裸名前面」, 新实现下这层顺序**不存在了**
⇒ 改成盯两件等价且更强的事:

1. 取数**只**走别名表(视图里不许再内联字面量取金额);
2. 字典侧 orders 域**只登记 (RMB) 变体** —— 裸名(原币列)不在别名里
   ⇒ ``resolve_alias`` 逐字匹配时永远命中不到原币列。

metabase 模型(``sql/metabase_models/orders_model.sql``)也在 B1 里切到了
``semantic.resolve_alias`` ⇒ 那条盯「手写链里 (RMB) 排在裸名前」的用例
失去对象 ⇒ 改成盯**等价且更强**的事实: metabase 取数也只走别名表。
"""

from pathlib import Path


def _resolve_alias_call(field: str) -> str:
    return (
        "semantic.resolve_alias(raw_data, data_domain, "
        f"'{field}', platform_code, granularity)"
    )


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="replace")


def test_orders_atomic_sql_resolves_amounts_through_alias_registry():
    sql_text = _read("sql/semantic/orders_atomic.sql")

    for field in ("paid_amount", "profit", "platform_commission"):
        assert _resolve_alias_call(field) in sql_text, f"{field} 没走别名表"


def test_orders_atomic_sql_never_reads_raw_currency_columns_directly():
    """裸名(原币列)不许出现在取数表达式里。"""
    sql_text = _read("sql/semantic/orders_atomic.sql")

    for raw_header in ("利润", "买家支付", "仓库操作费", "订单原始金额"):
        assert (
            f"raw_data->>'{raw_header}'" not in sql_text
        ), f"取数仍在直读裸名列 {raw_header!r}(原币列)"


def test_orders_alias_table_only_registers_rmb_variants():
    """字典侧: orders 域只登 (RMB) 变体, 裸名(原币列)不在别名里。"""
    from backend.services.semantic_field_registry import (
        ORDER_PLATFORM_ALIASES,
        ORDER_SEMANTIC_ALIASES,
    )

    profit_aliases = ORDER_SEMANTIC_ALIASES["profit"]
    assert "利润(RMB)" in profit_aliases
    assert "利润" not in profit_aliases

    # paid_amount 是**平台维度**别名(两个平台列名不同)。
    for platform in ("shopee", "tiktok"):
        aliases = ORDER_PLATFORM_ALIASES[platform]["paid_amount"]
        assert all(
            alias.endswith("(RMB)") for alias in aliases
        ), f"{platform} 的 paid_amount 别名混进了非人民币列: {aliases}"
    assert "买家支付" not in ORDER_PLATFORM_ALIASES["shopee"]["paid_amount"]
    assert "买家实付金额" not in ORDER_PLATFORM_ALIASES["tiktok"]["paid_amount"]


def test_orders_monthly_atomic_sql_resolves_amounts_through_alias_registry():
    sql_text = _read("sql/semantic/orders_monthly_atomic_mv.sql")

    for field in ("paid_amount", "profit"):
        assert _resolve_alias_call(field) in sql_text, f"{field} 没走别名表"


def test_orders_model_sql_resolves_amounts_through_alias_registry():
    """metabase 模型取数**只**走别名表, 不再内联字面量金额。"""
    sql_text = _read("sql/metabase_models/orders_model.sql")

    for field in ("paid_amount", "profit", "platform_commission"):
        assert _resolve_alias_call(field) in sql_text, f"{field} 没走别名表"

    for raw_header in ("profit_rmb", "profit", "买家支付"):
        assert (
            f"raw_data->>'{raw_header}'" not in sql_text
        ), f"metabase 取数仍在直读字面量列 {raw_header!r}"
