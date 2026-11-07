"""批次 B: 值形态漂移检测 + ``format_drift`` 状态 + 结构化错误码。

这份测试钉死的是**批次 A 事故的第二道防线**
------------------------------------------------
批次 A 修好了「Shopee 流量月度模板声明的日期格式与文件对不上」这个**具体**事故,
但它只覆盖了**一个**模板。如果下次平台又改了格式(或者别的域也改了),
我们仍然要等到**入库时整份文件失败**才能知道。

批次 B 把这件事变成**可预判**的:

1. **值形态体检** —— 用样本行试解析模板声明的日期格式, 解不出来就报 ``format_drift``;
2. **状态词汇** —— ``format_drift`` 进 ``data_sync_status_semantics`` 的 SSOT,
   并落进「阻断」集合(继续入库只会整份失败);
3. **结构化错误码** —— 入库失败时消息带 ``[错误码]``,
   前端据此区分「格式不匹配 / 日期超出文件期间 / 日期歧义」。

另外钉死一条**批次 A 引入的回归**:
``auto_by_companion_period`` 的规则**必须**拿到文件期间才能判定样本是否吻合,
否则变体选择器会把它整个丢掉 ⇒ 没有契约的文件又匹配不上模板。
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from modules.core.db import CatalogFile, FieldMappingTemplate


REPO_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_ERROR_PARSER_PATH = (
    REPO_ROOT
    / "frontend"
    / "src"
    / "domains"
    / "data_platform"
    / "utils"
    / "syncTaskErrorParser.js"
)

#: 事故里的真实值(横杠)
REAL_DASH_VALUE = "01-10-2026"
REAL_SLASH_VALUE = "01/10/2026"
REAL_PERIOD_FROM = date(2026, 10, 1)
REAL_PERIOD_TO = date(2026, 10, 31)


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


@pytest_asyncio.fixture
async def status_session_factory():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("ATTACH DATABASE ':memory:' AS core"))
        await conn.run_sync(CatalogFile.__table__.create)
        await conn.run_sync(FieldMappingTemplate.__table__.create)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield session_factory
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# 1. 值形态分析: 四类错误码互斥且正确
# ---------------------------------------------------------------------------


def test_value_shape_reports_format_mismatch_for_dash_value_under_slash_format():
    from backend.services.template_parse_rules_service import (
        DATE_ERROR_FORMAT_MISMATCH,
        analyze_date_value_shape,
    )

    code, detail = analyze_date_value_shape(
        REAL_DASH_VALUE,
        date_format="dd/mm/yyyy",
        value_kind="single_date",
    )

    assert code == DATE_ERROR_FORMAT_MISMATCH
    assert detail


def test_value_shape_accepts_matching_format():
    from backend.services.template_parse_rules_service import analyze_date_value_shape

    code, _detail = analyze_date_value_shape(
        REAL_DASH_VALUE,
        date_format="dd-mm-yyyy",
        value_kind="single_date",
    )

    assert code is None


def test_value_shape_reports_ambiguity_for_overlapping_candidates():
    from backend.services.template_parse_rules_service import (
        DATE_ERROR_AMBIGUOUS,
        analyze_date_value_shape,
    )

    # dd-mm-yyyy 与 mm-dd-yyyy 对 "01-10-2026" 给出**不同**的日期 ⇒ 不确定, 不能猜。
    code, detail = analyze_date_value_shape(
        REAL_DASH_VALUE,
        date_format="auto_by_companion_period",
        value_kind="single_date",
        format_candidates=["dd-mm-yyyy", "mm-dd-yyyy"],
    )

    assert code == DATE_ERROR_AMBIGUOUS
    assert detail


def test_value_shape_reports_out_of_period_separately_from_mismatch():
    from backend.services.template_parse_rules_service import (
        DATE_ERROR_OUT_OF_PERIOD,
        analyze_date_value_shape,
    )

    code, _detail = analyze_date_value_shape(
        "05-12-2026",
        date_format="dd-mm-yyyy",
        value_kind="single_date",
        companion_date_from=REAL_PERIOD_FROM,
        companion_date_to=REAL_PERIOD_TO,
    )

    assert code == DATE_ERROR_OUT_OF_PERIOD


def test_value_shape_ignores_empty_values():
    from backend.services.template_parse_rules_service import analyze_date_value_shape

    assert analyze_date_value_shape(
        "", date_format="dd-mm-yyyy", value_kind="single_date"
    ) == (None, "")
    assert analyze_date_value_shape(
        None, date_format="dd-mm-yyyy", value_kind="single_date"
    ) == (None, "")


# ---------------------------------------------------------------------------
# 2. 值形态报告: 漂移判定与「不误伤」
# ---------------------------------------------------------------------------


def test_value_shape_report_flags_format_drift():
    from backend.services.template_parse_rules_service import evaluate_date_value_shape

    rules = [
        {
            "target_field": "metric_date",
            "source_column": "日期",
            "value_kind": "single_date",
            "date_format": "dd/mm/yyyy",
        }
    ]
    rows = [{"日期": REAL_DASH_VALUE}]

    report = evaluate_date_value_shape(rules, rows)

    assert report.format_drift is True
    assert report.issues[0].error_code == "date_format_mismatch"
    assert report.issues[0].source_column == "日期"


def test_value_shape_report_does_not_flag_out_of_period_as_format_drift():
    """越界是**文件期间元数据**的问题, 不是模板声明的格式变了。"""
    from backend.services.template_parse_rules_service import evaluate_date_value_shape

    rules = [
        {
            "target_field": "metric_date",
            "source_column": "日期",
            "value_kind": "single_date",
            "date_format": "dd-mm-yyyy",
        }
    ]
    rows = [{"日期": "05-12-2026"}]

    report = evaluate_date_value_shape(
        rules,
        rows,
        companion_date_from=REAL_PERIOD_FROM,
        companion_date_to=REAL_PERIOD_TO,
    )

    assert report.issues[0].error_code == "date_out_of_period"
    assert report.format_drift is False


def test_value_shape_report_without_samples_does_not_judge():
    from backend.services.template_parse_rules_service import evaluate_date_value_shape

    rules = [
        {
            "target_field": "metric_date",
            "source_column": "日期",
            "value_kind": "single_date",
            "date_format": "dd/mm/yyyy",
        }
    ]

    report = evaluate_date_value_shape(rules, [])

    assert report.issues == []
    assert report.format_drift is False


def test_value_shape_report_skips_file_date_companion_columns():
    """伴生日期列取的是**文件**日期, 不是文件里的某一列 ⇒ 没有样本值可试。"""
    from backend.services.template_parse_rules_service import evaluate_date_value_shape

    rules = [
        {
            "target_field": "metric_date",
            "source_column": "__file_date_from__",
            "value_kind": "single_date",
            "date_format": "yyyy-mm-dd",
        }
    ]
    rows = [{"日期": REAL_DASH_VALUE}]

    report = evaluate_date_value_shape(rules, rows)

    assert report.issues == []
    assert report.format_drift is False


# ---------------------------------------------------------------------------
# 3. 状态词汇 SSOT
# ---------------------------------------------------------------------------


def test_format_drift_is_registered_in_status_semantics():
    from backend.services.data_sync_status_semantics import (
        BLOCKING_GOVERNANCE_STATUSES,
        GOVERNANCE_STATUS_FORMAT_DRIFT,
        GOVERNANCE_STATUSES,
        TEMPLATE_STATUS_FORMAT_DRIFT,
        TEMPLATE_STATUSES,
        TEMPLATE_STATUS_TO_GOVERNANCE,
        governance_status_for,
        is_blocking_governance_status,
    )

    assert TEMPLATE_STATUS_FORMAT_DRIFT in TEMPLATE_STATUSES
    assert GOVERNANCE_STATUS_FORMAT_DRIFT in GOVERNANCE_STATUSES
    assert (
        TEMPLATE_STATUS_TO_GOVERNANCE[TEMPLATE_STATUS_FORMAT_DRIFT]
        == GOVERNANCE_STATUS_FORMAT_DRIFT
    )
    assert governance_status_for(TEMPLATE_STATUS_FORMAT_DRIFT) == GOVERNANCE_STATUS_FORMAT_DRIFT
    # 值形态漂移 ⇒ 继续入库只会整份失败 ⇒ 阻断
    assert is_blocking_governance_status(GOVERNANCE_STATUS_FORMAT_DRIFT) is True
    assert GOVERNANCE_STATUS_FORMAT_DRIFT in BLOCKING_GOVERNANCE_STATUSES


def test_blocking_header_change_treats_format_drift_as_blocking():
    """表头一个字段都没变(is_exact_match=True), 但值形态变了 ⇒ 仍然阻断。"""
    from backend.services.data_sync_service import DataSyncService

    assert (
        DataSyncService._is_blocking_header_change(
            {"detected": False, "is_exact_match": True, "format_drift": True}
        )
        is True
    )
    assert (
        DataSyncService._is_blocking_header_change(
            {"detected": True, "is_exact_match": True, "format_drift": False}
        )
        is False
    )


# ---------------------------------------------------------------------------
# 4. 漂移检测接入值形态维度(真实走 detect_header_changes)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detect_header_changes_flags_format_drift_on_unchanged_header(status_session_factory):
    from backend.services.template_matcher import TemplateMatcher

    now = datetime.now(timezone.utc)
    async with status_session_factory() as session:
        template = FieldMappingTemplate(
            platform="shopee",
            data_domain="analytics",
            granularity="monthly",
            sub_domain=None,
            template_name="shopee_analytics__monthly_slash_v3",
            version=3,
            status="published",
            header_row=3,
            header_columns=["日期", "页面浏览数"],
            field_parse_rules=[
                {
                    "target_field": "metric_date",
                    "source_column": "日期",
                    "value_kind": "single_date",
                    "date_format": "dd/mm/yyyy",
                }
            ],
            created_at=now,
            updated_at=now,
        )
        session.add(template)
        await session.commit()
        await session.refresh(template)

        matcher = TemplateMatcher(session)
        result = await matcher.detect_header_changes(
            template.id,
            ["日期", "页面浏览数"],
            sample_rows=[{"日期": REAL_DASH_VALUE}],
        )

        assert result["format_drift"] is True
        assert result["value_shape"]["format_drift"] is True
        assert "日期" in result["blocking_changes"]
        # 表头本身没变
        assert result["is_exact_match"] is True


@pytest.mark.asyncio
async def test_detect_header_changes_reports_no_drift_when_format_matches(status_session_factory):
    from backend.services.template_matcher import TemplateMatcher

    now = datetime.now(timezone.utc)
    async with status_session_factory() as session:
        template = FieldMappingTemplate(
            platform="shopee",
            data_domain="analytics",
            granularity="monthly",
            sub_domain=None,
            template_name="shopee_analytics__monthly_slash_v3",
            version=3,
            status="published",
            header_row=3,
            header_columns=["日期", "页面浏览数"],
            field_parse_rules=[
                {
                    "target_field": "metric_date",
                    "source_column": "日期",
                    "value_kind": "single_date",
                    "date_format": "dd-mm-yyyy",
                }
            ],
            created_at=now,
            updated_at=now,
        )
        session.add(template)
        await session.commit()
        await session.refresh(template)

        matcher = TemplateMatcher(session)
        result = await matcher.detect_header_changes(
            template.id,
            ["日期", "页面浏览数"],
            sample_rows=[{"日期": REAL_DASH_VALUE}],
        )

        assert result["format_drift"] is False
        assert result["value_shape"]["issues"] == []


# ---------------------------------------------------------------------------
# 5. 批次 A 回归: auto 模式必须拿到文件期间
# ---------------------------------------------------------------------------


def test_auto_variant_matching_requires_companion_period():
    """``auto_by_companion_period`` 没有期间 ⇒ 变体选择器会把它整个丢掉。"""
    from backend.services.template_family_service import _variant_matches_sample_rows

    rules = [
        {
            "target_field": "metric_date",
            "source_column": "日期",
            "value_kind": "single_date",
            "date_format": "auto_by_companion_period",
            "format_candidates": ["dd-mm-yyyy", "dd/mm/yyyy"],
        }
    ]
    rows = [{"日期": REAL_DASH_VALUE}]

    assert _variant_matches_sample_rows(rules, rows) is False
    assert (
        _variant_matches_sample_rows(
            rules,
            rows,
            companion_date_from=REAL_PERIOD_FROM,
            companion_date_to=REAL_PERIOD_TO,
        )
        is True
    )


def test_pick_by_sample_rows_passes_period_to_auto_rules():
    from backend.services.template_matcher import _pick_by_sample_rows

    now = datetime.now(timezone.utc)

    def _template(template_id: int, name: str, date_format: str) -> FieldMappingTemplate:
        return FieldMappingTemplate(
            id=template_id,
            platform="shopee",
            data_domain="analytics",
            granularity="monthly",
            sub_domain=None,
            template_name=name,
            version=template_id,
            status="published",
            header_row=3,
            header_columns=["日期"],
            field_parse_rules=[
                {
                    "target_field": "metric_date",
                    "source_column": "日期",
                    "value_kind": "single_date",
                    "date_format": date_format,
                    "format_candidates": ["dd-mm-yyyy", "dd/mm/yyyy"],
                }
            ],
            created_at=now,
            updated_at=now,
        )

    auto_template = _template(1, "auto", "auto_by_companion_period")
    fixed_template = _template(2, "fixed", "dd-mm-yyyy")
    rows = [{"日期": REAL_DASH_VALUE}]

    picked = _pick_by_sample_rows(
        [auto_template, fixed_template],
        rows,
        file_date_from=REAL_PERIOD_FROM,
        file_date_to=REAL_PERIOD_TO,
    )

    assert picked.id == auto_template.id


# ---------------------------------------------------------------------------
# 6. 结构化错误码: 入库期与前端消费
# ---------------------------------------------------------------------------


def test_importer_error_classification_matches_value_shape():
    from backend.services.raw_data_importer import _classify_date_parse_error
    from backend.services.template_parse_rules_service import analyze_date_value_shape

    rule = {
        "date_format": "dd/mm/yyyy",
        "value_kind": "single_date",
        "source_column": "日期",
    }

    code = _classify_date_parse_error(REAL_DASH_VALUE, rule=rule)
    expected, _detail = analyze_date_value_shape(
        REAL_DASH_VALUE,
        date_format="dd/mm/yyyy",
        value_kind="single_date",
    )

    assert code == expected == "date_format_mismatch"


def test_importer_error_classification_detects_out_of_period():
    from backend.services.raw_data_importer import _classify_date_parse_error

    rule = {
        "date_format": "dd-mm-yyyy",
        "value_kind": "single_date",
        "source_column": "日期",
    }

    code = _classify_date_parse_error(
        "05-12-2026",
        rule=rule,
        file_date_from=REAL_PERIOD_FROM,
        file_date_to=REAL_PERIOD_TO,
    )

    assert code == "date_out_of_period"


def test_frontend_error_parser_knows_all_backend_error_codes():
    """前后端错误码必须一致 —— 前端按错误码分流, 少一个就退化成「解析失败」。"""
    from backend.services.template_parse_rules_service import DATE_ERROR_CODES

    source = FRONTEND_ERROR_PARSER_PATH.read_text(encoding="utf-8")

    for code in DATE_ERROR_CODES:
        assert f"{code}:" in source, f"前端缺少错误码 {code}"


def test_frontend_error_parser_extracts_structured_code():
    """前端解析器能从消息里取出错误码(用 node 跑真实实现)。"""
    import json
    import subprocess

    script = (
        "import { parseDateErrorCode, extractDateParseErrorEntries } from "
        f"'{FRONTEND_ERROR_PARSER_PATH.as_uri()}';\n"
        "const msg = '文件2732: 同步失败:raw_storage,[date_out_of_period] "
        "metric_date 2026-12-05 is later than file_date_to 2026-10-31';\n"
        "console.log(JSON.stringify({"
        "  code: parseDateErrorCode(msg),"
        "  entries: extractDateParseErrorEntries({ errors: [{ message: msg }] })"
        "}));\n"
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(REPO_ROOT / "frontend"),
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout.strip().splitlines()[-1])

    assert payload["code"] == "date_out_of_period"
    assert payload["entries"][0]["error_code"] == "date_out_of_period"
    assert payload["entries"][0]["file_id"] == 2732
    assert payload["entries"][0]["error_label"]
    assert payload["entries"][0]["error_hint"]


def test_importer_parse_error_message_carries_error_code():
    """入库抛出的消息必须带 ``[错误码]`` 前缀, 否则前端无法分流。"""
    import backend.services.raw_data_importer as importer_module

    module_path = Path(importer_module.__file__)
    text_source = module_path.read_text(encoding="utf-8")

    assert re.search(
        r"\[{error_code}\]\s*failed to parse", text_source
    ), "入库解析失败消息必须带 [错误码] 前缀"
