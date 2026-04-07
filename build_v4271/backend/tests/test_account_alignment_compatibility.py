from __future__ import annotations

from backend.routers import account_alignment


class _FetchAllResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


def test_build_distinct_raw_store_items_returns_frontend_safe_objects():
    items = account_alignment.build_distinct_raw_store_items(
        [
            ("acc-1", "ph", "菲律宾1店", 3, 128.5, "2026-03-01", "2026-03-21"),
        ]
    )

    assert items[0]["account"] == "acc-1"
    assert items[0]["site"] == "ph"
    assert items[0]["store_label_raw"] == "菲律宾1店"
    assert items[0]["order_count"] == 3
    assert items[0]["total_gmv"] == 128.5
    assert items[0]["suggested_target_id"]


async def _call_get_distinct_raw_stores_with_missing_source():
    class FakeSession:
        async def execute(self, statement, params=None):
            sql = str(statement)
            if "information_schema.tables" in sql:
                return _ScalarResult(None)
            raise AssertionError(f"unexpected sql: {sql}")

    return await account_alignment.get_distinct_raw_stores(db=FakeSession())


def test_get_distinct_raw_stores_returns_empty_list_when_source_missing():
    import asyncio

    response = asyncio.run(_call_get_distinct_raw_stores_with_missing_source())

    assert response.success is True
    assert response.count == 0
    assert response.stores == []
