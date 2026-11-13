"""商品中心 SPU 值域端点与归属规则（2026-11-12）。

背景
----
工具栏「所属 SPU」筛选器的候选集，原本绑定的是「SPU 管理」tab 的**分页表格数据**
（``/api/spus`` 默认 page=1、page_size=20）。而 ``dim_spu`` 实测有 286 条 ⇒
第 36 个 SPU（``XH-FASHION-001``）永远不在候选集里：运营输入后看到
「无匹配数据」，回车不生效，筛选根本没发生，下面的表格还是全量。

根因不是「翻页」，是**用实体列表当枚举值域**，并且把两件语义相反的事混成一件：

  * 工具栏筛选器 = **查询条件**（手上有什么编码都能查，不能被候选集挡住）
  * 新增 SKU 行选款 = **外键选择**（款必须真实存在，且现在还允许挂）

本文件锁定两件事：

  1. **值域端点**：候选集由后端按业务口径给出，前端不再依赖任何 tab 的表格数据；
  2. **归属规则**：已淘汰 / 已删除的 SPU 不能接新 SKU —— 这条规则以前只存在于人脑子里。

⚠️ 判定条件本身不在本文件定义，而在
``backend/services/product_spu_lifecycle.py``（律 1「真源只能有一个」）——
本文件只断言**行为**，不重新定义口径。
"""

from datetime import date
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException

from backend.domains.business.routers.product_center import (
    _apply_bulk_sku_spu_binding,
    bind_spu_sku,
    list_spu_assignable_options,
    list_spu_options,
)
from backend.schemas.product_center import SpuSkuBindingRequest


# ---------------------------------------------------------------------------
# 假会话
# ---------------------------------------------------------------------------


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class _OptionsDb:
    """值域端点用：记录执行的语句并回一批 SPU 行。"""

    def __init__(self, rows=()):
        self.executed = []
        self._rows = list(rows)

    async def execute(self, statement):
        self.executed.append(statement)
        return _RowsResult(self._rows)


class _BindingDb:
    """绑定用：只关心「有没有把绑定写下去」。"""

    def __init__(self, spu_row=None, sku_row=None, current_binding=None):
        self.spu_row = spu_row
        self.sku_row = sku_row
        self.current_binding = current_binding
        self.added = []
        self.committed = False

    async def get(self, model, key):
        if model.__name__ == "DimSpu":
            return self.spu_row
        if model.__name__ == "DimErpSku":
            return self.sku_row
        return None

    async def execute(self, statement):
        return _RowsResult([self.current_binding] if self.current_binding else [])

    def add(self, row):
        self.added.append(row)

    async def commit(self):
        self.committed = True

    async def rollback(self):
        pass

    async def refresh(self, row):
        return row


def _where_sql(statement) -> str:
    whereclause = statement.whereclause
    if whereclause is None:
        return ""
    return str(whereclause.compile(compile_kwargs={"literal_binds": True}))


def _spu(active=True, biz_status="candidate", spu="XH-TEST"):
    return SimpleNamespace(
        spu=spu,
        spu_name="Test SPU",
        category_l1="CAT-1",
        category_l2="CAT-1-1",
        biz_status=biz_status,
        owner_user_id=None,
        active=active,
    )


def _sku():
    return SimpleNamespace(
        sku_id=7,
        sku_key="SKU-7",
        sku_name="Test SKU",
        specification=None,
        weight_kg=None,
        package_length_cm=None,
        package_width_cm=None,
        package_height_cm=None,
        units_per_carton=None,
        default_purchase_cost=None,
        purchase_cost_source=None,
        purchase_cost_confidence=None,
    )


