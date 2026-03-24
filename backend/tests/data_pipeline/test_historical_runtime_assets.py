from pathlib import Path


def test_historical_runtime_assets_are_explicitly_non_runtime():
    files = [
        "archive/metabase/backend/routers/dashboard_api.py",
        "archive/metabase/backend/routers/metabase_proxy.py",
        "archive/metabase/backend/services/metabase_question_service.py",
    ]

    for path_str in files:
        text = Path(path_str).read_text(encoding="utf-8", errors="replace").lower()
        assert "historical only" in text
        assert "not imported by runtime" in text


def test_hr_commission_no_longer_describes_metabase_computation():
    text = Path("backend/routers/hr_commission.py").read_text(encoding="utf-8", errors="replace")

    assert "由Metabase定时计算" not in text
