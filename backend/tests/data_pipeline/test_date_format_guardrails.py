"""批次 A: 日期格式白名单闸门 + 样本试解析 + 模板改「伴生周期自动判断」。

这份测试钉死的是**一次真实事故**及其防线
----------------------------------------
2026-11-07 实测(开发库):

* ``shopee_analytics__monthly_slash_v3``(模板 id=321)声明
  ``date_format: "dd/mm/yyyy"``;
* 平台实际导出的「日期」列是**横杠**:``01-10-2026`` / ``01-11-2026``;
* ⇒ ``parse_date_by_declared_format`` 用 ``strptime(raw, "%d/%m/%Y")`` 失败
  ⇒ ``raw_data_importer`` 抛 ``failed to parse metric_date from source_column=日期``
  ⇒ **整份文件入库失败**;
* ⇒ ``public.catalog_files`` 里 shopee/analytics 的 4 个文件 status='failed',
  采集时间跨 2026-11-02 ~ 11-07 —— **每次采集都失败一次**。

三道防线, 本文件逐条钉死:

1. **白名单闸门** —— 非法/与 value_kind 不自洽的 ``date_format`` 在**保存时**被拒;
2. **样本试解析** —— 格式合法但**与文件对不上**(dd/mm/yyyy vs 横杠)时, 保存时就被拒;
3. **迁移** —— 把该模板改成 ``auto_by_companion_period`` + 日-月-年候选集。

测试环境
--------
按 ``backend/tests/conftest.py`` 的护栏, pytest 期间 ``DATABASE_URL`` 被指向
一次性隔离库(testcontainers), **绝不允许连真实业务库**。
"""

from __future__ import annotations

import importlib.util
import re
from datetime import date
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_PATH = (
    REPO_ROOT
    / "current_migrations"
    / "versions"
    / "20261123_shopee_analytics_monthly_date_format.py"
)
FRONTEND_RULES_PATH = (
    REPO_ROOT
    / "frontend"
    / "src"
    / "domains"
    / "data_platform"
    / "utils"
    / "templateFieldParseRules.js"
)

#: 事故里的真实值(横杠)与真实报错里的值
REAL_DASH_VALUE = "01-10-2026"
REAL_SLASH_VALUE = "01/10/2026"
REAL_PERIOD_FROM = date(2026, 10, 1)
REAL_PERIOD_TO = date(2026, 10, 31)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "migration_20261123_shopee_analytics_date_format", MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def migration():
    return _load_migration()


# ---------------------------------------------------------------------------
# 1. 解析器白名单(唯一口径)
# ---------------------------------------------------------------------------


def test_supported_formats_cover_all_parser_tokens():
    """白名单必须**恰好**等于解析器认识的 token 集合, 不多不少。

    少一个 ⇒ 合法模板被误拒; 多一个 ⇒ 非法模板被放行(运行期才炸)。
    """
    from modules.services.smart_date_parser import (
        SUPPORTED_DECLARED_DATE_FORMATS,
        _DECLARED_RANGE_BASE_FORMATS,
        _DECLARED_SINGLE_FORMATS,
        _DECLARED_TIME_FORMATS,
        _AUTO_COMPANION_FORMAT,
    )

    expected = (
        set(_DECLARED_SINGLE_FORMATS)
        | set(_DECLARED_TIME_FORMATS)
        | set(_DECLARED_RANGE_BASE_FORMATS)
        | {_AUTO_COMPANION_FORMAT}
    )
    assert set(SUPPORTED_DECLARED_DATE_FORMATS) == expected
    # 18 单值 + 2 时间 + 4 区间 + 1 auto
    assert len(_DECLARED_SINGLE_FORMATS) == 18
    assert len(_DECLARED_TIME_FORMATS) == 2
    assert len(_DECLARED_RANGE_BASE_FORMATS) == 4
    assert len(SUPPORTED_DECLARED_DATE_FORMATS) == 25


