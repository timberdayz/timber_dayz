"""阶段 2.1b · 人工覆盖下沉到「SKU × 平台」的回归测试。

这一阶段要钉死四件事：

1. **人工覆盖写进平台级新表** —— 不再写 SKU 主数据。
2. **覆盖值是平台级的** —— TikTok 的覆盖**不影响** Shopee 的底线，反之亦然。
3. **重置为自动值** —— 清掉覆盖后回到系统算的底线。
4. **新表能活过「采集机 → 云端」同步** —— 这是本阶段真正的业务价值：
   同步脚本对 ``core.dim_erp_sku`` 做 ``TRUNCATE ... RESTART IDENTITY CASCADE``，
   而 PostgreSQL 的 ``TRUNCATE ... CASCADE`` **不看引用侧的 ondelete**，
   只要有外键指着被清空的表，那张表就一起被清空。
   ⇒ 覆盖值所在的表**必须没有外键**，否则运营刚设的护栏上限每次同步都蒸发。

第 4 条是**红线**：它是「人工覆盖存在过，但每次同步后悄悄消失」这类
静默数据丢失的唯一防线。
"""

from __future__ import annotations

import importlib.util
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from backend.services.product_pricing_override_service import (
    MANUAL_OVERRIDE_SOURCE,
    clear_platform_override,
    get_platform_override,
    set_platform_override,
)
from backend.services.product_pricing_query_service import (
    compute_pricing_state,
    load_pricing_context,
)
from backend.utils.project_env import isolated_database_url


VERSIONS_DIR = Path("current_migrations/versions")
SINK_MIGRATION = VERSIONS_DIR / "20261118_sink_manual_override_to_platform.py"

TIKTOK_OTHER_COST_RATE = Decimal("0.2727")
TIKTOK_CREATOR_RATE = Decimal("0.0606")
SHOPEE_OTHER_COST_RATE = Decimal("0.4165")
SHOPEE_CREATOR_RATE = Decimal("0.0111")

PURCHASE_COST = Decimal("45.20")
SPU_RETURN_LOSS_RATE = Decimal("0.0467")
SPU_DAMAGE_RATE = Decimal("0.0158")
TARGET_MARGIN_RATE = Decimal("0.25")
DISCOUNT_RATE = Decimal("0.10")
REFERENCE_SELLING_PRICE = Decimal("30.00")

TIKTOK_FLOOR = Decimal("127.61")
SHOPEE_FLOOR = Decimal("173.91")
DISCOUNT_GUARD = Decimal("27.00")


def _load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "sink_migration_under_test", SINK_MIGRATION
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _floor(payload: dict) -> Decimal:
    value = payload["min_selling_price"]
    assert value is not None, payload
    return Decimal(str(value))


# ---------------------------------------------------------------------------
# SQLite 夹具
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def pricing_sqlite_session():
    """只建本用例需要的表的 SQLite 会话（与阶段 2.1 的夹具同款）。"""
    from modules.core.db import Base

    wanted = (
        "core.dim_platforms",
        "core.dim_spu",
        "core.dim_erp_sku",
        "core.bridge_spu_sku",
        "finance.sku_pricing_policies",
        "finance.sku_platform_pricing",
    )
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.connect() as conn:
        for schema in ("core", "finance", "ops"):
            await conn.exec_driver_sql(f"ATTACH DATABASE ':memory:' AS {schema}")
        for name in wanted:
            await conn.run_sync(Base.metadata.tables[name].create, checkfirst=True)
        async with AsyncSession(conn) as session:
            yield session
    await engine.dispose()


