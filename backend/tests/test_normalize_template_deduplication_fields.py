"""数据修复脚本的归一逻辑测试。

覆盖 ``scripts/normalize_template_deduplication_fields.py`` 的纯函数部分，
以及在一次性 PostgreSQL 容器上的 apply / restore 往返。

⚠️ 护栏：``backend/tests/conftest.py`` 会把 DATABASE_URL 重定向到一次性容器，
本文件只会在隔离库里读写，绝不触碰真实业务库。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "normalize_template_deduplication_fields.py"
)


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "normalize_template_deduplication_fields_script", SCRIPT_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


script = _load_script()


def _plan(**overrides):
    payload = {
        "template_id": 1,
        "template_name": "shopee_analytics__daily_v1",
        "data_domain": "analytics",
        "granularity": "daily",
        "status": "published",
        "deduplication_fields": ["日期"],
        "header_bindings": [
            {
                "raw_name": "日期",
                "semantic_key": "metric_date",
                "semantic_review_status": "confirmed_semantic",
            }
        ],
        "header_columns": ["日期"],
        "field_parse_rules": [],
    }
    payload.update(overrides)
    return script.plan_template_field_mapping(**payload)


def test_alias_index_maps_chinese_headers_to_semantic_keys():
    index = script.build_alias_semantic_index()

    assert index["订单号"] == ["order_id"]
    assert index["订单编号"] == ["order_id"]
    assert index["产品id"] == ["product_id"]
    assert index["平台sku"] == ["platform_sku"]
    assert index["sku id"] == ["sku_id"]
    assert index["仓库"] == ["warehouse_name"]


def test_global_index_only_keeps_unique_hits():
    templates = [
        {
            "header_bindings": [
                {"raw_name": "订单号", "semantic_key": "order_id"},
            ]
        },
        {
            "header_bindings": [
                {"raw_name": "订单号", "semantic_key": "order_id"},
                {"raw_name": "产品ID", "semantic_key": "product_id"},
            ]
        },
    ]

    index = script.build_global_semantic_index(templates)

    assert index["订单号"] == ["order_id"]
    assert index["产品id"] == ["product_id"]


def test_global_index_drops_conflicting_headers():
    templates = [
        {"header_bindings": [{"raw_name": "金额", "semantic_key": "gmv"}]},
        {"header_bindings": [{"raw_name": "金额", "semantic_key": "sales_amount"}]},
    ]

    index = script.build_global_semantic_index(templates)

    assert "金额" not in index


def test_merge_marks_conflicting_headers_as_ambiguous():
    merged = script.merge_semantic_candidates(
        {"金额": ["gmv"]},
        {"金额": ["sales_amount"]},
    )

    assert merged["金额"] == ["gmv", "sales_amount"]


def test_classify_semantic_key_separates_identity_from_metric():
    assert script.classify_semantic_key("order_id") == script.ACTION_REPLACE
    assert script.classify_semantic_key("product_name") == script.ACTION_REPLACE
    assert script.classify_semantic_key("gmv") == script.ACTION_REMOVE
    assert script.classify_semantic_key("visitor_count") == script.ACTION_REMOVE


def test_plan_replaces_header_name_with_semantic_key():
    plan = _plan()

    assert plan.needs_change is True
    assert plan.replacements == [
        {"from": "日期", "to": "metric_date", "source": "semantic_index"}
    ]
    assert plan.planned_fields == ["metric_date"]


def test_plan_removes_metric_fields_from_identity_set():
    plan = _plan(
        data_domain="analytics",
        granularity="daily",
        deduplication_fields=["metric_date", "访客数"],
        header_bindings=[
            {
                "raw_name": "日期",
                "semantic_key": "metric_date",
                "semantic_review_status": "confirmed_semantic",
            },
            {
                "raw_name": "访客数",
                "semantic_key": "visitor_count",
                "semantic_review_status": "confirmed_semantic",
            },
        ],
        header_columns=["日期", "访客数"],
    )

    assert plan.needs_change is True
    assert plan.removals and plan.removals[0]["from"] == "访客数"
    assert plan.planned_fields == ["metric_date"]


def test_plan_keeps_ambiguous_fields_untouched():
    plan = _plan(
        deduplication_fields=["日期", "金额"],
        header_bindings=[
            {
                "raw_name": "日期",
                "semantic_key": "metric_date",
                "semantic_review_status": "confirmed_semantic",
            }
        ],
        header_columns=["日期", "金额"],
        candidate_index={"日期": ["metric_date"], "金额": ["gmv", "sales_amount"]},
    )

    assert plan.ambiguous_fields == ["金额"]
    assert "金额" in plan.planned_fields


def test_plan_skips_rewrite_when_gates_still_fail():
    plan = _plan(
        data_domain="products",
        granularity="daily",
        deduplication_fields=["日期"],
        header_bindings=[
            {
                "raw_name": "日期",
                "semantic_key": "metric_date",
                "semantic_review_status": "confirmed_semantic",
            }
        ],
        header_columns=["日期"],
    )

    assert plan.needs_change is False
    assert plan.skipped_reason and "未通过" in plan.skipped_reason
    assert "product_id" in plan.missing_identity_keys


def test_plan_is_idempotent_for_already_semantic_fields():
    plan = _plan(deduplication_fields=["metric_date"])

    assert plan.needs_change is False
    assert plan.planned_fields == ["metric_date"]


def test_hint_index_is_scoped_by_data_domain():
    products_index = script.build_hint_semantic_index(data_domain="products")
    services_index = script.build_hint_semantic_index(data_domain="services")

    assert products_index["规格编号"] == ["sku_id"]
    assert products_index["商品编号"] == ["product_id"]
    assert "规格编号" not in services_index

    assert services_index["客服id"] == ["service_id"]
    assert "客服id" not in products_index


def test_plan_removes_unrecognized_column_as_non_identity():
    """注册表里完全没有的列名 = 业务属性，不能继续当身份键。"""
    plan = _plan(
        data_domain="orders",
        granularity="daily",
        deduplication_fields=["订单号", "订单状态"],
        header_bindings=[
            {
                "raw_name": "订单号",
                "semantic_key": "order_id",
                "semantic_review_status": "confirmed_semantic",
            },
            {
                "raw_name": "订单状态",
                "semantic_key": None,
            },
        ],
        header_columns=["订单号", "订单状态"],
    )

    assert plan.needs_change is True
    assert [item["from"] for item in plan.removals] == ["订单状态"]
    assert plan.removals[0]["evidence"] == "binding_without_semantic_key"
    assert plan.planned_fields == ["order_id"]


def test_plan_keeps_parse_rule_source_column_with_multiple_targets():
    """解析规则来源列是有数据的，多义时保持原样而不是剔除。"""
    plan = _plan(
        data_domain="services",
        granularity="monthly",
        deduplication_fields=["日期期间"],
        header_bindings=[],
        header_columns=["日期期间"],
        field_parse_rules=[
            {"target_field": "metric_date", "source_column": "日期期间"},
            {"target_field": "period_start_date", "source_column": "日期期间"},
            {"target_field": "period_end_date", "source_column": "日期期间"},
        ],
    )

    assert plan.removals == []
    assert plan.ambiguous_fields == ["日期期间"]
    assert "日期期间" in plan.planned_fields


def test_plan_replaces_column_with_single_parse_rule_target():
    """解析规则唯一产出一个语义键时，可以直接改写。"""
    plan = _plan(
        data_domain="analytics",
        granularity="daily",
        deduplication_fields=["统计周期"],
        header_bindings=[],
        header_columns=["统计周期"],
        field_parse_rules=[
            {"target_field": "metric_date", "source_column": "统计周期"},
        ],
    )

    assert plan.needs_change is True
    assert plan.replacements == [
        {"from": "统计周期", "to": "metric_date", "source": "parse_rule"}
    ]
    assert plan.planned_fields == ["metric_date"]


def test_plan_adds_missing_domain_identity_key_when_template_has_it():
    """模板自身有已确认绑定时，允许受控补齐域级必需身份键。"""
    plan = _plan(
        data_domain="orders",
        granularity="daily",
        deduplication_fields=["产品ID"],
        header_bindings=[
            {
                "raw_name": "产品ID",
                "semantic_key": "product_id",
                "semantic_review_status": "confirmed_semantic",
            },
            {
                "raw_name": "订单号",
                "semantic_key": "order_id",
                "semantic_review_status": "confirmed_semantic",
            },
        ],
        header_columns=["产品ID", "订单号"],
    )

    assert plan.needs_change is True
    assert [item["key"] for item in plan.additions] == ["order_id"]
    assert plan.planned_fields == ["product_id", "order_id"]


def test_plan_refuses_to_add_identity_key_without_data_source():
    """没有数据来源的身份键绝不凭空补进来。"""
    plan = _plan(
        data_domain="orders",
        granularity="daily",
        deduplication_fields=["产品ID"],
        header_bindings=[
            {
                "raw_name": "产品ID",
                "semantic_key": "product_id",
                "semantic_review_status": "confirmed_semantic",
            },
        ],
        header_columns=["产品ID"],
    )

    assert plan.needs_change is False
    assert plan.additions == []
    assert plan.skipped_reason and "未通过" in plan.skipped_reason
    assert "order_id" in plan.missing_identity_keys


def test_plan_skips_when_removal_leaves_no_identity_key():
    plan = _plan(
        data_domain="services",
        granularity="daily",
        deduplication_fields=["聊天询问"],
        header_bindings=[],
        header_columns=["聊天询问"],
    )

    assert plan.needs_change is False
    assert plan.removals and plan.removals[0]["from"] == "聊天询问"
    assert plan.skipped_reason and "没有任何身份键" in plan.skipped_reason


@pytest.mark.asyncio
async def test_apply_then_restore_round_trip(tmp_path):
    """在隔离库上验证 apply / restore 往返。

    这里不用 ``pg_session`` fixture：它的 engine 与 ``@pytest.mark.asyncio``
    的事件循环作用域不一致（session 级 fixture vs function 级 loop），
    会触发 "attached to a different loop"。

    也不复用 ``backend.models.database.AsyncSessionLocal``：它的连接池在
    import 时就建好，跨测试复用同一个 pool 时 asyncpg 会把连接绑到
    第一次使用它的那个 event loop 上，在全量回归里表现为
    "attached to a different loop"。因此这里自建 engine，用完即弃。

    护栏已把 DATABASE_URL 指向一次性容器，绝不会碰到真实业务库。
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from backend.models.database import DATABASE_URL, get_async_database_url
    from modules.core.db import FieldMappingTemplate

    engine = create_async_engine(get_async_database_url(DATABASE_URL), echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            template = FieldMappingTemplate(
                platform="shopee",
                data_domain="analytics",
                granularity="daily",
                account="unit-test-account",
                template_name="unit_test_normalize_dedup",
                version=1,
                status="archived",
                encoding="utf-8",
                header_row=0,
                header_columns=["日期"],
                deduplication_fields=["日期"],
                header_bindings=[
                    {
                        "raw_name": "日期",
                        "semantic_key": "metric_date",
                        "semantic_review_status": "confirmed_semantic",
                    }
                ],
                field_parse_rules=[],
            )
            session.add(template)
            await session.commit()
            template_id = template.id

            plan = script.plan_template_field_mapping(
                template_id=template_id,
                template_name="unit_test_normalize_dedup",
                data_domain="analytics",
                granularity="daily",
                status="archived",
                deduplication_fields=["日期"],
                header_bindings=template.header_bindings,
                header_columns=template.header_columns,
                field_parse_rules=[],
            )
            assert plan.needs_change is True

            backup_path = tmp_path / "backup.json"
            changed = await script.apply_plans([plan], backup_path, session=session)
            assert changed == 1

            row = await session.execute(
                text(
                    "SELECT deduplication_fields FROM core.field_mapping_templates "
                    "WHERE id = :tid"
                ),
                {"tid": template_id},
            )
            assert row.scalar() == ["metric_date"]

            restored = await script.restore_plans(backup_path, session=session)
            assert restored == 1

            row = await session.execute(
                text(
                    "SELECT deduplication_fields FROM core.field_mapping_templates "
                    "WHERE id = :tid"
                ),
                {"tid": template_id},
            )
            assert row.scalar() == ["日期"]

            await session.execute(
                text("DELETE FROM core.field_mapping_templates WHERE id = :tid"),
                {"tid": template_id},
            )
            await session.commit()
    finally:
        await engine.dispose()
