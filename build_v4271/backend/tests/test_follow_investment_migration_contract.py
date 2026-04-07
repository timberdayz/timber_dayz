from pathlib import Path


def test_follow_investment_migration_exists():
    migration_dir = Path("migrations/versions")
    candidates = list(migration_dir.glob("*follow_investment_profit_basis*.py"))

    assert candidates, "缺少跟投收益/利润分配基准迁移脚本"

    text = candidates[0].read_text(encoding="utf-8")
    assert "shop_profit_basis" in text
    assert "follow_investments" in text
    assert "follow_investment_settlements" in text
    assert "follow_investment_details" in text
