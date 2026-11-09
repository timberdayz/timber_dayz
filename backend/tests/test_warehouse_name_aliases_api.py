"""仓名别名维护接口的契约测试。

覆盖
----
* 列表（含「库存里出现但没登记」的仓名提示）
* 新增 / 改指向 / 删除
* 仓码必须指向 ``core.dim_warehouses`` 里真实存在的仓（友好预检,不是裸 FK 报错）
* 源仓名唯一
* 改动后**状态层的仓码要跟着重算**（``mart.inventory_state`` 是表不是视图,
  别名改了不会自动生效 —— 忘了重算就是「接口说改成功了、页面上仓码还是旧的」）

为什么用 ``pg_session`` 而不是 SQLite
--------------------------------------
项目的表分布在 PostgreSQL 的 schema 命名空间里（``core`` / ``mart`` / …），
SQLite 建不出来（见 ``backend/tests/conftest.py`` 的说明）。
``pg_session`` 连的是 conftest 起的**一次性隔离容器**，
里面已经建好全部 ORM 表 ⇒ 不需要自己建表,也不会碰真实业务库。
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies.auth import get_current_user
from backend.domains.collection.routers import warehouse_name_aliases
from backend.models.database import get_async_db


_ALIAS_ROWS = [
    ("新加坡", "SG-01"),
    ("马来仓", "MY-01"),
]

_WAREHOUSE_ROWS = [
    ("SG-01", "新加坡仓", "SG", "新加坡"),
    ("MY-01", "马来仓", "MY", "马来西亚"),
]


async def _seed(pg_session: AsyncSession) -> None:
    """播种最小数据集（幂等：先清后插）。

    ⚠️ ``pg_session`` 的 session 是**函数级**的,但接口内部会 ``db.commit()``
    ⇒ 提交是真的落到隔离库 ⇒ 每个用例都要自己清干净。
    """
    await pg_session.execute(text("DROP TABLE IF EXISTS mart.inventory_state"))
    # conftest 的隔离库只建 core/a_class/b_class/c_class/finance/ops/semantic
    # 七个 schema —— **没有 mart**（mart 层是 SQL 资产建的，不是 ORM 表）。
    await pg_session.execute(text("CREATE SCHEMA IF NOT EXISTS mart"))
    await pg_session.execute(
        text(
            """
            CREATE TABLE mart.inventory_state (
                id serial PRIMARY KEY,
                platform_code varchar(64) NOT NULL,
                sku_key varchar(255) NOT NULL,
                warehouse_name varchar(255) NOT NULL,
                warehouse_code varchar(128)
            )
            """
        )
    )
    await pg_session.execute(text("DELETE FROM core.dim_warehouse_name_aliases"))
    await pg_session.execute(text("DELETE FROM core.dim_warehouses"))
    for code, name, country, country_name in _WAREHOUSE_ROWS:
        await pg_session.execute(
            text(
                """
                INSERT INTO core.dim_warehouses
                    (warehouse_code, warehouse_name, country_code, country_name, status)
                VALUES (:code, :name, :country, :country_name, 'active')
                """
            ),
            {
                "code": code,
                "name": name,
                "country": country,
                "country_name": country_name,
            },
        )
    for source_name, code in _ALIAS_ROWS:
        await pg_session.execute(
            text(
                """
                INSERT INTO core.dim_warehouse_name_aliases
                    (source_warehouse_name, warehouse_code, source)
                VALUES (:source_name, :code, 'seed')
                """
            ),
            {"source_name": source_name, "code": code},
        )
    await pg_session.execute(
        text(
            """
            INSERT INTO mart.inventory_state
                (platform_code, sku_key, warehouse_name, warehouse_code)
            VALUES ('miaoshou', 'SKU-1', '新加坡', 'SG-01'),
                   ('miaoshou', 'SKU-2', '马来仓', 'MY-01'),
                   ('miaoshou', 'SKU-3', '未登记仓', NULL)
            """
        )
    )
    await pg_session.commit()


async def _cleanup(pg_session: AsyncSession) -> None:
    await pg_session.rollback()
    await pg_session.execute(text("DROP TABLE IF EXISTS mart.inventory_state"))
    await pg_session.execute(text("DELETE FROM core.dim_warehouse_name_aliases"))
    await pg_session.execute(text("DELETE FROM core.dim_warehouses"))
    await pg_session.commit()
    await pg_session.execute(text("DROP SCHEMA IF EXISTS mart CASCADE"))


async def _state_codes(pg_session: AsyncSession) -> dict[str, object]:
    result = await pg_session.execute(
        text("SELECT sku_key, warehouse_code FROM mart.inventory_state")
    )
    return {row[0]: row[1] for row in result.fetchall()}


@pytest_asyncio.fixture
async def alias_client(pg_session: AsyncSession):
    await _seed(pg_session)

    app = FastAPI()
    app.include_router(warehouse_name_aliases.router, prefix="/api")

    async def override_get_async_db():
        yield pg_session

    async def override_current_user():
        return type(
            "AdminUser",
            (),
            {
                "user_id": 1,
                "id": 1,
                "username": "admin",
                "is_active": True,
                "status": "active",
                "is_superuser": True,
                "roles": [
                    type("Role", (), {"role_code": "admin", "role_name": "admin"})()
                ],
            },
        )()

    app.dependency_overrides[get_async_db] = override_get_async_db
    app.dependency_overrides[get_current_user] = override_current_user

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, pg_session

    await _cleanup(pg_session)


@pytest.mark.asyncio
async def test_list_returns_aliases_with_warehouse_metadata(alias_client) -> None:
    client, _ = alias_client
    response = await client.get("/api/warehouse-name-aliases")
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    by_name = {item["source_warehouse_name"]: item for item in payload["items"]}
    assert by_name["新加坡"]["warehouse_code"] == "SG-01"
    assert by_name["新加坡"]["warehouse_name"] == "新加坡仓"
    assert by_name["新加坡"]["country_code"] == "SG"


@pytest.mark.asyncio
async def test_list_survives_missing_semantic_view(alias_client) -> None:
    """语义层视图不存在时，列表接口不能整个失败 —— 提示信息缺失可降级。"""
    client, _ = alias_client
    response = await client.get("/api/warehouse-name-aliases")
    assert response.status_code == 200
    assert response.json()["unmapped_warehouse_names"] == []


@pytest.mark.asyncio
async def test_create_rejects_unknown_warehouse_code(alias_client) -> None:
    client, _ = alias_client
    response = await client.post(
        "/api/warehouse-name-aliases",
        json={"source_warehouse_name": "新仓", "warehouse_code": "NOT-EXIST"},
    )
    assert response.status_code == 422
    assert "dim_warehouses" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_rejects_duplicate_source_name(alias_client) -> None:
    client, _ = alias_client
    response = await client.post(
        "/api/warehouse-name-aliases",
        json={"source_warehouse_name": "新加坡", "warehouse_code": "MY-01"},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_create_new_alias_and_rebuild_state_codes(alias_client) -> None:
    """新增登记后，状态层对应行的仓码要被补上。"""
    client, pg_session = alias_client
    response = await client.post(
        "/api/warehouse-name-aliases",
        json={"source_warehouse_name": "马来仓2", "warehouse_code": "MY-01"},
    )
    assert response.status_code == 200
    assert response.json()["warehouse_code"] == "MY-01"

    codes = await _state_codes(pg_session)
    assert codes["SKU-1"] == "SG-01"
    assert codes["SKU-2"] == "MY-01"
    assert codes["SKU-3"] is None


@pytest.mark.asyncio
async def test_update_changes_target_and_rebuilds_state_codes(alias_client) -> None:
    """改指向后，状态层对应行的仓码要跟着变（不能只改登记表）。"""
    client, pg_session = alias_client
    response = await client.put(
        "/api/warehouse-name-aliases/新加坡", json={"warehouse_code": "MY-01"}
    )
    assert response.status_code == 200
    assert response.json()["warehouse_code"] == "MY-01"

    codes = await _state_codes(pg_session)
    assert codes["SKU-1"] == "MY-01"


@pytest.mark.asyncio
async def test_delete_falls_state_code_back_to_null(alias_client) -> None:
    """删除登记后，原仓码回落 NULL —— 绝不静默归到别的仓。"""
    client, pg_session = alias_client
    response = await client.delete("/api/warehouse-name-aliases/新加坡")
    assert response.status_code == 200

    codes = await _state_codes(pg_session)
    assert codes["SKU-1"] is None
    assert codes["SKU-2"] == "MY-01"


@pytest.mark.asyncio
async def test_update_missing_alias_returns_404(alias_client) -> None:
    client, _ = alias_client
    response = await client.put(
        "/api/warehouse-name-aliases/不存在", json={"warehouse_code": "SG-01"}
    )
    assert response.status_code == 404
