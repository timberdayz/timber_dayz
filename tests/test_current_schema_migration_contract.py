import json
from pathlib import Path

import pytest

import scripts.run_current_schema_migrations as migration_runner
from scripts.generate_current_schema_baseline import (
    _clean_dump,
    _split_sql_statements,
    generate_baseline_source,
)
from scripts.run_current_schema_migrations import (
    MigrationDiagnosis,
    MigrationSafetyError,
    MigrationState,
    choose_migration_action,
    diagnose_migration_state,
    failure_code_for,
    run_current_schema_migrations,
    schema_fingerprint,
)


ROOT = Path(__file__).resolve().parents[1]
CURRENT_OPERATION_CONTRACT_FIX = (
    ROOT
    / "current_migrations"
    / "versions"
    / "20260810_operation_contract_isolation.py"
)
CURRENT_CONFIG = ROOT / "alembic-current.ini"
CURRENT_BASELINE = (
    ROOT / "current_migrations" / "versions" / "20260805_current_schema_baseline.py"
)
CURRENT_ENTRYPOINT = ROOT / "scripts" / "run_current_schema_migrations.py"
APPROVED_LEGACY_REVISION = "20260805_payroll_backfill_audit"
APPROVED_LEGACY_FINGERPRINT = (
    "5f27584d2911a7fff4ea659c954f5e8d152f984a9226f8d505acae46d8037578"
)


def test_empty_database_uses_only_the_current_upgrade_path():
    action = choose_migration_action(
        MigrationState(
            database_empty=True,
            current_revision=None,
            legacy_revision=None,
            schema_fingerprint=None,
        ),
        expected_source_revision=None,
    )

    assert action == "upgrade"


def test_unapproved_existing_database_is_rejected_before_writing():
    state = MigrationState(
        database_empty=False,
        current_revision=None,
        legacy_revision="legacy_20260808",
        schema_fingerprint="fingerprint-20260808",
    )

    with pytest.raises(MigrationSafetyError, match="not an approved legacy source"):
        choose_migration_action(state, expected_source_revision=None)


def test_existing_database_rejects_a_source_revision_that_does_not_match_read_only_probe():
    state = MigrationState(
        database_empty=False,
        current_revision=None,
        legacy_revision=APPROVED_LEGACY_REVISION,
        schema_fingerprint=APPROVED_LEGACY_FINGERPRINT,
    )

    with pytest.raises(MigrationSafetyError, match="does not match"):
        choose_migration_action(
            state,
            expected_source_revision="legacy_20260807",
            expected_source_fingerprint=APPROVED_LEGACY_FINGERPRINT,
        )


def test_approved_existing_database_stamps_current_baseline_without_caller_authorization():
    state = MigrationState(
        database_empty=False,
        current_revision=None,
        legacy_revision=APPROVED_LEGACY_REVISION,
        schema_fingerprint=APPROVED_LEGACY_FINGERPRINT,
    )

    assert (
        choose_migration_action(
            state,
            expected_source_revision=None,
            expected_source_fingerprint=None,
        )
        == "stamp"
    )


def test_unapproved_legacy_revision_and_fingerprint_cannot_self_authorize_adoption():
    state = MigrationState(
        database_empty=False,
        current_revision=None,
        legacy_revision="unknown_legacy_revision",
        schema_fingerprint="unknown_legacy_fingerprint",
    )

    with pytest.raises(MigrationSafetyError, match="not an approved legacy source"):
        choose_migration_action(
            state,
            expected_source_revision="unknown_legacy_revision",
            expected_source_fingerprint="unknown_legacy_fingerprint",
        )


def test_already_current_database_uses_the_current_chain_without_legacy_guessing():
    state = MigrationState(
        database_empty=False,
        current_revision="current_schema_20260808_operation_performance_workbench",
        legacy_revision=APPROVED_LEGACY_REVISION,
        schema_fingerprint=APPROVED_LEGACY_FINGERPRINT,
    )

    assert choose_migration_action(state, expected_source_revision=None) == "upgrade"


def test_unknown_current_revision_is_rejected_before_any_writer_is_called():
    state = MigrationState(
        database_empty=False,
        current_revision="current_schema_unknown",
        legacy_revision=None,
        schema_fingerprint="fingerprint-unknown",
    )

    with pytest.raises(MigrationSafetyError, match="not a supported current revision"):
        choose_migration_action(state, expected_source_revision=None)


