"""``20261221_collapse_duplicate_columns`` 的降级/升级可逆性回归测试。

2026-11-09 生产演练实测：影子库从 head 降级到 20261214 之后**再也升不回 head**，
报错是::

    UPDATE "a_class"."attendance_records" SET "work_hours" = "工作时长" WHERE ...

根因：``20261221.downgrade()`` 重建被删列时一律用 ``TEXT``，
而 ``工作时长`` 的原始类型是 ``double precision``、``状态`` 是 ``varchar(32)``。
类型对不上，回填语句直接报错 —— 也就是**回滚之后升不回去**。

本测试直接驱动迁移代码（用假的 ``op`` 绑到真实连接上），
在独立临时库里跑一遍「降级 → 升级」往返，确保这条路径真的可逆。
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_FILE = (
    PROJECT_ROOT
    / "current_migrations"
    / "versions"
    / "20261221_collapse_duplicate_columns.py"
)


#: 「20261221 升级之后」的表结构（只保留与本迁移相关的列）。
#: 来源：静态基线 20260805 + 20261220 的改名结果。
REPLICA_DDL = (
    """
    CREATE SCHEMA IF NOT EXISTS a_class;
    CREATE SCHEMA IF NOT EXISTS core;
    """,
    """
    CREATE TABLE a_class.attendance_records (
        id bigint NOT NULL,
        employee_code character varying(64) NOT NULL,
        attendance_date date NOT NULL,
        clock_in_time timestamp with time zone,
        clock_out_time timestamp with time zone,
        created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
        updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
        work_hours double precision,
        status character varying(32) DEFAULT 'normal' NOT NULL
    )
    """,
    """
    CREATE TABLE core.data_files (
        id integer NOT NULL,
        file_name character varying(200) NOT NULL,
        file_type character varying(50),
        created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
    )
    """,
)


class _FakeOp:
    """把 alembic 的 ``op`` 换成一个绑在真实连接上的最小替身。"""

    def __init__(self, bind) -> None:
        self._bind = bind

    def get_bind(self):
        return self._bind

    def execute(self, statement):
        if isinstance(statement, str):
            statement = text(statement)
        return self._bind.execute(statement)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "migration_20261221_collapse_duplicate_columns", MIGRATION_FILE
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _column_type(conn, schema: str, table: str, column: str) -> str:
    return str(
        conn.execute(
            text(
                """
                SELECT data_type FROM information_schema.columns
                 WHERE table_schema = :schema AND table_name = :table
                   AND column_name = :column
                """
            ),
            {"schema": schema, "table": table, "column": column},
        ).scalar()
        or ""
    )


@pytest.fixture()
def replica_db():
    """建一个只含本迁移相关表的临时库（独立于隔离库主 schema）。"""
    from backend.models.database import DATABASE_URL

    base_url = make_url(DATABASE_URL)
    admin_engine = create_engine(
        base_url.set(database="postgres"), isolation_level="AUTOCOMMIT", future=True
    )
    database_name = f"collapse_dup_{uuid.uuid4().hex[:10]}"
    try:
        with admin_engine.connect() as conn:
            conn.execute(
                text(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)')
            )
            conn.execute(text(f'CREATE DATABASE "{database_name}"'))

        engine = create_engine(
            base_url.set(database=database_name).render_as_string(hide_password=False),
            future=True,
        )
        with engine.begin() as conn:
            for ddl in REPLICA_DDL:
                conn.execute(text(ddl))
        yield engine
        engine.dispose()
    finally:
        with admin_engine.connect() as conn:
            conn.execute(
                text(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)')
            )
        admin_engine.dispose()


def test_downgrade_then_upgrade_round_trip_is_reversible(replica_db):
    """降级 → 升级 必须能跑通，且列类型保持原始类型。"""
    migration = _load_migration()

    with replica_db.connect() as conn:
        migration.op = _FakeOp(conn)

        # 1) 降级：把被删的列按**原始类型**加回来
        migration.downgrade()

        assert _column_type(conn, "a_class", "attendance_records", "工作时长") == (
            "double precision"
        ), "降级重建的「工作时长」必须保持 double precision，否则再升级会类型不匹配"
        assert _column_type(conn, "a_class", "attendance_records", "状态") == (
            "character varying"
        ), "降级重建的「状态」必须保持 character varying"

        # 2) 再升级：回填 + 删冗余列（这一步在旧实现上会直接报错）
        migration.upgrade()

        assert _column_type(conn, "a_class", "attendance_records", "work_hours") == (
            "double precision"
        )
        assert _column_type(conn, "a_class", "attendance_records", "status") == (
            "character varying"
        )
        # 冗余列已被合并删除
        assert _column_type(conn, "a_class", "attendance_records", "工作时长") == ""
        assert _column_type(conn, "a_class", "attendance_records", "状态") == ""
        assert _column_type(conn, "core", "data_files", "data_type") == ""
        assert _column_type(conn, "core", "data_files", "discovery_time") == ""


def test_merge_refuses_mismatched_column_types(replica_db):
    """来源列与目标列类型不一致时必须**拒绝执行**（而不是静默截断或报错）。"""
    migration = _load_migration()

    with replica_db.connect() as conn:
        migration.op = _FakeOp(conn)

        # 人为制造类型不一致：把来源列建成 TEXT
        conn.execute(
            text(
                'ALTER TABLE a_class.attendance_records '
                'ADD COLUMN "工作时长" TEXT'
            )
        )

        with pytest.raises(RuntimeError, match="类型不一致"):
            migration.upgrade()


def test_restore_column_ddl_matches_original_types():
    """回滚重建用的 DDL 必须与静态基线的原始类型一致（静态护栏）。"""
    migration = _load_migration()

    assert (
        migration.RESTORE_COLUMN_DDL[("a_class.attendance_records", "工作时长")]
        == "double precision"
    )
    assert "character varying(32)" in migration.RESTORE_COLUMN_DDL[
        ("a_class.attendance_records", "状态")
    ]
    assert "timestamp with time zone" in migration.RESTORE_COLUMN_DDL[
        ("core.data_files", "discovery_time")
    ]
    assert "character varying(50)" in migration.RESTORE_DROP_ONLY_DDL[
        ("core.data_files", "status")
    ]
