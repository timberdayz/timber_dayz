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

from typing import Any, Iterable, List

from modules.services.smart_date_parser import (
    SUPPORTED_DECLARED_DATE_FORMATS,
    declared_date_formats_for_value_kind,
    is_declared_date_format_compatible,
    is_supported_declared_date_format,
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
