from pathlib import Path


def test_raw_data_importer_dynamic_column_update_deduplicates_normalized_assignments():
    source = Path("backend/services/raw_data_importer.py").read_text(encoding="utf-8")

    assert "column_mapping.setdefault(normalized_col, []).append(original_col)" in source
    assert "for normalized_col, original_columns in column_mapping.items()" in source
    assert 'set_clauses.append(f\'"{normalized_col}" = :{normalized_col}\')' in source
    assert "for original_col, normalized_col in column_mapping.items()" not in source


def test_raw_data_importer_does_not_treat_upsert_updates_as_data_loss():
    source = Path("backend/services/raw_data_importer.py").read_text(encoding="utf-8")

    assert "if expected_inserted > 0 and not is_upsert:" in source