async def _seed_two_platforms(session) -> int:
    from modules.core.db import (
        BridgeSpuSku,
        DimErpSku,
        DimPlatform,
        DimSpu,
        SkuPricingPolicy,
    )

    session.add_all(
        [
            DimPlatform(
                platform_code="tiktok",
                name="TikTok",
                default_creator_commission_rate=TIKTOK_CREATOR_RATE,
                other_cost_rate=TIKTOK_OTHER_COST_RATE,
                platform_role="sales",
                is_active=True,
            ),
            DimPlatform(
                platform_code="shopee",
                name="Shopee",
                default_creator_commission_rate=SHOPEE_CREATOR_RATE,
                other_cost_rate=SHOPEE_OTHER_COST_RATE,
                platform_role="sales",
                is_active=True,
            ),
            DimPlatform(
                platform_code="miaoshou",
                name="妙手（库存来源）",
                platform_role="source",
                is_active=True,
            ),
            SkuPricingPolicy(
                min_restock_days=0,
                tier_label="日常",
                discount_rate=DISCOUNT_RATE,
                target_margin_rate=TARGET_MARGIN_RATE,
                platform_basis="tiktok",
                effective_from=date(2026, 1, 1),
                effective_to=None,
                status="active",
                source="test",
            ),
            DimSpu(
                spu="SPU-1",
                spu_name="测试 SPU",
                logistics_damage_rate=SPU_DAMAGE_RATE,
                return_loss_rate=SPU_RETURN_LOSS_RATE,
                biz_status="active",
                active=True,
            ),
        ]
    )
    sku = DimErpSku(
        sku_key="SKU-TEST-1",
        sku_name="测试 SKU",
        specification="1 件",
        default_purchase_cost=PURCHASE_COST,
        purchase_cost_currency="CNY",
        purchase_cost_confidence="high",
        reference_selling_price=REFERENCE_SELLING_PRICE,
        # 阶段 4 工具 2：有基准售价就必须有确认日期
        selling_price_confirmed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        selling_price_currency="CNY",
        status="active",
    )
    session.add(sku)
    await session.flush()
    session.add(
        BridgeSpuSku(
            spu="SPU-1",
            sku_id=sku.sku_id,
            effective_from=date(2026, 1, 1),
            effective_to=None,
            binding_status="active",
        )
    )
    await session.flush()
    return sku.sku_id


async def _floors_by_platform(session, sku_id: int) -> dict[str, Decimal]:
    from modules.core.db import DimErpSku, DimSpu

    context = await load_pricing_context(session, [sku_id], ["tiktok", "shopee"])
    sku_row = await session.get(DimErpSku, sku_id)
    linked_spu = await session.get(DimSpu, "SPU-1")
    floors = {}
    for platform_code in ("tiktok", "shopee"):
        state = compute_pricing_state(
            context=context,
            sku_row=sku_row,
            linked_spu=linked_spu,
            platform_code=platform_code,
        )
        floors[platform_code] = _floor(state["pricing"])
    return floors


# ---------------------------------------------------------------------------
# ① 写入路径：覆盖值落平台级新表，且**不**落 SKU 主数据
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_override_is_written_to_the_platform_table(pricing_sqlite_session):
    """设置覆盖 ⇒ 写进 ``finance.sku_platform_pricing``，来源标记为 manual_override。"""
    from modules.core.db import SkuPlatformPricing

    session = pricing_sqlite_session
    sku_id = await _seed_two_platforms(session)

    row = await set_platform_override(
        session, sku_id=sku_id, platform_code="shopee", value=250.00, user_id=7
    )

    assert Decimal(str(row.min_selling_price_override)) == Decimal("250.00")
    assert row.min_selling_price_source == MANUAL_OVERRIDE_SOURCE
    assert row.created_by == 7

    await session.commit()

    stored = (
        await session.execute(
            select(SkuPlatformPricing).where(
                SkuPlatformPricing.sku_id == sku_id,
                SkuPlatformPricing.platform_code == "shopee",
            )
        )
    ).scalars().all()
    assert len(stored) == 1
    assert Decimal(str(stored[0].min_selling_price_override)) == Decimal("250.00")