@pytest.fixture
def stub_side_effects(monkeypatch):
    """把投影、审计、后台投递换成空实现 —— 本文件只关心归属规则。"""
    from backend.domains.business.routers import product_center as pc_module

    class _NoopProjection:
        def __init__(self, db):
            self.db = db

        async def enqueue(self, *args, **kwargs):
            return None

    async def _noop_audit(*args, **kwargs):
        return None

    async def _noop_delivery():
        return None

    monkeypatch.setattr(pc_module, "FeishuProjectionService", _NoopProjection)
    monkeypatch.setattr(pc_module, "_write_product_center_audit", _noop_audit)
    monkeypatch.setattr(
        pc_module, "trigger_pending_projection_delivery", _noop_delivery
    )


# ---------------------------------------------------------------------------
# 值域端点
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_browse_options_endpoint_returns_active_spus():
    """浏览域：在售即可（已淘汰但没删的款仍能被筛到）。"""
    db = _OptionsDb([SimpleNamespace(spu="XH-1", spu_name="One")])
    result = await list_spu_options(db=db, keyword=None, limit=50)

    where = _where_sql(db.executed[0])
    assert "active IS true" in where
    assert result.data[0].spu == "XH-1"


@pytest.mark.asyncio
async def test_assignable_options_endpoint_excludes_retired_spus():
    """可绑定域：已淘汰 / 已删除的款不在候选里 —— 新 SKU 挂不上它们。"""
    db = _OptionsDb([SimpleNamespace(spu="XH-1", spu_name="One")])
    await list_spu_assignable_options(db=db, keyword=None, limit=50)

    where = _where_sql(db.executed[0])
    assert "biz_status" in where
    assert "retired" not in where
    for value in ("candidate", "testing", "promoted"):
        assert value in where


@pytest.mark.asyncio
async def test_options_endpoints_apply_keyword_filter():
    """值域端点必须支持按编码/名称搜索 —— 否则 286 条款只能靠翻。"""
    db = _OptionsDb([])
    await list_spu_options(db=db, keyword="FASHION", limit=50)

    where = _where_sql(db.executed[0]).lower()
    # ⚠️ PostgreSQL 方言把 ``ilike`` 渲染成 ``lower(x) like lower(y)``
    #    ⇒ 断言渲染结果里的 like，而不是 ilike 字面量。
    assert "like" in where
    assert "fashion" in where


@pytest.mark.asyncio
async def test_options_endpoint_returns_only_code_and_name():
    """值域只需要编码与名称 —— 不下发整个 SPU 管理行（含软删标记、分类等）。"""
    db = _OptionsDb([SimpleNamespace(spu="XH-1", spu_name="One", active=True)])
    result = await list_spu_options(db=db, keyword=None, limit=50)

    payload = result.data[0].model_dump()
    assert set(payload) == {"spu", "spu_name"}


@pytest.mark.asyncio
async def test_options_endpoints_do_not_depend_on_pagination():
    """值域是候选集，不是管理列表 —— 它不分页，也不该有页码概念。"""
    import inspect

    for handler in (list_spu_options, list_spu_assignable_options):
        params = inspect.signature(handler).parameters
        assert "page" not in params, f"{handler.__name__} 不该有分页参数"
        assert "page_size" not in params, f"{handler.__name__} 不该有分页参数"


