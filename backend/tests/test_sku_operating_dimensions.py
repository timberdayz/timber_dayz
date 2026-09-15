from types import SimpleNamespace

import pytest

from backend.domains.business.routers.product_center import list_sku_operating_dimensions


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _DimensionsDb:
    def __init__(self):
        self.executed = []
        self._results = [
            _ScalarResult([SimpleNamespace(
                platform_code="shopee",
                name="Shopee",
                default_fee_rate=None,
                fee_rate_effective_from=None,
                fee_rate_source=None,
                fee_rate_version=None,
            )]),
            _ScalarResult([SimpleNamespace(warehouse_code="US-WH", warehouse_name="US Warehouse", country_code="US", country_name="United States")]),
            _ScalarResult(["SPU-A"]),
            _RowsResult([
                SimpleNamespace(sku_id=1, sku_key="SKU-1", sku_name="Bound SKU"),
                SimpleNamespace(sku_id=2, sku_key="SKU-2", sku_name="Unbound SKU"),
            ]),
            _ScalarResult([SimpleNamespace(sku_id=1, spu="SPU-A")]),
        ]

    async def execute(self, statement):
        self.executed.append(statement)
        return self._results.pop(0)


@pytest.mark.asyncio
async def test_sku_operating_dimensions_returns_current_spu_for_each_sku_in_one_batch_query():
    db = _DimensionsDb()
    result = await list_sku_operating_dimensions(db=db)

    assert result["skus"] == [
        {"sku_id": 1, "sku_key": "SKU-1", "sku_name": "Bound SKU", "spu": "SPU-A"},
        {"sku_id": 2, "sku_key": "SKU-2", "sku_name": "Unbound SKU", "spu": None},
    ]
    assert len(db.executed) == 5
