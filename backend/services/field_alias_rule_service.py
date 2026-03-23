"""
Field alias rule helpers for semantic-layer standardization.

This first iteration is intentionally small:
- scope filtering
- grouping by standard field
- stable priority ordering

Database read integration can build on these pure helpers in later tasks.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, Iterable


def filter_rules_by_scope(
    rules: Iterable[dict[str, Any]],
    platform_code: str,
    data_domain: str,
    sub_domain: str | None = None,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for rule in rules:
        if not rule.get("active", True):
            continue
        if rule.get("platform_code") != platform_code:
            continue
        if rule.get("data_domain") != data_domain:
            continue
        if rule.get("sub_domain") != sub_domain:
            continue
        filtered.append(rule)
    return filtered


def group_rules_by_standard_field(
    rules: Iterable[dict[str, Any]],
) -> "OrderedDict[str, list[dict[str, Any]]]":
    grouped: "OrderedDict[str, list[dict[str, Any]]]" = OrderedDict()
    for rule in rules:
        if not rule.get("active", True):
            continue
        standard_field = rule["standard_field_name"]
        grouped.setdefault(standard_field, []).append(rule)

    for standard_field, field_rules in grouped.items():
        grouped[standard_field] = sorted(
            field_rules,
            key=lambda item: int(item.get("priority", 0)),
            reverse=True,
        )
    return grouped


class FieldAliasRuleService:
    def __init__(self, rules: Iterable[dict[str, Any]] | None = None):
        self._rules = list(rules or [])

    def set_rules(self, rules: Iterable[dict[str, Any]]) -> None:
        self._rules = list(rules)

    def get_rules_for_domain(
        self,
        platform_code: str,
        data_domain: str,
        sub_domain: str | None = None,
    ) -> list[dict[str, Any]]:
        return filter_rules_by_scope(
            rules=self._rules,
            platform_code=platform_code,
            data_domain=data_domain,
            sub_domain=sub_domain,
        )

    def group_rules_for_domain(
        self,
        platform_code: str,
        data_domain: str,
        sub_domain: str | None = None,
    ) -> "OrderedDict[str, list[dict[str, Any]]]":
        return group_rules_by_standard_field(
            self.get_rules_for_domain(
                platform_code=platform_code,
                data_domain=data_domain,
                sub_domain=sub_domain,
            )
        )

    def get_aliases(
        self,
        platform_code: str,
        data_domain: str,
        standard_field: str,
        sub_domain: str | None = None,
    ) -> list[str]:
        grouped = self.group_rules_for_domain(
            platform_code=platform_code,
            data_domain=data_domain,
            sub_domain=sub_domain,
        )
        return [
            rule["source_field_name"]
            for rule in grouped.get(standard_field, [])
        ]
