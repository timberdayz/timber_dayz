def test_migration_rehearsal_reports_missing_data_sync_critical_columns():
    from scripts.validate_migrations_fresh_db import find_missing_data_sync_critical_columns

    class _FakeInspector:
        def get_columns(self, table_name, schema=None):
            columns_by_table = {
                ("core", "data_quarantine"): [{"name": "id"}, {"name": "source_file"}],
                ("core", "staging_orders"): [{"name": "id"}, {"name": "file_id"}],
                ("core", "staging_product_metrics"): [{"name": "id"}, {"name": "file_id"}],
                ("core", "staging_inventory"): [{"name": "id"}, {"name": "file_id"}],
            }
            return columns_by_table.get((schema, table_name), [])

    missing = find_missing_data_sync_critical_columns(_FakeInspector())

    assert missing == ["core.data_quarantine.catalog_file_id"]


def test_migration_rehearsal_accepts_complete_data_sync_critical_columns():
    from scripts.validate_migrations_fresh_db import find_missing_data_sync_critical_columns

    class _FakeInspector:
        def get_columns(self, table_name, schema=None):
            columns_by_table = {
                ("core", "data_quarantine"): [
                    {"name": "id"},
                    {"name": "source_file"},
                    {"name": "catalog_file_id"},
                ],
                ("core", "staging_orders"): [{"name": "id"}, {"name": "file_id"}],
                ("core", "staging_product_metrics"): [{"name": "id"}, {"name": "file_id"}],
                ("core", "staging_inventory"): [{"name": "id"}, {"name": "file_id"}],
            }
            return columns_by_table.get((schema, table_name), [])

    missing = find_missing_data_sync_critical_columns(_FakeInspector())

    assert missing == []
