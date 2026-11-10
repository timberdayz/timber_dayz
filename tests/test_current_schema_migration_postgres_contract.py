"""Real PostgreSQL contracts for the fail-closed current-schema migration entrypoint."""

from __future__ import annotations

import os
import json
import hashlib
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

import scripts.run_current_schema_migrations as migration_runner


ROOT = Path(__file__).resolve().parents[1]
CURRENT_BASELINE_REVISION = "current_schema_20260805"
LEGACY_REVISION = "20260805_payroll_backfill_audit"

#: ``current_schema_20261116_add_tiktok_export_store_name_aliases`` 的前置检查
#: 要求这 6 个 TikTok 出口账号**已经存在**且是在营经营店，否则迁移拒绝继续。
#: 生产库之所以能过，是因为这些账号来自真实运营数据。
#: ⇒ 「从零建库的测试」必须自己补上这份**数据前置**，否则迁移链会在 20261116
#: 断掉，后面所有 revision（包含新加的 20261222 / 20261223）都跑不到。
#: 内容必须与迁移里的 ``_TIKTOK_EXPORT_ALIASES`` 逐条一致（账号 ID / 区域）。
TIKTOK_EXPORT_ACCOUNT_SEED = (
    ("tiktok_sg_daone_mall_local", "SG", "DAONE Mall"),
    ("tiktok_my_dawie_mall_local", "MY", "DAWIE Mall"),
    ("tiktok_ph_explorers_mall_local", "PH", "Explorers Mall"),
    ("tiktok_my_flora_mall_local", "MY", "Malaysia(Flora Mall)"),
    ("tiktok_ph_daju_mall_local", "PH", "Philippines(DAJU Mall)"),
    ("tiktok_sg_hx_home_local", "SG", "Singapore(HX Home)"),
)


def _current_head_revisions() -> set[str]:
    """当前 schema 迁移链的 head 集合（**动态取**，不写死）。

    为什么不能写死
    --------------
    这个文件以前把 head 写死成 ``current_schema_20260920_...``，而链上 head
    早就前移了 ⇒ 「升级后 version_num == HEAD」这条断言必然失败，且报错
    （断言不等的两个 revision 名）与真实原因（迁移链在 20261116 中断）完全无关，
    把排查方向带偏。

    ⇒ head 每加一个迁移就会变，**只有动态取**才不会周期性假红。
    """
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(str(ROOT / "alembic-current.ini"))
    return set(ScriptDirectory.from_config(config).get_heads())


