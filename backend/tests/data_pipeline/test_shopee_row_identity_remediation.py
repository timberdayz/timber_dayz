"""``20261117_remediate_shopee_row_identity_conflicts`` 迁移的行为守护测试。

为什么要有这个测试
----------------
历史订正迁移改的是**已经落库的事实行** —— 一旦方向错了, 业务数据(访客数/GMV)
会被**搬到别的店**下面去, 而且看板数字看不出异常(行数与 UV 总量都不变)。
所以必须把方向与不变量钉死。

测试环境
--------
按 ``backend/tests/conftest.py`` 的**测试护栏**: pytest 期间 ``DATABASE_URL``
被指向一次性隔离库(testcontainers), **绝不允许连真实业务库**。
本文件在隔离库里**自造数据**, 验证迁移行为 —— 不依赖开发库的数据状态,
也不会碰到真实业务库。

锁住的不变量
------------
1. **订正方向 = 编号权威** —— 行内编号反查到哪个账号, 行就归哪个账号。
   (UV 量级证据: 错配行 avg 786.9 吻合 xhkj11.ph(896.4) 而非 xhkj11.sg(314.7))
2. **只改身份字段** —— 业务字段一个都不动。
3. **``data_hash`` 一个字节都不变** —— 否则重采会插重复行。
4. **幂等** —— 重跑 0 行。
5. **可回滚** —— 从留痕键原样还原。
6. **停用店 / 编号未登记的行不动**。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import text


REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_PATH = (
    REPO_ROOT
    / "current_migrations"
    / "versions"
    / "20261117_remediate_shopee_row_identity_conflicts.py"
)

ANALYTICS_TABLE = "b_class.fact_shopee_analytics_monthly"

#: 自造的两个在营 Shopee 店(A = 标签所属, B = 编号所属) + 一个停用店
ACCOUNT_A_ID = 9001
ACCOUNT_B_ID = 9002
ACCOUNT_OFF_ID = 9003
ACCOUNT_A_SAID = "shopee_sg_alpha_local"
ACCOUNT_B_SAID = "shopee_ph_beta_local"
ACCOUNT_A_PSID = "1111111"
ACCOUNT_B_PSID = "2222222"
ACCOUNT_OFF_PSID = "3333333"

FACT_ID = 9001
FACT_DATA_HASH = "hash-alpha-row-001"


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "migration_20261117_shopee_identity", MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def migration():
    return _load_migration()


def _update_sql(migration, table=ANALYTICS_TABLE) -> str:
    """订正语句。

    ⚠️ 用 ``.replace`` 而不是 ``.format`` —— ``_ROLLBACK_SQL`` 里有一对
    ``{{}}``(JSONB 空对象), 迁移在模块加载时已把它转成了字面 ``{}``;
    再走一次 ``.format`` 会把 ``{}`` 当成占位符 ⇒ IndexError。
    """
    return migration._UPDATE_SQL.replace("{table}", table)


def _rollback_sql(migration, table=ANALYTICS_TABLE) -> str:
    return migration._ROLLBACK_SQL.replace("{table}", table)


async def _ensure_fact_table(pg_session) -> None:
    """隔离库里没有这张**动态列表**(它由 RawDataImporter 运行时建, ORM 不定义它)。

    这里按迁移实际用到的列建一张最小表; DDL 随 ``pg_session`` 的事务一起回滚。
    """
    await pg_session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS b_class.fact_shopee_analytics_monthly (
                id               bigint PRIMARY KEY,
                platform_code    varchar(32) NOT NULL,
                shop_id          varchar(256),
                data_domain      varchar(64) DEFAULT 'analytics' NOT NULL,
                granularity      varchar(32) DEFAULT 'monthly' NOT NULL,
                sub_domain       varchar(64),
                metric_date      date NOT NULL,
                raw_data         jsonb NOT NULL,
                header_columns   jsonb,
                data_hash        varchar(64) NOT NULL,
                ingest_timestamp timestamptz DEFAULT now()
            )
            """
        )
    )


