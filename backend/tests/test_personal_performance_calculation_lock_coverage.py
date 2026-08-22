from pathlib import Path


def test_income_calculation_serializes_month_and_rechecks_lock_before_commit():
    source = Path("backend/services/hr_income_calculation_service.py").read_text(encoding="utf-8")
    body = source[source.index("async def calculate_month"):]

    assert body.index("acquire_month_transaction_lock") < body.index("assert_month_mutable")
    assert body.rindex("assert_month_mutable") < body.rindex("await self.db.commit()")


def test_performance_recalculation_serializes_month_and_rechecks_lock_before_commit():
    source = Path("backend/domains/business/routers/performance_management.py").read_text(encoding="utf-8")
    body = source[source.index("async def calculate_performance_scores"):]

    assert body.index("acquire_month_transaction_lock") < body.index("assert_month_mutable")
    assert body.rindex("assert_month_mutable") < body.rindex("await db.commit()")