CURRENT_HEAD_REVISIONS = _current_head_revisions()


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    result = subprocess.run(
        ["docker", "info"], capture_output=True, text=True, check=False
    )
    return result.returncode == 0


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _wait_for_postgres(container_id: str) -> None:
    for _ in range(30):
        result = subprocess.run(
            ["docker", "exec", container_id, "pg_isready", "-U", "current_test"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode == 0:
            time.sleep(1)
            return
        time.sleep(1)
    raise RuntimeError("temporary PostgreSQL container did not become ready")


def _write_approved_policy(tmp_path: Path, fingerprint: str) -> Path:
    manifest_path = tmp_path / "approved-manifest.json"
    manifest = {
        "manifest_version": 1,
        "legacy_revision": LEGACY_REVISION,
        "baseline_revision": CURRENT_BASELINE_REVISION,
        "schema_fingerprint": fingerprint,
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    policy_path = tmp_path / "support_policy.json"
    policy_path.write_text(
        json.dumps(
            {
                "approved_legacy_sources": [
                    {
                        "legacy_revision": LEGACY_REVISION,
                        "schema_fingerprint": fingerprint,
                        "baseline_revision": CURRENT_BASELINE_REVISION,
                        "manifest_version": 1,
                        "manifest_path": str(manifest_path),
                        "manifest_sha256": hashlib.sha256(
                            manifest_path.read_bytes()
                        ).hexdigest(),
                        "approval_note": "temporary PostgreSQL integration fixture",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return policy_path


def _alembic_upgrade(database_url: str, revision: str) -> subprocess.CompletedProcess:
    """把临时库迁到指定 revision（直接用 alembic，不走 runner 的 fail-closed 入口）。

    迁移链里有若干「数据前置检查」（fail-closed）：目标数据不存在就拒绝升级。
    要在两个 revision 之间补数据，就必须能停在中间 —— 这就是本 helper 的用途。
    """
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "alembic-current.ini",
            "upgrade",
            revision,
        ],
        cwd=ROOT,
        env={**os.environ, "DATABASE_URL": database_url},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _seed_tiktok_export_accounts(engine) -> None:
    """预置 20261116 迁移要求存在的 6 个 TikTok 出口账号。

    字段取自 ``core.shop_accounts`` 的实际结构：
    ``platform='tiktok'`` / ``enabled=true`` / ``business_role='operating_store'``
    / ``shop_region`` 与迁移期望一致。

    ⚠️ ``platform_shop_id`` 刻意留空：迁移的前置检查会拒绝「别名键撞上某个
    账号的 platform_shop_id」，而我们不希望引入这种歧义。

    ⚠️ ``core.shop_accounts.main_account_id`` 有外键指向 ``core.main_accounts``
    ⇒ 必须先落主账号行。这 6 个出口账号共用同一个主账号（与生产口径一致：
    同一批 TikTok 店铺挂在同一个采集主账号下）。
    """
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO core.main_accounts "
                "(id, platform, main_account_id, username, password_encrypted, "
                "enabled, main_account_name) "
                "VALUES (:id, 'tiktok', :main_account_id, :username, "
                ":password_encrypted, true, :main_account_name)"
            ),
            {
                "id": 900_001,
                "main_account_id": "main_tiktok_export_local",
                "username": "tiktok-export-operator",
                # 测试夹具占位值，**不是**任何真实凭据。
                "password_encrypted": "test-fixture-not-a-real-secret",
                "main_account_name": "TikTok Export Operator",
            },
        )
        for index, (shop_account_id, shop_region, store_name) in enumerate(
            TIKTOK_EXPORT_ACCOUNT_SEED, start=2
        ):
            connection.execute(
                text(
                    "INSERT INTO core.shop_accounts "
                    "(id, platform, shop_account_id, main_account_id, store_name, "
                    "shop_region, shop_type, enabled, business_role, "
                    "platform_shop_id_status) "
                    "VALUES (:id, 'tiktok', :shop_account_id, :main_account_id, "
                    ":store_name, :shop_region, 'online_shop', true, 'operating_store', "
                    "'missing')"
                ),
                {
                    "id": 900_001 + index,
                    "shop_account_id": shop_account_id,
                    "main_account_id": "main_tiktok_export_local",
                    "store_name": store_name,
                    "shop_region": shop_region,
                },
            )


def test_migration_advisory_lock_rejects_a_second_writer_without_ddl():
    if not _docker_available():
        pytest.skip("requires a reachable Docker daemon and PostgreSQL 15 image")

    port = _free_port()
    started = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-d",
            "-e",
            "POSTGRES_USER=current_test",
            "-e",
            "POSTGRES_PASSWORD=current_test",
            "-e",
            "POSTGRES_DB=current_test",
            "-p",
            f"127.0.0.1:{port}:5432",
            "postgres:15",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    container_id = started.stdout.strip()
    database_url = (
        f"postgresql://current_test:current_test@127.0.0.1:{port}/current_test"
    )
    try:
        _wait_for_postgres(container_id)
        with migration_runner.migration_advisory_lock(database_url):
            with pytest.raises(
                migration_runner.MigrationSafetyError, match="lock is already held"
            ):
                with migration_runner.migration_advisory_lock(database_url):
                    pass
        engine = create_engine(database_url)
        assert not inspect(engine).get_table_names(schema="public")
    finally:
        subprocess.run(["docker", "stop", "-t", "1", container_id], check=False)


def test_current_wrapper_rejects_nonempty_database_without_mutation_then_bootstraps_fresh():
    if not _docker_available():
        pytest.skip("requires a reachable Docker daemon and PostgreSQL 15 image")

    port = _free_port()
    started = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-d",
            "-e",
            "POSTGRES_USER=current_test",
            "-e",
            "POSTGRES_PASSWORD=current_test",
            "-e",
            "POSTGRES_DB=current_test",
            "-p",
            f"127.0.0.1:{port}:5432",
            "postgres:15",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    container_id = started.stdout.strip()
    database_url = (
        f"postgresql://current_test:current_test@127.0.0.1:{port}/current_test"
    )
    try:
        _wait_for_postgres(container_id)
        engine = create_engine(database_url)
        with engine.begin() as connection:
            connection.execute(
                text("CREATE TABLE public.legacy_probe (id integer primary key)")
            )

        rejected = subprocess.run(
            [sys.executable, "scripts/run_current_schema_migrations.py"],
            cwd=ROOT,
            env={**os.environ, "DATABASE_URL": database_url},
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        assert rejected.returncode == 2
        assert "not an approved legacy source" in rejected.stderr
        assert inspect(engine).has_table("legacy_probe", schema="public")
        assert not inspect(engine).has_table(
            "current_schema_alembic_version", schema="public"
        )

        with engine.begin() as connection:
            connection.execute(text("CREATE SCHEMA core"))
            connection.execute(
                text(
                    "CREATE TABLE core.alembic_version "
                    "(version_num varchar(64) NOT NULL PRIMARY KEY)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO core.alembic_version (version_num) VALUES ('unknown')"
                )
            )

        unknown_revision = subprocess.run(
            [sys.executable, "scripts/run_current_schema_migrations.py"],
            cwd=ROOT,
            env={**os.environ, "DATABASE_URL": database_url},
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        assert unknown_revision.returncode == 2
        assert "not an approved legacy source" in unknown_revision.stderr
        assert inspect(engine).has_table("legacy_probe", schema="public")
        assert not inspect(engine).has_table(
            "current_schema_alembic_version", schema="public"
        )

        with engine.begin() as connection:
            connection.execute(text("DELETE FROM core.alembic_version"))
            connection.execute(
                text(
                    "INSERT INTO core.alembic_version (version_num) "
                    "VALUES ('20260805_payroll_backfill_audit')"
                )
            )

        mismatched_fingerprint = subprocess.run(
            [sys.executable, "scripts/run_current_schema_migrations.py"],
            cwd=ROOT,
            env={**os.environ, "DATABASE_URL": database_url},
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        assert mismatched_fingerprint.returncode == 2
        assert "fingerprint is not approved" in mismatched_fingerprint.stderr
        assert inspect(engine).has_table("legacy_probe", schema="public")
        assert not inspect(engine).has_table(
            "current_schema_alembic_version", schema="public"
        )

        with engine.begin() as connection:
            connection.execute(text("DROP TABLE core.alembic_version"))
            connection.execute(text("DROP SCHEMA core"))
            connection.execute(text("DROP TABLE public.legacy_probe"))

        # 空库 → 先把 schema **真正建到基线**（不是 stamp），再补上 20261116
        # 要求的数据前置，最后由 runner 续跑到 head。
        # 为什么不能一口气 upgrade head：迁移链里有 fail-closed 的数据前置检查
        # （见 _seed_tiktok_export_accounts），缺数据就会在半路拒绝升级。
        baseline = _alembic_upgrade(database_url, CURRENT_BASELINE_REVISION)
        assert baseline.returncode == 0, baseline.stderr
        _seed_tiktok_export_accounts(engine)

        bootstrapped = subprocess.run(
            [sys.executable, "scripts/run_current_schema_migrations.py"],
            cwd=ROOT,
            env={**os.environ, "DATABASE_URL": database_url},
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        assert bootstrapped.returncode == 0, bootstrapped.stderr
        assert inspect(engine).has_table(
            "current_schema_alembic_version", schema="public"
        )
        assert len(inspect(engine).get_table_names(schema="a_class")) > 0
        assert inspect(engine).has_table(
            "operation_performance_shop_scopes", schema="a_class"
        )
    finally:
        subprocess.run(["docker", "stop", "-t", "1", container_id], check=False)


def test_approved_legacy_adoption_preserves_business_data_and_runs_current_increment(
    tmp_path, monkeypatch
):
    """A supported production-shaped database stamps only the static baseline."""
    if not _docker_available():
        pytest.skip("requires a reachable Docker daemon and PostgreSQL 15 image")

    port = _free_port()
    started = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-d",
            "-e",
            "POSTGRES_USER=current_test",
            "-e",
            "POSTGRES_PASSWORD=current_test",
            "-e",
            "POSTGRES_DB=current_test",
            "-p",
            f"127.0.0.1:{port}:5432",
            "postgres:15",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    container_id = started.stdout.strip()
    database_url = (
        f"postgresql://current_test:current_test@127.0.0.1:{port}/current_test"
    )
    try:
        _wait_for_postgres(container_id)
        baseline = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "alembic-current.ini",
                "upgrade",
                CURRENT_BASELINE_REVISION,
            ],
            cwd=ROOT,
            env={**os.environ, "DATABASE_URL": database_url},
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        assert baseline.returncode == 0, baseline.stderr

        engine = create_engine(database_url)
        _seed_tiktok_export_accounts(engine)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO a_class.employees (employee_code, name) "
                    "VALUES ('MIGRATION-KEEP', 'Migration Keep')"
                )
            )
            connection.execute(text("DROP TABLE public.current_schema_alembic_version"))
            connection.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS core.alembic_version "
                    "(version_num varchar(64) NOT NULL PRIMARY KEY)"
                )
            )
            connection.execute(text("DELETE FROM core.alembic_version"))
            connection.execute(
                text(
                    "INSERT INTO core.alembic_version (version_num) VALUES (:revision)"
                ),
                {"revision": LEGACY_REVISION},
            )

        with engine.connect() as connection:
            fingerprint = migration_runner.schema_fingerprint(connection)
        policy_path = _write_approved_policy(tmp_path, fingerprint)
        monkeypatch.setattr(migration_runner, "SUPPORT_POLICY_PATH", policy_path)
        monkeypatch.setenv("LOCAL_POSTGRES_CONTAINER", container_id)
        monkeypatch.setenv(migration_runner.LOCAL_BACKUP_GUARD_ENV, "1")

        assert (
            migration_runner.run_current_schema_migrations(
                database_url,
                expected_source_revision=None,
                expected_source_fingerprint=None,
            )
            == "stamp"
        )

        inspector = inspect(engine)
        assert inspector.has_table("operation_metric_catalog", schema="a_class")
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT name FROM a_class.employees "
                        "WHERE employee_code = 'MIGRATION-KEEP'"
                    )
                ).scalar_one()
                == "Migration Keep"
            )
            assert (
                connection.execute(
                    text(
                        "SELECT version_num FROM public.current_schema_alembic_version"
                    )
                ).scalar_one()
                in CURRENT_HEAD_REVISIONS
            )
            assert (
                connection.execute(
                    text("SELECT version_num FROM core.alembic_version")
                ).scalar_one()
                == LEGACY_REVISION
            )
        assert (
            migration_runner.run_current_schema_migrations(
                database_url,
                expected_source_revision=None,
                expected_source_fingerprint=None,
            )
            == "upgrade"
        )
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT name FROM a_class.employees "
                        "WHERE employee_code = 'MIGRATION-KEEP'"
                    )
                ).scalar_one()
                == "Migration Keep"
            )
    finally:
        subprocess.run(["docker", "stop", "-t", "1", container_id], check=False)


