from datetime import date, datetime
from pathlib import Path

import pytest

from backend.services.raw_data_importer import RawDataImporter
from modules.services.smart_date_parser import parse_date


def _make_importer() -> RawDataImporter:
    return RawDataImporter.__new__(RawDataImporter)


def test_parse_date_keeps_year_first_format_even_when_dayfirst_is_true():
    assert parse_date("2026-03-12", prefer_dayfirst=True) == date(2026, 3, 12)
    assert parse_date("2026/03/12", prefer_dayfirst=True) == date(2026, 3, 12)
    assert parse_date("2026-03-12 12:30:00", prefer_dayfirst=True) == date(2026, 3, 12)


def test_parse_date_by_declared_format_supports_single_date_and_datetime():
    from modules.services.smart_date_parser import parse_date_by_declared_format

    parsed_date, parsed_datetime = parse_date_by_declared_format(
        "2026-03-12 12:30:00",
        date_format="yyyy-mm-dd hh:mm:ss",
        value_kind="single_date",
    )

    assert parsed_date == date(2026, 3, 12)
    assert parsed_datetime == datetime(2026, 3, 12, 12, 30, 0)


def test_parse_date_by_declared_format_supports_time_of_day_with_anchor():
    from modules.services.smart_date_parser import parse_date_by_declared_format

    parsed_date, parsed_datetime = parse_date_by_declared_format(
        "13:00",
        date_format="hh:mm",
        value_kind="time_of_day",
        date_anchor=date(2026, 6, 8),
    )

    assert parsed_date == date(2026, 6, 8)
    assert parsed_datetime == datetime(2026, 6, 8, 13, 0, 0)


def test_parse_date_by_declared_format_supports_datetime_and_time_ranges():
    from modules.services.smart_date_parser import parse_date_by_declared_format

    start_date, start_datetime = parse_date_by_declared_format(
        "2026-06-08 13:00 - 2026-06-08 14:00",
        date_format="yyyy-mm-dd hh:mm",
        value_kind="datetime_range",
        range_pick="start",
    )
    end_date, end_datetime = parse_date_by_declared_format(
        "13:00-14:00",
        date_format="hh:mm",
        value_kind="time_range",
        range_pick="end",
        date_anchor=date(2026, 6, 8),
    )

    assert start_date == date(2026, 6, 8)
    assert start_datetime == datetime(2026, 6, 8, 13, 0, 0)
    assert end_date == date(2026, 6, 8)
    assert end_datetime == datetime(2026, 6, 8, 14, 0, 0)


def test_parse_date_by_declared_format_supports_day_first_range_pick():
    from modules.services.smart_date_parser import parse_date_by_declared_format

    start_date, _ = parse_date_by_declared_format(
        "14-04-2026-18-04-2026",
        date_format="dd-mm-yyyy-dd-mm-yyyy",
        value_kind="date_range",
        range_pick="start",
    )
    end_date, _ = parse_date_by_declared_format(
        "14-04-2026-18-04-2026",
        date_format="dd-mm-yyyy-dd-mm-yyyy",
        value_kind="date_range",
        range_pick="end",
    )

    assert start_date == date(2026, 4, 14)
    assert end_date == date(2026, 4, 18)


def test_parse_date_by_declared_format_supports_month_first_regional_formats():
    from modules.services.smart_date_parser import parse_date_by_declared_format

    slash_date, _ = parse_date_by_declared_format(
        "05/06/2026",
        date_format="mm/dd/yyyy",
        value_kind="single_date",
    )
    dash_date, dash_datetime = parse_date_by_declared_format(
        "05-06-2026 13:45",
        date_format="mm-dd-yyyy hh:mm",
        value_kind="single_datetime",
    )

    assert slash_date == date(2026, 5, 6)
    assert dash_date == date(2026, 5, 6)
    assert dash_datetime == datetime(2026, 5, 6, 13, 45)