def test_reachable_current_increment_is_accepted_without_changing_a_hardcoded_head():
    state = MigrationState(
        database_empty=False,
        current_revision="current_schema_20260810_additive_change",
        legacy_revision=None,
        schema_fingerprint="fingerprint-current",
    )

    assert (
        choose_migration_action(
            state,
            expected_source_revision=None,
            supported_current_revisions={
                "current_schema_20260805",
                "current_schema_20260810_additive_change",
            },
        )
        == "upgrade"
    )


def test_approved_revision_with_mismatched_database_fingerprint_is_rejected():
    state = MigrationState(
        database_empty=False,
        current_revision=None,
        legacy_revision=APPROVED_LEGACY_REVISION,
        schema_fingerprint="wrong_fingerprint",
    )

    with pytest.raises(MigrationSafetyError, match="fingerprint is not approved"):
        choose_migration_action(
            state,
            expected_source_revision=APPROVED_LEGACY_REVISION,
            expected_source_fingerprint=None,
        )


def test_existing_database_rejects_a_mismatched_schema_fingerprint_before_stamping():
    state = MigrationState(
        database_empty=False,
        current_revision=None,
        legacy_revision=APPROVED_LEGACY_REVISION,
        schema_fingerprint=APPROVED_LEGACY_FINGERPRINT,
    )

    with pytest.raises(
        MigrationSafetyError, match="fingerprint does not match the approved"
    ):
        choose_migration_action(
            state,
            expected_source_revision=APPROVED_LEGACY_REVISION,
            expected_source_fingerprint="fingerprint-20260807",
        )


def test_schema_drift_has_a_stable_failure_code_and_actionable_diagnosis(monkeypatch):
    state = MigrationState(
        database_empty=False,
        current_revision=None,
        legacy_revision=APPROVED_LEGACY_REVISION,
        schema_fingerprint="unexpected-fingerprint",
    )
    monkeypatch.setattr(
        migration_runner,
        "probe_migration_state",
        lambda _database_url: state,
    )
    monkeypatch.setattr(
        migration_runner,
        "schema_object_summary",
        lambda _database_url: {"tables": [{"schema": "public", "name": "orders"}]},
    )

    diagnosis = diagnose_migration_state("postgresql://not-disclosed")

    assert isinstance(diagnosis, MigrationDiagnosis)
    assert diagnosis.failure_code == "migration_schema_drift"
    assert diagnosis.recommended_action == "manual_schema_review"
    assert diagnosis.actual_fingerprint == "unexpected-fingerprint"
    assert diagnosis.approved_fingerprint == APPROVED_LEGACY_FINGERPRINT
    assert diagnosis.object_summary["tables"] == [{"schema": "public", "name": "orders"}]
    assert "postgresql" not in diagnosis.to_dict().__repr__()


def test_schema_object_summary_reports_column_defaults_without_business_rows(monkeypatch):
    class Inspector:
        def get_schema_names(self):
            return ["public"]

        def get_table_names(self, schema):
            return ["orders"]

        def get_columns(self, table, schema):
            return [{"name": "id", "type": "integer", "nullable": False, "default": "nextval('orders_id_seq')"}]

        def get_pk_constraint(self, table, schema):
            return {"constrained_columns": ["id"]}

        def get_unique_constraints(self, table, schema):
            return []

        def get_foreign_keys(self, table, schema):
            return []

        def get_check_constraints(self, table, schema):
            return []

        def get_indexes(self, table, schema):
            return []

        def get_view_names(self, schema):
            return []

    class Connection:
        def execute(self, _query):
            raise RuntimeError("catalog unavailable in unit test")

    class Engine:
        def connect(self):
            class Context:
                def __enter__(self):
                    return Connection()

                def __exit__(self, *_args):
                    return None

            return Context()

        def dispose(self):
            return None

    monkeypatch.setattr(migration_runner, "create_engine", lambda _url: Engine())
    monkeypatch.setattr(migration_runner, "inspect", lambda _connection: Inspector())

    summary = migration_runner.schema_object_summary("postgresql://not-disclosed")

    assert summary["columns"] == [
        {
            "schema": "public",
            "table": "orders",
            "columns": [
                {"name": "id", "type": "integer", "nullable": False, "default": "nextval('orders_id_seq')"}
            ],
        }
    ]


