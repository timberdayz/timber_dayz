"""``verify_schema_completeness()`` 的行为守护。

⚠️ 迁移链口径(2026-08-09 起)
---------------------------
``backend/models/database.py`` 的 ``verify_schema_completeness()`` 已经改用
**当前**迁移链(``alembic-current.ini``)与 ``public.current_schema_alembic_version``
来判定迁移状态(commit ``98381ebf``「refactor: establish current schema migration
chain」)⇒ 旧的 ``_get_alembic_revisions_by_schema`` /
``_pick_effective_current_revision`` 不再参与这条路径。

所以本文件的假件(fixture)按新链路来搭:
``_FakeInspector`` 需要 ``has_table``, 连接需要能返回当前 revision 行。
"""

from alembic.config import Config
from alembic.script import ScriptDirectory


def _current_chain_head() -> str:
    return ScriptDirectory.from_config(Config("alembic-current.ini")).get_current_head()


def test_verify_schema_completeness_reports_missing_sync_columns(monkeypatch):
    import backend.models.database as database_module

    head_revision = _current_chain_head()

    class _FakeInspector:
        def get_schema_names(self):
            return ["core"]

        def get_table_names(self, schema=None):
            return []

        def has_table(self, table_name, schema=None):
            # 当前链把版本表放在 public.current_schema_alembic_version
            return True

    class _FakeResult:
        def scalars(self):
            return self

        def all(self):
            return [head_revision]

    class _FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, *_args, **_kwargs):
            return _FakeResult()

    class _FakeEngine:
        def connect(self):
            return _FakeConnection()

    monkeypatch.setattr(database_module, "engine", _FakeEngine())
    monkeypatch.setattr("sqlalchemy.inspect", lambda _obj: _FakeInspector())
    monkeypatch.setattr(
        database_module,
        "_collect_existing_tables",
        lambda _inspector: set(database_module.Base.metadata.tables.keys()),
    )
    monkeypatch.setattr(
        database_module,
        "_find_missing_critical_columns",
        lambda _inspector, existing_tables=None: [
            "core.data_quarantine.catalog_file_id"
        ],
        raising=False,
    )

    result = database_module.verify_schema_completeness()

    assert result["all_tables_exist"] is True
    assert result["all_critical_columns_exist"] is False
    assert result["missing_columns"] == ["core.data_quarantine.catalog_file_id"]
    assert result["migration_status"] == "up_to_date"
    assert result["current_revision"] == head_revision
    assert result["head_revision"] == head_revision


def test_data_sync_critical_columns_include_template_header_bindings():
    import backend.models.database as database_module

    assert "core.field_mapping_templates" in database_module.DATA_SYNC_CRITICAL_COLUMNS
    assert (
        "header_bindings"
        in database_module.DATA_SYNC_CRITICAL_COLUMNS["core.field_mapping_templates"]
    )