def test_value_kind_compatibility_matrix():
    """value_kind 与 date_format 必须自洽。"""
    from modules.services.smart_date_parser import (
        declared_date_formats_for_value_kind,
        is_declared_date_format_compatible,
    )

    # date_range 只能配区间格式, 不能配单值格式
    assert is_declared_date_format_compatible("date_range", "yyyy-mm-dd-yyyy-mm-dd")
    assert not is_declared_date_format_compatible("date_range", "yyyy-mm-dd")
    # datetime_range 必须带时分秒
    assert is_declared_date_format_compatible("datetime_range", "yyyy-mm-dd hh:mm")
    assert not is_declared_date_format_compatible("datetime_range", "yyyy-mm-dd")
    # time_of_day 只能配时间格式
    assert is_declared_date_format_compatible("time_of_day", "hh:mm")
    assert not is_declared_date_format_compatible("time_of_day", "yyyy-mm-dd")
    # auto 只对有候选集的 kind 有效
    assert is_declared_date_format_compatible("single_date", "auto_by_companion_period")
    assert not is_declared_date_format_compatible("time_of_day", "auto_by_companion_period")
    # 未知 kind ⇒ 一律不兼容(不静默放行)
    assert declared_date_formats_for_value_kind("no_such_kind") == frozenset()
    assert not is_declared_date_format_compatible("no_such_kind", "yyyy-mm-dd")


# ---------------------------------------------------------------------------
# 2. 白名单闸门(保存时拦住非法声明)
# ---------------------------------------------------------------------------


def test_validate_declared_date_formats_rejects_garbage():
    from backend.services.template_parse_rules_service import (
        validate_declared_date_formats,
    )

    problems = validate_declared_date_formats(
        [
            {
                "target_field": "metric_date",
                "value_kind": "single_date",
                "date_format": "dd/mm/yyyy随便写的",
                "source_column": "日期",
            }
        ]
    )
    assert problems
    assert "unsupported date_format" in problems[0]


def test_validate_declared_date_formats_rejects_kind_mismatch():
    from backend.services.template_parse_rules_service import (
        validate_declared_date_formats,
    )

    problems = validate_declared_date_formats(
        [
            {
                "target_field": "period_start_date",
                "value_kind": "date_range",
                "date_format": "yyyy-mm-dd",
                "source_column": "期间",
            }
        ]
    )
    assert problems
    assert "incompatible with value_kind" in problems[0]


def test_validate_declared_date_formats_rejects_bad_candidates():
    from backend.services.template_parse_rules_service import (
        validate_declared_date_formats,
    )

    problems = validate_declared_date_formats(
        [
            {
                "target_field": "metric_date",
                "value_kind": "single_date",
                "date_format": "auto_by_companion_period",
                "format_candidates": ["dd-mm-yyyy", "不是格式"],
                "source_column": "日期",
            }
        ]
    )
    assert problems
    assert "unsupported format_candidates entry" in problems[0]


def test_validate_declared_date_formats_accepts_real_fix():
    """事故的修法必须通过白名单闸门 —— 否则改完也存不进去。"""
    from backend.services.template_parse_rules_service import (
        validate_declared_date_formats,
    )

    problems = validate_declared_date_formats(
        [
            {
                "target_field": "metric_date",
                "value_kind": "single_date",
                "date_format": "auto_by_companion_period",
                "format_candidates": ["dd-mm-yyyy", "dd/mm/yyyy"],
                "source_column": "日期",
            }
        ]
    )
    assert problems == []


# ---------------------------------------------------------------------------
# 3. 样本试解析(格式合法但与文件对不上 ⇒ 保存时拦住)
# ---------------------------------------------------------------------------


def test_sample_check_catches_the_real_incident():
    """``dd/mm/yyyy`` 撞横杠值 —— 事故原样复现, 必须被抓。"""
    from backend.services.template_save_readiness_service import (
        validate_field_parse_rules_against_samples,
    )

    problems = validate_field_parse_rules_against_samples(
        [
            {
                "target_field": "metric_date",
                "value_kind": "single_date",
                "date_format": "dd/mm/yyyy",
                "source_column": "日期",
            }
        ],
        [{"日期": REAL_DASH_VALUE}],
    )
    assert problems
    assert REAL_DASH_VALUE in problems[0]


def test_sample_check_passes_with_auto_and_day_first_candidates():
    """改成 auto + 日-月-年候选后, 同一份样本必须能过闸门。"""
    from backend.services.template_save_readiness_service import (
        validate_field_parse_rules_against_samples,
    )

    problems = validate_field_parse_rules_against_samples(
        [
            {
                "target_field": "metric_date",
                "value_kind": "single_date",
                "date_format": "auto_by_companion_period",
                "format_candidates": ["dd-mm-yyyy", "dd/mm/yyyy"],
                "source_column": "日期",
            }
        ],
        [{"日期": REAL_DASH_VALUE}, {"日期": REAL_SLASH_VALUE}],
    )
    assert problems == []