def test_auto_by_companion_period_selects_day_first_format():
    from modules.services.smart_date_parser import parse_date_by_declared_format

    parsed_date, parsed_datetime = parse_date_by_declared_format(
        "01/03/2026",
        date_format="auto_by_companion_period",
        value_kind="single_date",
        companion_date_from=date(2026, 3, 1),
        companion_date_to=date(2026, 3, 31),
        format_candidates=["dd/mm/yyyy", "mm/dd/yyyy"],
    )

    assert parsed_date == date(2026, 3, 1)
    assert parsed_datetime is None


def test_auto_by_companion_period_selects_month_first_format():
    from modules.services.smart_date_parser import parse_date_by_declared_format

    parsed_date, _ = parse_date_by_declared_format(
        "03/01/2026",
        date_format="auto_by_companion_period",
        value_kind="single_date",
        companion_date_from=date(2026, 3, 1),
        companion_date_to=date(2026, 3, 31),
        format_candidates=["dd/mm/yyyy", "mm/dd/yyyy"],
    )

    assert parsed_date == date(2026, 3, 1)


def test_auto_by_companion_period_rejects_ambiguous_candidates():
    from modules.services.smart_date_parser import parse_date_by_declared_format

    with pytest.raises(ValueError, match="ambiguous companion-constrained date format"):
        parse_date_by_declared_format(
            "03/03/2026",
            date_format="auto_by_companion_period",
            value_kind="single_date",
            companion_date_from=date(2026, 3, 1),
            companion_date_to=date(2026, 3, 31),
            format_candidates=["dd/mm/yyyy", "mm/dd/yyyy"],
        )


def test_raw_data_importer_resolves_auto_metric_date_with_companion_period():
    importer = _make_importer()
    importer.file_date_from = date(2026, 3, 1)
    importer.file_date_to = date(2026, 3, 31)
    importer.field_parse_rules = [
        {
            "target_field": "metric_date",
            "source_column": "Date",
            "value_kind": "single_date",
            "date_format": "auto_by_companion_period",
            "format_candidates": ["dd/mm/yyyy", "mm/dd/yyyy"],
            "strict": True,
        }
    ]

    (
        metric_date,
        period_start_date,
        period_end_date,
        period_start_time,
        period_end_time,
    ) = importer._resolve_period_dates_for_insert(
        row={"Date": "01/03/2026", "page_views": 985},
        header_columns=["Date", "page_views"],
        granularity="monthly",
    )

    assert metric_date == date(2026, 3, 1)
    assert period_start_date == date(2026, 3, 1)
    assert period_end_date == date(2026, 3, 1)
    assert period_start_time is None
    assert period_end_time is None


def test_raw_data_importer_rejects_source_metric_date_outside_companion_period():
    importer = _make_importer()
    importer.file_date_from = date(2026, 3, 1)
    importer.file_date_to = date(2026, 3, 31)
    importer.field_parse_rules = [
        {
            "target_field": "metric_date",
            "source_column": "Date",
            "value_kind": "single_date",
            "date_format": "mm/dd/yyyy",
            "strict": True,
        }
    ]

    with pytest.raises(ValueError, match="earlier than file_date_from"):
        importer._resolve_period_dates_for_insert(
            row={"Date": "01/03/2026", "page_views": 985},
            header_columns=["Date", "page_views"],
            granularity="monthly",
        )


def test_raw_data_importer_field_parse_rules_override_heuristic_metric_date_resolution():
    importer = _make_importer()

    (
        metric_date,
        period_start_date,
        period_end_date,
        period_start_time,
        period_end_time,
    ) = importer._extract_period_dates_by_rules(
        row={"order_time": "2026-03-12 12:30:00"},
        field_parse_rules=[
            {
                "target_field": "metric_date",
                "source_column": "order_time",
                "value_kind": "single_date",
                "date_format": "yyyy-mm-dd hh:mm:ss",
                "strict": True,
            }
        ],
    )

    assert metric_date == date(2026, 3, 12)
    assert period_start_date == date(2026, 3, 12)
    assert period_end_date == date(2026, 3, 12)
    assert period_start_time == datetime(2026, 3, 12, 12, 30, 0)
    assert period_end_time == datetime(2026, 3, 12, 12, 30, 0)


