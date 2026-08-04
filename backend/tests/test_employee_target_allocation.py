from inspect import getsource, signature
from pathlib import Path
from types import SimpleNamespace

import pytest

from modules.core.db import EmployeeShopAssignment
from backend.schemas.hr import (
    EmployeeShopAssignmentCreate,
    EmployeeShopAssignmentResponse,
    EmployeeShopAssignmentUpdate,
)


def test_employee_shop_assignment_orm_exposes_target_ratio_and_backfill_source():
    columns = EmployeeShopAssignment.__table__.c

    assert "target_allocation_ratio" in columns
    assert "target_allocation_ratio_source" in columns


def test_target_allocation_migration_follows_business_role_migration():
    source = Path("migrations/versions/20260803_add_target_allocation_ratio.py").read_text(
        encoding="utf-8"
    )

    assert 'down_revision = "20260803_shop_account_business_role"' in source


def test_employee_shop_assignment_contracts_expose_independent_target_ratio():
    assert "target_allocation_ratio" in EmployeeShopAssignmentCreate.model_fields
    assert "target_allocation_ratio" in EmployeeShopAssignmentResponse.model_fields
    assert "target_allocation_ratio_source" not in EmployeeShopAssignmentCreate.model_fields
    assert "target_allocation_ratio_source" not in EmployeeShopAssignmentUpdate.model_fields
    assert "target_allocation_ratio_source" in EmployeeShopAssignmentResponse.model_fields


def test_assignment_writes_new_shared_ratio_without_accepting_legacy_source():
    from backend.domains.business.routers.hr_commission import (
        copy_employee_shop_assignments_from_prev_month,
        create_employee_shop_assignment,
    )

    create_source = getsource(create_employee_shop_assignment)
    copy_source = getsource(copy_employee_shop_assignments_from_prev_month)

    assert "body.target_allocation_ratio_source" not in create_source
    assert 'target_allocation_ratio_source="manual"' in create_source
    assert "target_allocation_ratio=1.0" in copy_source
    assert "target_allocation_ratio=r.target_allocation_ratio" not in copy_source


def test_target_ratio_backfill_migration_assigns_single_and_equal_split_sources():
    migration = Path("migrations/versions/20260803_add_target_allocation_ratio.py")

    assert migration.exists()
    source = migration.read_text(encoding="utf-8")
    assert "WHEN assignment_counts.employee_count = 1 THEN 1.0" in source
    assert "ELSE 1.0 / assignment_counts.employee_count" in source
    assert "'backfill_equal'" in source


def test_target_ratio_backfill_migration_covers_inactive_history_before_not_null():
    migration = Path("migrations/versions/20260803_add_target_allocation_ratio.py")

    source = migration.read_text(encoding="utf-8")

    assert "backfill_inactive_history" in source
    assert "WHERE target_allocation_ratio IS NULL" in source
    assert "target_allocation_ratio_source IS NULL" in source


def test_personal_target_summary_route_is_exposed():
    from backend.domains.business.routers.hr_salary import router

    assert any(route.path == "/api/hr/employee-target-summary" for route in router.routes)


def test_personal_target_summary_uses_full_shop_metrics_for_shared_responsibility():
    from backend.domains.business.routers import hr_salary

    build_summary = getattr(hr_salary, "build_employee_target_summary", None)
    assert callable(build_summary)
    assert "all_assignments" not in signature(build_summary).parameters

    assignment = SimpleNamespace(
        employee_code="E1",
        platform_code="shopee",
        shop_id="S1",
        target_allocation_ratio=0.5,
        target_allocation_ratio_source="manual",
    )
    summary = build_summary(
        employee_code="E1",
        employee_name="Alice",
        assignments=[assignment],
        shop_targets={
            ("shopee", "S1"): {
                "shop_name": "Shop One",
                "sales_target": 1000.0,
                "gross_profit_target": 200.0,
            }
        },
        shop_actuals={
            ("shopee", "S1"): {"monthly_sales": 400.0, "monthly_profit": 100.0}
        },
    )

    assert summary["sales_target"] == 1000.0
    assert summary["sales_actual"] == 400.0
    assert summary["sales_achievement_rate"] == 0.4
    assert summary["gross_profit_target"] == 200.0
    assert summary["gross_profit_actual"] == 100.0
    assert summary["gross_profit_achievement_rate"] == 0.5
    assert "has_allocation_risk" not in summary
    assert "target_allocation_ratio" not in summary["shops"][0]


