import pytest
from pydantic import ValidationError
from types import SimpleNamespace
from unittest.mock import AsyncMock


def test_monthly_scope_model_uses_month_and_shop_as_its_identity():
    from modules.core.db import OperationPerformanceShopScope

    table = OperationPerformanceShopScope.__table__
    assert table.schema == "a_class"
    assert {"year_month", "platform_code", "shop_id"}.issubset(table.c.keys())
    assert any(
        constraint.name == "uq_operation_performance_shop_scope_month_shop"
        for constraint in table.constraints
    )


def test_auto_integer_migration_adds_scope_identity_snapshot_columns():
    from pathlib import Path

    source = (
        Path("current_migrations/versions")
        / "20260817_operation_performance_auto_integer_v1.py"
    ).read_text(encoding="utf-8")

    assert 'down_revision = "current_schema_20260817_operation_performance_monthly_scope"' in source
    assert "source_shop_account_id" in source
    assert "standard_name_snapshot" in source
    assert "alias_snapshots" in source
    assert "chk_operation_performance_scope_exclusion_reason" in source


def test_scope_contract_allows_empty_optional_note_for_an_excluded_shop():
    from backend.schemas.target import OperationWorkbenchScopeApplyRequest

    request = OperationWorkbenchScopeApplyRequest(
        year_month="2026-08",
        shops=[
            {
                "platform_code": "shopee",
                "shop_id": "S001",
                "is_included": False,
            }
        ],
    )

    assert request.shops[0].exclusion_reason is None


def test_entry_contract_rejects_duplicate_shop_metric_keys():
    from backend.schemas.target import OperationWorkbenchEntryApplyRequest

    with pytest.raises(ValidationError, match="店铺指标不能重复"):
        OperationWorkbenchEntryApplyRequest(
            year_month="2026-08",
            entries=[
                {
                    "metric_code": "reply_timeliness",
                    "platform_code": "shopee",
                    "shop_id": "S001",
                    "actual_value": 95,
                },
                {
                    "metric_code": "reply_timeliness",
                    "platform_code": "SHOPEE",
                    "shop_id": "S001",
                    "actual_value": 96,
                },
            ],
        )


def test_entry_contract_rejects_multiple_controlled_input_kinds():
    from backend.schemas.target import OperationWorkbenchEntryApplyRequest

    with pytest.raises(ValidationError, match="一种受控录入"):
        OperationWorkbenchEntryApplyRequest(
            year_month="2026-08",
            entries=[
                {
                    "metric_code": "reply_timeliness",
                    "platform_code": "shopee",
                    "shop_id": "S001",
                    "actual_value": 95,
                    "result": "passed",
                }
            ],
        )


def test_rule_contract_rejects_actual_values_and_manual_scores():
    from backend.schemas.target import OperationWorkbenchApplyRequest

    with pytest.raises(ValidationError, match="achieved_value"):
        OperationWorkbenchApplyRequest(
            year_month="2026-08",
            catalog_version=1,
            metrics=[
                {
                    "metric_code": "reply_timeliness",
                    "target_value": 95,
                    "achieved_value": 96,
                    "max_score": 20,
                }
            ],
        )


@pytest.mark.asyncio
async def test_scope_confirmation_rejects_an_included_shop_without_sales_target(
    monkeypatch,
):
    from backend.schemas.target import OperationWorkbenchScopeApplyRequest
    from backend.services import operation_performance_workbench_service as module

    service = module.OperationPerformanceWorkbenchService(db=SimpleNamespace())
    service._active_shops = AsyncMock(
        return_value=[
            {
                "source_shop_account_id": 1,
                "platform_code": "shopee",
                "shop_id": "S001",
                "standard_name": "店铺 A",
                "aliases": [],
            }
        ]
    )
    service._unresolved_scope_shops = AsyncMock(return_value=[])
    service._sales_target_shop_keys = AsyncMock(return_value=set())
    monkeypatch.setattr(
        module.PayrollPeriodLockService,
        "assert_month_mutable",
        AsyncMock(),
    )

    request = OperationWorkbenchScopeApplyRequest(
        year_month="2026-08",
        shops=[
            {
                "platform_code": "shopee",
                "shop_id": "S001",
                "is_included": True,
            }
        ],
    )

    with pytest.raises(ValueError, match="销售目标"):
        await service.apply_scope(request, username="admin")