@pytest.mark.asyncio
async def test_setting_an_override_twice_updates_the_same_row(pricing_sqlite_session):
    """同一 SKU × 平台重复设置 ⇒ **同一行**被更新，不插第二行。"""
    from modules.core.db import SkuPlatformPricing

    session = pricing_sqlite_session
    sku_id = await _seed_two_platforms(session)

    await set_platform_override(
        session, sku_id=sku_id, platform_code="shopee", value=250.00
    )
    await set_platform_override(
        session, sku_id=sku_id, platform_code="shopee", value=260.00
    )
    await session.commit()

    rows = (
        await session.execute(
            select(SkuPlatformPricing).where(
                SkuPlatformPricing.sku_id == sku_id,
                SkuPlatformPricing.platform_code == "shopee",
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    assert Decimal(str(rows[0].min_selling_price_override)) == Decimal("260.00")


@pytest.mark.asyncio
async def test_override_must_be_positive(pricing_sqlite_session):
    """0 / 负数不是「不设覆盖」，而是「把底线压到 0」= 把护栏关掉 ⇒ 必须拒。"""
    session = pricing_sqlite_session
    sku_id = await _seed_two_platforms(session)

    with pytest.raises(ValueError):
        await set_platform_override(
            session, sku_id=sku_id, platform_code="shopee", value=0
        )
    with pytest.raises(ValueError):
        await set_platform_override(
            session, sku_id=sku_id, platform_code="shopee", value=-1
        )
    with pytest.raises(ValueError):
        await set_platform_override(
            session, sku_id=sku_id, platform_code="shopee", value=None
        )


# ---------------------------------------------------------------------------
# ② 覆盖值是平台级的：TikTok 的覆盖不影响 Shopee
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_override_on_one_platform_does_not_touch_the_other(pricing_sqlite_session):
    """TikTok 设了覆盖 ⇒ **只有** TikTok 的底线被抬起来，Shopee 不变。"""
    session = pricing_sqlite_session
    sku_id = await _seed_two_platforms(session)

    before = await _floors_by_platform(session, sku_id)
    assert before["tiktok"] == TIKTOK_FLOOR
    assert before["shopee"] == SHOPEE_FLOOR

    await set_platform_override(
        session, sku_id=sku_id, platform_code="tiktok", value=300.00
    )
    await session.commit()

    after = await _floors_by_platform(session, sku_id)
    assert after["tiktok"] == Decimal("300.00")   # 被覆盖值抬起来
    assert after["shopee"] == SHOPEE_FLOOR        # 一个字节都没变


@pytest.mark.asyncio
async def test_override_replaces_the_floor_entirely(pricing_sqlite_session):
    """人工覆盖**取代**底线（不是参与取最大）。

    这是阶段 0 就定下的语义（``compute_min_selling_price``）：
    运营明确说「这个 SKU 的最低售价就是 X」⇒ 底线就是 X，
    哪怕它低于成本线（清货意图）与纪律线。

    界面上用来源标签 ``manual_override`` 明写这是人工值，不是系统算的。
    """
    session = pricing_sqlite_session
    sku_id = await _seed_two_platforms(session)

    # 覆盖值低于成本线（127.61）⇒ 底线就是覆盖值本身
    await set_platform_override(
        session, sku_id=sku_id, platform_code="tiktok", value=10.00
    )
    await session.commit()
    floors = await _floors_by_platform(session, sku_id)
    assert floors["tiktok"] == Decimal("10.00")
    # 纪律线（27.00）在本夹具里低于成本线 ⇒ 不参与取最大；这里只把它钉住。
    assert DISCOUNT_GUARD < TIKTOK_FLOOR

    # 覆盖值高于成本线 ⇒ 底线就是覆盖值
    await set_platform_override(
        session, sku_id=sku_id, platform_code="tiktok", value=200.00
    )
    await session.commit()
    floors = await _floors_by_platform(session, sku_id)
    assert floors["tiktok"] == Decimal("200.00")


# ---------------------------------------------------------------------------
# ③ 重置为自动值
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clear_override_returns_to_the_system_floor(pricing_sqlite_session):
    """重置 ⇒ 回到系统算的底线（不是把底线压到 0）。"""
    session = pricing_sqlite_session
    sku_id = await _seed_two_platforms(session)

    await set_platform_override(
        session, sku_id=sku_id, platform_code="shopee", value=250.00
    )
    await session.commit()
    floors = await _floors_by_platform(session, sku_id)
    assert floors["shopee"] == Decimal("250.00")

    cleared = await clear_platform_override(
        session, sku_id=sku_id, platform_code="shopee"
    )
    await session.commit()
    assert cleared is True

    floors = await _floors_by_platform(session, sku_id)
    assert floors["shopee"] == SHOPEE_FLOOR
    assert await get_platform_override(session, sku_id, "shopee") is None


@pytest.mark.asyncio
async def test_clearing_a_missing_override_is_a_noop(pricing_sqlite_session):
    """没设过覆盖就重置 ⇒ 不报错，明确返回「没清掉任何东西」。"""
    session = pricing_sqlite_session
    sku_id = await _seed_two_platforms(session)

    cleared = await clear_platform_override(
        session, sku_id=sku_id, platform_code="shopee"
    )
    assert cleared is False


# ---------------------------------------------------------------------------
# ④ 新表能活过「采集机 → 云端」同步（**红线**）
# ---------------------------------------------------------------------------


def test_platform_pricing_table_has_no_foreign_keys(isolated_engine):
    """``finance.sku_platform_pricing`` **不能有外键**（ORM 层面）。

    为什么是红线：同步脚本对 ``core.dim_erp_sku`` / ``core.dim_platforms``
    做 ``TRUNCATE ... RESTART IDENTITY CASCADE``，
    而 PostgreSQL 的 ``TRUNCATE ... CASCADE`` 会清空**所有**引用被清空表的表，
    **与引用侧声明的 ondelete 无关**（RESTRICT / CASCADE / NO ACTION 行为一样）。

    ⇒ 只要新表带着外键，运营设的「人工覆盖最低售价」每次同步都会被抹掉，
    而那正是护栏依赖的上限 ⇒ 抹掉 = 护栏形同虚设。

    这里查 ORM（元数据的唯一出处），而不是查某一时刻的数据库状态 ——
    数据库状态会被迁移改掉，ORM 才是「建出来的表长什么样」的事实来源。
    """
    from modules.core.db import SkuPlatformPricing

    fks = [
        fk
        for fk in SkuPlatformPricing.__table__.foreign_keys
    ]
    assert fks == [], f"覆盖表不能带外键（否则被 TRUNCATE CASCADE 连带清空）：{fks}"


def test_truncate_cascade_only_reaches_tables_with_foreign_keys(isolated_engine):
    """把 PostgreSQL 的这条规则本身钉死（用临时表，不碰业务表）。

    有外键的表被连带清空；没有外键的表**活下来**。
    这条规则就是「覆盖表不能带外键」那条断言的依据。
    """
    with isolated_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS _t_child_fk, _t_child_plain, _t_parent"))
        conn.execute(text("CREATE TABLE _t_parent (id integer PRIMARY KEY)"))
        conn.execute(
            text(
                "CREATE TABLE _t_child_fk (id integer PRIMARY KEY, "
                "parent_id integer REFERENCES _t_parent(id) ON DELETE CASCADE)"
            )
        )
        conn.execute(text("CREATE TABLE _t_child_plain (id integer PRIMARY KEY)"))
        conn.execute(text("INSERT INTO _t_parent VALUES (1)"))
        conn.execute(text("INSERT INTO _t_child_fk VALUES (1, 1)"))
        conn.execute(text("INSERT INTO _t_child_plain VALUES (1)"))

        conn.execute(text("TRUNCATE _t_parent RESTART IDENTITY CASCADE"))

        fk_rows = conn.execute(text("SELECT count(*) FROM _t_child_fk")).scalar()
        plain_rows = conn.execute(text("SELECT count(*) FROM _t_child_plain")).scalar()

        conn.execute(text("DROP TABLE IF EXISTS _t_child_fk, _t_child_plain, _t_parent"))

    assert fk_rows == 0, "带外键的子表应被 TRUNCATE CASCADE 连带清空"
    assert plain_rows == 1, "不带外键的表必须活下来（覆盖表靠的就是这一点）"


# ---------------------------------------------------------------------------
# ⑤ 迁移：幂等 + 可回退 + 旧列数据迁移
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def isolated_engine():
    url = isolated_database_url()
    if not url:
        pytest.skip("隔离测试库地址未就绪")
    engine = create_engine(url)
    yield engine
    engine.dispose()


def _run_migration(engine, module, func_name: str) -> None:
    def _do(connection):
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            getattr(module, func_name)()

    with engine.begin() as connection:
        _do(connection)


def _fk_constraint_names(engine) -> list[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid = 'finance.sku_platform_pricing'::regclass "
                "AND contype = 'f'"
            )
        ).all()
    return [row[0] for row in rows]


def test_sink_migration_is_repeatable_and_rolls_back_cleanly(isolated_engine):
    """真实 PostgreSQL 上跑：upgrade ×2 → downgrade → upgrade。

    隔离库是从 ORM 建的，所以「迁移前的样子」（旧列 + 两个外键）要**自己造出来**，
    否则测的只是「迁移对已经改好的库做什么」。
    """
    module = _load_migration_module()
    _restore_pre_migration_shape(isolated_engine)

    _run_migration(isolated_engine, module, "upgrade")
    _run_migration(isolated_engine, module, "upgrade")

    inspector = inspect(isolated_engine)
    sku_columns = {
        column["name"]
        for column in inspector.get_columns("dim_erp_sku", schema="core")
    }
    assert "min_selling_price_override" not in sku_columns

    assert _fk_constraint_names(isolated_engine) == [], (
        "迁移必须把两个外键摘掉（否则同步会连带清空覆盖值）"
    )

    _run_migration(isolated_engine, module, "downgrade")

    inspector = inspect(isolated_engine)
    sku_columns = {
        column["name"]
        for column in inspector.get_columns("dim_erp_sku", schema="core")
    }
    assert "min_selling_price_override" in sku_columns

    assert len(_fk_constraint_names(isolated_engine)) == 2, (
        "downgrade 必须把外键加回去"
    )

    _run_migration(isolated_engine, module, "upgrade")
    inspector = inspect(isolated_engine)
    sku_columns = {
        column["name"]
        for column in inspector.get_columns("dim_erp_sku", schema="core")
    }
    assert "min_selling_price_override" not in sku_columns


def _restore_pre_migration_shape(engine) -> None:
    """把隔离库摆成「阶段 2.1b 之前」的样子：旧列 + 两个外键 + 平台种子。

    隔离库是从 **ORM** 建的（``Base.metadata.create_all``），
    而 ORM 已经改过了 ⇒ 不自己摆一次，测的就不是迁移，而是「迁移对已经改好的库做什么」。
    """
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE core.dim_erp_sku "
                "ADD COLUMN IF NOT EXISTS min_selling_price_override numeric(18,2)"
            )
        )
        # 上一个用例的 downgrade 可能已经把约束加回来了 ⇒ 先摘再加。
        conn.execute(
            text(
                "ALTER TABLE core.dim_erp_sku DROP CONSTRAINT IF EXISTS "
                "ck_dim_erp_sku_min_selling_price_override"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE core.dim_erp_sku ADD CONSTRAINT "
                "ck_dim_erp_sku_min_selling_price_override "
                "CHECK (min_selling_price_override IS NULL "
                "OR min_selling_price_override > 0)"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE finance.sku_platform_pricing "
                "DROP CONSTRAINT IF EXISTS sku_platform_pricing_sku_id_fkey"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE finance.sku_platform_pricing "
                "DROP CONSTRAINT IF EXISTS sku_platform_pricing_platform_code_fkey"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE finance.sku_platform_pricing ADD CONSTRAINT "
                "sku_platform_pricing_sku_id_fkey FOREIGN KEY (sku_id) "
                "REFERENCES core.dim_erp_sku(sku_id) ON DELETE CASCADE"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE finance.sku_platform_pricing ADD CONSTRAINT "
                "sku_platform_pricing_platform_code_fkey FOREIGN KEY (platform_code) "
                "REFERENCES core.dim_platforms(platform_code) ON DELETE RESTRICT"
            )
        )
        # 平台种子：两个**可定价**销售平台 + 一个库存来源平台。
        conn.execute(text("DELETE FROM finance.sku_platform_pricing"))
        conn.execute(
            text(
                "INSERT INTO core.dim_platforms "
                "(platform_code, name, platform_role, is_active, other_cost_rate) "
                "VALUES ('tiktok','TikTok','sales',true,0.2727), "
                "('shopee','Shopee','sales',true,0.4165), "
                "('miaoshou','妙手','source',true,NULL) "
                "ON CONFLICT (platform_code) DO NOTHING"
            )
        )
        # SKU 种子：隔离库是空表（create_all 不灌数据），
        # 没有 SKU 行 ⇒ 旧列没有值 ⇒ 迁移的复制步骤无事可做。
        conn.execute(
            text(
                "INSERT INTO core.dim_erp_sku (sku_key, sku_name, "
                "purchase_cost_currency, purchase_cost_confidence, "
                "selling_price_currency, status, created_at, updated_at) "
                "VALUES ('SKU-MIG-1', '迁移测试 SKU', 'CNY', 'high', 'CNY', "
                "'active', NOW(), NOW()) "
                "ON CONFLICT (sku_key) DO NOTHING"
            )
        )


