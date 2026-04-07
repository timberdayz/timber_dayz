from datetime import date

import pytest

from backend.services.annual_cost_aggregate import get_annual_cost_aggregate


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _RecordingAsyncDb:
    def __init__(self, b_row=(10, 2, 3, 100), fail_b=False):
        self.calls = []
        self.fail_b = fail_b
        self.a_row = (5,)
        self.b_row = b_row

    async def execute(self, sql, params):
        self.calls.append((str(sql), dict(params)))
        if "FROM a_class.operating_costs" in str(sql):
            return _FakeResult(self.a_row)
        if "FROM u" in str(sql):
            if self.fail_b:
                raise RuntimeError("b query failed")
            return _FakeResult(self.b_row)
        raise AssertionError(f"Unexpected SQL: {sql}")


@pytest.mark.asyncio
async def test_annual_cost_aggregate_passes_date_objects_to_monthly_b_query():
    db = _RecordingAsyncDb()

    await get_annual_cost_aggregate(db, "monthly", "2025-09")

    b_query_call = next(call for call in db.calls if "FROM u" in call[0])
    params = b_query_call[1]
    assert isinstance(params["period_start"], date)
    assert isinstance(params["period_end"], date)


@pytest.mark.asyncio
async def test_annual_cost_aggregate_raises_when_b_query_fails():
    db = _RecordingAsyncDb(fail_b=True)

    with pytest.raises(RuntimeError, match="b query failed"):
        await get_annual_cost_aggregate(db, "monthly", "2025-09")


@pytest.mark.asyncio
async def test_annual_cost_aggregate_keeps_b_side_gmv_when_monthly_rows_exist():
    db = _RecordingAsyncDb(b_row=(60, 5, 15, 108.78))

    result = await get_annual_cost_aggregate(db, "monthly", "2025-09")

    assert result["total_cost_a"] == 5
    assert result["total_cost_b"] == 80
    assert result["total_cost"] == 85
    assert result["gmv"] == 108.78