def test_legacy_adoption_preserves_duplicate_operation_shop_overrides_and_audits_them(
    tmp_path, monkeypatch, capsys
):
    """老库采纳（legacy adoption）必须**走得通**，且历史 operation 型档位行**原样保留**。

    [*] 2026-11-10 业务拍板（口径材料：
    ``docs/reports/2026-11-10-老库升级路径-只读触发器冲突口径决策材料.md``）：
    没有 ``metric_catalog_version`` 的 operation 型父目标下的历史档位行
    **本来就不该被补** ``period_label`` ⇒ 迁移必须**显式跳过并记日志**。

    ⇒ 这条用例从「缺陷探测器」变成「新口径的守护」：
    - 采纳路径不再抛 'historical operation breakdowns are read-only'；
    - 历史行的 ``period_label`` 保持 NULL（没被改）；
    - 跳过的行数出现在迁移日志里（不静默漏改）。
    """
    if not _docker_available():
        pytest.skip("requires a reachable Docker daemon and PostgreSQL 15 image")

    port = _free_port()
    started = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-d",
            "-e",
            "POSTGRES_USER=current_test",
            "-e",
            "POSTGRES_PASSWORD=current_test",
            "-e",
            "POSTGRES_DB=current_test",
            "-p",
            f"127.0.0.1:{port}:5432",
            "postgres:15",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    container_id = started.stdout.strip()
    database_url = (
        f"postgresql://current_test:current_test@127.0.0.1:{port}/current_test"
    )
    try:
        _wait_for_postgres(container_id)
        baseline = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "alembic-current.ini",
                "upgrade",
                CURRENT_BASELINE_REVISION,
            ],
            cwd=ROOT,
            env={**os.environ, "DATABASE_URL": database_url},
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        assert baseline.returncode == 0, baseline.stderr

        engine = create_engine(database_url)
        _seed_tiktok_export_accounts(engine)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO core.dim_platforms (platform_code, name, is_active) "
                    "VALUES ('platform', 'Platform', true)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO core.dim_shops (platform_code, shop_id, shop_name) "
                    "VALUES ('platform', 'shop', 'Shop')"
                )
            )
            target_id = connection.execute(
                text(
                    "INSERT INTO a_class.sales_targets "
                    "(target_name, target_type, period_start, period_end, scope_type, "
                    "metric_code, metric_direction, target_value, max_score) "
                    "VALUES ('Legacy operation', 'operation', '2026-07-01', '2026-07-31', "
                    "'shop', 'legacy_metric', 'higher_better', 1, 10) RETURNING id"
                )
            ).scalar_one()
            for achieved_value in (1, 2):
                connection.execute(
                    text(
                        "INSERT INTO a_class.target_breakdown "
                        "(target_id, breakdown_type, platform_code, shop_id, "
                        "period_start, period_end, target_amount, target_quantity, "
                        "achieved_amount, achieved_quantity, achievement_rate, achieved_value) "
                        "VALUES (:target_id, 'shop', 'platform', 'shop', "
                        "'2026-07-01', '2026-07-31', 1, 0, 0, 0, 0, :achieved_value)"
                    ),
                    {"target_id": target_id, "achieved_value": achieved_value},
                )
            incomplete_target_id = connection.execute(
                text(
                    "INSERT INTO a_class.sales_targets "
                    "(target_name, target_type, period_start, period_end, scope_type) "
                    "VALUES ('Incomplete legacy operation', 'operation', '2026-07-02', '2026-07-31', NULL) "
                    "RETURNING id"
                )
            ).scalar_one()
            connection.execute(
                text(
                    "INSERT INTO a_class.target_breakdown "
                    "(target_id, breakdown_type, target_amount, target_quantity, "
                    "achieved_amount, achieved_quantity, achievement_rate) "
                    "VALUES (:target_id, 'time', 0, 0, 0, 0, 0)"
                ),
                {"target_id": incomplete_target_id},
            )
            connection.execute(text("DROP TABLE public.current_schema_alembic_version"))
            connection.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS core.alembic_version "
                    "(version_num varchar(64) NOT NULL PRIMARY KEY)"
                )
            )
            connection.execute(text("DELETE FROM core.alembic_version"))
            connection.execute(
                text(
                    "INSERT INTO core.alembic_version (version_num) VALUES (:revision)"
                ),
                {"revision": LEGACY_REVISION},
            )

        with engine.connect() as connection:
            fingerprint = migration_runner.schema_fingerprint(connection)
        policy_path = _write_approved_policy(tmp_path, fingerprint)
        monkeypatch.setattr(migration_runner, "SUPPORT_POLICY_PATH", policy_path)
        monkeypatch.setenv("LOCAL_POSTGRES_CONTAINER", container_id)
        monkeypatch.setenv(migration_runner.LOCAL_BACKUP_GUARD_ENV, "1")

        assert (
            migration_runner.run_current_schema_migrations(
                database_url,
                expected_source_revision=None,
                expected_source_fingerprint=None,
            )
            == "stamp"
        )

        inspector = inspect(engine)
        assert inspector.has_table("current_schema_alembic_version", schema="public")
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM a_class.target_breakdown "
                        "WHERE target_id = :target_id"
                    ),
                    {"target_id": target_id},
                ).scalar_one()
                == 2
            )
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM a_class.target_breakdown "
                        "WHERE target_id = :target_id "
                        "AND operation_contract_version IS NULL"
                    ),
                    {"target_id": target_id},
                ).scalar_one()
                == 2
            )
            # [*] 2026-11-10 业务拍板：历史 operation 型（无 metric_catalog_version）
            # 父目标下的档位行**不该被回填** ⇒ 迁移必须**跳过并记日志**，
            # 而不是去改它们（改了会撞只读触发器 'historical operation breakdowns are read-only'）。
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM a_class.target_breakdown "
                        "WHERE target_id = :target_id AND period_label IS NULL"
                    ),
                    {"target_id": target_id},
                ).scalar_one()
                == 2
            )
            # 被跳过的行数必须出现在迁移日志里（不静默漏改，避免被误读成「数据漏改」）
            assert (
                "跳过（业务口径：历史 operation 型档位行不改）"
                in capsys.readouterr().out
            )

        audit = migration_runner.audit_legacy_operation_data(database_url)
        assert audit["legacy_count"] == 2
        assert audit["missing_metric_code"]["count"] == 1
        assert audit["missing_metric_direction"]["count"] == 1
        assert audit["non_calendar_month"]["count"] == 1
        assert audit["missing_shop_scope"]["count"] == 1
        assert audit["incomplete_override"]["count"] == 1
        assert audit["duplicate_override"]["count"] == 2
        assert len(audit["duplicate_override"]["ids"]) == 2
        cli_audit = subprocess.run(
            [
                sys.executable,
                "scripts/run_current_schema_migrations.py",
                "--database-url",
                database_url,
                "--audit-legacy-operation-data",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        assert cli_audit.returncode == 0, cli_audit.stderr
        assert json.loads(cli_audit.stdout) == audit
    finally:
        subprocess.run(["docker", "stop", "-t", "1", container_id], check=False)


def test_current_operation_contract_rejects_invalid_targets_and_matching_duplicate_overrides():
    if not _docker_available():
        pytest.skip("requires a reachable Docker daemon and PostgreSQL 15 image")

    port = _free_port()
    started = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-d",
            "-e",
            "POSTGRES_USER=current_test",
            "-e",
            "POSTGRES_PASSWORD=current_test",
            "-e",
            "POSTGRES_DB=current_test",
            "-p",
            f"127.0.0.1:{port}:5432",
            "postgres:15",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    container_id = started.stdout.strip()
    database_url = (
        f"postgresql://current_test:current_test@127.0.0.1:{port}/current_test"
    )
    try:
        _wait_for_postgres(container_id)
        # 先迁到 20261116 的**前一个** revision：迁移链里有 fail-closed 的数据
        # 前置检查（TikTok 出口账号必须存在），必须停下来补数据才能继续往 head 走。
        staged = _alembic_upgrade(
            database_url, "current_schema_20261115_add_sku_platform_pricing"
        )
        assert staged.returncode == 0, staged.stderr
        engine = create_engine(database_url)
        _seed_tiktok_export_accounts(engine)
        migrated = _alembic_upgrade(database_url, "head")
        assert migrated.returncode == 0, migrated.stderr

        with engine.begin() as connection:
            invalid_target_savepoint = connection.begin_nested()
            with pytest.raises(Exception, match="scope_type=shop"):
                connection.execute(
                    text(
                        "INSERT INTO a_class.sales_targets "
                        "(target_name, target_type, period_start, period_end, metric_catalog_version) "
                        "VALUES ('Invalid current', 'operation', '2026-07-01', '2026-07-31', 1)"
                    )
                )
            invalid_target_savepoint.rollback()

            historical_insert_savepoint = connection.begin_nested()
            with pytest.raises(
                Exception, match="historical operation targets are read-only"
            ):
                connection.execute(
                    text(
                        "INSERT INTO a_class.sales_targets "
                        "(target_name, target_type, period_start, period_end) "
                        "VALUES ('Legacy write rejected', 'operation', '2026-07-02', '2026-07-31')"
                    )
                )
            historical_insert_savepoint.rollback()
            connection.execute(
                text(
                    "INSERT INTO core.dim_platforms (platform_code, name, is_active) "
                    "VALUES ('platform', 'Platform', true)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO core.dim_shops (platform_code, shop_id, shop_name) "
                    "VALUES ('platform', 'shop', 'Shop')"
                )
            )

            current_id = connection.execute(
                text(
                    "INSERT INTO a_class.sales_targets "
                    "(target_name, target_type, period_start, period_end, scope_type, metric_code, "
                    "metric_direction, metric_catalog_version) "
                    "VALUES ('Current valid', 'operation', '2026-07-01', '2026-07-31', 'shop', "
                    "'metric', 'higher_better', 1) RETURNING id"
                )
            ).scalar_one()
            invalid_override_savepoint = connection.begin_nested()
            with pytest.raises(Exception, match="only allow shop breakdowns"):
                connection.execute(
                    text(
                        "INSERT INTO a_class.target_breakdown "
                        "(target_id, breakdown_type, operation_contract_version) "
                        "VALUES (:target_id, 'time', 1)"
                    ),
                    {"target_id": current_id},
                )
            invalid_override_savepoint.rollback()
            override_sql = text(
                "INSERT INTO a_class.target_breakdown "
                "(target_id, breakdown_type, platform_code, shop_id, period_start, period_end, "
                "target_amount, target_quantity, achieved_amount, achieved_quantity, achievement_rate, "
                "operation_contract_version) "
                "VALUES (:target_id, 'shop', 'platform', 'shop', '2026-07-01', '2026-07-31', "
                "0, 0, 0, 0, 0, 1)"
            )
            connection.execute(override_sql, {"target_id": current_id})
            duplicate_override_savepoint = connection.begin_nested()
            with pytest.raises(Exception, match="uq_operation_shop_override"):
                connection.execute(override_sql, {"target_id": current_id})
            duplicate_override_savepoint.rollback()

            connection.execute(text("DROP INDEX a_class.uq_operation_shop_override"))
            connection.execute(override_sql, {"target_id": current_id})

        with pytest.raises(
            migration_runner.MigrationSafetyError,
            match="invalid current operation contract data",
        ):
            migration_runner.assert_legacy_adoption_data_is_safe(database_url)

        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE a_class.sales_targets "
                    "DISABLE TRIGGER trg_enforce_operation_target_contract"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO a_class.sales_targets "
                    "(target_name, target_type, period_start, period_end, metric_catalog_version) "
                    "VALUES ('Invalid current preflight', 'operation', '2026-07-01', '2026-07-31', 1)"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE a_class.sales_targets "
                    "ENABLE TRIGGER trg_enforce_operation_target_contract"
                )
            )

        with pytest.raises(
            migration_runner.MigrationSafetyError,
            match="invalid current operation contract data",
        ):
            migration_runner.assert_legacy_adoption_data_is_safe(database_url)

        with pytest.raises(
            migration_runner.MigrationSafetyError,
            match="invalid current operation contract data",
        ):
            migration_runner.run_current_schema_migrations(
                database_url,
                expected_source_revision=None,
                expected_source_fingerprint=None,
            )
    finally:
        subprocess.run(["docker", "stop", "-t", "1", container_id], check=False)