def test_sample_check_does_not_fire_without_evidence():
    """没有样本证据时**不得**误伤 —— 伴生列取的是文件日期, 不是某一列。"""
    from backend.services.template_save_readiness_service import (
        validate_field_parse_rules_against_samples,
    )

    problems = validate_field_parse_rules_against_samples(
        [
            {
                "target_field": "metric_date",
                "value_kind": "single_date",
                "date_format": "dd/mm/yyyy",
                "source_column": "__file_date_from__",
            }
        ],
        [{"其他列": "x"}],
    )
    assert problems == []


def test_sample_check_does_not_fire_without_sample_rows():
    from backend.services.template_save_readiness_service import (
        validate_field_parse_rules_against_samples,
    )

    problems = validate_field_parse_rules_against_samples(
        [
            {
                "target_field": "metric_date",
                "value_kind": "single_date",
                "date_format": "dd/mm/yyyy",
                "source_column": "日期",
            }
        ],
        [],
    )
    assert problems == []


# ---------------------------------------------------------------------------
# 4. auto 模式的真实解析行为
# ---------------------------------------------------------------------------


def test_auto_with_day_first_candidates_resolves_real_value():
    """日-月-年候选集 ⇒ 真实值解析成 2026-10-01。"""
    from modules.services.smart_date_parser import parse_date_by_declared_format

    parsed_date, _ = parse_date_by_declared_format(
        REAL_DASH_VALUE,
        date_format="auto_by_companion_period",
        value_kind="single_date",
        companion_date_from=REAL_PERIOD_FROM,
        companion_date_to=REAL_PERIOD_TO,
        format_candidates=["dd-mm-yyyy", "dd/mm/yyyy"],
    )
    assert parsed_date == REAL_PERIOD_FROM


def test_auto_with_mixed_families_is_ambiguous():
    """候选里混进「月-日-年」家族 ⇒ 同一个值有两种解释 ⇒ 必须报歧义而不是猜。

    这条是「为什么候选集要限定在单一语义家族」的根据:
    日-月-年 与 月-日-年 对 ``01-10-2026`` 都能解析, 只能靠文件期间消歧。
    """
    from modules.services.smart_date_parser import parse_date_by_declared_format

    with pytest.raises(ValueError, match="ambiguous"):
        parse_date_by_declared_format(
            REAL_DASH_VALUE,
            date_format="auto_by_companion_period",
            value_kind="single_date",
            companion_date_from=date(2026, 1, 1),
            companion_date_to=date(2026, 12, 31),
            format_candidates=["dd-mm-yyyy", "mm-dd-yyyy"],
        )


def test_auto_requires_companion_period():
    """auto 模式硬依赖伴生周期 —— 缺了就必须报错, 不能退化成瞎猜。"""
    from modules.services.smart_date_parser import parse_date_by_declared_format

    with pytest.raises(ValueError, match="companion date_from/date_to is required"):
        parse_date_by_declared_format(
            REAL_DASH_VALUE,
            date_format="auto_by_companion_period",
            value_kind="single_date",
            format_candidates=["dd-mm-yyyy"],
        )


# ---------------------------------------------------------------------------
# 5. 迁移: 链 / 改写规则 / 幂等 / 可逆
# ---------------------------------------------------------------------------


def test_migration_chain(migration):
    assert (
        migration.revision
        == "current_schema_20261123_shopee_analytics_monthly_date_format"
    )
    assert (
        migration.down_revision
        == "current_schema_20261122_remove_disabled_shop_collection_scopes"
    )


def test_migration_rewrite_is_idempotent_and_reversible(migration):
    original = [
        {
            "strict": True,
            "value_kind": "single_date",
            "date_format": "dd/mm/yyyy",
            "target_field": "metric_date",
            "source_column": "日期",
        }
    ]

    upgraded = migration._rewrite_rules(original, target=migration._NEW_DATE_FORMAT)
    assert upgraded is not None
    assert upgraded[0]["date_format"] == "auto_by_companion_period"
    assert upgraded[0]["format_candidates"] == ["dd-mm-yyyy", "dd/mm/yyyy"]
    # 其它字段必须原样保留
    assert upgraded[0]["source_column"] == "日期"
    assert upgraded[0]["strict"] is True

    # 幂等: 再改一次没有变化
    assert migration._rewrite_rules(upgraded, target=migration._NEW_DATE_FORMAT) is None

    # 可逆: 回滚恢复原声明并清掉候选
    downgraded = migration._rewrite_rules(upgraded, target=migration._ORIGINAL_DATE_FORMAT)
    assert downgraded is not None
    assert downgraded[0]["date_format"] == "dd/mm/yyyy"
    assert "format_candidates" not in downgraded[0]


