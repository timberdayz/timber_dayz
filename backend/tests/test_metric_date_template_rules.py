from datetime import date, datetime

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


def test_raw_data_importer_field_parse_rules_override_heuristic_metric_date_resolution():
    importer = _make_importer()

    metric_date, period_start_date, period_end_date, period_start_time, period_end_time = (
        importer._extract_period_dates_by_rules(
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

    metric_date, period_start_date, period_end_date, period_start_time, period_end_time = (
        importer._extract_period_dates_by_rules(
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
    )

    assert metric_date == date(2026, 3, 1)
    assert period_start_date == date(2026, 3, 1)
    assert period_end_date == date(2026, 3, 1)
    assert period_start_time is None
    assert period_end_time is None
