from pathlib import Path


def test_verify_performance_display_acceptance_allows_update_or_insert_write_evidence():
    text = Path("scripts/verify_performance_display_acceptance.py").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert 'after >= before' in text
    assert 'shop_performance_upserts' in text
    assert '有效写入 performance_scores' in text
    assert 'after > before' not in text
