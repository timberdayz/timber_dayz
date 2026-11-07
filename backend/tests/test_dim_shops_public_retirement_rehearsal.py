"""``dim_shops`` 的 public 副本退役预演(按**当前事实源**重放)。

⚠️ 口径变化(2026-08 起)
----------------------
* 历史链 ``migrations/versions/`` 已被 ``current_migrations/README.md`` 标成
  **只读历史**(部署/启动都不再走它), 而且它在空库上已经**不能重放**
  (``20260130_v4_21_0_hr_module_tables.py`` 会去 ALTER 一个还不存在的
  ``a_class.employees``)⇒ 继续跑旧链预演已经没有意义。
* **当前唯一事实源**是 ``current_migrations/``(``alembic-current.ini``):
  静态基线 ``current_schema_20260805`` 直接建 ``core.dim_shops``,
  **不建** ``public.dim_shops`` ⇒ 想退役的那份 public 副本在当前事实源里
  已经不存在(归档动作早已由历史迁移完成)。

所以预演改为在临时库里重放**当前链**, 守住真正的契约:
1. 当前链能干净地升到 head;
2. public 侧的 ``dim_shops`` 副本**不存在**(不许复活);
3. 规范副本在 ``core.dim_shops``;
4. 迁移状态与 head 一致, 且 ORM 声明的表都真实存在。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from backend.utils.config import get_settings


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CURRENT_CHAIN_CONFIG = "alembic-current.ini"
CURRENT_BASELINE_REVISION = "current_schema_20260805"

#: 当前链里的 ``current_schema_20261116_add_tiktok_export_store_name_aliases``
#: 是**数据依赖**迁移: 它要求库里已经存在这 6 个 TikTok 店铺账号, 缺一个就
#: fail-closed 拒绝升级 ⇒ 空库预演必须先补上这批账号才能升到 head。
TIKTOK_EXPORT_ALIAS_ACCOUNTS = (
    ("DAONE Mall", "tiktok_sg_daone_mall_local", "SG"),
    ("DAWIE Mall", "tiktok_my_dawie_mall_local", "MY"),
    ("Explorers Mall", "tiktok_ph_explorers_mall_local", "PH"),
    ("Malaysia(Flora Mall)", "tiktok_my_flora_mall_local", "MY"),
    ("Philippines(DAJU Mall)", "tiktok_ph_daju_mall_local", "PH"),
    ("Singapore(HX Home)", "tiktok_sg_hx_home_local", "SG"),
)
REHEARSAL_MAIN_ACCOUNT_ID = "rehearsal-main-account"


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
            "alembic failed: "
            f"{' '.join(args)}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )


def _table_exists(engine, schema_name: str, table_name: str) -> bool:
    with engine.connect() as conn:
        value = conn.execute(
            text(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = :schema_name
                  AND table_name = :table_name
                LIMIT 1
                """
            ),
            {"schema_name": schema_name, "table_name": table_name},
        ).scalar()
    return value is not None


def _seed_required_shop_accounts(engine) -> None:
    """补上当前链里那条数据依赖迁移需要的 TikTok 店铺账号。"""
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
                        platform,
                        shop_account_id,
                        main_account_id,
                        store_name,
                        shop_region,
                        enabled,
                        business_role
                    ) VALUES (
                        'tiktok',
                        :shop_account_id,
                        :main_account_id,
                        :store_name,
                        :shop_region,
                        TRUE,
                        'operating_store'
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


def _verify_schema_completeness(database_url: str) -> dict[str, object]:
    """在临时库上跑权威的完整性校验(独立进程 ⇒ 不会连到别的库)。"""
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json; "
                "from backend.models.database import verify_schema_completeness; "
                "print(json.dumps(verify_schema_completeness()))"
            ),
        ],
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "verify_schema_completeness failed\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    return json.loads(completed.stdout.strip().splitlines()[-1])


def _current_chain_head() -> str:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    return ScriptDirectory.from_config(
        Config(str(PROJECT_ROOT / CURRENT_CHAIN_CONFIG))
    ).get_current_head()


def _rehearse_current_chain() -> dict[str, object]:
    """在隔离库的临时库上重放当前迁移链, 返回预演结果。"""
    settings = get_settings()
    base_url = make_url(settings.DATABASE_URL)
    admin_engine = create_engine(
        base_url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        future=True,
    )
    database_name = f"dim_shops_retirement_rehearsal_{uuid.uuid4().hex[:10]}"
    temp_url = base_url.set(database=database_name).render_as_string(
        hide_password=False
    )
    env = os.environ.copy()
    env["DATABASE_URL"] = temp_url

    try:
        with admin_engine.connect() as conn:
            conn.execute(
                text(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)')
            )
            conn.execute(text(f'CREATE DATABASE "{database_name}"'))

        _run_alembic(["upgrade", CURRENT_BASELINE_REVISION], env)

        temp_engine = create_engine(temp_url, future=True)
        try:
            _seed_required_shop_accounts(temp_engine)
        finally:
            temp_engine.dispose()

        _run_alembic(["upgrade", "head"], env)

        temp_engine = create_engine(temp_url, future=True)
        try:
            with temp_engine.connect() as conn:
                current_revision = conn.execute(
                    text(
                        "SELECT version_num FROM public.current_schema_alembic_version"
                    )
                ).scalar()
            public_dim_shops = _table_exists(temp_engine, "public", "dim_shops")
            core_dim_shops = _table_exists(temp_engine, "core", "dim_shops")
        finally:
            temp_engine.dispose()

        completeness = _verify_schema_completeness(temp_url)
        completeness.update(
            {
                "database_name": database_name,
                "current_revision": current_revision,
                "head_revision": _current_chain_head(),
                "public_dim_shops_exists": public_dim_shops,
                "core_dim_shops_exists": core_dim_shops,
            }
        )
        return completeness
    finally:
        with admin_engine.connect() as conn:
            conn.execute(
                text(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)')
            )
        admin_engine.dispose()


def test_dim_shops_public_retirement_rehearsal_retires_public_copy_cleanly():
    result = _rehearse_current_chain()

    assert result["current_revision"] == result["head_revision"]
    assert result["all_tables_exist"] is True
    # public 侧的副本已退役: 当前事实源里不允许它存在
    assert result["public_dim_shops_exists"] is False
    # 规范副本在 core
    assert result["core_dim_shops_exists"] is True
