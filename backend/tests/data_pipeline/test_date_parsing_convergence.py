"""批次 C: 日期解析 7 套收成 2 套 + 「不确定 ⇒ 落 unknown, 绝不猜」。

这份测试钉死的是**一条硬原则**
----------------------------
> 歧义宁可落 ``unknown`` 报警, 绝不静默猜一个。

以前「日-月-年 vs 月-日-年」在两处被静默拍板:

1. ``smart_date_parser._parse_explicit_year_position_date`` —— 对 ``d/m/Y``
   **无条件**先试 day-first。于是 ``11/01/2026`` 被解成 1 月 11 日,
   而它也完全可以是 11 月 1 日。
2. ``data_standardizer`` / ``ingestion_worker`` —— 硬编码 ``prefer_dayfirst=True``。

两处都会把 11 月 1 日写成 1 月 11 日, **而且没有任何痕迹**。

批次 C 之后:

* ``parse_date_by_declared_format`` —— **严格声明式**, 入库路径**唯一**允许的实现;
* ``parse_date`` / ``probe_date`` —— 宽松(探测/预览专用), 歧义 ⇒ 落 unknown + 报警;

其余 5 套实现全部**委派**给上面这两个, 不再自带格式表。

测试环境
--------
纯单元测试, 不连数据库(按 ``backend/tests/conftest.py``, pytest 期间
``DATABASE_URL`` 会被指向一次性隔离库, 本文件用不到它)。
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]

#: 事故里最典型的歧义值
AMBIGUOUS_VALUE = "11/01/2026"
#: 唯一的 day-first 值(日 > 12)
DAY_FIRST_ONLY = "25/09/2025"
#: 唯一的 month-first 值(月 > 12)
MONTH_FIRST_ONLY = "09/25/2025"


# ---------------------------------------------------------------------------
# 1. 歧义不猜
# ---------------------------------------------------------------------------


def test_probe_date_marks_ambiguous_value_as_unknown():
    from modules.services.smart_date_parser import (
        DATE_PROBE_AMBIGUOUS,
        probe_date,
    )

    probe = probe_date(AMBIGUOUS_VALUE)

    assert probe.status == DATE_PROBE_AMBIGUOUS
    assert probe.value is None
    assert probe.ambiguous is True
    assert probe.detail


def test_parse_date_returns_none_for_ambiguous_value():
    """静默猜一个是最贵的错 —— 落 unknown 才是对的。"""
    from modules.services.smart_date_parser import parse_date

    assert parse_date(AMBIGUOUS_VALUE) is None


def test_parse_date_honours_explicit_column_level_preference():
    """调用方已经做完**列级**判定时, 尊重它。"""
    from modules.services.smart_date_parser import parse_date

    assert parse_date(AMBIGUOUS_VALUE, prefer_dayfirst=True) == date(2026, 1, 11)
    assert parse_date(AMBIGUOUS_VALUE, prefer_dayfirst=False) == date(2026, 11, 1)


def test_parse_date_resolves_unambiguous_values_without_preference():
    from modules.services.smart_date_parser import parse_date

    assert parse_date(DAY_FIRST_ONLY) == date(2025, 9, 25)
    assert parse_date(MONTH_FIRST_ONLY) == date(2025, 9, 25)


def test_detect_dayfirst_stays_none_when_both_parts_ambiguous():
    """列级判定不出来时必须返回 None —— 不猜。"""
    from modules.services.smart_date_parser import detect_dayfirst

    assert detect_dayfirst(["11/01/2026", "12/01/2026"]) is None
    assert detect_dayfirst(["25/09/2025"]) is True
    assert detect_dayfirst(["09/25/2025"]) is False


def test_year_first_values_are_never_ambiguous():
    from modules.services.smart_date_parser import parse_date

    assert parse_date("2026-03-12") == date(2026, 3, 12)
    assert parse_date("2026/03/12") == date(2026, 3, 12)
    assert parse_date("2026-03-12 12:30:00") == date(2026, 3, 12)


def test_parse_iso_date_only_accepts_iso():
    from modules.services.smart_date_parser import parse_iso_date

    assert parse_iso_date("2026-03-12") == date(2026, 3, 12)
    assert parse_iso_date("2026-03-12T10:00:00") == date(2026, 3, 12)
    assert parse_iso_date("12/03/2026") is None


# ---------------------------------------------------------------------------
# 2. 入库路径只允许严格声明式
# ---------------------------------------------------------------------------


def test_ingest_path_does_not_fall_back_to_loose_date_parser():
    """``_resolve_period_dates_for_insert`` 不得再调用宽松解析。

    宽松解析器在「日/月都 ≤ 12」时只能猜一个 ——
    入库路径一旦走到它, 就等于替用户拍板。
    """
    import backend.services.raw_data_importer as importer_module

    source = Path(importer_module.__file__).read_text(encoding="utf-8")
    method_source = source.split("def _resolve_period_dates_for_insert", 1)[1].split(
        "def ", 1
    )[0]

    assert (
        "self.extract_period_dates(" not in method_source
    ), "入库路径不得回落到宽松解析(extract_period_dates)"
    assert (
        "prefer_dayfirst=True" not in source
    ), "raw_data_importer 不得硬编码 prefer_dayfirst=True"


def test_ingest_path_without_rules_and_without_period_fails_loudly():
    """既无声明式规则又无文件期间 ⇒ 明确失败, 不猜。"""
    import backend.services.raw_data_importer as importer_module

    importer = importer_module.RawDataImporter.__new__(importer_module.RawDataImporter)
    importer.field_parse_rules = []
    importer.file_date_from = None
    importer.file_date_to = None

    with pytest.raises(ValueError) as excinfo:
        importer._resolve_period_dates_for_insert(
            {"日期": "01/10/2026"}, ["日期"], "monthly"
        )

    assert "refusing to guess" in str(excinfo.value)


def test_ingest_path_with_declared_rules_is_unaffected():
    """有声明式规则时仍走严格声明式(批次 A 的口径)。"""
    import backend.services.raw_data_importer as importer_module

    importer = importer_module.RawDataImporter.__new__(importer_module.RawDataImporter)
    importer.field_parse_rules = [
        {
            "target_field": "metric_date",
            "source_column": "日期",
            "value_kind": "single_date",
            "date_format": "dd-mm-yyyy",
        }
    ]
    importer.file_date_from = date(2026, 10, 1)
    importer.file_date_to = date(2026, 10, 31)

    metric_date, period_start, period_end, _, _ = (
        importer._resolve_period_dates_for_insert(
            {"日期": "01-10-2026"}, ["日期"], "monthly"
        )
    )

    assert metric_date == date(2026, 10, 1)
    assert period_start == date(2026, 10, 1)
    assert period_end == date(2026, 10, 1)


# ---------------------------------------------------------------------------
# 3. 其余实现统一委派(单一口径)
# ---------------------------------------------------------------------------


def test_data_validator_delegates_to_single_implementation():
    import backend.services.data_validator as module

    source = Path(module.__file__).read_text(encoding="utf-8")

    assert "from modules.services.smart_date_parser import parse_date" in source
    # dateutil 兜底是「猜」, 必须去掉(只看真正的调用, 不看文档里的说明)
    body = source.split("def _parse_date", 1)[1].split("\ndef ", 1)[0]
    assert "from dateutil import" not in body
    assert not re.search(r"\bdate_parser\.parse\(", body)


def test_data_validator_v2_delegates_to_single_implementation():
    import backend.services.data_validator_v2 as module

    source = Path(module.__file__).read_text(encoding="utf-8")

    assert "from modules.services.smart_date_parser import parse_date" in source
    body = source.split("def _parse_date", 1)[1].split("\ndef ", 1)[0]
    assert '"%d/%m/%Y"' not in body and "'%d/%m/%Y'" not in body


def test_source_freshness_delegates_to_single_implementation():
    import backend.services.data_pipeline.source_freshness_service as module

    source = Path(module.__file__).read_text(encoding="utf-8")

    assert "parse_iso_date" in source


def test_type_detector_delegates_range_split_to_single_implementation():
    import backend.services.field_mapping.type_detector as module
    from modules.services.smart_date_parser import split_date_range_value

    source = Path(module.__file__).read_text(encoding="utf-8")

    assert "split_date_range_value" in source

    # 委派前后行为必须一致
    for raw in (
        "2025-08-25 17:01~2025-08-26 11:02",
        "2025-08-25~2025-08-26",
        "25/08/2025 - 26/08/2025",
        "2025-08-18-15:01~2025-08-25-15:01",
    ):
        assert module.detect_date_range_format(raw) == split_date_range_value(raw)


def test_standardizer_has_no_hardcoded_dayfirst():
    """C-3: 硬编码 dayfirst=True 全部清掉。"""
    import backend.services.data_standardizer as module

    source = Path(module.__file__).read_text(encoding="utf-8")

    assert "prefer_dayfirst=True" not in source


def test_ingestion_worker_has_no_hardcoded_dayfirst():
    import modules.services.ingestion_worker as module

    source = Path(module.__file__).read_text(encoding="utf-8")

    assert "prefer_dayfirst=True" not in source


def test_standardizer_date_value_delegates_and_keeps_time():
    from backend.services.data_standardizer import standardize_date_value

    # 年份在前 —— 唯一, 带时间也要保住
    parsed = standardize_date_value("2026-03-12 10:30:00", keep_time=True)
    assert parsed is not None
    assert parsed.hour == 10 and parsed.minute == 30

    # 歧义值 ⇒ 落 unknown
    assert standardize_date_value(AMBIGUOUS_VALUE) is None
    # 唯一 day-first ⇒ 能解
    assert standardize_date_value(DAY_FIRST_ONLY) == date(2025, 9, 25)


# ---------------------------------------------------------------------------
# 4. 口径唯一: 仓库里不再有第二份「猜」的日期解析
# ---------------------------------------------------------------------------


def test_no_other_module_declares_its_own_day_month_year_format_list():
    """禁止再出现「自带一份 dd/mm 与 mm/dd 顺序」的格式表。

    旧的三份罪证:
      - ``data_validator``: 自带格式表 + dateutil 兜底
      - ``data_validator_v2``: 自带格式表(``%d/%m/%Y`` 在前)
      - ``data_standardizer``: 自带格式表(``%d/%m/%Y ...`` 在前)
    """
    offenders = []
    for relative in (
        "backend/services/data_validator.py",
        "backend/services/data_validator_v2.py",
        "backend/services/data_standardizer.py",
        "backend/services/raw_data_importer.py",
    ):
        source = (REPO_ROOT / relative).read_text(encoding="utf-8")
        if re.search(r'["\']%d/%m/%Y', source):
            offenders.append(relative)

    assert not offenders, f"这些文件仍在自带 dd/mm 格式表: {offenders}"