def test_old_20260808_database_upgrades_to_enforce_operation_breakdown_versions():
    if not _docker_available():
        pytest.skip("requires a reachable Docker daemon and PostgreSQL 15 image")

    port = _free_port()
    started = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-d",
            "-e",
            "POSTGRES_USER=current_test",
            "-e",
            "POSTGRES_PASSWORD=current_test",
            "-e",
            "POSTGRES_DB=current_test",
            "-p",
            f"127.0.0.1:{port}:5432",
            "postgres:15",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    container_id = started.stdout.strip()
    database_url = (
        f"postgresql://current_test:current_test@127.0.0.1:{port}/current_test"
    )
    try:
        _wait_for_postgres(container_id)
        old_upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "alembic-current.ini",
                "upgrade",
                "current_schema_20260808_operation_performance_workbench",
            ],
            cwd=ROOT,
            env={**os.environ, "DATABASE_URL": database_url},
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        assert old_upgrade.returncode == 0, old_upgrade.stderr

        engine = create_engine(database_url)
        # 20261116 的前置检查要求这 6 个 TikTok 出口账号存在
        # （详见 _seed_tiktok_export_accounts 的说明）。
        _seed_tiktok_export_accounts(engine)
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT version_num FROM public.current_schema_alembic_version"
                    )
                ).scalar_one()
                == "current_schema_20260808_operation_performance_workbench"
            )

        with engine.begin() as connection:
            historical_id = connection.execute(
                text(
                    "INSERT INTO a_class.sales_targets "
                    "(target_name, target_type, period_start, period_end) "
                    "VALUES ('Historical versionless', 'operation', '2026-07-01', '2026-07-31') "
                    "RETURNING id"
                )
            ).scalar_one()
            historical_breakdown_id = connection.execute(
                text(
                    "INSERT INTO a_class.target_breakdown "
                    "(target_id, breakdown_type, target_amount, target_quantity, achieved_amount, "
                    "achieved_quantity, achievement_rate) "
                    "VALUES (:target_id, 'time', 0, 0, 0, 0, 0) RETURNING id"
                ),
                {"target_id": historical_id},
            ).scalar_one()

        assert (
            migration_runner.run_current_schema_migrations(
                database_url,
                expected_source_revision=None,
                expected_source_fingerprint=None,
            )
            == "upgrade"
        )

        with engine.begin() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT version_num FROM public.current_schema_alembic_version"
                    )
                ).scalar_one()
                in CURRENT_HEAD_REVISIONS
            )
            connection.execute(
                text(
                    "INSERT INTO core.dim_platforms (platform_code, name, is_active) "
                    "VALUES ('platform', 'Platform', true)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO core.dim_shops (platform_code, shop_id, shop_name) "
                    "VALUES ('platform', 'shop', 'Shop')"
                )
            )
            current_id = connection.execute(
                text(
                    "INSERT INTO a_class.sales_targets "
                    "(target_name, target_type, period_start, period_end, scope_type, metric_code, "
                    "metric_direction, metric_catalog_version) "
                    "VALUES ('Current versioned', 'operation', '2026-07-01', '2026-07-31', 'shop', "
                    "'metric', 'higher_better', 1) RETURNING id"
                )
            ).scalar_one()
            inherited_breakdown_id = connection.execute(
                text(
                    "INSERT INTO a_class.target_breakdown "
                    "(target_id, breakdown_type, platform_code, shop_id, period_start, period_end, "
                    "target_amount, target_quantity, achieved_amount, achieved_quantity, achievement_rate) "
                    "VALUES (:target_id, 'shop', 'platform', 'shop', '2026-07-01', '2026-07-31', "
                    "0, 0, 0, 0, 0) RETURNING id"
                ),
                {"target_id": current_id},
            ).scalar_one()
            assert (
                connection.execute(
                    text(
                        "SELECT operation_contract_version FROM a_class.target_breakdown WHERE id = :id"
                    ),
                    {"id": inherited_breakdown_id},
                ).scalar_one()
                == 1
            )
            connection.execute(
                text(
                    "UPDATE a_class.target_breakdown "
                    "SET target_amount = 1, operation_contract_version = NULL WHERE id = :id"
                ),
                {"id": inherited_breakdown_id},
            )
            assert (
                connection.execute(
                    text(
                        "SELECT operation_contract_version FROM a_class.target_breakdown WHERE id = :id"
                    ),
                    {"id": inherited_breakdown_id},
                ).scalar_one()
                == 1
            )
            wrong_version_savepoint = connection.begin_nested()
            with pytest.raises(Exception, match="contract version must match"):
                connection.execute(
                    text(
                        "INSERT INTO a_class.target_breakdown "
                        "(target_id, breakdown_type, platform_code, shop_id, period_start, period_end, "
                        "operation_contract_version) "
                        "VALUES (:target_id, 'shop', 'platform', 'shop', '2026-07-01', '2026-07-31', 2)"
                    ),
                    {"target_id": current_id},
                )
            wrong_version_savepoint.rollback()
            historical_target_insert_savepoint = connection.begin_nested()
            with pytest.raises(
                Exception, match="historical operation targets are read-only"
            ):
                connection.execute(
                    text(
                        "INSERT INTO a_class.sales_targets "
                        "(target_name, target_type, period_start, period_end) "
                        "VALUES ('New legacy target', 'operation', '2026-07-01', '2026-07-31')"
                    )
                )
            historical_target_insert_savepoint.rollback()
            for statement in (
                text(
                    "UPDATE a_class.sales_targets SET target_name = 'Changed' WHERE id = :id"
                ),
                text("DELETE FROM a_class.sales_targets WHERE id = :id"),
            ):
                savepoint = connection.begin_nested()
                with pytest.raises(
                    Exception, match="historical operation targets are read-only"
                ):
                    connection.execute(statement, {"id": historical_id})
                savepoint.rollback()
            for statement in (
                text(
                    "INSERT INTO a_class.target_breakdown "
                    "(target_id, breakdown_type, target_amount, target_quantity, achieved_amount, "
                    "achieved_quantity, achievement_rate) "
                    "VALUES (:target_id, 'time', 0, 0, 0, 0, 0)"
                ),
                text(
                    "UPDATE a_class.target_breakdown SET target_amount = 1 WHERE id = :id"
                ),
                text("DELETE FROM a_class.target_breakdown WHERE id = :id"),
            ):
                savepoint = connection.begin_nested()
                with pytest.raises(
                    Exception, match="historical operation breakdowns are read-only"
                ):
                    connection.execute(
                        statement,
                        {"id": historical_breakdown_id, "target_id": historical_id},
                    )
                savepoint.rollback()
            assert (
                connection.execute(
                    text(
                        "SELECT operation_contract_version FROM a_class.target_breakdown WHERE id = :id"
                    ),
                    {"id": historical_breakdown_id},
                ).scalar_one()
                is None
            )
            connection.execute(
                text(
                    "ALTER TABLE a_class.target_breakdown "
                    "DISABLE TRIGGER trg_enforce_operation_breakdown_contract"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO a_class.target_breakdown "
                    "(target_id, breakdown_type, target_amount, target_quantity, achieved_amount, "
                    "achieved_quantity, achievement_rate, operation_contract_version) "
                    "VALUES (:target_id, 'time', 0, 0, 0, 0, 0, NULL)"
                ),
                {"target_id": current_id},
            )
            connection.execute(
                text(
                    "ALTER TABLE a_class.target_breakdown "
                    "ENABLE TRIGGER trg_enforce_operation_breakdown_contract"
                )
            )

        with pytest.raises(
            migration_runner.MigrationSafetyError,
            match="invalid current operation contract data",
        ):
            migration_runner.assert_legacy_adoption_data_is_safe(database_url)
    finally:
        subprocess.run(["docker", "stop", "-t", "1", container_id], check=False)


