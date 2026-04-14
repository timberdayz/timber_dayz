from pathlib import Path

import pandas as pd

from backend.services.excel_parser import ExcelParser


def test_excel_parser_prefers_calamine_for_xlsx(monkeypatch, tmp_path):
    file_path = tmp_path / "sample.xlsx"
    file_path.write_bytes(b"PK\x03\x04demo")

    calls = []

    def _fake_read_excel(path, engine=None, header=0, nrows=None, **kwargs):
        calls.append(engine)
        return pd.DataFrame(columns=["a", "b"])

    monkeypatch.setattr("pandas.read_excel", _fake_read_excel)

    df = ExcelParser.read_excel(file_path, header=1, nrows=1)

    assert list(df.columns) == ["a", "b"]
    assert calls == ["calamine"]


def test_excel_parser_falls_back_to_openpyxl_after_calamine_failure_for_xlsx(monkeypatch, tmp_path):
    file_path = tmp_path / "sample.xlsx"
    file_path.write_bytes(b"PK\x03\x04demo")

    calls = []

    def _fake_read_excel(path, engine=None, header=0, nrows=None, **kwargs):
        calls.append(engine)
        if engine == "calamine":
            raise ImportError("Missing optional dependency 'python-calamine'")
        return pd.DataFrame(columns=["a", "b"])

    monkeypatch.setattr("pandas.read_excel", _fake_read_excel)

    df = ExcelParser.read_excel(file_path, header=1, nrows=1)

    assert list(df.columns) == ["a", "b"]
    assert calls == ["calamine", "openpyxl"]


def test_excel_parser_tries_calamine_before_legacy_xls_paths(monkeypatch, tmp_path):
    file_path = tmp_path / "sample.xls"
    file_path.write_bytes(b"\xD0\xCF\x11\xE0demo")

    calls = []

    def _fake_read_excel(path, engine=None, header=0, nrows=None, **kwargs):
        calls.append(engine)
        return pd.DataFrame(columns=["a", "b"])

    monkeypatch.setattr("pandas.read_excel", _fake_read_excel)

    df = ExcelParser.read_excel(file_path, header=1, nrows=1)

    assert list(df.columns) == ["a", "b"]
    assert calls == ["calamine"]