@pytest.mark.asyncio
async def test_entry_save_rejects_an_excluded_shop(monkeypatch):
    from backend.schemas.target import OperationWorkbenchEntryApplyRequest
    from backend.services import operation_performance_workbench_service as module

    service = module.OperationPerformanceWorkbenchService(db=SimpleNamespace())
    service._scope_rows = AsyncMock(
        return_value=[
            SimpleNamespace(
                platform_code="shopee",
                shop_id="S001",
                is_included=False,
                snapshot_version=1,
            )
        ]
    )
    monkeypatch.setattr(
        module.PayrollPeriodLockService,
        "assert_month_mutable",
        AsyncMock(),
    )

    request = OperationWorkbenchEntryApplyRequest(
        year_month="2026-08",
        entries=[
            {
                "metric_code": "reply_timeliness",
                "platform_code": "shopee",
                "shop_id": "S001",
                "actual_value": 95,
            }
        ],
    )

    with pytest.raises(ValueError, match="未参与"):
        await service.apply_entries(request, username="admin")


@pytest.mark.asyncio
async def test_entries_read_structured_payload_and_auto_score_from_rule_snapshot():
    from backend.services import operation_performance_workbench_service as module

    service = module.OperationPerformanceWorkbenchService(db=SimpleNamespace())
    scope = SimpleNamespace(
        platform_code="shopee",
        shop_id="S001",
        is_included=True,
        snapshot_version=1,
        standard_name_snapshot="Standard shop",
        alias_snapshots=["Shop alias"],
    )
    target = SimpleNamespace(
        id=101,
        is_enabled=True,
        metric_code="training_completion_rate",
        metric_name="Training completion",
        metric_direction="higher_better",
        target_value=100,
        max_score=20,
        operation_rule_snapshot={
            "input_kind": "training_counts",
            "target_value": 100,
            "guidance": "Enter completed and required counts",
        },
    )
    breakdown = SimpleNamespace(
        operation_input_payload={"completed_count": 9, "required_count": 10},
        achieved_value=999,
        manual_score_value=7,
    )
    service._scope_rows = AsyncMock(return_value=[scope])
    service._active_shops = AsyncMock(return_value=[])
    service._targets = AsyncMock(return_value=[target])
    service._entry_breakdowns = AsyncMock(
        return_value={(101, "shopee", "S001"): breakdown}
    )

    result = await service.get_entries("2026-08")

    metric = result["shops"][0]["metrics"][0]
    assert metric["input_kind"] == "training_counts"
    assert metric["input_payload"] == {"completed_count": 9, "required_count": 10}
    assert metric["auto_score"] == 18
    assert metric["status"] == "completed"
    assert metric["scoring_detail"]["achievement_rate"] == 0.9
    assert "achieved_value" not in metric
    assert "manual_score_value" not in metric


@pytest.mark.asyncio
async def test_entry_save_requires_confirmed_scope(monkeypatch):
    from backend.schemas.target import OperationWorkbenchEntryApplyRequest
    from backend.services import operation_performance_workbench_service as module

    service = module.OperationPerformanceWorkbenchService(db=SimpleNamespace())
    service._scope_rows = AsyncMock(
        return_value=[
            SimpleNamespace(
                platform_code="shopee",
                shop_id="S001",
                is_included=True,
                snapshot_version=None,
            )
        ]
    )
    service._targets = AsyncMock(return_value=[])
    monkeypatch.setattr(
        module.PayrollPeriodLockService,
        "assert_month_mutable",
        AsyncMock(),
    )
    request = OperationWorkbenchEntryApplyRequest(
        year_month="2026-08",
        entries=[
            {
                "metric_code": "reply_timeliness",
                "platform_code": "shopee",
                "shop_id": "S001",
                "actual_value": 95,
            }
        ],
    )

    with pytest.raises(ValueError):
        await service.apply_entries(request, username="admin")


@pytest.mark.asyncio
async def test_entries_do_not_expose_unconfirmed_legacy_scope_as_writable():
    from backend.services import operation_performance_workbench_service as module

    service = module.OperationPerformanceWorkbenchService(db=SimpleNamespace())
    service._scope_rows = AsyncMock(
        return_value=[
            SimpleNamespace(
                platform_code="shopee",
                shop_id="S001",
                is_included=True,
                snapshot_version=None,
            )
        ]
    )
    service._targets = AsyncMock(return_value=[])

    result = await service.get_entries("2026-08")

    assert result["scope_confirmed"] is False
    assert result["shops"] == []