def test_migration_failure_code_classifies_unapproved_sources_and_backup_failures():
    assert failure_code_for(MigrationSafetyError("database revision is not an approved legacy source")) == (
        "migration_unapproved_source"
    )
    assert failure_code_for(MigrationSafetyError("database schema fingerprint is not approved")) == (
        "migration_schema_drift"
    )
    assert failure_code_for(MigrationSafetyError("migration backup validation failed")) == (
        "migration_backup_failed"
    )


def test_migration_cli_emits_backup_failure_protocol_without_connection_details(
    monkeypatch, capsys
):
    monkeypatch.setattr(
        migration_runner,
        "run_current_schema_migrations",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            MigrationSafetyError("migration backup validation failed: pg_restore --list failed")
        ),
    )
    monkeypatch.setattr(
        migration_runner.sys,
        "argv",
        ["run_current_schema_migrations.py", "--database-url", "postgresql://user:secret@example/db"],
    )

    assert migration_runner.main() == 2
    captured = capsys.readouterr()
    assert "XIHONG_FAILURE_CODE=migration_backup_failed" in captured.err
    assert "XIHONG_SOURCE_EXIT_CODE=2" in captured.err
    assert "secret" not in captured.err


def test_support_policy_requires_a_versioned_manifest_with_integrity_metadata():
    policy = json.loads(
        (ROOT / "current_migrations" / "support_policy.json").read_text(encoding="utf-8")
    )
    source = policy["approved_legacy_sources"][0]

    assert source["manifest_version"] == 1
    assert source["manifest_path"].startswith("current_migrations/manifests/")
    assert len(source["manifest_sha256"]) == 64
    assert source["approval_note"]


