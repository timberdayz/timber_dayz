"""批次 9 迁移的 **downgrade 往返**演练（20261239_cost_floor_caliber_closure）。

为什么要有这个文件
----------------
批次 9 的迁移会**删列**（``core.dim_platforms.delivery_cost_rate``）。
删列的 ``downgrade`` 是这条迁移链上**最危险的一段代码**：
删错了退不回来 ⇒ 生产上就是一次不可逆操作。

⚠️ 而现有的演练（``test_schema_cleanup_rehearsal.py``）**只跑 ``upgrade head``** ——
**从来没验过「退得回去」**。于是批次 9 的 downgrade 里真的藏着两个会当场崩的 bug：

1. ``op.drop_column(RETIRED_COLUMN, schema=..., table_name=...)`` ——
   SQLAlchemy 2.x 的签名是 ``(table_name, column_name, schema=...)``，
   再同时传 ``table_name=`` ⇒ ``TypeError: got multiple values for argument 'table_name'``
   ⇒ **整条迁移链在 upgrade 阶段就断**。
2. ``op.add_column(t, sa.Column(..., schema=SCHEMA))`` ——
   ``schema`` 是 **``op.add_column``** 的参数，**不能**传给 ``sa.Column`` 本身
   ⇒ ``TypeError: Additional arguments should be named <dialectname>_<argument>``。
   这条**只有真正跑 downgrade 才会暴露**。

本文件把「退得回去」变成**每次回归都跑**的守护。

跑的流程（全部在**隔离临时库**上，结束即删库）
--------------------------------------------
    baseline → 播种（数据依赖迁移需要的 TikTok 账号 + 平台行）
             → upgrade 20261238（列还在、桶是旧值）
             → upgrade head    （列被删、桶换新值）
             → downgrade 20261238（**必须**恢复列 + 旧桶值）
             → upgrade head    （再升上来，证明可重复）

断言的不是「不报错」，而是**数据真的还原了**：
列存在、桶值回到 0.4165 / 0.2727、``fee_rate_source`` 与 ``fee_rate_version`` 也回到旧值。
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from backend.utils.config import get_settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CURRENT_CHAIN_CONFIG = "alembic-current.ini"
BASELINE_REVISION = "current_schema_20260805"
PREV_REVISION = "current_schema_20261238_official_platform_fee_rates"


def _resolve_head_revision(env: dict[str, str]) -> str:
    """从当前迁移链解析**唯一**的 head。

    ⚠️ 为什么不再写死 head 字符串：
    每加一个迁移，写死的 head 就会红一次（2026-11-20 加 ``20261240`` 时就红了一次），
    而这个红跟被测的迁移**毫无关系** —— 它只说明「链头又前移了」。
    ⇒ 改为从链上解析，并**顺带断言链上只有一个 head**（分叉必须当场发现）。
    """
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", CURRENT_CHAIN_CONFIG, "heads"],
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"alembic heads failed\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    heads = []
    for line in completed.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        # ``alembic heads`` 的输出形如 ``<revision> (head)`` ⇒ 只取 revision 本身
        heads.append(line.split()[0])
    assert len(heads) == 1, "当前迁移链必须只有一个 head（实际：{0}）".format(heads)
    return heads[0]


#: 当前链里 ``20261116_add_tiktok_export_store_name_aliases`` 是**数据依赖**迁移：
#: 它要求库里已有这 6 个 TikTok 店铺账号，缺一个就 fail-closed 拒绝升级。
TIKTOK_EXPORT_ALIAS_ACCOUNTS = (
    ("DAONE Mall", "tiktok_sg_daone_mall_local", "SG"),
    ("DAWIE Mall", "tiktok_my_dawie_mall_local", "MY"),
    ("Explorers Mall", "tiktok_ph_explorers_mall_local", "PH"),
    ("Malaysia(Flora Mall)", "tiktok_my_flora_mall_local", "MY"),
    ("Philippines(DAJU Mall)", "tiktok_ph_daju_mall_local", "PH"),
    ("Singapore(HX Home)", "tiktok_sg_hx_home_local", "SG"),
)
REHEARSAL_MAIN_ACCOUNT_ID = "rehearsal-main-account"

#: 旧口径的桶值与来源（批次 9 迁移的 ``LEGACY_*`` 常量，见迁移文件）。
LEGACY_BUCKET = {"shopee": 0.4165, "tiktok": 0.2727}
LEGACY_VERSION = "v3"
#: 新口径的桶值（结算单实测）。
NEW_BUCKET = {"shopee": 0.0358, "tiktok": 0.0311}
NEW_VERSION = "v4"


def _run_alembic(args: list[str], env: dict[str, str]) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", CURRENT_CHAIN_CONFIG, *args],
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=1800,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"alembic {' '.join(args)} failed\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )


def _seed(engine) -> None:
    """补上迁移链需要的种子数据。

    ⚠️ 基线版本的 ``core.dim_platforms`` 只有 5 个列（费率列是后续迁移加的），
    所以平台行**先按基线列插**，费率值等到升过 20261237/20261238 之后再写。
    """
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO core.main_accounts (
                    platform, main_account_id, username, password_encrypted, main_account_name
                ) VALUES (
                    'tiktok', :main_account_id, 'rehearsal', 'x', 'Rehearsal Main Account'
                )
                """
            ),
            {"main_account_id": REHEARSAL_MAIN_ACCOUNT_ID},
        )
        for store_name, shop_account_id, shop_region in TIKTOK_EXPORT_ALIAS_ACCOUNTS:
            conn.execute(
                text(
                    """
                    INSERT INTO core.shop_accounts (
                        platform, shop_account_id, main_account_id, store_name,
                        shop_region, enabled, business_role
                    ) VALUES (
                        'tiktok', :shop_account_id, :main_account_id, :store_name,
                        :shop_region, TRUE, 'operating_store'
                    )
                    """
                ),
                {
                    "shop_account_id": shop_account_id,
                    "main_account_id": REHEARSAL_MAIN_ACCOUNT_ID,
                    "store_name": store_name,
                    "shop_region": shop_region,
                },
            )
        conn.execute(
            text(
                "INSERT INTO core.dim_platforms (platform_code, name, is_active) "
                "VALUES ('shopee','Shopee',TRUE), ('tiktok','TikTok',TRUE)"
            )
        )


