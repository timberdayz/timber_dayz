from pathlib import Path


def test_readiness_review_recommends_preprod_gray():
    text = Path("docs/development/POSTGRESQL_DASHBOARD_READINESS_REVIEW_2026-03-22.md").read_text(
        encoding="utf-8"
    )
    assert "Recommended next step: enter pre-production gray validation." in text
    assert "no code-level blockers" in text
    assert "Go for pre-production gray validation." in text
