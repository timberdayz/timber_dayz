"""批次 F-3 护栏测试: 语义契约表的粒度补齐 + 「域级下限护栏」角色降级。

锁住四件事
----------

1. **粒度补齐不漂移** —— 迁移里给 ``orders/daily`` 与 ``analytics/weekly``
   补的行, 必须与代码里的常量兜底 :data:`DEFAULT_CONTRACTS` **逐条一致**。
   不一致 ⇒ 补齐前后判定行为变了(补齐本该是「行为不变」的纯数据搬运)。
2. **无契约域不引入新阻断** —— ``products`` / ``inventory`` / ``services``
   补的行**一律没有 required**。这三个域的文件列解析不出语义键 ⇒
   只要有 required 就会恒为 ``breaking_drift`` ⇒ 新增阻断。
3. **域级下限护栏口径** —— 契约的 required 降为「下限」:
   指标类不阻断, 身份/时间类仍阻断, 模板级清单 required 是主来源。
4. **迁移自包含** —— 迁移不能 import backend(否则迁移链在裸环境跑不动)。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from backend.services.semantic_field_contract_service import (
    DEFAULT_CONTRACTS,
    NON_BLOCKING_CONTRACT_KINDS,
    _semantic_kind,
)

REPO_ROOT = Path(__file__).resolve().parents[3]

MIGRATION_PATH = (
    REPO_ROOT
    / "current_migrations"
    / "versions"
    / "20261127_semantic_contract_backfill.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("_mig_20261127", MIGRATION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# 1) 粒度补齐不漂移
# ---------------------------------------------------------------------------


def test_migration_granularity_rows_match_default_contracts():
    """补齐的两个粒度, 行内容必须与常量兜底**逐条一致**。

    补齐的目的只是「不再依赖常量兜底」⇒ 行为必须一模一样。
    """
    module = _load_migration()

    def as_map(definitions):
        return {key: (importance, impact) for key, importance, impact in definitions}

    def as_default_map(domain):
        return {
            item.semantic_key: (item.importance, item.impact_description)
            for item in DEFAULT_CONTRACTS[domain]
        }

    assert as_map(module._ORDERS_CONTRACT) == as_default_map("orders")
    assert as_map(module._ANALYTICS_CONTRACT) == as_default_map("analytics")


def test_migration_covers_every_granularity_gap():
    """粒度缺口只有两个: orders/daily 与 analytics/weekly。"""
    module = _load_migration()

    plan = {
        (domain, granularity)
        for domain, granularity, _definitions in module._INSERT_PLAN
        if granularity is not None
    }

    assert plan == {("orders", "daily"), ("analytics", "weekly")}


# ---------------------------------------------------------------------------
# 2) 无契约域不引入新阻断
# ---------------------------------------------------------------------------


def test_no_contract_domains_have_no_required_rows():
    """products / inventory / services 补的行**一律没有 required**。

    这三个域的文件列解析不出语义键(域名限定别名表只覆盖 orders/analytics) ⇒
    只要有 required, 这些域就会恒为 breaking_drift ⇒ **新增阻断**。
    """
    module = _load_migration()

    for domain, granularity, definitions in module._INSERT_PLAN:
        if domain not in {"products", "inventory", "services"}:
            continue
        required = [
            key for key, importance, _impact in definitions if importance == "required"
        ]
        assert not required, f"{domain} 域补了 required 行: {required}"


def test_migration_covers_all_five_data_domains():
    """5 个数据域都要有契约(原来只有 2 个)。"""
    module = _load_migration()

    domains = {domain for domain, _g, _d in module._INSERT_PLAN}

    assert domains == {"orders", "analytics", "products", "inventory", "services"}


def test_migration_does_not_import_backend():
    """迁移必须自包含(不能 import backend.*)。"""
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "import backend" not in source
    assert "from backend" not in source


# ---------------------------------------------------------------------------
# 3) 域级下限护栏口径
# ---------------------------------------------------------------------------


def test_metric_keys_are_non_blocking_contract_kinds():
    """指标类属于「不阻断」那一类。"""
    for key in ["page_views", "visitor_count", "paid_amount", "sales_volume", "profit"]:
        assert _semantic_kind(key) == "metric"
        assert key not in _blocking_keys()


def _blocking_keys():
    """契约 required 里仍然阻断的键(= 非指标类)。"""
    blocking = []
    for domain, definitions in DEFAULT_CONTRACTS.items():
        for item in definitions:
            if item.importance != "required":
                continue
            if _semantic_kind(item.semantic_key) in NON_BLOCKING_CONTRACT_KINDS:
                continue
            blocking.append(item.semantic_key)
    return blocking


def test_identity_and_time_keys_still_block():
    """身份/时间类**仍然阻断** —— 降级只针对指标类。"""
    blocking = _blocking_keys()

    for key in ["order_id", "shop_id", "order_date", "metric_date"]:
        assert key in blocking, f"{key} 不该被降级成不阻断"


def test_contract_result_exposes_below_domain_floor_keys():
    """域级下限缺口要能被前端拿到(治理面板引导用户去勾)。"""
    from backend.services.semantic_field_contract_service import SemanticContractResult

    payload = SemanticContractResult(
        status="non_breaking_drift",
        should_block=False,
        below_domain_floor_keys=["paid_amount"],
    ).to_dict()

    assert payload["below_domain_floor_keys"] == ["paid_amount"]


@pytest.mark.asyncio
async def test_domain_floor_gap_does_not_block_but_is_visible():
    """域级下限缺口: 可见、不阻断。"""
    from backend.services.semantic_field_contract_service import (
        SemanticFieldContractService,
    )

    service = SemanticFieldContractService(db=None)
    result = await service.evaluate(
        platform="shopee",
        data_domain="orders",
        granularity="daily",
        sub_domain=None,
        header_bindings=[],
        current_columns=["订单编号", "店铺", "下单时间"],
        core_fields=[
            {
                "semantic_key": "order_id",
                "raw_name": "订单编号",
                "required": True,
                "in_hash": True,
            }
        ],
    )

    assert result.should_block is False
    assert result.missing_required_keys == []
    # 清单只勾了 order_id ⇒ 域级下限里其余的键都是缺口
    assert "shop_id" in result.below_domain_floor_keys
    assert "order_id" not in result.below_domain_floor_keys


# ---------------------------------------------------------------------------
# 4) 「已确认的新列」忽略清单(批次 F-4 / API-6)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ignored_extra_fields_are_excluded_from_noise():
    """用户确认过的新列不再算成 ``extra_raw_fields`` 噪音。

    没有这个表达方式时, 源文件多出来的列每次都被报出来 ⇒ 治理面板上是一条
    **永久噪音**(不阻断, 但永远消不掉)。
    """
    from backend.services.semantic_field_contract_service import (
        SemanticFieldContractService,
    )

    service = SemanticFieldContractService(db=None)
    result = await service.evaluate(
        platform="shopee",
        data_domain="orders",
        granularity="weekly",
        sub_domain=None,
        header_bindings=_confirmed_orders_bindings(),
        current_columns=[
            "order_no",
            "shop_name",
            "order_created_at",
            "sold_qty",
            "buyer_paid",
            "profit_amount",
            "platform_new_column",
        ],
        template_columns=[
            "order_no",
            "shop_name",
            "order_created_at",
            "sold_qty",
            "buyer_paid",
            "profit_amount",
        ],
    )

    assert result.extra_raw_fields == ["platform_new_column"]
    assert result.should_block is False


@pytest.mark.asyncio
async def test_ignored_extra_fields_remove_the_noise_entirely():
    """勾选之后, 连 ``non_breaking_drift`` 都不再产生 ⇒ 治理面板回到干净状态。"""
    from backend.services.semantic_field_contract_service import (
        SemanticFieldContractService,
    )

    service = SemanticFieldContractService(db=None)
    result = await service.evaluate(
        platform="shopee",
        data_domain="orders",
        granularity="weekly",
        sub_domain=None,
        header_bindings=_confirmed_orders_bindings(),
        current_columns=[
            "order_no",
            "shop_name",
            "order_created_at",
            "sold_qty",
            "buyer_paid",
            "profit_amount",
            "platform_new_column",
        ],
        template_columns=[
            "order_no",
            "shop_name",
            "order_created_at",
            "sold_qty",
            "buyer_paid",
            "profit_amount",
        ],
        ignored_extra_fields=["platform_new_column"],
    )

    assert result.extra_raw_fields == []
    assert result.status == "ready"
    assert result.should_block is False


def _confirmed_orders_bindings():
    return [
        {"raw_name": "order_no", "semantic_key": "order_id"},
        {"raw_name": "shop_name", "semantic_key": "shop_id"},
        {"raw_name": "order_created_at", "semantic_key": "order_date"},
    ]


def test_ignored_extra_fields_migration_adds_column():
    """迁移给 legacy 模板加 ``ignored_extra_fields`` 列。"""
    import importlib.util

    migration_path = (
        REPO_ROOT
        / "current_migrations"
        / "versions"
        / "20261128_legacy_ignored_extra_fields.py"
    )
    spec = importlib.util.spec_from_file_location("_mig_20261128", migration_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    source = migration_path.read_text(encoding="utf-8")
    assert "ignored_extra_fields" in source
    assert "ADD COLUMN IF NOT EXISTS" in source
    assert callable(module.apply_upgrade)
    assert callable(module.apply_downgrade)