async def _seed(pg_session) -> None:
    """在隔离库里造出「一行自相矛盾的事实行」。"""
    await _ensure_fact_table(pg_session)
    # 主账号(shop_accounts.main_account_id 是指向 core.main_accounts.main_account_id 的 FK)
    await pg_session.execute(
        text(
            """
            INSERT INTO core.main_accounts
                (id, platform, main_account_id, username, password_encrypted, enabled)
            VALUES
                (8001, 'shopee', 'MA-1', 'alpha-user', 'x', true),
                (8002, 'shopee', 'MA-2', 'beta-user', 'x', true),
                (8003, 'shopee', 'MA-3', 'off-user', 'x', true)
            """
        )
    )
    await pg_session.execute(
        text(
            """
            INSERT INTO core.shop_accounts
                (id, platform, shop_account_id, main_account_id, store_name,
                 platform_shop_id, shop_region, enabled, business_role)
            VALUES
                (:a_id, 'shopee', :a_said, 'MA-1', 'alpha.sg',
                 :a_psid, 'SG', true, 'operating_store'),
                (:b_id, 'shopee', :b_said, 'MA-2', 'beta.ph',
                 :b_psid, 'PH', true, 'operating_store'),
                (:off_id, 'shopee', 'shopee_my_off_local', 'MA-3', 'off.my',
                 :off_psid, 'MY', false, 'operating_store')
            """
        ),
        {
            "a_id": ACCOUNT_A_ID,
            "a_said": ACCOUNT_A_SAID,
            "a_psid": ACCOUNT_A_PSID,
            "b_id": ACCOUNT_B_ID,
            "b_said": ACCOUNT_B_SAID,
            "b_psid": ACCOUNT_B_PSID,
            "off_id": ACCOUNT_OFF_ID,
            "off_psid": ACCOUNT_OFF_PSID,
        },
    )
    await pg_session.execute(
        text(
            """
            INSERT INTO b_class.fact_shopee_analytics_monthly
                (id, platform_code, shop_id, data_domain, granularity,
                 metric_date, raw_data, data_hash)
            VALUES
                (:id, 'shopee', :num_psid, 'analytics', 'monthly',
                 DATE '2026-06-22',
                 jsonb_build_object(
                     'shop_account_id', CAST(:a_said AS text),
                     'store_name', 'alpha.sg',
                     'shop_id', CAST(:num_psid AS varchar),
                     '访客数', '807',
                     '页面浏览数', '1234',
                     '日期', '22/06/2026'
                 ),
                 :data_hash)
            """
        ),
        {
            "id": FACT_ID,
            "num_psid": ACCOUNT_B_PSID,
            "a_said": ACCOUNT_A_SAID,
            "data_hash": FACT_DATA_HASH,
        },
    )


async def _fetch(pg_session):
    result = await pg_session.execute(
        text(
            """
            SELECT raw_data ->> 'shop_account_id' AS said,
                   raw_data ->> 'store_name'       AS name,
                   raw_data ->> 'shop_id'          AS sid,
                   raw_data ->> 'platform_shop_id' AS psid,
                   shop_id                          AS col_sid,
                   raw_data ->> '访客数'             AS uv,
                   raw_data ->> '页面浏览数'          AS pv,
                   raw_data ->> '日期'              AS d,
                   data_hash                        AS data_hash,
                   raw_data ? '{audit}'             AS has_audit
            FROM {table}
            WHERE id = :id
            """.format(
                table=ANALYTICS_TABLE, audit="__audit__"
            )
        ),
        {"id": FACT_ID},
    )
    row = result.mappings().first()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# 迁移链
# ---------------------------------------------------------------------------


def test_migration_chain(migration):
    """迁移链的 revision / down_revision 必须是预期值。"""
    assert (
        migration.revision
        == "current_schema_20261117_remediate_shopee_row_identity_conflicts"
    )
    assert migration.down_revision == (
        "current_schema_20261116_add_tiktok_export_store_name_aliases"
    )


def test_required_refresh_targets_are_registered(migration):
    """订正后必须刷的物化视图不能少。"""
    assert "semantic.fact_analytics_atomic_mv" in migration._REQUIRED_REFRESH_TARGETS
    assert (
        "semantic.fact_analytics_monthly_atomic_mv"
        in migration._REQUIRED_REFRESH_TARGETS
    )
    assert "semantic.fact_products_atomic_mv" in migration._REQUIRED_REFRESH_TARGETS


# ---------------------------------------------------------------------------
# 订正行为
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remediation_follows_the_platform_number(pg_session, migration):
    """订正方向 = **编号权威**: 行归到「行内编号所属」的账号。

    ⚠️ 这是最关键的一条: 方向反了会把业务数据搬到别的店下面, 而且看板看不出来。
    """
    await _seed(pg_session)
    before = await _fetch(pg_session)
    assert before["said"] == ACCOUNT_A_SAID
    assert before["sid"] == ACCOUNT_B_PSID

    await pg_session.execute(text(_update_sql(migration)))

    after = await _fetch(pg_session)
    assert after["said"] == ACCOUNT_B_SAID, "必须归到编号所属的账号"
    assert after["sid"] == ACCOUNT_B_PSID
    assert after["psid"] == ACCOUNT_B_PSID
    assert after["col_sid"] == ACCOUNT_B_PSID