def test_shared_shop_responsibility_ignores_legacy_ratios_for_every_employee():
    from backend.services.employee_target_allocation_service import (
        build_employee_target_summary,
    )

    shop_targets = {
        ("shopee", "S1"): {
            "shop_name": "Shop One",
            "sales_target": 1000.0,
            "gross_profit_target": 200.0,
        }
    }
    shop_actuals = {
        ("shopee", "S1"): {"monthly_sales": 800.0, "monthly_profit": 120.0}
    }
    summaries = [
        build_employee_target_summary(
            employee_code=employee_code,
            employee_name=employee_code,
            assignments=[
                SimpleNamespace(
                    employee_code=employee_code,
                    platform_code="shopee",
                    shop_id="S1",
                    target_allocation_ratio=ratio,
                )
            ],
            shop_targets=shop_targets,
            shop_actuals=shop_actuals,
        )
        for employee_code, ratio in (("E1", 0.25), ("E2", 0.15), ("E3", 0.90))
    ]

    for summary in summaries:
        assert summary["sales_target"] == 1000.0
        assert summary["sales_actual"] == 800.0
        assert summary["sales_achievement_rate"] == 0.8
        assert summary["gross_profit_target"] == 200.0
        assert summary["gross_profit_actual"] == 120.0
        assert summary["gross_profit_achievement_rate"] == 0.6
        assert "has_allocation_risk" not in summary


def test_employee_target_summary_adds_complete_targets_for_each_responsible_shop():
    from backend.services.employee_target_allocation_service import (
        build_employee_target_summary,
    )

    summary = build_employee_target_summary(
        employee_code="E1",
        employee_name="Alice",
        assignments=[
            SimpleNamespace(platform_code="shopee", shop_id="S1"),
            SimpleNamespace(platform_code="tiktok", shop_id="S2"),
        ],
        shop_targets={
            ("shopee", "S1"): {"sales_target": 1000.0, "gross_profit_target": 200.0},
            ("tiktok", "S2"): {"sales_target": 600.0, "gross_profit_target": 90.0},
        },
        shop_actuals={
            ("shopee", "S1"): {"monthly_sales": 800.0, "monthly_profit": 120.0},
            ("tiktok", "S2"): {"monthly_sales": 300.0, "monthly_profit": 30.0},
        },
    )

    assert summary["sales_target"] == 1600.0
    assert summary["sales_actual"] == 1100.0
    assert summary["gross_profit_target"] == 290.0
    assert summary["gross_profit_actual"] == 150.0


def test_shop_assignment_rejects_new_non_shared_target_allocation_ratio():
    with pytest.raises(ValueError, match="共同承接"):
        EmployeeShopAssignmentCreate(
            year_month="2026-08",
            employee_code="E1",
            platform_code="shopee",
            shop_id="S1",
            target_allocation_ratio=0.25,
        )

    with pytest.raises(ValueError, match="共同承接"):
        EmployeeShopAssignmentUpdate(target_allocation_ratio=0.25)


def test_target_assignment_frontend_uses_shared_shop_responsibility_without_ratio_controls():
    shop_assignment = Path("frontend/src/domains/business/views/hr/ShopAssignment.vue").read_text(
        encoding="utf-8"
    )
    target_overview = Path(
        "frontend/src/domains/business/views/target/TargetPersonManagement.vue"
    ).read_text(encoding="utf-8")
    target_utils = Path(
        "frontend/src/domains/business/views/target/personTargetUtils.js"
    ).read_text(encoding="utf-8")

    assert "共同承接店铺目标" in shop_assignment
    assert "共同承接店铺目标" in target_overview
    assert "v-if=\"hasAllocationRisk\"" not in target_overview
    assert "target_allocation_ratio" not in shop_assignment
    assert "target_allocation_ratio" not in target_overview
    assert "target_allocation_ratio" not in target_utils
    assert "has_allocation_risk" not in target_overview
    assert "commission_ratio" in shop_assignment
    assert "sumCommissionRatio" in shop_assignment