def test_migration_does_not_touch_us_format(migration):
    """美式(``mm-dd-yyyy``)不在改写范围内 —— 混进来会让同一个值有两种解释。"""
    original = [
        {
            "value_kind": "single_date",
            "date_format": "mm-dd-yyyy",
            "target_field": "metric_date",
            "source_column": "Date",
        }
    ]
    assert migration._rewrite_rules(original, target=migration._NEW_DATE_FORMAT) is None


def test_migration_does_not_touch_other_value_kinds(migration):
    original = [
        {
            "value_kind": "date_range",
            "date_format": "dd/mm/yyyy-dd/mm/yyyy",
            "target_field": "period_start_date",
            "source_column": "期间",
        }
    ]
    assert migration._rewrite_rules(original, target=migration._NEW_DATE_FORMAT) is None


# ---------------------------------------------------------------------------
# 6. 迁移在隔离库里的实际效果(模板 + 变体两处都要改)
# ---------------------------------------------------------------------------


async def _seed_template_rows(pg_session) -> None:
    """在隔离库造一份 shopee/analytics/monthly 的模板 + 族 + 版本 + 变体。"""
    from modules.core.db import (
        FieldMappingTemplate,
        FieldMappingTemplateFamily,
        FieldMappingTemplateVariant,
        FieldMappingTemplateVersion,
    )

    broken_rules = [
        {
            "strict": True,
            "value_kind": "single_date",
            "date_format": "dd/mm/yyyy",
            "target_field": "metric_date",
            "source_column": "日期",
        }
    ]

    family = FieldMappingTemplateFamily(
        id=9401,
        platform="shopee",
        data_domain="analytics",
        granularity="monthly",
        sub_domain=None,
        account=None,
        governance_status="ready",
        source_mode="legacy_projection",
        display_name="shopee/analytics/monthly",
    )
    version = FieldMappingTemplateVersion(
        id=9402,
        family_id=9401,
        version_no=1,
        status="active",
        template_name="shopee_analytics__monthly_v1",
        deduplication_fields=["metric_date"],
        header_bindings=[],
    )
    variant = FieldMappingTemplateVariant(
        id=9403,
        template_version_id=9402,
        variant_key="monthly_dash",
        match_priority=1,
        header_row=0,
        field_parse_rules=list(broken_rules),
    )
    template = FieldMappingTemplate(
        id=9404,
        platform="shopee",
        data_domain="analytics",
        granularity="monthly",
        sub_domain=None,
        account=None,
        header_row=0,
        header_columns=["日期", "访客数"],
        deduplication_fields=["metric_date"],
        header_bindings=[],
        field_parse_rules=list(broken_rules),
        template_name="shopee_analytics__monthly_v1",
        version=1,
        status="published",
        field_count=2,
    )
    pg_session.add_all([family, version, variant, template])
    await pg_session.flush()
    family.active_version_id = 9402
    await pg_session.flush()


async def test_migration_updates_both_template_and_variant(pg_session, migration):
    """模板(投影来源)与变体(入库实际消费的那份)必须一起改。

    只改一处 ⇒ 当前态仍失败 或 下次重投影被打回。
    """
    await _seed_template_rows(pg_session)

    await pg_session.run_sync(migration.apply_upgrade)
    await pg_session.flush()

    from sqlalchemy import text

    rows = (
        await pg_session.execute(
            text(
                """
                SELECT id, field_parse_rules
                FROM core.field_mapping_templates
                WHERE id = 9404
                """
            )
        )
    ).fetchall()
    assert len(rows) == 1
    template_rules = rows[0].field_parse_rules
    if isinstance(template_rules, str):
        import json

        template_rules = json.loads(template_rules)
    assert template_rules[0]["date_format"] == "auto_by_companion_period"
    assert template_rules[0]["format_candidates"] == ["dd-mm-yyyy", "dd/mm/yyyy"]

    variant_rows = (
        await pg_session.execute(
            text(
                """
                SELECT id, field_parse_rules
                FROM core.field_mapping_template_variants
                WHERE id = 9403
                """
            )
        )
    ).fetchall()
    assert len(variant_rows) == 1
    variant_rules = variant_rows[0].field_parse_rules
    if isinstance(variant_rules, str):
        import json

        variant_rules = json.loads(variant_rules)
    assert variant_rules[0]["date_format"] == "auto_by_companion_period"
    assert variant_rules[0]["format_candidates"] == ["dd-mm-yyyy", "dd/mm/yyyy"]


