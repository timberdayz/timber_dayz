"""模板日期解析规则的**格式合法性**校验。

为什么单独一个模块
------------------
``backend/domains/data_platform/routers/field_mapping_templates.py`` 里有
1500+ 行, 日期规则的校验散在 router 内部, 没法单独测。
而这份校验是**事故的直接防线** —— 必须能被独立断言, 所以抽到这里。

它解决的是哪类事故
------------------
模板里写的 ``date_format`` 是**运行期**才会被解析器消费的字符串。
以前保存闸门只查「非空」, 于是:

* ``date_format: "dd/mm/yyyy"``(模板声明)
  撞上平台实际导出的 ``01-10-2026``(横杠)
  ⇒ ``parse_date_by_declared_format`` 抛
  ``failed to parse metric_date from source_column=日期: 01-10-2026``
  ⇒ **整份文件入不了库**, 而且事前没有任何提示
  (漂移检测只看列名, 不看值形态)。

⇒ 这份校验的职责: 让**非法或与文件不匹配的格式在保存时就被拦住**。

唯一口径
--------
合法 token 集合来自 ``modules/services/smart_date_parser.py`` ——
那是解析器**唯一**的实现, 白名单必须与它同源, 不能各写一份。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Iterable, List, Optional, Sequence

from modules.services.smart_date_parser import (
    SUPPORTED_DECLARED_DATE_FORMATS,
    _AUTO_COMPANION_FORMAT,
    _DEFAULT_AUTO_RANGE_FORMAT_CANDIDATES,
    _DEFAULT_AUTO_SINGLE_FORMAT_CANDIDATES,
    declared_date_formats_for_value_kind,
    is_declared_date_format_compatible,
    is_supported_declared_date_format,
    parse_date_by_declared_format,
)


def validate_declared_date_formats(
    field_parse_rules: Iterable[dict[str, Any]],
) -> List[str]:
    """校验每条日期规则的 ``date_format`` 与 ``format_candidates``。

    Returns:
        问题描述列表; 全部合法则返回空列表。

    校验三件事:
    1. ``date_format`` 必须是解析器认识的 token(否则运行期抛
       "unsupported declared date format");
    2. ``date_format`` 必须与 ``value_kind`` 自洽(例如 ``date_range``
       不能配 ``yyyy-mm-dd`` 这种单值格式);
    3. ``format_candidates`` 里每一项也必须合法且与 ``value_kind`` 自洽 ——
       候选里混进非法值, 会在入库时被**静默跳过**, 让人误以为
       「候选都试过了, 是文件的问题」。
    """
    problems: List[str] = []
    for rule in field_parse_rules or []:
        if not isinstance(rule, dict):
            continue
        target_field = str(rule.get("target_field") or "").strip()
        if not target_field:
            continue
        date_format = str(rule.get("date_format") or "").strip()
        if not date_format:
            # 「非空」由 router 的既有校验负责, 这里不重复报。
            continue
        value_kind = str(rule.get("value_kind") or "single_date").strip() or "single_date"

        if not is_supported_declared_date_format(date_format):
            problems.append(
                f"field_parse_rules for {target_field} declares unsupported date_format: "
                f"{date_format!r}; supported formats: "
                + ", ".join(sorted(SUPPORTED_DECLARED_DATE_FORMATS))
            )
            continue

        if not is_declared_date_format_compatible(value_kind, date_format):
            problems.append(
                f"field_parse_rules for {target_field} declares date_format "
                f"{date_format!r} which is incompatible with value_kind {value_kind!r}; "
                "compatible formats: "
                + ", ".join(sorted(declared_date_formats_for_value_kind(value_kind)))
            )

        format_candidates = rule.get("format_candidates")
        if not format_candidates:
            continue
        if not isinstance(format_candidates, list):
            problems.append(
                f"field_parse_rules for {target_field} format_candidates must be a list"
            )
            continue
        for candidate in format_candidates:
            candidate_text = str(candidate or "").strip()
            if not candidate_text:
                continue
            if not is_supported_declared_date_format(candidate_text):
                problems.append(
                    f"field_parse_rules for {target_field} declares unsupported "
                    f"format_candidates entry: {candidate_text!r}"
                )
            elif not is_declared_date_format_compatible(value_kind, candidate_text):
                problems.append(
                    f"field_parse_rules for {target_field} declares format_candidates "
                    f"entry {candidate_text!r} incompatible with value_kind {value_kind!r}"
                )
    return problems


# ── 结构化错误码 (SSOT) ─────────────────────────────────────────────
#
# 以前入库失败只有一句自然语言:
#   "failed to parse metric_date from source_column=日期: 01-10-2026"
# 前端只能靠字符串匹配去猜原因, 于是三种完全不同的处置
# (换模板 / 查文件期间 / 消歧义) 全都显示成同一句"解析失败"。
#
# 现在把原因拆成**互斥**的四类, 后端产出、前端消费:
DATE_ERROR_FORMAT_MISMATCH = "date_format_mismatch"
"""声明的格式解不出这个值 —— 文件的值形态变了(最常见: 横杠 vs 斜杠)。"""

DATE_ERROR_OUT_OF_PERIOD = "date_out_of_period"
"""能解析出来, 但落在文件期间之外 —— 文件期间与内容对不上。"""

DATE_ERROR_AMBIGUOUS = "date_ambiguous"
"""多个候选都能解析出**不同**的日期 —— 不确定, 不能猜。"""

DATE_ERROR_UNSUPPORTED_FORMAT = "date_unsupported_format"
"""声明的格式本身非法 —— 模板配置错了(保存闸门本该拦住)。"""

DATE_ERROR_CODES = (
    DATE_ERROR_FORMAT_MISMATCH,
    DATE_ERROR_OUT_OF_PERIOD,
    DATE_ERROR_AMBIGUOUS,
    DATE_ERROR_UNSUPPORTED_FORMAT,
)

#: 这些错误码意味着「值本身解不出来」⇒ 属于值形态漂移(格式变了)。
DATE_ERROR_FORMAT_DRIFT_CODES = frozenset(
    {
        DATE_ERROR_FORMAT_MISMATCH,
        DATE_ERROR_AMBIGUOUS,
        DATE_ERROR_UNSUPPORTED_FORMAT,
    }
)


@dataclass(frozen=True)
class DateValueShapeIssue:
    """一条值形态问题。"""

    target_field: str
    source_column: str
    error_code: str
    sample_value: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_field": self.target_field,
            "source_column": self.source_column,
            "error_code": self.error_code,
            "sample_value": self.sample_value,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class DateValueShapeReport:
    """一份规则的「值形态体检报告」。"""

    checked_rules: int = 0
    checked_values: int = 0
    issues: List[DateValueShapeIssue] = field(default_factory=list)

    @property
    def format_drift(self) -> bool:
        """是否出现「值解不出来」的形态漂移。

        只认 :data:`DATE_ERROR_FORMAT_DRIFT_CODES` ——
        「日期超出文件期间」不计入: 越界是**文件期间元数据**的问题,
        不是模板声明的格式变了, 混进来会把模板治理与文件治理搅在一起。
        """
        return any(issue.error_code in DATE_ERROR_FORMAT_DRIFT_CODES for issue in self.issues)

    @property
    def error_codes(self) -> List[str]:
        return sorted({issue.error_code for issue in self.issues})

    def to_dict(self) -> dict[str, Any]:
        return {
            "checked_rules": self.checked_rules,
            "checked_values": self.checked_values,
            "format_drift": self.format_drift,
            "error_codes": self.error_codes,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def _coerce_optional_date(value: object) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):  # noqa: F821 - 见下方运行时导入
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _within_period(
    parsed: Optional[date],
    start: Optional[date],
    end: Optional[date],
) -> bool:
    if parsed is None:
        return False
    if start and parsed < start:
        return False
    if end and parsed > end:
        return False
    return True


def _auto_candidates(value_kind: str) -> List[str]:
    """auto 模式的默认候选集 —— 必须与解析器内部口径一致。"""
    if value_kind in {"single_date", "single_datetime", "datetime_range"}:
        return list(_DEFAULT_AUTO_SINGLE_FORMAT_CANDIDATES)
    if value_kind == "date_range":
        return list(_DEFAULT_AUTO_RANGE_FORMAT_CANDIDATES)
    return []


def analyze_date_value_shape(
    value: object,
    *,
    date_format: str,
    value_kind: str = "single_date",
    format_candidates: Optional[Sequence[str]] = None,
    range_pick: Optional[str] = None,
    date_anchor: object = None,
    companion_date_from: object = None,
    companion_date_to: object = None,
) -> tuple[Optional[str], str]:
    """判断**一个值**能不能被声明的规则解析, 并给出结构化原因。

    Returns:
        ``(error_code, detail)``; 解析成功时 ``error_code`` 为 ``None``。
        值本身为空时同样返回 ``(None, "")`` —— 空值不是「形态漂移」。

    为什么不用「直接调一次解析器」就够了
    ----------------------------------
    因为解析器抛出来的异常**分不清**两种完全不同的原因:

    * 文件从 ``01/10/2026`` 变成了 ``01-10-2026``(格式不匹配);
    * 文件的日期本身没错, 但落在文件期间之外(期间不匹配)。

    ``auto_by_companion_period`` 在这两种情况下抛的是**同一句**
    ``no companion-constrained date format matched``。
    ⇒ 这里改成**逐候选**试解析, 把「谁能解出来」与「解出来后在不在期间内」拆开判断。
    """
    fmt = str(date_format or "").strip()
    kind = str(value_kind or "single_date").strip() or "single_date"
    if value is None:
        return None, ""
    if isinstance(value, str) and not value.strip():
        return None, ""
    if isinstance(value, (date,)) and not isinstance(value, datetime):  # noqa: F821
        parsed = value
        start = _coerce_optional_date(companion_date_from)
        end = _coerce_optional_date(companion_date_to)
        if not _within_period(parsed, start, end):
            return (
                DATE_ERROR_OUT_OF_PERIOD,
                f"parsed {parsed.isoformat()} is outside file period "
                f"{start.isoformat() if start else '-'}..{end.isoformat() if end else '-'}",
            )
        return None, ""

    start = _coerce_optional_date(companion_date_from)
    end = _coerce_optional_date(companion_date_to)

    if fmt.lower() == _AUTO_COMPANION_FORMAT:
        candidates = [
            str(candidate).strip()
            for candidate in (format_candidates or [])
            if str(candidate or "").strip()
        ] or _auto_candidates(kind)
        if not candidates:
            return (
                DATE_ERROR_UNSUPPORTED_FORMAT,
                f"auto_by_companion_period does not support value_kind {kind!r}",
            )
        matched: List[tuple[str, Optional[date]]] = []
        unsupported: List[str] = []
        for candidate in candidates:
            try:
                parsed_date, _ = parse_date_by_declared_format(
                    value,
                    date_format=candidate,
                    value_kind=kind,
                    range_pick=range_pick,
                    date_anchor=date_anchor,
                )
            except ValueError as exc:
                if "unsupported declared" in str(exc):
                    unsupported.append(candidate)
                continue
            matched.append((candidate, parsed_date))
        if not matched:
            if unsupported and len(unsupported) == len(candidates):
                return (
                    DATE_ERROR_UNSUPPORTED_FORMAT,
                    f"none of the declared candidates is a supported format: {unsupported}",
                )
            return (
                DATE_ERROR_FORMAT_MISMATCH,
                f"value {value!r} cannot be parsed by any candidate in {candidates}",
            )
        if start or end:
            inside = [item for item in matched if _within_period(item[1], start, end)]
            if not inside:
                return (
                    DATE_ERROR_OUT_OF_PERIOD,
                    f"value {value!r} parses to "
                    f"{[item[1].isoformat() if item[1] else None for item in matched]}, "
                    f"none inside file period "
                    f"{start.isoformat() if start else '-'}..{end.isoformat() if end else '-'}",
                )
            matched = inside
        distinct = {item[1] for item in matched}
        if len(distinct) > 1:
            return (
                DATE_ERROR_AMBIGUOUS,
                f"value {value!r} is parsed into different dates by "
                f"{[item[0] for item in matched]}: "
                f"{sorted(item[1].isoformat() for item in matched if item[1])}",
            )
        return None, ""

    try:
        parsed_date, _ = parse_date_by_declared_format(
            value,
            date_format=fmt,
            value_kind=kind,
            range_pick=range_pick,
            date_anchor=date_anchor,
        )
    except ValueError as exc:
        message = str(exc)
        if "unsupported declared" in message:
            return DATE_ERROR_UNSUPPORTED_FORMAT, message
        return DATE_ERROR_FORMAT_MISMATCH, message

    if not _within_period(parsed_date, start, end):
        return (
            DATE_ERROR_OUT_OF_PERIOD,
            f"parsed {parsed_date.isoformat() if parsed_date else None} is outside file period "
            f"{start.isoformat() if start else '-'}..{end.isoformat() if end else '-'}",
        )
    return None, ""


def evaluate_date_value_shape(
    field_parse_rules: Optional[Iterable[dict[str, Any]]],
    sample_rows: Optional[Iterable[dict[str, Any]]],
    *,
    companion_date_from: object = None,
    companion_date_to: object = None,
    max_values_per_rule: int = 20,
) -> DateValueShapeReport:
    """对一组规则做**值形态体检**。

    这是保存闸门(静态合法性)之外的**动态**体检: 规则本身合法,
    但文件里的值可能已经变成另一种形态。

    没有样本证据时**不做判断**(返回空报告) —— 不误伤。
    """
    rows = list(sample_rows or [])
    rules = [rule for rule in (field_parse_rules or []) if isinstance(rule, dict)]
    if not rules or not rows:
        return DateValueShapeReport()

    issues: List[DateValueShapeIssue] = []
    checked_rules = 0
    checked_values = 0

    for rule in rules:
        target_field = str(rule.get("target_field") or "").strip()
        if not target_field:
            continue
        date_format = str(rule.get("date_format") or "").strip()
        if not date_format:
            continue
        value_kind = str(rule.get("value_kind") or "single_date").strip() or "single_date"
        source_column = str(rule.get("source_column") or "").strip()
        if not source_column or source_column in {"__file_date_from__", "__file_date_to__"}:
            # 伴生日期列取的是文件日期, 不是文件里的某一列 ⇒ 没有样本值可试。
            continue

        values = _collect_sample_values(rule, rows)
        if not values:
            continue

        checked_rules += 1
        seen_codes = set()
        for value in values[:max_values_per_rule]:
            checked_values += 1
            error_code, detail = analyze_date_value_shape(
                value,
                date_format=date_format,
                value_kind=value_kind,
                format_candidates=rule.get("format_candidates"),
                range_pick=rule.get("range_pick"),
                date_anchor=rule.get("date_anchor"),
                companion_date_from=companion_date_from,
                companion_date_to=companion_date_to,
            )
            if not error_code:
                continue
            if error_code in seen_codes:
                continue
            seen_codes.add(error_code)
            issues.append(
                DateValueShapeIssue(
                    target_field=target_field,
                    source_column=source_column,
                    error_code=error_code,
                    sample_value=str(value),
                    detail=detail,
                )
            )

    return DateValueShapeReport(
        checked_rules=checked_rules,
        checked_values=checked_values,
        issues=issues,
    )


def _collect_sample_values(
    field_parse_rule: dict[str, Any],
    sample_rows: Iterable[dict[str, Any]],
) -> List[Any]:
    """取出该规则对应列在样本行里的所有非空值。"""
    source_column = str(field_parse_rule.get("source_column") or "").strip()
    if not source_column or source_column in {"__file_date_from__", "__file_date_to__"}:
        return []
    wanted = source_column.lower()
    values: List[Any] = []
    for row in sample_rows or []:
        if not isinstance(row, dict):
            continue
        lookup = {str(key).strip().lower(): value for key, value in row.items()}
        if wanted not in lookup:
            continue
        value = lookup[wanted]
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        values.append(value)
    return values