def test_old_20260808_current_operation_overrides_are_backfilled_without_touching_history():
    if not _docker_available():
        pytest.skip("requires a reachable Docker daemon and PostgreSQL 15 image")

    port = _free_port()
    started = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-d",
            "-e",
            "POSTGRES_USER=current_test",
            "-e",
            "POSTGRES_PASSWORD=current_test",
            "-e",
            "POSTGRES_DB=current_test",
            "-p",
            f"127.0.0.1:{port}:5432",
            "postgres:15",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    container_id = started.stdout.strip()
    database_url = (
        f"postgresql://current_test:current_test@127.0.0.1:{port}/current_test"
    )
    try:
        _wait_for_postgres(container_id)
        old_upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "alembic-current.ini",
                "upgrade",
                "current_schema_20260808_operation_performance_workbench",
            ],
            cwd=ROOT,
            env={**os.environ, "DATABASE_URL": database_url},
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        assert old_upgrade.returncode == 0, old_upgrade.stderr

        engine = create_engine(database_url)
        # 20261116 的前置检查要求这 6 个 TikTok 出口账号存在
        # （详见 _seed_tiktok_export_accounts 的说明）。
        _seed_tiktok_export_accounts(engine)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO core.dim_platforms (platform_code, name, is_active) "
                    "VALUES ('platform', 'Platform', true)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO core.dim_shops (platform_code, shop_id, shop_name) VALUES "
                    "('platform', 'current-shop', 'Current shop'), "
                    "('platform', 'legacy-shop', 'Legacy shop')"
                )
            )
            current_target_id = connection.execute(
                text(
                    "INSERT INTO a_class.sales_targets "
                    "(target_name, target_type, scope_type, period_start, period_end, metric_code, "
                    "metric_direction, metric_catalog_version) "
                    "VALUES ('Current target', 'operation', 'shop', '2026-08-01', '2026-08-31', "
                    "'reply', 'higher_better', 7) RETURNING id"
                )
            ).scalar_one()
            historical_target_id = connection.execute(
                text(
                    "INSERT INTO a_class.sales_targets "
                    "(target_name, target_type, period_start, period_end) "
                    "VALUES ('Historical target', 'operation', '2026-08-02', '2026-08-20') RETURNING id"
                )
            ).scalar_one()
            current_breakdown_id = connection.execute(
                text(
                    "INSERT INTO a_class.target_breakdown "
                    "(target_id, breakdown_type, platform_code, shop_id, period_start, period_end, "
                    "target_amount, target_quantity, achieved_amount, achieved_quantity, achievement_rate, "
                    "operation_contract_version) "
                    "VALUES (:target_id, 'shop', 'platform', 'current-shop', '2026-08-01', '2026-08-31', "
                    "123, 4, 45, 2, 36.5, 7) RETURNING id"
                ),
                {"target_id": current_target_id},
            ).scalar_one()
            historical_breakdown_id = connection.execute(
                text(
                    "INSERT INTO a_class.target_breakdown "
                    "(target_id, breakdown_type, platform_code, shop_id, period_start, period_end, "
                    "target_amount, target_quantity, achieved_amount, achieved_quantity, achievement_rate) "
                    "VALUES (:target_id, 'time', 'platform', 'legacy-shop', '2026-08-03', '2026-08-03', "
                    "99, 3, 11, 1, 11.1) RETURNING id"
                ),
                {"target_id": historical_target_id},
            ).scalar_one()
            history_before = connection.execute(
                text(
                    "SELECT target_id, breakdown_type, platform_code, shop_id, period_start, period_end, "
                    "target_amount, target_quantity, achieved_amount, achieved_quantity, achievement_rate "
                    "FROM a_class.target_breakdown WHERE id = :id"
                ),
                {"id": historical_breakdown_id},
            ).one()
            connection.execute(text("DROP INDEX a_class.uq_operation_shop_override"))
            connection.execute(
                text(
                    "ALTER TABLE a_class.target_breakdown "
                    "DROP COLUMN operation_contract_version"
                )
            )

        assert (
            migration_runner.run_current_schema_migrations(
                database_url,
                expected_source_revision=None,
                expected_source_fingerprint=None,
            )
            == "upgrade"
        )

        with engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT operation_contract_version FROM a_class.target_breakdown "
                        "WHERE id = :id"
                    ),
                    {"id": current_breakdown_id},
                ).scalar_one()
                == 7
            )
            history_after = connection.execute(
                text(
                    "SELECT target_id, breakdown_type, platform_code, shop_id, period_start, period_end, "
                    "target_amount, target_quantity, achieved_amount, achieved_quantity, achievement_rate "
                    "FROM a_class.target_breakdown WHERE id = :id"
                ),
                {"id": historical_breakdown_id},
            ).one()
            assert history_after == history_before
            assert (
                connection.execute(
                    text(
                        "SELECT operation_contract_version FROM a_class.target_breakdown "
                        "WHERE id = :id"
                    ),
                    {"id": historical_breakdown_id},
                ).scalar_one()
                is None
            )
    finally:
        subprocess.run(["docker", "stop", "-t", "1", container_id], check=False)


