from pathlib import Path


def test_financial_management_page_exposes_follow_investment_sections():
    text = Path("frontend/src/views/FinancialManagement.vue").read_text(encoding="utf-8")

    assert "利润分配基准" in text
    assert "跟投记录" in text
    assert "结算台账" in text


def test_router_registers_my_follow_investment_income_page():
    text = Path("frontend/src/router/index.js").read_text(encoding="utf-8")

    assert "/my-follow-investment-income" in text
    assert "MyFollowInvestmentIncome.vue" in text


def test_backend_registers_follow_investment_routers():
    main_text = Path("backend/main.py").read_text(encoding="utf-8")

    assert "follow_investment" in main_text
    assert "profit_basis" in main_text

    assert Path("backend/routers/follow_investment.py").exists()
    assert Path("backend/routers/profit_basis.py").exists()