@pytest.mark.asyncio
async def test_entry_save_rejects_payload_that_does_not_match_metric_input_kind(
    monkeypatch,
):
    from backend.schemas.target import OperationWorkbenchEntryApplyRequest
    from backend.services import operation_performance_workbench_service as module

    service = module.OperationPerformanceWorkbenchService(db=SimpleNamespace())
    service._scope_rows = AsyncMock(
        return_value=[
            SimpleNamespace(
                platform_code="shopee",
                shop_id="S001",
                is_included=True,
                snapshot_version=1,
            )
        ]
    )
    service._targets = AsyncMock(
        return_value=[
            SimpleNamespace(
                id=101,
                metric_code="operation_special_check",
                metric_direction="manual_score",
                target_value=None,
                max_score=20,
                metric_catalog_version=2,
                is_enabled=True,
                operation_rule_snapshot={"input_kind": "special_check"},
            )
        ]
    )
    service._entry_breakdowns = AsyncMock(return_value={})
    monkeypatch.setattr(
        module.PayrollPeriodLockService,
        "assert_month_mutable",
        AsyncMock(),
    )
    request = OperationWorkbenchEntryApplyRequest(
        year_month="2026-08",
        entries=[
            {
                "metric_code": "operation_special_check",
                "platform_code": "shopee",
                "shop_id": "S001",
                "actual_value": 90,
            }
        ],
    )

    with pytest.raises(ValueError, match="专项检查"):
        await service.apply_entries(request, username="admin")


@pytest.mark.asyncio
async def test_entry_save_accepts_catalog_percentage_as_numeric_input(monkeypatch):
    from backend.schemas.target import OperationWorkbenchEntryApplyRequest
    from backend.services import operation_performance_workbench_service as module

    breakdown = SimpleNamespace(
        operation_input_payload=None,
        achieved_value=None,
        manual_score_value=None,
        updated_at=None,
    )
    db = SimpleNamespace(commit=AsyncMock())
    service = module.OperationPerformanceWorkbenchService(db=db)
    service._scope_rows = AsyncMock(
        return_value=[
            SimpleNamespace(
                platform_code="shopee",
                shop_id="S001",
                is_included=True,
                snapshot_version=1,
            )
        ]
    )
    service._targets = AsyncMock(
        return_value=[
            SimpleNamespace(
                id=101,
                metric_code="customer_satisfaction",
                metric_direction="higher_better",
                target_value=100,
                max_score=20,
                metric_catalog_version=2,
                is_enabled=True,
                operation_rule_snapshot={"input_kind": "percentage"},
            )
        ]
    )
    service._entry_breakdowns = AsyncMock(
        return_value={(101, "shopee", "S001"): breakdown}
    )
    service.get_entries = AsyncMock(return_value={"saved": True})
    monkeypatch.setattr(
        module.PayrollPeriodLockService,
        "assert_month_mutable",
        AsyncMock(),
    )
    request = OperationWorkbenchEntryApplyRequest(
        year_month="2026-08",
        entries=[
            {
                "metric_code": "customer_satisfaction",
                "platform_code": "shopee",
                "shop_id": "S001",
                "actual_value": 90,
            }
        ],
    )

    assert await service.apply_entries(request, username="admin") == {"saved": True}
    assert breakdown.operation_input_payload == {"actual_value": 90.0}


def test_target_router_exposes_monthly_scope_and_entry_endpoints():
    from backend.domains.business.routers.target_management import router

    routes = {(route.path, tuple(route.methods)) for route in router.routes}
    assert ("/targets/operation-workbench/scope", ("GET",)) in routes
    assert ("/targets/operation-workbench/scope", ("PUT",)) in routes
    assert ("/targets/operation-workbench/entries", ("GET",)) in routes
    assert ("/targets/operation-workbench/entries", ("PUT",)) in routes
    assert ("/targets/operation-workbench/scope/revoke", ("POST",)) in routes


def test_operation_workbench_write_routes_require_an_administrator():
    from backend.dependencies.auth import require_admin as require_platform_admin
    from backend.domains.business.routers.target_management import router

    write_paths = {
        "/targets/operation-workbench",
        "/targets/operation-workbench/scope",
        "/targets/operation-workbench/entries",
        "/targets/operation-workbench/copy-prev-month",
    }
    for route in router.routes:
        if route.path in write_paths and route.methods & {"PUT", "POST"}:
            assert any(
                dependency.call is require_platform_admin
                for dependency in route.dependant.dependencies
            ), route.path


def test_settlement_filters_out_excluded_operation_scope_shops():
    from backend.domains.business.routers.performance_management import (
        _filter_source_rows_by_operation_scope,
    )

    source_rows = {
        "shopee|S001": {"shop_id": "S001"},
        "shopee|S002": {"shop_id": "S002"},
    }

    assert _filter_source_rows_by_operation_scope(
        source_rows, {"shopee|S002"}
    ) == {"shopee|S002": {"shop_id": "S002"}}