def test_raw_data_importer_field_parse_rules_raise_on_invalid_strict_value():
    importer = _make_importer()

    with pytest.raises(ValueError, match="metric_date"):
        importer._extract_period_dates_by_rules(
            row={"order_time": "bad-date"},
            field_parse_rules=[
                {
                    "target_field": "metric_date",
                    "source_column": "order_time",
                    "value_kind": "single_date",
                    "date_format": "yyyy-mm-dd",
                    "strict": True,
                }
            ],
        )


def test_raw_data_importer_field_parse_rules_support_file_date_from_token():
    importer = _make_importer()
    importer.file_date_from = date(2026, 3, 1)

    (
        metric_date,
        period_start_date,
        period_end_date,
        period_start_time,
        period_end_time,
    ) = importer._extract_period_dates_by_rules(
        row={},
        field_parse_rules=[
            {
                "target_field": "metric_date",
                "source_column": "__file_date_from__",
                "value_kind": "single_date",
                "date_format": "yyyy-mm-dd",
                "strict": True,
            }
        ],
    )

    assert metric_date == date(2026, 3, 1)
    assert period_start_date == date(2026, 3, 1)
    assert period_end_date == date(2026, 3, 1)
    assert period_start_time is None
    assert period_end_time is None


def test_raw_data_importer_field_parse_rules_support_hour_target_with_file_date_anchor():
    importer = _make_importer()
    importer.file_date_from = date(2026, 6, 8)

    (
        metric_date,
        period_start_date,
        period_end_date,
        period_start_time,
        period_end_time,
    ) = importer._extract_period_dates_by_rules(
        row={"hour": "13:00"},
        field_parse_rules=[
            {
                "target_field": "metric_date",
                "source_column": "__file_date_from__",
                "value_kind": "single_date",
                "date_format": "yyyy-mm-dd",
                "strict": True,
            },
            {
                "target_field": "period_start_time",
                "source_column": "hour",
                "value_kind": "time_of_day",
                "date_format": "hh:mm",
                "date_anchor": "__file_date_from__",
                "strict": True,
            },
        ],
    )

    assert metric_date == date(2026, 6, 8)
    assert period_start_date == date(2026, 6, 8)
    assert period_end_date == date(2026, 6, 8)
    assert period_start_time == datetime(2026, 6, 8, 13, 0, 0)
    assert period_end_time == datetime(2026, 6, 8, 13, 0, 0)


def test_raw_data_importer_field_parse_rules_support_source_alias_fallback():
    importer = _make_importer()

    (
        metric_date,
        period_start_date,
        period_end_date,
        period_start_time,
        period_end_time,
    ) = importer._extract_period_dates_by_rules(
        row={"统计日期": "2026-03-12 12:30:00"},
        field_parse_rules=[
            {
                "target_field": "metric_date",
                "source_column": "Unnamed: 0",
                "source_label": "日期",
                "source_aliases": ["日期", "统计日期"],
                "value_kind": "single_date",
                "date_format": "yyyy-mm-dd hh:mm:ss",
                "strict": True,
            }
        ],
    )

    assert metric_date == date(2026, 3, 12)
    assert period_start_date == date(2026, 3, 12)
    assert period_end_date == date(2026, 3, 12)
    assert period_start_time == datetime(2026, 3, 12, 12, 30, 0)
    assert period_end_time == datetime(2026, 3, 12, 12, 30, 0)


def test_validate_metric_date_contract_rejects_date_outside_file_range():
    from backend.services.data_ingestion_service import validate_metric_date_contract

    assert (
        validate_metric_date_contract(
            metric_date=date(2026, 4, 16),
            file_date_from=date(2026, 5, 16),
            file_date_to=date(2026, 5, 16),
        )
        is False
    )