def test_20260808_preflight_rejects_invalid_current_override_when_contract_column_is_absent():
    if not _docker_available():
        pytest.skip("requires a reachable Docker daemon and PostgreSQL 15 image")

    port = _free_port()
    started = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-d",
            "-e",
            "POSTGRES_USER=current_test",
            "-e",
            "POSTGRES_PASSWORD=current_test",
            "-e",
            "POSTGRES_DB=current_test",
            "-p",
            f"127.0.0.1:{port}:5432",
            "postgres:15",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    container_id = started.stdout.strip()
    database_url = (
        f"postgresql://current_test:current_test@127.0.0.1:{port}/current_test"
    )
    try:
        _wait_for_postgres(container_id)
        old_upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "alembic-current.ini",
                "upgrade",
                "current_schema_20260808_operation_performance_workbench",
            ],
            cwd=ROOT,
            env={**os.environ, "DATABASE_URL": database_url},
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        assert old_upgrade.returncode == 0, old_upgrade.stderr

        engine = create_engine(database_url)
        with engine.begin() as connection:
            current_target_id = connection.execute(
                text(
                    "INSERT INTO a_class.sales_targets "
                    "(target_name, target_type, scope_type, period_start, period_end, metric_code, "
                    "metric_direction, metric_catalog_version) "
                    "VALUES ('Current target', 'operation', 'shop', '2026-08-01', '2026-08-31', "
                    "'reply', 'higher_better', 7) RETURNING id"
                )
            ).scalar_one()
            # The old trigger only validates matching explicit versions, so a
            # versionless invalid time breakdown can exist in a 20260808 DB.
            connection.execute(
                text(
                    "INSERT INTO a_class.target_breakdown "
                    "(target_id, breakdown_type, period_start, period_end, target_amount, target_quantity, "
                    "achieved_amount, achieved_quantity, achievement_rate) "
                    "VALUES (:target_id, 'time', '2026-08-02', '2026-08-02', 0, 0, 0, 0, 0)"
                ),
                {"target_id": current_target_id},
            )
            connection.execute(text("DROP INDEX a_class.uq_operation_shop_override"))
            connection.execute(
                text(
                    "ALTER TABLE a_class.target_breakdown "
                    "DROP COLUMN operation_contract_version"
                )
            )

        preflight = subprocess.run(
            [
                sys.executable,
                "scripts/run_current_schema_migrations.py",
                "--database-url",
                database_url,
                "--preflight-only",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        assert preflight.returncode == 2
        assert "invalid current operation contract data" in preflight.stderr

        with engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT version_num FROM public.current_schema_alembic_version"
                    )
                ).scalar_one()
                == "current_schema_20260808_operation_performance_workbench"
            )
            assert "operation_contract_version" not in {
                row[0]
                for row in connection.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'a_class' AND table_name = 'target_breakdown'"
                    )
                )
            }
    finally:
        subprocess.run(["docker", "stop", "-t", "1", container_id], check=False)