# ---------------------------------------------------------------------------
# 默认排序（2026-11-13 新增，批次 B）
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def spu_value_domain_session():
    """值域排序用的内存 SQLite 会话（挂 ``core`` schema）。

    ⚠️ 为什么不用 ``sqlite_session`` fixture：它跑 ``Base.metadata.create_all``，
    而生产表挂在 PostgreSQL 的 ``core`` schema 下 ⇒ SQLite 直接报
    ``unknown database core``。仓库里已有 ``ATTACH DATABASE ':memory:' AS core``
    的成熟做法（``backend/tests/data_pipeline/test_refresh_queue_service.py``），
    这里沿用同一招 ⇒ 这组用例不必依赖 PostgreSQL 容器，任何环境都能跑。
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from modules.core.db import Base, BridgeSpuSku, DimSpu

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("ATTACH DATABASE ':memory:' AS core"))
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                bind=sync_conn,
                tables=[DimSpu.__table__, BridgeSpuSku.__table__],
            )
        )

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


async def _seed_spus_and_bindings(session, spus, bindings):
    """种下若干款与它们的归属关系。

    :param spus: 款编码列表（**没有**归属的款也要列进来 —— 它就是「空款」）。
    :param bindings: ``[(spu, sku_id, binding_status)]``，``binding_status``
        取 ``active`` / ``inactive`` / ``historical``。
    """
    from modules.core.db import BridgeSpuSku, DimSpu

    for spu in spus:
        session.add(DimSpu(spu=spu, spu_name=spu, biz_status="candidate", active=True))
    await session.flush()
    for spu, sku_id, binding_status in bindings:
        session.add(
            BridgeSpuSku(
                spu=spu,
                sku_id=sku_id,
                effective_from=date(2026, 11, 13),
                effective_to=None,
                binding_status=binding_status,
            )
        )
    await session.flush()


@pytest.mark.asyncio
async def test_value_domain_default_order_lists_busiest_spus_first(
    spu_value_domain_session,
):
    """默认候选必须按「当前挂货数」排 —— 否则运营看不到真正在经营的款。

    背景（2026-11-13 实测，生产）：284 个在售款按编码排序时，前 50 个是
    ``XH-BABY-MC`` ~ ``XH-FASHION-695`` ⇒ **玩具类几乎永远不在默认候选里**
    （``XH-TOYS-MYTK`` 排第 277 位）⇒ 运营不输入关键词就选不到那些款。

    ⚠️ 种子数据刻意让「编码升序」与「挂货数降序」**结论相反**
    （ALPHA < MID < ZULU，但挂货数是 0 < 1 < 2）⇒ 旧实现（按编码排）
       必定红 ⇒ 这条断言不是"写完就绿"的假测试。
    """
    await _seed_spus_and_bindings(
        spu_value_domain_session,
        ["XH-ALPHA", "XH-MID", "XH-ZULU"],
        [
            ("XH-MID", 501, "active"),
            ("XH-ZULU", 502, "active"),
            ("XH-ZULU", 503, "active"),
        ],
    )

    result = await list_spu_options(db=spu_value_domain_session, keyword=None, limit=50)

    assert [item.spu for item in result.data] == ["XH-ZULU", "XH-MID", "XH-ALPHA"]


@pytest.mark.asyncio
async def test_value_domain_default_order_ignores_closed_bindings(
    spu_value_domain_session,
):
    """只有**当前有效**的归属算数 —— 已封存/已归档的不能把款顶到前面。"""
    await _seed_spus_and_bindings(
        spu_value_domain_session,
        ["XH-ALPHA", "XH-ZULU"],
        [
            ("XH-ZULU", 601, "active"),
            # 已换款归档（historical）与软删封存（inactive）都**不算**挂货
            ("XH-ALPHA", 602, "historical"),
            ("XH-ALPHA", 603, "inactive"),
        ],
    )

    result = await list_spu_options(db=spu_value_domain_session, keyword=None, limit=50)

    assert [item.spu for item in result.data] == ["XH-ZULU", "XH-ALPHA"]


@pytest.mark.asyncio
async def test_both_value_domain_endpoints_share_the_same_order(
    spu_value_domain_session,
):
    """两个口径端点必须用**同一份**排序 ⇒ 不会一个按编码、一个按挂货数。"""
    await _seed_spus_and_bindings(
        spu_value_domain_session,
        ["XH-ALPHA", "XH-ZULU"],
        [
            ("XH-ZULU", 701, "active"),
            ("XH-ZULU", 702, "active"),
        ],
    )

    browse = await list_spu_options(db=spu_value_domain_session, keyword=None, limit=50)
    assignable = await list_spu_assignable_options(
        db=spu_value_domain_session, keyword=None, limit=50
    )

    assert [item.spu for item in browse.data] == [item.spu for item in assignable.data]
    assert [item.spu for item in browse.data] == ["XH-ZULU", "XH-ALPHA"]


def test_spu_option_order_counts_only_current_bindings():
    """挂货数的口径必须来自真源 ``current_binding_condition()`` —— 不许手抄。

    ⚠️ 律 1「真源只能一个」：如果这里手写 ``effective_to IS NULL``，
       一旦归属状态定义变了，排序就会和别的口径**悄悄漂移**
       （下拉顺序与「这个款现在挂几个货」显示不一致）。
    """
    from sqlalchemy import select

    from modules.core.db import DimSpu
    from backend.domains.business.routers.product_center import _spu_option_order

    sql = str(
        select(DimSpu.spu)
        .order_by(*_spu_option_order())
        .compile(compile_kwargs={"literal_binds": True})
    )
    order_by_sql = sql.split("ORDER BY", 1)[1]

    assert "count(core.bridge_spu_sku.sku_id)" in order_by_sql
    assert "core.bridge_spu_sku.binding_status = 'active'" in order_by_sql
    assert "core.bridge_spu_sku.effective_to IS NULL" in order_by_sql
    # 同分时按编码升序 ⇒ 顺序稳定，运营不会看到「每次刷都不一样」
    #    （SQLAlchemy 不渲染默认的 ``ASC`` ⇒ 这里只断言它排在最后）
    assert order_by_sql.rstrip().endswith("core.dim_spu.spu")


# ---------------------------------------------------------------------------
# 归属规则
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_sku_save_cannot_bind_a_retired_spu():
    """批量保存 SKU 时把货挂到已淘汰的款上 —— 必须拒绝。"""
    db = _BindingDb(spu_row=_spu(active=True, biz_status="retired"))

    with pytest.raises(HTTPException) as exc:
        await _apply_bulk_sku_spu_binding(db, _sku(), "XH-TEST", None)

    assert exc.value.status_code == 422
    assert db.added == []


@pytest.mark.asyncio
async def test_bulk_sku_save_cannot_bind_a_soft_deleted_spu():
    """已软删的款 —— 必须拒绝。

    ⚠️ 建模 A 的不变量（``active=false ⟹ biz_status='retired'``）让这一条
    由 biz_status 判定即可覆盖，但本用例独立锁住它，防止不变量被破坏后静默放行。
    """
    db = _BindingDb(spu_row=_spu(active=False, biz_status="retired"))

    with pytest.raises(HTTPException) as exc:
        await _apply_bulk_sku_spu_binding(db, _sku(), "XH-TEST", None)

    assert exc.value.status_code == 422
    assert db.added == []


@pytest.mark.asyncio
async def test_bulk_sku_save_cannot_bind_an_unknown_spu():
    db = _BindingDb(spu_row=None)

    with pytest.raises(HTTPException) as exc:
        await _apply_bulk_sku_spu_binding(db, _sku(), "XH-NOPE", None)

    assert exc.value.status_code == 422
    assert db.added == []


@pytest.mark.asyncio
async def test_bulk_sku_save_still_binds_an_active_spu():
    """规则不能误伤正常路径：在售的款必须还能挂货。"""
    db = _BindingDb(spu_row=_spu(active=True, biz_status="candidate"))

    await _apply_bulk_sku_spu_binding(db, _sku(), "XH-TEST", date(2026, 11, 12))

    assert len(db.added) == 1
    assert db.added[0].spu == "XH-TEST"


@pytest.mark.asyncio
async def test_sku_ownership_binding_endpoint_cannot_bind_a_retired_spu(
    stub_side_effects,
):
    """「SKU 归属」抽屉里的绑定入口同样要守规则 —— 两处入口必须一致。"""
    db = _BindingDb(spu_row=_spu(active=True, biz_status="retired"), sku_row=_sku())
    body = SpuSkuBindingRequest(sku_id=7, effective_from=date(2026, 11, 12))

    with pytest.raises(HTTPException) as exc:
        await bind_spu_sku(
            spu="XH-TEST",
            body=body,
            db=db,
            current_user=SimpleNamespace(user_id=1, role="admin"),
        )

    assert exc.value.status_code == 422
    assert db.added == []
