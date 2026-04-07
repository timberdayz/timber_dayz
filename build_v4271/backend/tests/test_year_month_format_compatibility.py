"""
月份格式兼容性回归测试
"""

import asyncio
from unittest.mock import AsyncMock

from backend.routers.target_management import get_target_by_month
from backend.utils.year_month_utils import normalize_year_month, year_month_to_first_day


class _MockScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


def test_normalize_year_month_accepts_year_month_and_full_date():
    assert normalize_year_month("2026-03") == "2026-03"
    assert normalize_year_month("2026-03-01") == "2026-03"
    assert year_month_to_first_day("2026-03-18").isoformat() == "2026-03-01"


def test_target_by_month_accepts_full_date_format():
    db = AsyncMock()
    # 首次查询目标返回空，接口应返回“该月暂无目标”而不是格式错误
    db.execute = AsyncMock(return_value=_MockScalarResult(None))

    result = asyncio.run(
        get_target_by_month(
            request=None,
            month="2026-03-01",
            target_type="shop",
            db=db,
            current_user=None,
        )
    )

    assert result.status_code == 200