def _has_column(engine, name: str) -> bool:
    with engine.connect() as conn:
        return bool(
            conn.execute(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_schema='core' AND table_name='dim_platforms' "
                    "AND column_name=:name"
                ),
                {"name": name},
            ).scalar()
        )


def _bucket_rows(engine) -> dict[str, dict]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT platform_code, other_cost_rate, fee_rate_source, fee_rate_version "
                "FROM core.dim_platforms "
                "WHERE platform_code IN ('shopee','tiktok') ORDER BY platform_code"
            )
        ).all()
    return {
        row[0]: {
            "other_cost_rate": float(row[1]) if row[1] is not None else None,
            "fee_rate_source": row[2],
            "fee_rate_version": row[3],
        }
        for row in rows
    }


@pytest.fixture(scope="module")
def roundtrip_db():
    """在隔离临时库上跑完整往返，返回（引擎, 清理函数）。"""
    settings = get_settings()
    base_url = make_url(settings.DATABASE_URL)
    admin_engine = create_engine(
        base_url.set(database="postgres"), isolation_level="AUTOCOMMIT", future=True
    )
    database_name = f"batch9_roundtrip_{uuid.uuid4().hex[:10]}"
    temp_url = base_url.set(database=database_name).render_as_string(
        hide_password=False
    )
    env = os.environ.copy()
    env["DATABASE_URL"] = temp_url
    engine = create_engine(temp_url, future=True)
    try:
        with admin_engine.connect() as conn:
            conn.execute(
                text(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)')
            )
            conn.execute(text(f'CREATE DATABASE "{database_name}"'))
        _run_alembic(["upgrade", BASELINE_REVISION], env)
        _seed(engine)
        _run_alembic(["upgrade", PREV_REVISION], env)
        yield engine, env
    finally:
        engine.dispose()
        with admin_engine.connect() as conn:
            conn.execute(
                text(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)')
            )
        admin_engine.dispose()


def test_downgrade_restores_the_dropped_column_and_the_legacy_bucket(roundtrip_db):
    """**删列必须退得回去**：列恢复、桶值/来源/版本全部还原。

    ⚠️ 这是本文件存在的全部理由 ——
    批次 9 的 ``downgrade`` 里真的藏着两个当场崩的 bug（``drop_column`` 参数冲突 +
    ``sa.Column(schema=...)``），而只跑 ``upgrade head`` 的演练**看不见它们**。
    """
    engine, env = roundtrip_db

    # 1) 上一版：列还在、桶是旧值
    assert _has_column(engine, "delivery_cost_rate") is True
    before = _bucket_rows(engine)
    for code, rate in LEGACY_BUCKET.items():
        assert before[code]["other_cost_rate"] == pytest.approx(rate)
        assert before[code]["fee_rate_version"] == LEGACY_VERSION

    # 2) 升到 head：列被删、桶换新值
    _run_alembic(["upgrade", "head"], env)
    assert _has_column(engine, "delivery_cost_rate") is False
    after = _bucket_rows(engine)
    for code, rate in NEW_BUCKET.items():
        assert after[code]["other_cost_rate"] == pytest.approx(rate)
        assert after[code]["fee_rate_version"] == NEW_VERSION

    # 3) **退回去**（重点）：列恢复 + 旧值全回来
    _run_alembic(["downgrade", PREV_REVISION], env)
    assert _has_column(engine, "delivery_cost_rate") is True
    restored = _bucket_rows(engine)
    for code, rate in LEGACY_BUCKET.items():
        assert restored[code]["other_cost_rate"] == pytest.approx(rate)
        assert restored[code]["fee_rate_version"] == LEGACY_VERSION
        assert "residual" in restored[code]["fee_rate_source"]

    # 4) 再升上来：证明可重复（不是一次性能过）
    _run_alembic(["upgrade", "head"], env)
    assert _has_column(engine, "delivery_cost_rate") is False
    again = _bucket_rows(engine)
    for code, rate in NEW_BUCKET.items():
        assert again[code]["other_cost_rate"] == pytest.approx(rate)
    with engine.connect() as conn:
        revision = conn.execute(
            text("SELECT version_num FROM public.current_schema_alembic_version")
        ).scalar()
    assert revision == _resolve_head_revision(env)
