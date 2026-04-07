import pytest

from modules.core.db import (
    Account,
    DataFile,
    DataQuarantine,
    DataRecord,
    FieldMapping,
    MappingSession,
    SyncProgressTask,
)


@pytest.mark.parametrize(
    ("model", "table_name"),
    [
        (Account, "accounts"),
        (DataFile, "data_files"),
        (DataQuarantine, "data_quarantine"),
        (DataRecord, "data_records"),
        (FieldMapping, "field_mappings"),
        (MappingSession, "mapping_sessions"),
        (SyncProgressTask, "sync_progress_tasks"),
    ],
)
def test_wave_b_tables_bind_explicitly_to_core_schema(model, table_name):
    table = model.__table__

    assert table.name == table_name
    assert table.schema == "core"
    assert table.fullname == f"core.{table_name}"


def test_field_mapping_file_fk_targets_core_data_files():
    fk_targets = {fk.target_fullname for fk in FieldMapping.__table__.foreign_keys}

    assert "core.data_files.id" in fk_targets