def test_sink_migration_copies_legacy_values_to_every_priceable_platform(
    isolated_engine,
):
    """旧列（公司级）的值 ⇒ 复制到**每一个可定价销售平台**。

    旧值对所有平台生效 ⇒ 迁到全部平台才是等价的；
    只迁一个平台 = 悄悄改变了其他平台的口径。
    库存来源平台（'miaoshou'，无 other_cost_rate）**不迁** ——
    覆盖值是「某个销售渠道上的最低售价下限」，库存来源平台不是销售渠道。
    """
    module = _load_migration_module()
    _restore_pre_migration_shape(isolated_engine)

    with isolated_engine.begin() as conn:
        conn.execute(text("DELETE FROM finance.sku_platform_pricing"))
        conn.execute(
            text(
                "UPDATE core.dim_erp_sku SET min_selling_price_override = 88.00 "
                "WHERE sku_id = (SELECT min(sku_id) FROM core.dim_erp_sku)"
            )
        )

    _run_migration(isolated_engine, module, "upgrade")

    with isolated_engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT platform_code, min_selling_price_override, "
                "min_selling_price_source FROM finance.sku_platform_pricing "
                "ORDER BY platform_code"
            )
        ).all()

    assert rows, "迁移后应有平台级覆盖行"
    codes = {row[0] for row in rows}
    assert codes == {"tiktok", "shopee"}, f"应迁到每个可定价平台，实际 {codes}"
    for row in rows:
        assert Decimal(str(row[1])) == Decimal("88.00")
        assert row[2] == "migrated_from_sku_level"


def test_sink_migration_is_chained_on_the_current_head():
    """迁移挂在当前 head 上（链不能分叉）。"""
    module = _load_migration_module()
    assert module.down_revision == (
        "current_schema_20261117_remediate_shopee_row_identity_conflicts"
    )
    assert module.revision == "current_schema_20261118_sink_manual_override_to_platform"