async def test_migration_is_idempotent(pg_session, migration):
    """重复执行不报错, 也不二次改写。"""
    await _seed_template_rows(pg_session)
    await pg_session.run_sync(migration.apply_upgrade)
    await pg_session.flush()
    await pg_session.run_sync(migration.apply_upgrade)
    await pg_session.flush()

    from sqlalchemy import text

    row = (
        await pg_session.execute(
            text(
                """
                SELECT field_parse_rules
                FROM core.field_mapping_template_variants
                WHERE id = 9403
                """
            )
        )
    ).fetchone()
    rules = row[0]
    if isinstance(rules, str):
        import json

        rules = json.loads(rules)
    assert rules[0]["date_format"] == "auto_by_companion_period"
    assert rules[0]["format_candidates"] == ["dd-mm-yyyy", "dd/mm/yyyy"]


# ---------------------------------------------------------------------------
# 7. 前端与后端白名单必须一致
# ---------------------------------------------------------------------------


def _frontend_date_format_tokens() -> set[str]:
    source = FRONTEND_RULES_PATH.read_text(encoding="utf-8")
    block = re.search(
        r"export const DATE_FORMAT_OPTIONS = \[(.*?)\n\]", source, re.S
    )
    assert block, "DATE_FORMAT_OPTIONS not found in frontend util"
    return set(re.findall(r"value: '([^']+)'", block.group(1)))


def test_frontend_options_cover_backend_whitelist():
    """前端下拉框必须能选到后端支持的**每一个**格式。

    之前前端少了 2 个 yyyy 区间格式 ⇒ 用户选不到。
    """
    from modules.services.smart_date_parser import SUPPORTED_DECLARED_DATE_FORMATS

    frontend_tokens = _frontend_date_format_tokens()
    missing = set(SUPPORTED_DECLARED_DATE_FORMATS) - frontend_tokens
    assert not missing, f"frontend date format options missing: {sorted(missing)}"


def test_frontend_has_no_unknown_format_token():
    """前端不得出现后端不认识的 token(否则保存必被拒)。"""
    from modules.services.smart_date_parser import SUPPORTED_DECLARED_DATE_FORMATS

    frontend_tokens = _frontend_date_format_tokens()
    unknown = frontend_tokens - set(SUPPORTED_DECLARED_DATE_FORMATS)
    assert not unknown, f"frontend exposes unsupported formats: {sorted(unknown)}"


def test_frontend_candidates_keep_us_family():
    """候选集**不得**按「日-月-年」家族收窄 —— 美式报表(m/d/y)会解析不了。

    日 vs 月的歧义由**文件伴生周期**消解, 候选集必须覆盖全部家族。
    """
    source = FRONTEND_RULES_PATH.read_text(encoding="utf-8")
    block = re.search(
        r"export const COMPANION_AUTO_DATE_FORMAT_CANDIDATES = \[(.*?)\n\]",
        source,
        re.S,
    )
    assert block
    tokens = set(re.findall(r"'([^']+)'", block.group(1)))
    assert "mm-dd-yyyy" in tokens
    assert "mm/dd/yyyy" in tokens
    assert "dd-mm-yyyy" in tokens
    assert "dd/mm/yyyy" in tokens


def test_frontend_update_rules_reuses_single_source():
    """``templateUpdateFieldParseRules.js`` 不得再自带一份候选表副本。"""
    update_path = (
        REPO_ROOT
        / "frontend"
        / "src"
        / "domains"
        / "data_platform"
        / "utils"
        / "templateUpdateFieldParseRules.js"
    )
    source = update_path.read_text(encoding="utf-8")
    assert "const COMPANION_AUTO_DATE_FORMAT_CANDIDATES" not in source
    assert "companionFormatCandidatesForValueKind" in source
