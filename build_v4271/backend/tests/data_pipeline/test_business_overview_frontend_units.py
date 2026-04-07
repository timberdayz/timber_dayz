from pathlib import Path


def test_business_overview_frontend_no_longer_marks_raw_amounts_as_w():
    text = Path("frontend/src/views/BusinessOverview.vue").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "(w)" not in text
    assert 'const targetUnit = ref("")' in text
