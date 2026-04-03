from alembic.config import Config
from alembic.script import ScriptDirectory


def test_verify_schema_completeness_reports_missing_sync_columns(monkeypatch):
    import backend.models.database as database_module

    class _FakeInspector:
        def get_schema_names(self):
            return ["core"]

        def get_table_names(self, schema=None):
            return []

    class _FakeConnection:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    class _FakeEngine:
        def connect(self):
            return _FakeConnection()

    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)
    head_revision = script.get_current_head()

    monkeypatch.setattr(database_module, "engine", _FakeEngine())
    monkeypatch.setattr("sqlalchemy.inspect", lambda _obj: _FakeInspector())
    monkeypatch.setattr(
        database_module,
        "_collect_existing_tables",
        lambda _inspector: set(database_module.Base.metadata.tables.keys()),
    )
    monkeypatch.setattr(
        database_module,
        "_get_alembic_revisions_by_schema",
        lambda _conn, inspector=None: {"core": head_revision},
    )
    monkeypatch.setattr(
        database_module,
        "_pick_effective_current_revision",
        lambda _revisions, head: head,
    )
    monkeypatch.setattr(
        database_module,
        "_find_missing_critical_columns",
        lambda _inspector, existing_tables=None: ["core.data_quarantine.catalog_file_id"],
        raising=False,
    )

    result = database_module.verify_schema_completeness()

    assert result["all_tables_exist"] is True
    assert result["all_critical_columns_exist"] is False
    assert result["missing_columns"] == ["core.data_quarantine.catalog_file_id"]
    assert result["migration_status"] == "up_to_date"