def test_personal_performance_target_migration_round_trips_from_the_previous_head():
    if not _docker_available():
        pytest.skip("requires a reachable Docker daemon and PostgreSQL 15 image")

    previous_revision = "current_schema_20260817_operation_performance_auto_integer_v1"
    personal_revision = "current_schema_20260822_personal_performance_target_workbench"
    personal_tables = (
        "personal_performance_metric_catalog",
        "personal_performance_plans",
        "personal_performance_employee_scopes",
        "personal_performance_assignment_snapshots",
        "personal_performance_entries",
    )
    port = _free_port()
    started = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-d",
            "-e",
            "POSTGRES_USER=current_test",
            "-e",
            "POSTGRES_PASSWORD=current_test",
            "-e",
            "POSTGRES_DB=current_test",
            "-p",
            f"127.0.0.1:{port}:5432",
            "postgres:15",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    container_id = started.stdout.strip()
    database_url = (
        f"postgresql://current_test:current_test@127.0.0.1:{port}/current_test"
    )
    alembic_env = {**os.environ, "DATABASE_URL": database_url}

    def run_alembic(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "alembic", "-c", "alembic-current.ini", *args],
            cwd=ROOT,
            env=alembic_env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

    try:
        _wait_for_postgres(container_id)
        previous_upgrade = run_alembic("upgrade", previous_revision)
        assert previous_upgrade.returncode == 0, previous_upgrade.stderr

        engine = create_engine(database_url)
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT version_num FROM public.current_schema_alembic_version"
                    )
                ).scalar_one()
                == previous_revision
            )
            inspector = inspect(connection)
            assert all(
                not inspector.has_table(table, schema="a_class")
                for table in personal_tables
            )

        personal_upgrade = run_alembic("upgrade", personal_revision)
        assert personal_upgrade.returncode == 0, personal_upgrade.stderr

        with engine.begin() as connection:
            inspector = inspect(connection)
            assert all(
                inspector.has_table(table, schema="a_class")
                for table in personal_tables
            )
            assert "calculation_details" in {
                column["name"]
                for column in inspector.get_columns(
                    "employee_performance", schema="c_class"
                )
            }
            seeded_metrics = connection.execute(
                text(
                    "SELECT metric_code, metric_name "
                    "FROM a_class.personal_performance_metric_catalog "
                    "WHERE catalog_version = 1 ORDER BY sort_key"
                )
            ).all()
            assert seeded_metrics == [
                ("attendance_compliance_rate", "\u8003\u52e4\u8fbe\u6807\u7387"),
                ("training_completion_rate", "\u57f9\u8bad\u5b8c\u6210\u7387"),
                (
                    "personal_goal_completion_rate",
                    "\u4e2a\u4eba\u76ee\u6807\u5b8c\u6210\u7387",
                ),
                (
                    "personal_special_task",
                    "\u4e13\u9879\u4efb\u52a1\u5b8c\u6210\u60c5\u51b5",
                ),
            ]
            connection.execute(
                text(
                    "INSERT INTO a_class.personal_performance_plans "
                    "(year_month, calculation_mode, catalog_version, scoring_model_version, rule_snapshot) "
                    "VALUES ('2026-10', 'controlled_targets_v1', 1, "
                    "'controlled_targets_v1', '{}'::json)"
                )
            )
            immutable_mode = connection.begin_nested()
            with pytest.raises(Exception, match="calculation mode is immutable"):
                connection.execute(
                    text(
                        "UPDATE a_class.personal_performance_plans "
                        "SET calculation_mode = 'legacy_inputs' "
                        "WHERE year_month = '2026-10'"
                    )
                )
            immutable_mode.rollback()

        blocked_personal_downgrade = run_alembic("downgrade", previous_revision)
        assert blocked_personal_downgrade.returncode != 0
        assert (
            "cannot downgrade personal performance target workbench"
            in blocked_personal_downgrade.stderr
        )

        with engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT version_num FROM public.current_schema_alembic_version"
                    )
                ).scalar_one()
                == personal_revision
            )

        with engine.begin() as connection:
            connection.execute(text("DELETE FROM a_class.personal_performance_plans"))

            connection.execute(
                text(
                    "INSERT INTO c_class.employee_performance "
                    "(employee_code, year_month, actual_sales, achievement_rate, "
                    "performance_score, calculated_at, calculation_status, "
                    "performance_source_type) VALUES "
                    "('CONTROLLED-DOWNGRADE', '2026-10', 0, 0, 0, now(), "
                    "'complete', 'controlled_targets_v1')"
                )
            )

        blocked_controlled_result_downgrade = run_alembic(
            "downgrade", previous_revision
        )
        assert blocked_controlled_result_downgrade.returncode != 0
        assert (
            "cannot downgrade personal performance target workbench"
            in blocked_controlled_result_downgrade.stderr
        )

        with engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT version_num FROM public.current_schema_alembic_version"
                    )
                ).scalar_one()
                == personal_revision
            )

        with engine.begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM c_class.employee_performance "
                    "WHERE employee_code = 'CONTROLLED-DOWNGRADE'"
                )
            )

        personal_downgrade = run_alembic("downgrade", previous_revision)
        assert personal_downgrade.returncode == 0, personal_downgrade.stderr

        with engine.connect() as connection:
            inspector = inspect(connection)
            assert all(
                not inspector.has_table(table, schema="a_class")
                for table in personal_tables
            )
            assert "calculation_details" not in {
                column["name"]
                for column in inspector.get_columns(
                    "employee_performance", schema="c_class"
                )
            }

        personal_reupgrade = run_alembic("upgrade", personal_revision)
        assert personal_reupgrade.returncode == 0, personal_reupgrade.stderr

        with engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT version_num FROM public.current_schema_alembic_version"
                    )
                ).scalar_one()
                == personal_revision
            )
            inspector = inspect(connection)
            assert all(
                inspector.has_table(table, schema="a_class")
                for table in personal_tables
            )
            assert "calculation_details" in {
                column["name"]
                for column in inspector.get_columns(
                    "employee_performance", schema="c_class"
                )
            }
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM a_class.personal_performance_metric_catalog "
                        "WHERE catalog_version = 1"
                    )
                ).scalar_one()
                == 4
            )
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM pg_trigger AS trigger "
                        "JOIN pg_class AS relation ON relation.oid = trigger.tgrelid "
                        "JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace "
                        "WHERE namespace.nspname = 'a_class' "
                        "AND relation.relname = 'personal_performance_plans' "
                        "AND trigger.tgname = 'trg_prevent_personal_performance_plan_mode_change' "
                        "AND NOT trigger.tgisinternal"
                    )
                ).scalar_one()
                == 1
            )
    finally:
        engine.dispose()
        subprocess.run(["docker", "stop", "-t", "1", container_id], check=False)


