from pathlib import Path


def test_cloud_cutover_report_exists_and_records_success():
    text = Path(
        "docs/development/CLOUD_DIRECT_POSTGRESQL_DASHBOARD_CUTOVER_REPORT_2026-03-23.md"
    ).read_text(encoding="utf-8", errors="replace")

    assert "Cloud direct PostgreSQL Dashboard cutover report" in text
    assert "134.175.222.171" in text
    assert "xihong" in text
    assert "all key smoke endpoints returned 200" in text
    assert "/metabase/" in text
    assert "404" in text


def test_origin_release_readiness_doc_exists_and_recommends_tag_release():
    text = Path(
        "docs/development/POSTGRESQL_DASHBOARD_ORIGIN_RELEASE_READINESS_2026-03-23.md"
    ).read_text(encoding="utf-8", errors="replace")

    assert "Origin tag release readiness review" in text
    assert "recommended next step" in text.lower()
    assert "git push origin v" in text
    assert "PostgreSQL Dashboard" in text
    assert "go for origin tag release" in text.lower()