def test_validate_metric_date_contract_accepts_date_within_file_range():
    from backend.services.data_ingestion_service import validate_metric_date_contract

    assert (
        validate_metric_date_contract(
            metric_date=date(2026, 5, 16),
            file_date_from=date(2026, 5, 1),
            file_date_to=date(2026, 5, 31),
        )
        is True
    )


def test_v721_template_migration_repairs_shopee_products_monthly_rules():
    migration_text = Path(
        "migrations/versions/20260609_v7_2_1_shopee_products_monthly_dates.py"
    ).read_text(encoding="utf-8")

    assert "TEMPLATE_ID = 296" in migration_text
    assert '"target_field": "metric_date"' in migration_text
    assert '"source_column": "__file_date_from__"' in migration_text
    assert '"target_field": "period_end_date"' in migration_text
    assert '"source_column": "__file_date_to__"' in migration_text
    assert '"metric_date"' in migration_text


def test_raw_data_importer_resolves_monthly_file_date_range_without_today_fallback():
    importer = _make_importer()
    importer.file_date_from = date(2026, 4, 1)
    importer.file_date_to = date(2026, 4, 30)
    importer.field_parse_rules = [
        {
            "target_field": "metric_date",
            "source_column": "__file_date_from__",
            "value_kind": "single_date",
            "date_format": "yyyy-mm-dd",
            "strict": True,
        },
        {
            "target_field": "period_start_date",
            "source_column": "__file_date_from__",
            "value_kind": "single_date",
            "date_format": "yyyy-mm-dd",
            "strict": True,
        },
        {
            "target_field": "period_end_date",
            "source_column": "__file_date_to__",
            "value_kind": "single_date",
            "date_format": "yyyy-mm-dd",
            "strict": True,
        },
    ]

    (
        metric_date,
        period_start_date,
        period_end_date,
        period_start_time,
        period_end_time,
    ) = importer._resolve_period_dates_for_insert(
        row={"商品编号": "sku-1"},
        header_columns=["商品编号", "商品"],
        granularity="monthly",
    )

    assert metric_date == date(2026, 4, 1)
    assert period_start_date == date(2026, 4, 1)
    assert period_end_date == date(2026, 4, 30)
    assert period_start_time is None
    assert period_end_time is None


def test_raw_data_importer_keeps_source_metric_date_when_companion_period_exists():
    importer = _make_importer()
    importer.file_date_from = date(2026, 5, 1)
    importer.file_date_to = date(2026, 5, 31)
    importer.field_parse_rules = [
        {
            "target_field": "metric_date",
            "source_column": "日期",
            "value_kind": "single_date",
            "date_format": "dd/mm/yyyy",
            "strict": True,
        },
        {
            "target_field": "period_start_date",
            "source_column": "__file_date_from__",
            "value_kind": "single_date",
            "date_format": "yyyy-mm-dd",
            "strict": True,
        },
        {
            "target_field": "period_end_date",
            "source_column": "__file_date_to__",
            "value_kind": "single_date",
            "date_format": "yyyy-mm-dd",
            "strict": True,
        },
    ]

    (
        metric_date,
        period_start_date,
        period_end_date,
        period_start_time,
        period_end_time,
    ) = importer._resolve_period_dates_for_insert(
        row={"日期": "23/05/2026", "浏览量": "985"},
        header_columns=["日期", "浏览量"],
        granularity="monthly",
    )

    assert metric_date == date(2026, 5, 23)
    assert period_start_date == date(2026, 5, 1)
    assert period_end_date == date(2026, 5, 31)
    assert period_start_time is None
    assert period_end_time is None


