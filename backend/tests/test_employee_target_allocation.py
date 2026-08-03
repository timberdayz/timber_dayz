from inspect import signature
from pathlib import Path
from types import SimpleNamespace

from modules.core.db import EmployeeShopAssignment
from backend.schemas.hr import EmployeeShopAssignmentCreate, EmployeeShopAssignmentResponse


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


def test_assignment_copy_preserves_target_ratio_and_source_metadata():
    source = Path("backend/domains/business/routers/hr_commission.py").read_text(encoding="utf-8")

    assert "target_allocation_ratio=r.target_allocation_ratio" in source
    assert "target_allocation_ratio_source=r.target_allocation_ratio_source" in source


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


def test_personal_target_summary_allocates_sales_and_gross_profit_without_blocking_risk():
    from backend.domains.business.routers import hr_salary

    build_summary = getattr(hr_salary, "build_employee_target_summary", None)
    assert callable(build_summary)
    assert "shop_actuals" in signature(build_summary).parameters

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
        all_assignments=[
            assignment,
            SimpleNamespace(platform_code="shopee", shop_id="S1", target_allocation_ratio=0.4),
        ],
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

    assert summary["sales_target"] == 500.0
    assert summary["sales_actual"] == 200.0
    assert summary["sales_achievement_rate"] == 0.4
    assert summary["gross_profit_target"] == 100.0
    assert summary["gross_profit_actual"] == 50.0
    assert summary["gross_profit_achievement_rate"] == 0.5
    assert summary["has_allocation_risk"] is True
    assert summary["shops"][0]["allocation_ratio_total"] == 0.9
