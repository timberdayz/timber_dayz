from datetime import date

import pytest

from backend.models.database import SessionLocal
from backend.services.raw_data_importer import RawDataImporter


def test_raw_data_importer_parse_date_only_does_not_swap_iso_month_day(monkeypatch):
    """
    Regression: some legacy ingests misread year-first ISO strings like 2026-01-05 as
    2026-05-01 due to dayfirst fallbacks. Ensure we always parse year-first ISO correctly.
    """

    importer = RawDataImporter(SessionLocal())

    def _boom(*_args, **_kwargs):
        raise RuntimeError("force fallback path")

    monkeypatch.setattr("modules.services.smart_date_parser.parse_date", _boom, raising=True)

    assert importer._parse_date_only("2026-01-05") == date(2026, 1, 5)


def test_raw_data_importer_rejects_metric_date_outside_file_range():
    importer = RawDataImporter.__new__(RawDataImporter)
    importer.file_date_from = date(2026, 5, 16)
    importer.file_date_to = date(2026, 5, 16)

    with pytest.raises(ValueError, match="metric_date"):
        importer._validate_metric_date_against_file_range(date(2026, 4, 16))


def test_raw_data_importer_accepts_metric_date_within_file_range():
    importer = RawDataImporter.__new__(RawDataImporter)
    importer.file_date_from = date(2026, 5, 1)
    importer.file_date_to = date(2026, 5, 31)

    importer._validate_metric_date_against_file_range(date(2026, 5, 16))


def test_raw_data_importer_parse_date_range_value_returns_tuple_for_iso_single_date():
    importer = RawDataImporter.__new__(RawDataImporter)

    assert importer._parse_date_range_value("2026-03-17") == (
        date(2026, 3, 17),
        date(2026, 3, 17),
        None,
        None,
    )
