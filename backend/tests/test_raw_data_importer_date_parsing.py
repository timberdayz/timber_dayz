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

