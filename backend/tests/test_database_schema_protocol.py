from backend.models.database import schema_failure_protocol


def test_schema_failure_protocol_is_bounded_and_uses_current_schema_recovery():
    protocol = schema_failure_protocol(
        {
            "missing_tables": [f"a_class.table_{index}" for index in range(12)],
            "missing_columns": ["core.example.column"],
        }
    )

    assert protocol["code"] == "schema_incomplete"
    assert "a_class.table_0" in protocol["summary"]
    assert "a_class.table_10" not in protocol["summary"]
    assert "current-schema" in protocol["hint"]
    assert "alembic upgrade heads" not in protocol["hint"]
