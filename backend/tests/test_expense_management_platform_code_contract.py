from pathlib import Path


def test_expense_schema_requires_platform_code():
    source = Path("backend/schemas/expense.py").read_text(encoding="utf-8")

    assert "platform_code: Optional[str]" in source


def test_expense_router_reads_and_returns_platform_code():
    source = Path(
        "backend/domains/business/routers/expense_management.py"
    ).read_text(encoding="utf-8")

    assert '"platform_code"' in source
    assert '"platform_code" as platform_code' in source
    assert 'message="无法识别店铺所属平台"' in source


def test_expense_frontend_delete_copy_and_blank_save_guard_exist():
    source = Path(
        "frontend/src/domains/business/views/finance/ExpenseManagement.vue"
    ).read_text(encoding="utf-8")

    assert "确认删除本月费用" in source
    assert "删除后会保留一条空白编辑行，可重新保存恢复" in source
    assert "空白费用记录无需保存，请直接保留空白行" in source
    assert "buildExpenseRowKey" in source
    assert "platform_code: shop.platform_code" in source or "row.platform_code = shop.platform_code" in source
