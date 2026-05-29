import modules.core.db as core_db


MonthlyProfitShopBasisSnapshot = getattr(core_db, "MonthlyProfitShopBasisSnapshot", None)
MonthlyProfitEmployeeCommissionSnapshot = getattr(core_db, "MonthlyProfitEmployeeCommissionSnapshot", None)
MonthlyProfitEmployeePerformanceSnapshot = getattr(core_db, "MonthlyProfitEmployeePerformanceSnapshot", None)
MonthlyProfitPayrollSnapshot = getattr(core_db, "MonthlyProfitPayrollSnapshot", None)


def test_monthly_profit_snapshot_models_exist_and_bind_to_finance_schema():
    assert MonthlyProfitShopBasisSnapshot is not None, "MonthlyProfitShopBasisSnapshot model is missing from modules.core.db"
    assert MonthlyProfitEmployeeCommissionSnapshot is not None, "MonthlyProfitEmployeeCommissionSnapshot model is missing from modules.core.db"
    assert MonthlyProfitEmployeePerformanceSnapshot is not None, "MonthlyProfitEmployeePerformanceSnapshot model is missing from modules.core.db"
    assert MonthlyProfitPayrollSnapshot is not None, "MonthlyProfitPayrollSnapshot model is missing from modules.core.db"

    assert MonthlyProfitShopBasisSnapshot.__table__.schema == "finance"
    assert MonthlyProfitEmployeeCommissionSnapshot.__table__.schema == "finance"
    assert MonthlyProfitEmployeePerformanceSnapshot.__table__.schema == "finance"
    assert MonthlyProfitPayrollSnapshot.__table__.schema == "finance"