@pytest.mark.asyncio
async def test_remediation_keeps_business_fields_and_data_hash(pg_session, migration):
    """业务字段与 ``data_hash`` 一个都不许动。"""
    await _seed(pg_session)
    before = await _fetch(pg_session)

    await pg_session.execute(text(_update_sql(migration)))

    after = await _fetch(pg_session)
    assert after["uv"] == before["uv"]
    assert after["pv"] == before["pv"]
    assert after["d"] == before["d"]
    assert after["data_hash"] == before["data_hash"]


@pytest.mark.asyncio
async def test_remediation_is_idempotent(pg_session, migration):
    """重跑必须 0 行 —— 幂等。"""
    await _seed(pg_session)
    await pg_session.execute(text(_update_sql(migration)))
    second = await pg_session.execute(text(_update_sql(migration)))
    assert int(second.rowcount or 0) == 0


@pytest.mark.asyncio
async def test_remediation_keeps_original_identity_for_audit(pg_session, migration):
    """原始身份必须留痕(可回滚 + 可审计)。"""
    await _seed(pg_session)
    await pg_session.execute(text(_update_sql(migration)))

    result = await pg_session.execute(
        text(
            "SELECT raw_data -> '{key}' AS audit FROM {table} WHERE id = :id".format(
                table=ANALYTICS_TABLE, key=migration._AUDIT_KEY
            )
        ),
        {"id": FACT_ID},
    )
    audit = result.mappings().first()["audit"]

    assert audit is not None, "必须留痕原始身份"
    assert audit["shop_account_id"] == ACCOUNT_A_SAID
    assert audit["store_name"] == "alpha.sg"
    assert audit["shop_id"] == ACCOUNT_B_PSID


@pytest.mark.asyncio
async def test_rollback_restores_original_identity(pg_session, migration):
    """回滚必须把 4 个身份字段原样还原。"""
    await _seed(pg_session)

    await pg_session.execute(text(_update_sql(migration)))
    await pg_session.execute(text(_rollback_sql(migration)))

    after = await _fetch(pg_session)
    assert after["said"] == ACCOUNT_A_SAID
    assert after["name"] == "alpha.sg"
    assert after["sid"] == ACCOUNT_B_PSID
    assert after["col_sid"] == ACCOUNT_B_PSID
    assert after["has_audit"] is False, "回滚后留痕键必须被删掉"


@pytest.mark.asyncio
async def test_disabled_account_rows_are_not_touched(pg_session, migration):
    """停用店的编号不构成歧义(它不在语义层候选池里) ⇒ 行不动。"""
    await _seed(pg_session)
    await pg_session.execute(
        text(
            """
            INSERT INTO b_class.fact_shopee_analytics_monthly
                (id, platform_code, shop_id, data_domain, granularity,
                 metric_date, raw_data, data_hash)
            VALUES
                (9002, 'shopee', :off_psid, 'analytics', 'monthly',
                 DATE '2026-06-22',
                 jsonb_build_object(
                     'shop_account_id', 'shopee_my_off_local',
                     'store_name', 'off.my',
                     'shop_id', CAST(:off_psid AS varchar)
                 ),
                 'hash-off-row')
            """
        ),
        {"off_psid": ACCOUNT_OFF_PSID},
    )

    await pg_session.execute(text(_update_sql(migration)))

    result = await pg_session.execute(
        text(
            "SELECT raw_data ->> 'shop_account_id' AS said, data_hash "
            "FROM {table} WHERE id = 9002".format(table=ANALYTICS_TABLE)
        )
    )
    row = result.mappings().first()
    assert row["said"] == "shopee_my_off_local"
    assert row["data_hash"] == "hash-off-row"


@pytest.mark.asyncio
async def test_unregistered_numbers_are_left_untouched(pg_session, migration):
    """编号在主数据里查不到的行不动(它不命中任何候选 ⇒ 不构成歧义)。"""
    await _seed(pg_session)
    await pg_session.execute(
        text(
            """
            INSERT INTO b_class.fact_shopee_analytics_monthly
                (id, platform_code, shop_id, data_domain, granularity,
                 metric_date, raw_data, data_hash)
            VALUES
                (9003, 'shopee', '9999999', 'analytics', 'monthly',
                 DATE '2026-06-22',
                 jsonb_build_object(
                     'shop_account_id', 'shopee_my_ghost_local',
                     'store_name', 'ghost.my',
                     'shop_id', '9999999'
                 ),
                 'hash-ghost-row')
            """
        )
    )

    await pg_session.execute(text(_update_sql(migration)))

    result = await pg_session.execute(
        text(
            "SELECT raw_data ->> 'shop_account_id' AS said, data_hash "
            "FROM {table} WHERE id = 9003".format(table=ANALYTICS_TABLE)
        )
    )
    row = result.mappings().first()
    assert row["said"] == "shopee_my_ghost_local"
    assert row["data_hash"] == "hash-ghost-row"
