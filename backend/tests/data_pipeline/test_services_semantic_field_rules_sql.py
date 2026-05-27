from pathlib import Path


def _block_before(sql_text: str, marker: str) -> str:
    return sql_text.split(marker, 1)[0].rsplit("COALESCE(", 1)[-1]


def test_services_atomic_sql_does_not_merge_buyer_count_into_order_count():
    sql_text = Path("sql/semantic/services_atomic.sql").read_text(
        encoding="utf-8",
        errors="replace",
    )
    block = _block_before(sql_text, "AS order_count_raw")

    assert "raw_data->>'买家数'" not in block


def test_services_atomic_sql_exposes_buyer_count_field():
    sql_text = Path("sql/semantic/services_atomic.sql").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "buyer_count_raw" in sql_text
    assert "buyer_count" in sql_text
