from modules.core.db import (
    MonthlyProfitEmployeeCommissionSnapshot,
    MonthlyProfitEmployeePerformanceSnapshot,
    MonthlyProfitPayrollSnapshot,
    MonthlyProfitShopBasisSnapshot,
)


def test_monthly_profit_snapshot_tables_exist():
    assert MonthlyProfitShopBasisSnapshot.__table__.schema == "finance"
    assert MonthlyProfitEmployeeCommissionSnapshot.__table__.schema == "finance"
    assert MonthlyProfitEmployeePerformanceSnapshot.__table__.schema == "finance"
    assert MonthlyProfitPayrollSnapshot.__table__.schema == "finance"


def test_monthly_profit_snapshot_tables_have_version_and_status_columns():
    for model in (
        MonthlyProfitShopBasisSnapshot,
        MonthlyProfitEmployeeCommissionSnapshot,
        MonthlyProfitEmployeePerformanceSnapshot,
        MonthlyProfitPayrollSnapshot,
    ):
        columns = model.__table__.c
        assert "settlement_id" in columns
        assert "period_month" in columns
        assert "snapshot_version" in columns
        assert "snapshot_status" in columns