def test_operation_metric_catalog_v3_round_trips_without_changing_v2_catalog():
    if not _docker_available():
        pytest.skip("requires a reachable Docker daemon and PostgreSQL 15 image")

    personal_revision = "current_schema_20260822_personal_performance_target_workbench"
    v3_revision = "current_schema_20260822_operation_metric_catalog_v3"
    port = _free_port()
    started = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-d",
            "-e",
            "POSTGRES_USER=current_test",
            "-e",
            "POSTGRES_PASSWORD=current_test",
            "-e",
            "POSTGRES_DB=current_test",
            "-p",
            f"127.0.0.1:{port}:5432",
            "postgres:15",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    container_id = started.stdout.strip()
    database_url = (
        f"postgresql://current_test:current_test@127.0.0.1:{port}/current_test"
    )
    alembic_env = {**os.environ, "DATABASE_URL": database_url}

    def run_alembic(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "alembic", "-c", "alembic-current.ini", *args],
            cwd=ROOT,
            env=alembic_env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

    engine = create_engine(database_url)
    try:
        _wait_for_postgres(container_id)
        previous_upgrade = run_alembic("upgrade", personal_revision)
        assert previous_upgrade.returncode == 0, previous_upgrade.stderr

        v3_upgrade = run_alembic("upgrade", v3_revision)
        assert v3_upgrade.returncode == 0, v3_upgrade.stderr

        with engine.connect() as connection:
            v3_codes = (
                connection.execute(
                    text(
                        "SELECT metric_code FROM a_class.operation_metric_catalog "
                        "WHERE catalog_version = 3 ORDER BY sort_key"
                    )
                )
                .scalars()
                .all()
            )
            assert v3_codes == [
                "customer_satisfaction",
                "complaint_count",
                "reply_timeliness",
                "operation_special_check",
            ]
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM a_class.operation_metric_catalog "
                        "WHERE catalog_version = 2 "
                        "AND metric_code = 'training_completion_rate'"
                    )
                ).scalar_one()
                == 1
            )

        v3_downgrade = run_alembic("downgrade", personal_revision)
        assert v3_downgrade.returncode == 0, v3_downgrade.stderr

        with engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM a_class.operation_metric_catalog "
                        "WHERE catalog_version = 3"
                    )
                ).scalar_one()
                == 0
            )
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM a_class.operation_metric_catalog "
                        "WHERE catalog_version = 2 "
                        "AND metric_code = 'training_completion_rate'"
                    )
                ).scalar_one()
                == 1
            )

        v3_reupgrade = run_alembic("upgrade", v3_revision)
        assert v3_reupgrade.returncode == 0, v3_reupgrade.stderr

        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO core.dim_platforms (platform_code, name, is_active) "
                    "VALUES ('v3_test', 'V3 test', true)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO core.dim_shops "
                    "(platform_code, shop_id, shop_name, is_active) "
                    "VALUES ('v3_test', 'S001', 'V3 test shop', true)"
                )
            )
            target_id = connection.execute(
                text(
                    """
                    INSERT INTO a_class.sales_targets
                        (target_name, target_type, scope_type, period_start, period_end,
                         metric_code, metric_name, metric_direction, metric_catalog_version,
                         scoring_model_version, operation_rule_snapshot)
                    VALUES
                        ('V3 rule', 'operation', 'shop', '2026-08-01', '2026-08-31',
                         'customer_satisfaction', 'Customer satisfaction', 'higher_better', 3,
                         'auto_integer_v1', '{}'::jsonb)
                    RETURNING id
                    """
                )
            ).scalar_one()
            connection.execute(
                text(
                    """
                    INSERT INTO a_class.operation_performance_shop_scopes
                        (year_month, platform_code, shop_id, is_included, snapshot_version,
                         confirmed_at)
                    VALUES ('2026-08', 'v3_test', 'S001', true, 1, now())
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO a_class.target_breakdown
                        (target_id, breakdown_type, platform_code, shop_id, period_start,
                         period_end, target_amount, target_quantity, achieved_amount,
                         achieved_quantity, achievement_rate, operation_contract_version,
                         operation_input_payload)
                    VALUES
                        (:target_id, 'shop', 'v3_test', 'S001', '2026-08-01',
                         '2026-08-31', 0, 0, 0, 0, 0, 3, '{}'::jsonb)
                    """
                ),
                {"target_id": target_id},
            )

        blocked_downgrade = run_alembic("downgrade", personal_revision)
        assert blocked_downgrade.returncode != 0
        assert (
            "cannot downgrade operation metric catalog V3" in blocked_downgrade.stderr
        )
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT version_num FROM public.current_schema_alembic_version"
                    )
                ).scalar_one()
                == v3_revision
            )
    finally:
        engine.dispose()
        subprocess.run(["docker", "stop", "-t", "1", container_id], check=False)
