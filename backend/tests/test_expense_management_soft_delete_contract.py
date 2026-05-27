from pathlib import Path


def test_operating_cost_schema_and_router_include_soft_delete_contract():
    schema_source = Path("modules/core/db/schema_parts/business.py").read_text(
        encoding="utf-8"
    )
    router_source = Path(
        "backend/domains/business/routers/expense_management.py"
    ).read_text(encoding="utf-8")
    frontend_source = Path(
        "frontend/src/domains/business/views/finance/ExpenseManagement.vue"
    ).read_text(encoding="utf-8")

    assert 'deleted_at = Column("删除时间"' in schema_source
    assert 'deleted_by = Column("删除人"' in schema_source
    assert 'UPDATE a_class.operating_costs' in router_source
    assert '"删除时间" = NOW()' in router_source
    assert '@router.post("/{expense_id}/restore"' in router_source
    assert "恢复" in frontend_source