def test_approved_source_rejects_tampered_schema_manifest(tmp_path, monkeypatch):
    policy_path = tmp_path / "support_policy.json"
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text('{"manifest_version":1}', encoding="utf-8")
    policy_path.write_text(
        json.dumps(
            {
                "approved_legacy_sources": [
                    {
                        "legacy_revision": APPROVED_LEGACY_REVISION,
                        "schema_fingerprint": APPROVED_LEGACY_FINGERPRINT,
                        "baseline_revision": "current_schema_20260805",
                        "manifest_version": 1,
                        "manifest_path": str(manifest_path),
                        "manifest_sha256": "0" * 64,
                        "approval_note": "test approval",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(migration_runner, "SUPPORT_POLICY_PATH", policy_path)
    state = MigrationState(
        database_empty=False,
        current_revision=None,
        legacy_revision=APPROVED_LEGACY_REVISION,
        schema_fingerprint=APPROVED_LEGACY_FINGERPRINT,
    )

    with pytest.raises(MigrationSafetyError, match="manifest integrity check failed"):
        choose_migration_action(state, expected_source_revision=None)


def test_current_migration_files_are_isolated_from_historical_versions_and_static():
    config_source = CURRENT_CONFIG.read_text(encoding="utf-8")
    baseline_source = CURRENT_BASELINE.read_text(encoding="utf-8")

    assert "script_location = current_migrations" in config_source
    assert "version_table = current_schema_alembic_version" in config_source
    assert 'revision = "current_schema_20260805"' in baseline_source
    assert "down_revision = None" in baseline_source
    assert baseline_source.count("CREATE TABLE") >= 165
    assert "public.sales_targets" not in baseline_source
    assert "CREATE TABLE core.alembic_version (" not in baseline_source
    assert "CREATE TABLE public.alembic_version (" not in baseline_source
    assert (
        "CREATE TABLE core.data_quarantine (\\n    id integer NOT NULL,\\n    platform"
        not in baseline_source
    )
    assert "Base.metadata" not in baseline_source
    assert "Base.metadata.create_all" not in baseline_source

    increment_source = (
        ROOT
        / "current_migrations"
        / "versions"
        / "20260808_operation_performance_workbench.py"
    ).read_text(encoding="utf-8")
    assert 'down_revision = "current_schema_20260805"' in increment_source
    assert "operation_metric_catalog" in increment_source
    assert "DELETE FROM a_class.target_breakdown AS duplicate" not in increment_source
    assert "UPDATE a_class.sales_targets" not in increment_source
    assert "UPDATE a_class.target_breakdown" not in increment_source
    assert "operation_contract_version" in increment_source
    assert "metric_catalog_version IS NOT NULL" in increment_source


def test_operation_contract_isolated_from_legacy_rows_in_the_migration_and_ssot():
    business_schema_source = (
        ROOT / "modules" / "core" / "db" / "schema_parts" / "business.py"
    ).read_text(encoding="utf-8")
    entrypoint_source = CURRENT_ENTRYPOINT.read_text(encoding="utf-8")

    assert "operation_contract_version = Column(" in business_schema_source
    assert (
        'Integer, nullable=True, comment="运营工作台合同版本快照"'
        in business_schema_source
    )
    assert "--audit-legacy-operation-data" in entrypoint_source
    assert "audit_legacy_operation_data" in entrypoint_source
    assert "legacy operation data summary" in entrypoint_source


def test_current_operation_contract_fix_is_a_followup_migration_for_existing_20260808_databases():
    source = CURRENT_OPERATION_CONTRACT_FIX.read_text(encoding="utf-8")

    assert 'revision = "current_schema_20260810_operation_contract_isolation"' in source
    assert (
        'down_revision = "current_schema_20260808_operation_performance_workbench"'
        in source
    )
    assert "operation_contract_version" in source
    assert "DROP TRIGGER IF EXISTS trg_enforce_operation_target_contract" in source
    assert "DROP TRIGGER IF EXISTS trg_enforce_operation_breakdown_contract" in source
    assert "DROP INDEX IF EXISTS a_class.uq_operation_target_month_metric" in source
    assert "DROP INDEX IF EXISTS a_class.uq_operation_shop_override" in source
    assert "IS DISTINCT FROM parent_target.metric_catalog_version" in source


def test_unified_entrypoint_probes_before_invoking_current_alembic_writer():
    source = CURRENT_ENTRYPOINT.read_text(encoding="utf-8")

    assert "probe_migration_state" in source
    assert "schema_fingerprint" in source
    assert "choose_migration_action" in source
    assert '"-c"' in source
    assert '"alembic-current.ini"' in source
    assert "Base.metadata.create_all" not in source


def test_current_adoption_preflight_rejects_null_or_mismatched_breakdown_versions():
    source = CURRENT_ENTRYPOINT.read_text(encoding="utf-8")

    assert (
        "tb.operation_contract_version IS DISTINCT FROM st.metric_catalog_version"
        in source
    )


def test_operational_migration_entrypoints_delegate_to_the_fail_closed_wrapper():
    paths = [
        ROOT / "scripts" / "deploy_remote_production.sh",
        ROOT / "scripts" / "start_collection_formal.ps1",
        ROOT / "scripts" / "validate_migrations_fresh_db.py",
        ROOT / "scripts" / "rehearsal_prod_snapshot.py",
        ROOT / "docker-compose.prod.yml",
        ROOT / "docker" / "scripts" / "backend-entrypoint.sh",
    ]

    for path in paths:
        source = path.read_text(encoding="utf-8")
        assert "run_current_schema_migrations.py" in source, path

    deploy_source = paths[0].read_text(encoding="utf-8")
    assert "CURRENT_SCHEMA_SOURCE_REVISION" in deploy_source
    assert "alembic upgrade heads" not in deploy_source
    assert "CURRENT_SCHEMA_SOURCE_REVISION is required" not in deploy_source
    assert "CURRENT_SCHEMA_SOURCE_FINGERPRINT is required" not in deploy_source

    compose_source = (ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
    assert "CURRENT_SCHEMA_SOURCE_REVISION:?" not in compose_source
    assert "CURRENT_SCHEMA_SOURCE_FINGERPRINT:?" not in compose_source

    dockerfile_source = (ROOT / "Dockerfile.backend").read_text(encoding="utf-8")
    assert "COPY migrations /app/migrations" not in dockerfile_source
    assert "COPY alembic.ini /app/alembic.ini" not in dockerfile_source


def test_legacy_adoption_stamps_the_baseline_then_runs_current_increments(monkeypatch):
    state = MigrationState(
        database_empty=False,
        current_revision=None,
        legacy_revision=APPROVED_LEGACY_REVISION,
        schema_fingerprint=APPROVED_LEGACY_FINGERPRINT,
    )
    commands: list[list[str]] = []

    monkeypatch.setattr(migration_runner, "probe_migration_state", lambda _: state)
    monkeypatch.setattr(
        migration_runner,
        "get_supported_current_revisions",
        lambda: {
            "current_schema_20260805",
            "current_schema_20260808_operation_performance_workbench",
        },
    )
    monkeypatch.setattr(
        migration_runner,
        "assert_legacy_adoption_data_is_safe",
        lambda _: None,
    )
    monkeypatch.setattr(
        migration_runner,
        "create_and_verify_backup",
        lambda *_args, **_kwargs: {"metadata_path": "backup.json"},
    )
    monkeypatch.setattr(
        migration_runner,
        "verify_backup_metadata",
        lambda *_args, **_kwargs: None,
    )

    class Lock:
        def __enter__(self):
            return None

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr(migration_runner, "migration_advisory_lock", lambda _: Lock())

    def record_command(command, **_kwargs):
        commands.append(command)
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(migration_runner.subprocess, "run", record_command)

    assert (
        run_current_schema_migrations(
            "postgresql://example",
            expected_source_revision=APPROVED_LEGACY_REVISION,
            expected_source_fingerprint=APPROVED_LEGACY_FINGERPRINT,
        )
        == "stamp"
    )
    assert commands == [
        [
            migration_runner.sys.executable,
            "-m",
            "alembic",
            "-c",
            "alembic-current.ini",
            "stamp",
            "current_schema_20260805",
        ],
        [
            migration_runner.sys.executable,
            "-m",
            "alembic",
            "-c",
            "alembic-current.ini",
            "upgrade",
            "head",
        ],
    ]


def test_nonempty_migration_creates_verified_backup_and_rechecks_under_lock(monkeypatch):
    state = MigrationState(
        database_empty=False,
        current_revision=None,
        legacy_revision=APPROVED_LEGACY_REVISION,
        schema_fingerprint=APPROVED_LEGACY_FINGERPRINT,
    )
    events: list[str] = []
    monkeypatch.setenv(migration_runner.LOCAL_BACKUP_GUARD_ENV, "1")
    monkeypatch.setattr(migration_runner, "probe_migration_state", lambda _: state)
    monkeypatch.setattr(
        migration_runner,
        "preflight_current_schema_migrations",
        lambda *_args, **_kwargs: events.append("preflight") or "stamp",
    )
    monkeypatch.setattr(
        migration_runner,
        "create_and_verify_backup",
        lambda *_args, **_kwargs: events.append("backup") or {"metadata_path": "backup.json"},
    )
    monkeypatch.setattr(
        migration_runner,
        "verify_backup_metadata",
        lambda *_args, **_kwargs: events.append("verify-backup"),
    )

    class Lock:
        def __enter__(self):
            events.append("lock")

        def __exit__(self, *_args):
            events.append("unlock")

    monkeypatch.setattr(migration_runner, "migration_advisory_lock", lambda _: Lock())
    monkeypatch.setattr(migration_runner, "get_current_schema_baseline_revision", lambda: "current_schema_20260805")
    monkeypatch.setattr(
        migration_runner.subprocess,
        "run",
        lambda *_args, **_kwargs: type("Result", (), {"returncode": 0})(),
    )

    assert run_current_schema_migrations("postgresql://example", expected_source_revision=None, expected_source_fingerprint=None) == "stamp"
    assert events == ["preflight", "backup", "lock", "preflight", "verify-backup", "unlock"]


def test_empty_database_does_not_attempt_backup_before_migration(monkeypatch):
    state = MigrationState(True, None, None, None)
    monkeypatch.setattr(migration_runner, "probe_migration_state", lambda _: state)
    monkeypatch.setattr(migration_runner, "preflight_current_schema_migrations", lambda *_args, **_kwargs: "upgrade")
    monkeypatch.setattr(
        migration_runner,
        "create_and_verify_backup",
        lambda *_args, **_kwargs: pytest.fail("empty database must not be backed up"),
    )

    class Lock:
        def __enter__(self):
            return None

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr(migration_runner, "migration_advisory_lock", lambda _: Lock())
    monkeypatch.setattr(
        migration_runner.subprocess,
        "run",
        lambda *_args, **_kwargs: type("Result", (), {"returncode": 0})(),
    )

    assert run_current_schema_migrations("postgresql://example", expected_source_revision=None, expected_source_fingerprint=None) == "upgrade"


def test_schema_fingerprint_supports_postgresql_expression_indexes():
    class ExpressionIndexInspector:
        def get_schema_names(self):
            return ["public"]

        def get_table_names(self, schema):
            assert schema == "public"
            return ["fact_orders"]

        def get_columns(self, table, schema):
            return []

        def get_foreign_keys(self, table, schema):
            return []

        def get_indexes(self, table, schema):
            return [
                {
                    "name": "uq_fact_orders_hash",
                    "column_names": [None, "order_id"],
                    "expressions": ["md5(payload::text)", None],
                    "unique": True,
                }
            ]

        def get_pk_constraint(self, table, schema):
            return {"constrained_columns": []}

        def get_unique_constraints(self, table, schema):
            return []

    assert len(schema_fingerprint(None, ExpressionIndexInspector())) == 64


def test_schema_fingerprint_ignores_only_exact_current_and_historical_version_tables():
    class VersionTableInspector:
        def get_schema_names(self):
            return ["core", "public", "archive"]

        def get_table_names(self, schema):
            return ["alembic_version"] if schema in {"core", "archive"} else [
                "alembic_version",
                "alembic_version__archive_retired",
                "current_schema_alembic_version",
            ]

        def get_columns(self, table, schema):
            return [{"name": "version_num", "nullable": False, "type": "varchar", "default": None}]

        def get_foreign_keys(self, table, schema):
            return []

        def get_indexes(self, table, schema):
            return []

        def get_pk_constraint(self, table, schema):
            return {"constrained_columns": ["version_num"]}

        def get_unique_constraints(self, table, schema):
            return []

    exact = schema_fingerprint(None, VersionTableInspector())

    class WithoutArchiveVersionInspector(VersionTableInspector):
        def get_table_names(self, schema):
            tables = super().get_table_names(schema)
            return [table for table in tables if not (schema == "archive" and table == "alembic_version")]

    assert exact != schema_fingerprint(None, WithoutArchiveVersionInspector())


def test_baseline_generator_omits_only_retired_quarantine_columns():
    dump = (
        "\ufeff"
        + """
        CREATE TABLE core.data_quarantine (
            id integer NOT NULL,
            settlement_id integer NOT NULL,
            platform character varying(50),
        data_type character varying(100),
        platform_code character varying(32),
        shop_id character varying(64)
    );
    """
    )

    cleaned = _clean_dump(dump)

    assert "platform character varying(50)" not in cleaned
    assert "data_type character varying(100)" not in cleaned
    assert "platform_code character varying(32)" in cleaned
    assert "shop_id character varying(64)" in cleaned
    assert "settlement_id integer NOT NULL" in cleaned
    assert "\ufeff" not in cleaned


def test_baseline_generator_omits_archived_alembic_version_tables():
    dump = """
        CREATE TABLE core.alembic_version (
            version_num character varying(32) NOT NULL
        );
        ALTER TABLE ONLY core.alembic_version
            ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);
        CREATE TABLE public.alembic_version__archive_retired (
            version_num character varying(32) NOT NULL
        );
        CREATE MATERIALIZED VIEW b_class.test AS SELECT 1 AS id;
        CREATE TABLE a_class.live_configuration (
            id integer NOT NULL
        );
    """

    baseline = generate_baseline_source(dump)

    assert "core.alembic_version" not in baseline
    assert "alembic_version__archive_retired" not in baseline
    assert "CREATE MATERIALIZED VIEW b_class.test" not in baseline
    assert "a_class.live_configuration" in baseline


def test_baseline_generator_keeps_function_body_semicolons_in_one_statement():
    statements = _split_sql_statements(
        "CREATE FUNCTION core.test() RETURNS void AS $$ BEGIN PERFORM 1; END; $$ LANGUAGE plpgsql;"
        "CREATE TABLE core.test_table (id integer);"
    )

    assert statements == [
        "CREATE FUNCTION core.test() RETURNS void AS $$ BEGIN PERFORM 1; END; $$ LANGUAGE plpgsql",
        "CREATE TABLE core.test_table (id integer)",
    ]


def test_non_orm_runtime_objects_are_captured_or_assigned_to_their_existing_owner():
    manifest = (ROOT / "current_migrations" / "README.md").read_text(encoding="utf-8")
    baseline = CURRENT_BASELINE.read_text(encoding="utf-8")
    increment = (
        ROOT
        / "current_migrations"
        / "versions"
        / "20260808_operation_performance_workbench.py"
    ).read_text(encoding="utf-8")

    assert "trg_enforce_operation_target_contract" in increment
    assert "trg_enforce_operation_breakdown_contract" in increment
    assert "operation_metric_catalog" in increment
    assert "CREATE MATERIALIZED VIEW" in baseline
    assert "bootstrap_postgresql_dashboard.py" in manifest
    assert "dashboard" in manifest.lower()