def test_raw_data_importer_resolves_hour_range_with_companion_date_anchor():
    importer = _make_importer()
    importer.file_date_from = date(2026, 5, 1)
    importer.file_date_to = date(2026, 5, 1)
    importer.field_parse_rules = [
        {
            "target_field": "metric_date",
            "source_column": "__file_date_from__",
            "value_kind": "single_date",
            "date_format": "yyyy-mm-dd",
            "strict": True,
        },
        {
            "target_field": "period_start_time",
            "source_column": "小时",
            "value_kind": "time_range",
            "date_format": "hh:mm",
            "range_pick": "start",
            "date_anchor": "__file_date_from__",
            "strict": True,
        },
        {
            "target_field": "period_end_time",
            "source_column": "小时",
            "value_kind": "time_range",
            "date_format": "hh:mm",
            "range_pick": "end",
            "date_anchor": "__file_date_from__",
            "strict": True,
        },
    ]

    (
        metric_date,
        period_start_date,
        period_end_date,
        period_start_time,
        period_end_time,
    ) = importer._resolve_period_dates_for_insert(
        row={"小时": "13:00-14:00", "浏览量": "985"},
        header_columns=["小时", "浏览量"],
        granularity="daily",
    )

    assert metric_date == date(2026, 5, 1)
    assert period_start_date == date(2026, 5, 1)
    assert period_end_date == date(2026, 5, 1)
    assert period_start_time == datetime(2026, 5, 1, 13, 0)
    assert period_end_time == datetime(2026, 5, 1, 14, 0)


def test_raw_data_importer_rejects_missing_reliable_business_date():
    importer = _make_importer()
    importer.field_parse_rules = []

    with pytest.raises(ValueError, match="business date"):
        importer._resolve_period_dates_for_insert(
            row={"商品编号": "sku-1"},
            header_columns=["商品编号", "商品"],
            granularity="monthly",
        )


@pytest.mark.asyncio
async def test_async_batch_insert_copies_date_context_to_sync_importer(monkeypatch):
    class _FakeDb:
        def commit(self):
            return None

        def rollback(self):
            return None

        def close(self):
            return None

    class _FakeExecutorManager:
        async def run_io_intensive(self, func, *args, **kwargs):
            return func(*args, **kwargs)

    captured = {}

    def _fake_batch_insert(self, **_kwargs):
        captured["file_date_from"] = getattr(self, "file_date_from", None)
        captured["file_date_to"] = getattr(self, "file_date_to", None)
        captured["field_parse_rules"] = getattr(self, "field_parse_rules", None)
        captured["header_bindings"] = getattr(self, "header_bindings", None)
        return {"inserted": 1, "updated": 0, "skipped": 0}

    monkeypatch.setattr(
        "backend.models.database.SessionLocal",
        lambda: _FakeDb(),
    )
    monkeypatch.setattr(
        "backend.services.raw_data_importer.get_executor_manager",
        lambda: _FakeExecutorManager(),
    )
    monkeypatch.setattr(
        RawDataImporter,
        "batch_insert_raw_data",
        _fake_batch_insert,
    )

    importer = _make_importer()
    parse_rules = [
        {
            "target_field": "metric_date",
            "source_column": "__file_date_from__",
            "value_kind": "single_date",
            "date_format": "yyyy-mm-dd",
        }
    ]
    header_bindings = [{"source_header": "商品编号", "semantic_key": "product_id"}]

    result = await importer.async_batch_insert_raw_data(
        rows=[{"商品编号": "sku-1"}],
        data_hashes=["hash-1"],
        data_domain="products",
        granularity="monthly",
        platform_code="shopee",
        file_date_from=date(2026, 4, 1),
        file_date_to=date(2026, 4, 30),
        field_parse_rules=parse_rules,
        header_bindings=header_bindings,
    )

    assert result["inserted"] == 1
    assert captured["file_date_from"] == date(2026, 4, 1)
    assert captured["file_date_to"] == date(2026, 4, 30)
    assert captured["field_parse_rules"] == parse_rules
    assert captured["header_bindings"] == header_bindings
