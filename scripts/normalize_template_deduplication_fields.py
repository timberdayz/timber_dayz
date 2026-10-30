#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把历史模板的 deduplication_fields 统一成语义键（Data Hash 身份键唯一表示）。

背景
----
``deduplication_fields`` 在不同模板里混用了两种写法：

* 语义键：``order_id`` / ``product_id`` / ``platform_sku``
* 原始表头名：``订单号`` / ``产品ID`` / ``平台SKU``

两种写法都能算出 data_hash，但算出来的键名不同（语义键走 binding 解析，
表头名走字面匹配），于是同一行数据在不同模板下得到不同的 data_hash，
家族一致性校验却因为"都归一成语义键"而判它们"完全一致"，
最终表现为事实表里同一业务键对应多个 data_hash。

本脚本把能确凿判定的模板改写成语义键，写法不唯一的保持原样并列为待人工处理。

安全设计
--------
* 默认是 **干跑**，必须显式传 ``--apply`` 才会写库；
* 只有当某个表头名在模板自身的 ``header_bindings`` 里 **唯一命中** 一个
  canonical semantic_key 时才会替换；
* 替换后必须仍然通过模板的 hash 策略与保存就绪校验，否则该模板整体跳过；
* 写入前把原值备份到 JSON 文件，可用 ``--restore`` 回滚。

用法
----
    python scripts/normalize_template_deduplication_fields.py            # 干跑
    python scripts/normalize_template_deduplication_fields.py --apply    # 执行
    python scripts/normalize_template_deduplication_fields.py --restore backup.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.models.database import AsyncSessionLocal  # noqa: E402
from backend.services.semantic_field_registry import (  # noqa: E402
    SEMANTIC_FIELD_META,
    get_semantic_aliases,
    is_canonical_semantic_key,
    is_confirmed_semantic_binding,
    normalize_semantic_key,
    parse_rule_provided_semantic_keys,
)
from backend.services.template_hash_policy import (  # noqa: E402
    FILE_DATE_SOURCE_COLUMNS,
    TemplateHashPolicyService,
)
from backend.services.template_save_readiness_service import (  # noqa: E402
    TemplateSaveReadinessService,
)

# 字段处置分类
ACTION_REPLACE = "replace"  # 表头名 -> 可作身份键的语义键
ACTION_REMOVE = "remove"  # 表头名 -> 度量字段，不能区分行，应从去重字段中剔除
ACTION_UNKNOWN = "unknown"  # 无法判定，保持原样
ACTION_AMBIGUOUS = "ambiguous"  # 多个候选，保持原样


@dataclass
class TemplateFieldPlan:
    """单个模板的去重字段归一方案。"""

    template_id: int
    template_name: str
    data_domain: str
    granularity: Optional[str]
    status: str
    current_fields: List[str] = field(default_factory=list)
    planned_fields: List[str] = field(default_factory=list)
    replacements: List[Dict[str, str]] = field(default_factory=list)
    removals: List[Dict[str, str]] = field(default_factory=list)
    additions: List[Dict[str, str]] = field(default_factory=list)
    unmapped_fields: List[str] = field(default_factory=list)
    ambiguous_fields: List[str] = field(default_factory=list)
    missing_identity_keys: List[str] = field(default_factory=list)
    skipped_reason: Optional[str] = None

    @property
    def needs_change(self) -> bool:
        return (
            bool(self.replacements or self.removals or self.additions)
            and not self.skipped_reason
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "template_id": self.template_id,
            "template_name": self.template_name,
            "data_domain": self.data_domain,
            "granularity": self.granularity,
            "status": self.status,
            "current_fields": list(self.current_fields),
            "planned_fields": list(self.planned_fields),
            "replacements": [dict(item) for item in self.replacements],
            "removals": [dict(item) for item in self.removals],
            "additions": [dict(item) for item in self.additions],
            "unmapped_fields": list(self.unmapped_fields),
            "ambiguous_fields": list(self.ambiguous_fields),
            "missing_identity_keys": list(self.missing_identity_keys),
            "skipped_reason": self.skipped_reason,
            "needs_change": self.needs_change,
        }


def build_binding_semantic_index(
    header_bindings: Optional[List[Dict[str, Any]]],
) -> Dict[str, List[str]]:
    """建立 原始表头名(小写) -> 候选语义键 的索引。"""
    index: Dict[str, List[str]] = {}
    for binding in header_bindings or []:
        if not isinstance(binding, dict):
            continue
        semantic_key = normalize_semantic_key(binding.get("semantic_key"))
        if not semantic_key or not is_canonical_semantic_key(semantic_key):
            continue
        for raw in (
            binding.get("raw_name"),
            binding.get("source_header"),
            binding.get("display_name"),
        ):
            name = str(raw or "").strip()
            if not name:
                continue
            bucket = index.setdefault(name.lower(), [])
            if semantic_key not in bucket:
                bucket.append(semantic_key)
    return index


def build_global_semantic_index(
    templates: List[Dict[str, Any]],
) -> Dict[str, List[str]]:
    """跨模板学习 表头名 -> 语义键。

    历史模板自身的 header_bindings 里大多没有 semantic_key，
    但同一个表头名在别的模板里已经被确认过，可以据此归一。
    只保留全局唯一命中的，避免跨模板语义冲突。
    """
    collected: Dict[str, set] = {}
    for tpl in templates:
        for raw, keys in build_binding_semantic_index(tpl.get("header_bindings")).items():
            bucket = collected.setdefault(raw, set())
            bucket.update(keys)
    return {raw: sorted(keys) for raw, keys in collected.items() if len(keys) == 1}


def build_alias_semantic_index() -> Dict[str, List[str]]:
    """用语义字段注册表的别名表建立 表头名 -> 语义键 的兜底索引。"""
    index: Dict[str, List[str]] = {}
    for semantic_key in SEMANTIC_FIELD_META:
        for alias in get_semantic_aliases(semantic_key):
            name = str(alias or "").strip().lower()
            if not name:
                continue
            bucket = index.setdefault(name, [])
            if semantic_key not in bucket:
                bucket.append(semantic_key)
    return index


def merge_semantic_candidates(
    *indexes: Dict[str, List[str]],
) -> Dict[str, List[str]]:
    """合并多个映射来源；某个表头名在不同来源指向不同语义键时视为多候选。"""
    merged: Dict[str, set] = {}
    for index in indexes:
        for raw, keys in index.items():
            bucket = merged.setdefault(raw, set())
            bucket.update(keys)
    return {raw: sorted(keys) for raw, keys in merged.items()}


# 脚本专用的业务列名提示。
#
# 为什么单独放这里、而不是改 ``semantic_field_registry``：
# registry 是**全局语义契约**，后端 hash 计算、前端下拉框、前后端一致性测试
# 都依赖它；随手加别名会改变 ``normalize_semantic_key`` 的行为，
# 进而影响历史数据的 hash 取值路径。
#
# 这里只是「历史模板的列名写法和语义键命名不一致」的一次性归一提示，
# 只在本脚本内部生效，不外溢到运行时。
#
# 提示按数据域限定：同一个中文列名在不同域下含义可能不同，
# 跨域套用会把业务列错认成别的身份键。
LEGACY_COLUMN_SEMANTIC_HINTS: Dict[str, Dict[str, Any]] = {
    # 商品表：本地商品编号即 product_id，规格编号即 sku_id
    "商品编号": {"semantic_key": "product_id", "domains": {"products"}},
    "规格编号": {"semantic_key": "sku_id", "domains": {"products"}},
    # 客服工号即服务 ID
    "客服id": {"semantic_key": "service_id", "domains": {"services"}},
}


def build_hint_semantic_index(
    hints: Optional[Dict[str, Dict[str, Any]]] = None,
    data_domain: Optional[str] = None,
) -> Dict[str, List[str]]:
    """用业务列名提示表建立 原始表头名 -> 语义键 的索引。

    ``data_domain`` 不为空时，只启用适用于该数据域的提示。
    """
    domain = str(data_domain or "").strip().lower()
    index: Dict[str, List[str]] = {}
    for raw, spec in (hints or LEGACY_COLUMN_SEMANTIC_HINTS).items():
        if not isinstance(spec, dict):
            continue
        allowed_domains = spec.get("domains")
        if domain and allowed_domains and domain not in allowed_domains:
            continue
        normalized = normalize_semantic_key(spec.get("semantic_key"))
        if not normalized or not is_canonical_semantic_key(normalized):
            continue
        name = str(raw or "").strip().lower()
        if not name:
            continue
        bucket = index.setdefault(name, [])
        if normalized not in bucket:
            bucket.append(normalized)
    return index


def classify_semantic_key(semantic_key: str) -> str:
    """按语义字段的 kind 判断能否参与 Data Hash。"""
    meta = SEMANTIC_FIELD_META.get(semantic_key, {})
    kind = str(meta.get("kind") or "")
    if kind == "metric":
        return ACTION_REMOVE
    if bool(meta.get("hash_eligible")):
        return ACTION_REPLACE
    return ACTION_UNKNOWN


def collect_known_columns(
    header_columns: Optional[List[str]],
    header_bindings: Optional[List[Dict[str, Any]]],
) -> set[str]:
    """模板里真实存在的列名集合（小写）。"""
    known: set[str] = set()
    for column in header_columns or []:
        name = str(column or "").strip().lower()
        if name:
            known.add(name)
    for binding in header_bindings or []:
        if not isinstance(binding, dict):
            continue
        for raw in (binding.get("raw_name"), binding.get("source_header")):
            name = str(raw or "").strip().lower()
            if name:
                known.add(name)
    return known



def collect_confirmed_semantic_keys(
    header_bindings: Optional[List[Dict[str, Any]]],
) -> set[str]:
    """模板自身已确认的语义键集合。

    "已确认"= 绑定上带 semantic_key（迁移期兼容口径）或显式标记为
    confirmed_semantic。pending / confirmed_non_semantic 的绑定不算。
    """
    keys: set[str] = set()
    for binding in header_bindings or []:
        if not isinstance(binding, dict):
            continue
        if not is_confirmed_semantic_binding(binding):
            continue
        semantic_key = normalize_semantic_key(binding.get("semantic_key"))
        if semantic_key and is_canonical_semantic_key(semantic_key):
            keys.add(semantic_key)
    return keys


def collect_file_companion_rule_keys(
    field_parse_rules: Optional[List[Dict[str, Any]]],
) -> Dict[str, str]:
    """解析规则里来源为"文件伴生日期"的语义键 -> 来源列。

    这类日期来自文件名而不是行内数据，同一文件内所有行取值相同，
    只能作为"周期标识"，不能区分行。
    """
    sources: Dict[str, str] = {}
    for rule in field_parse_rules or []:
        if not isinstance(rule, dict):
            continue
        semantic_key = normalize_semantic_key(
            rule.get("target_field") or rule.get("semantic_key") or rule.get("field")
        )
        source_column = str(rule.get("source_column") or "").strip()
        if semantic_key and source_column in FILE_DATE_SOURCE_COLUMNS:
            sources[semantic_key] = source_column
    return sources


def build_parse_rule_source_index(
    field_parse_rules: Optional[List[Dict[str, Any]]],
) -> Dict[str, List[str]]:
    """原始表头名(小写) -> 解析规则产出的语义键 索引。

    解析规则的来源列是有数据的：规则会把这一列解析成某个语义键。
    所以来源列绝不能当成"无效列"剔除，否则会连周期标识一起丢掉。
    """
    index: Dict[str, List[str]] = {}
    for rule in field_parse_rules or []:
        if not isinstance(rule, dict):
            continue
        semantic_key = normalize_semantic_key(
            rule.get("target_field") or rule.get("semantic_key") or rule.get("field")
        )
        source_column = str(rule.get("source_column") or "").strip()
        if not semantic_key or not is_canonical_semantic_key(semantic_key):
            continue
        if not source_column:
            continue
        bucket = index.setdefault(source_column.lower(), [])
        if semantic_key not in bucket:
            bucket.append(semantic_key)
    return {raw: sorted(keys) for raw, keys in index.items()}


def _dedupe_fields(fields: List[str]) -> List[str]:
    """去重但保持顺序。"""
    deduped: List[str] = []
    seen = set()
    for item in fields:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _revalidate_fields(
    *,
    data_domain: str,
    granularity: Optional[str],
    sub_domain: Optional[str],
    deduplication_fields: List[str],
    header_columns: Optional[List[str]],
    header_bindings: Optional[List[Dict[str, Any]]],
    field_parse_rules: Optional[List[Dict[str, Any]]],
    hash_service: TemplateHashPolicyService,
    readiness_service: TemplateSaveReadinessService,
) -> Tuple[bool, List[str], str, Any]:
    """按两道闸门复验一组去重字段。

    返回 (是否通过, 还缺哪些身份键, 失败原因, hash 策略结果)。
    """
    readiness = readiness_service.assess(
        data_domain=data_domain,
        granularity=granularity,
        sub_domain=sub_domain,
        deduplication_fields=list(deduplication_fields),
        header_columns=list(header_columns or []),
        header_bindings=list(header_bindings or []),
        field_parse_rules=list(field_parse_rules or []),
    )
    if not readiness.can_save:
        return (
            False,
            collect_missing_identity_keys(readiness.hash_policy),
            "；".join(readiness.blocking_messages or readiness.blocking_errors),
            readiness.hash_policy,
        )
    policy = hash_service.validate(
        data_domain=data_domain,
        granularity=granularity,
        sub_domain=sub_domain,
        deduplication_fields=list(deduplication_fields),
        header_bindings=list(header_bindings or []),
        field_parse_rules=list(field_parse_rules or []),
    )
    if not policy.passed:
        return (
            False,
            collect_missing_identity_keys(policy),
            "；".join(policy.blocking_messages or policy.blocking_errors),
            policy,
        )
    return True, [], "", policy


def _plan_identity_additions(
    *,
    data_domain: str,
    granularity: Optional[str],
    sub_domain: Optional[str],
    current_fields: List[str],
    header_bindings: Optional[List[Dict[str, Any]]],
    field_parse_rules: Optional[List[Dict[str, Any]]],
    confirmed_keys: set[str],
    rule_keys: set[str],
    file_companion_keys: Dict[str, str],
    hash_service: TemplateHashPolicyService,
) -> List[Dict[str, str]]:
    """受控补齐域级必需身份键。

    只在"模板自身确实有数据来源"时才补：

    * 模板有已确认绑定指向该语义键；或
    * 解析规则能产出该语义键。

    绝不凭空造出没有数据来源的键；补齐后仍需复验两道闸门。
    """
    policy = hash_service.validate(
        data_domain=data_domain,
        granularity=granularity,
        sub_domain=sub_domain,
        deduplication_fields=list(current_fields),
        header_bindings=list(header_bindings or []),
        field_parse_rules=list(field_parse_rules or []),
    )
    missing_groups = [
        group
        for group in (policy.missing_required_groups or [])
        if group.get("severity") == "blocking"
    ]
    resolved = set(policy.resolved_keys or [])
    additions: List[Dict[str, str]] = []
    added_keys: set[str] = set()

    def _supports(key: str) -> bool:
        return key in confirmed_keys or key in rule_keys

    for group in missing_groups:
        accepted = list(group.get("accepted_keys") or [])
        requirement_type = str(group.get("requirement_type") or "any_of")
        if requirement_type == "any_of":
            wanted = list(accepted)
        else:
            wanted = [key for key in accepted if key not in resolved]
        for key in wanted:
            if key in resolved or key in added_keys:
                continue
            if not _supports(key):
                continue
            additions.append(
                {
                    "key": key,
                    "reason": (
                        "补齐域级必需身份键"
                        f"（{group.get('label') or group.get('key')}）"
                    ),
                }
            )
            added_keys.add(key)
            if requirement_type == "any_of":
                break

    # 周期键：解析规则的来源是文件伴生日期时，把它显式写进去重字段，
    # 让"周期标识"这一口径在模板里显式成立。
    for key in file_companion_keys:
        if key in resolved or key in added_keys:
            continue
        if not _supports(key):
            continue
        additions.append(
            {
                "key": key,
                "reason": "解析规则来源为文件伴生日期，作为周期标识显式写入去重字段",
            }
        )
        added_keys.add(key)

    return additions


def plan_template_field_mapping(
    *,
    template_id: int,
    template_name: str,
    data_domain: str,
    granularity: Optional[str],
    status: str,
    deduplication_fields: Optional[List[str]],
    header_bindings: Optional[List[Dict[str, Any]]],
    header_columns: Optional[List[str]],
    field_parse_rules: Optional[List[Dict[str, Any]]],
    sub_domain: Optional[str] = None,
    candidate_index: Optional[Dict[str, List[str]]] = None,
    hash_service: Optional[TemplateHashPolicyService] = None,
    readiness_service: Optional[TemplateSaveReadinessService] = None,
) -> TemplateFieldPlan:
    """计算单个模板的归一方案（纯函数，不碰数据库）。"""
    hash_service = hash_service or TemplateHashPolicyService()
    readiness_service = readiness_service or TemplateSaveReadinessService()

    local_index = merge_semantic_candidates(
        build_binding_semantic_index(header_bindings),
        build_alias_semantic_index(),
        build_hint_semantic_index(data_domain=data_domain),
    )
    if candidate_index is not None:
        candidate_index = merge_semantic_candidates(candidate_index, local_index)
    else:
        candidate_index = local_index

    current = [str(item).strip() for item in (deduplication_fields or []) if str(item).strip()]
    plan = TemplateFieldPlan(
        template_id=template_id,
        template_name=template_name,
        data_domain=data_domain,
        granularity=granularity,
        status=status,
        current_fields=list(current),
    )
    if not current:
        plan.skipped_reason = "模板未配置 deduplication_fields"
        return plan

    confirmed_keys = collect_confirmed_semantic_keys(header_bindings)
    rule_keys = parse_rule_provided_semantic_keys(field_parse_rules)
    file_companion_keys = collect_file_companion_rule_keys(field_parse_rules)
    parse_source_index = build_parse_rule_source_index(field_parse_rules)
    binding_raw_names = {
        str(raw or "").strip().lower()
        for binding in header_bindings or []
        if isinstance(binding, dict)
        for raw in (binding.get("raw_name"), binding.get("source_header"))
        if str(raw or "").strip()
    }

    planned: List[str] = []
    for raw_field in current:
        if is_canonical_semantic_key(raw_field):
            # 已经是语义键，保持原样
            planned.append(normalize_semantic_key(raw_field) or raw_field)
            continue
        candidates = candidate_index.get(raw_field.lower(), [])
        if len(candidates) == 1:
            semantic_key = candidates[0]
            action = classify_semantic_key(semantic_key)
            if action == ACTION_REPLACE:
                planned.append(semantic_key)
                plan.replacements.append(
                    {"from": raw_field, "to": semantic_key, "source": "semantic_index"}
                )
            elif action == ACTION_REMOVE:
                plan.removals.append(
                    {
                        "from": raw_field,
                        "to": semantic_key,
                        "source": "semantic_index",
                        "evidence": "semantic_metric",
                        "reason": "度量字段无法区分行，不应参与 Data Hash",
                    }
                )
            else:
                plan.unmapped_fields.append(raw_field)
                planned.append(raw_field)
        elif len(candidates) > 1:
            plan.ambiguous_fields.append(raw_field)
            planned.append(raw_field)
        else:
            derived_keys = parse_source_index.get(raw_field.lower(), [])
            if len(derived_keys) == 1:
                # 解析规则证明这一列会被解析成该语义键，直接改写成语义键
                planned.append(derived_keys[0])
                plan.replacements.append(
                    {"from": raw_field, "to": derived_keys[0], "source": "parse_rule"}
                )
            elif len(derived_keys) > 1:
                # 同一列被解析成多个语义键，无法确定用哪个，保持原样
                plan.ambiguous_fields.append(raw_field)
                planned.append(raw_field)
            else:
                # 该列名在语义字段注册表里完全不存在，也没有任何模板能给出映射，
                # 它不可能是合法的行身份键（业务属性 / 度量 / 导出时多出来的空列）。
                plan.removals.append(
                    {
                        "from": raw_field,
                        "to": "",
                        "source": "unrecognized_column",
                        "evidence": (
                            "binding_without_semantic_key"
                            if raw_field.lower() in binding_raw_names
                            else "no_binding"
                        ),
                        "reason": "该列名不在语义字段注册表内，无法作为行身份键",
                    }
                )

    deduped = _dedupe_fields(planned)
    plan.planned_fields = deduped

    if not deduped:
        plan.skipped_reason = "剔除后没有任何身份键，保持原样"
        return plan

    passed, missing, reason, _policy = _revalidate_fields(
        data_domain=data_domain,
        granularity=granularity,
        sub_domain=sub_domain,
        deduplication_fields=deduped,
        header_columns=header_columns,
        header_bindings=header_bindings,
        field_parse_rules=field_parse_rules,
        hash_service=hash_service,
        readiness_service=readiness_service,
    )

    if not passed:
        # 受控补齐：只有模板自身有数据来源的身份键才允许补进来
        additions = _plan_identity_additions(
            data_domain=data_domain,
            granularity=granularity,
            sub_domain=sub_domain,
            current_fields=deduped,
            header_bindings=header_bindings,
            field_parse_rules=field_parse_rules,
            confirmed_keys=confirmed_keys,
            rule_keys=rule_keys,
            file_companion_keys=file_companion_keys,
            hash_service=hash_service,
        )
        if additions:
            candidate_fields = _dedupe_fields(
                [*deduped, *(item["key"] for item in additions)]
            )
            passed2, missing2, reason2, _ = _revalidate_fields(
                data_domain=data_domain,
                granularity=granularity,
                sub_domain=sub_domain,
                deduplication_fields=candidate_fields,
                header_columns=header_columns,
                header_bindings=header_bindings,
                field_parse_rules=field_parse_rules,
                hash_service=hash_service,
                readiness_service=readiness_service,
            )
            if passed2:
                plan.additions = additions
                plan.planned_fields = candidate_fields
                return plan
            plan.missing_identity_keys = missing2
            plan.skipped_reason = (
                "补齐后仍未通过校验，保持原样：" + reason2
            )
            return plan

        plan.missing_identity_keys = missing
        if plan.replacements or plan.removals:
            plan.skipped_reason = "改写后未通过保存校验，保持原样：" + reason
        else:
            plan.skipped_reason = "当前配置未通过保存校验，且无法自动补齐，保持原样：" + reason
        return plan

    if not plan.replacements and not plan.removals and not plan.additions:
        plan.skipped_reason = "无需改写（已全部是语义键，且已通过校验）"
        return plan

    return plan


def collect_missing_identity_keys(policy) -> List[str]:
    """从 hash 策略结果里收集还缺哪些身份键。"""
    missing: List[str] = []
    for group in getattr(policy, "missing_required_groups", []) or []:
        for key in group.get("missing_keys") or []:
            if key not in missing:
                missing.append(key)
    return missing


_collect_missing_identity_keys = collect_missing_identity_keys


async def load_templates(session) -> List[Dict[str, Any]]:
    from sqlalchemy import text

    rows = await session.execute(
        text(
            """
            SELECT id, template_name, data_domain, granularity, sub_domain, status,
                   header_columns, deduplication_fields, field_parse_rules, header_bindings
            FROM core.field_mapping_templates
            WHERE deduplication_fields IS NOT NULL
            ORDER BY id
            """
        )
    )
    return [
        {
            "id": r[0],
            "template_name": r[1],
            "data_domain": r[2],
            "granularity": r[3],
            "sub_domain": r[4],
            "status": r[5],
            "header_columns": r[6] or [],
            "deduplication_fields": r[7] or [],
            "field_parse_rules": r[8] or [],
            "header_bindings": r[9] or [],
        }
        for r in rows
    ]


async def collect_plans() -> List[TemplateFieldPlan]:
    hash_service = TemplateHashPolicyService()
    readiness_service = TemplateSaveReadinessService()
    async with AsyncSessionLocal() as session:
        templates = await load_templates(session)

    candidate_index = merge_semantic_candidates(
        build_global_semantic_index(templates),
        build_alias_semantic_index(),
    )

    plans: List[TemplateFieldPlan] = []
    for tpl in templates:
        plans.append(
            plan_template_field_mapping(
                template_id=tpl["id"],
                template_name=tpl["template_name"],
                data_domain=tpl["data_domain"],
                granularity=tpl["granularity"],
                status=tpl["status"],
                deduplication_fields=tpl["deduplication_fields"],
                header_bindings=tpl["header_bindings"],
                header_columns=tpl["header_columns"],
                field_parse_rules=tpl["field_parse_rules"],
                sub_domain=tpl.get("sub_domain"),
                candidate_index=candidate_index,
                hash_service=hash_service,
                readiness_service=readiness_service,
            )
        )
    return plans


async def apply_plans(
    plans: List[TemplateFieldPlan],
    backup_path: Path,
    session=None,
) -> int:
    from sqlalchemy import text

    changed = [p for p in plans if p.needs_change]
    backup = {
        "generated_at": None,
        "templates": [
            {
                "template_id": p.template_id,
                "template_name": p.template_name,
                "before": p.current_fields,
                "after": p.planned_fields,
            }
            for p in changed
        ],
    }
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path.write_text(
        json.dumps(backup, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    async def _run(target) -> int:
        for plan in changed:
            await target.execute(
                text(
                    """
                    UPDATE core.field_mapping_templates
                    SET deduplication_fields = CAST(:fields AS jsonb),
                        updated_at = now()
                    WHERE id = :tid
                    """
                ),
                {
                    "fields": json.dumps(plan.planned_fields, ensure_ascii=False),
                    "tid": plan.template_id,
                },
            )
        await target.commit()
        return len(changed)

    if session is not None:
        return await _run(session)

    async with AsyncSessionLocal() as own_session:
        return await _run(own_session)


async def restore_plans(backup_path: Path, session=None) -> int:
    from sqlalchemy import text

    backup = json.loads(backup_path.read_text(encoding="utf-8"))
    entries = backup.get("templates") or []

    async def _run(target) -> int:
        for entry in entries:
            await target.execute(
                text(
                    """
                    UPDATE core.field_mapping_templates
                    SET deduplication_fields = CAST(:fields AS jsonb),
                        updated_at = now()
                    WHERE id = :tid
                    """
                ),
                {
                    "fields": json.dumps(entry["before"], ensure_ascii=False),
                    "tid": entry["template_id"],
                },
            )
        await target.commit()
        return len(entries)

    if session is not None:
        return await _run(session)

    async with AsyncSessionLocal() as own_session:
        return await _run(own_session)


def print_report(plans: List[TemplateFieldPlan]) -> None:
    changed = [p for p in plans if p.needs_change]
    skipped = [p for p in plans if not p.needs_change]
    print(f"共检查 {len(plans)} 个配置了 deduplication_fields 的模板")
    print(f"  可安全改写: {len(changed)}")
    print(f"  保持原样: {len(skipped)}")
    if changed:
        print("\n=== 可安全改写（表头名 -> 语义键） ===")
        for plan in changed:
            print(f"[{plan.template_id}] {plan.template_name} ({plan.data_domain}/{plan.granularity}, {plan.status})")
            for item in plan.replacements:
                print(f"    替换  {item['from']}  ->  {item['to']}   (依据: {item['source']})")
            for item in plan.removals:
                target = item["to"] or "(剔除)"
                evidence = item.get("evidence") or "-"
                print(
                    f"    剔除  {item['from']}  ->  {target}   "
                    f"({item['reason']}; 证据: {evidence})"
                )
            for item in plan.additions:
                print(f"    补齐  {item['key']}   ({item['reason']})")
            print(f"    结果  {plan.current_fields}  ->  {plan.planned_fields}")
            if plan.unmapped_fields:
                print(f"    无法判定，保持原样: {plan.unmapped_fields}")
            if plan.ambiguous_fields:
                print(f"    多个候选，保持原样: {plan.ambiguous_fields}")
    skipped_with_reason = [
        p for p in plans if p.skipped_reason and "无需改写" not in p.skipped_reason
    ]
    if skipped_with_reason:
        print("\n=== 改写后未通过校验，保持原样 ===")
        for plan in skipped_with_reason:
            print(
                f"[{plan.template_id}] {plan.template_name}: {plan.skipped_reason}"
            )
            if plan.missing_identity_keys:
                print(f"      还缺这些身份键: {plan.missing_identity_keys}")
    pending = [
        p
        for p in plans
        if p.needs_change or p.unmapped_fields or p.ambiguous_fields
    ]
    if pending:
        print("\n=== 需要人工确认的字段 ===")
        for plan in pending:
            if not plan.unmapped_fields and not plan.ambiguous_fields:
                continue
            print(
                f"[{plan.template_id}] {plan.template_name}: "
                f"无法判定={plan.unmapped_fields} 多候选={plan.ambiguous_fields}"
            )
    removed_columns: Dict[str, List[int]] = {}
    for plan in changed:
        for item in plan.removals:
            removed_columns.setdefault(item["from"], []).append(plan.template_id)
    if removed_columns:
        print("\n=== 被剔除的列名清单（请人工审阅） ===")
        for column, template_ids in sorted(removed_columns.items()):
            evidences = sorted(
                {
                    item.get("evidence") or "-"
                    for plan in changed
                    for item in plan.removals
                    if item["from"] == column
                }
            )
            print(f"    {column}  <- 模板 {template_ids}  证据: {evidences}")
    print("\n提示：把业务属性/度量列写进 deduplication_fields 本身就是配置错误，")
    print("      它们无法区分行；需要按域补齐真正的身份键（见各模板的『还缺这些身份键』）。")
    print("      被剔除的列名如果确实是业务身份键，请在对应模板里确认字段映射后重新运行本脚本。")


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="把模板 deduplication_fields 统一成语义键"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="真正写库（默认只干跑）",
    )
    parser.add_argument(
        "--backup",
        default=str(ROOT / "logs" / "dedup_fields_backup.json"),
        help="备份文件路径",
    )
    parser.add_argument(
        "--restore",
        default=None,
        help="用备份文件回滚",
    )
    args = parser.parse_args()

    if args.restore:
        path = Path(args.restore)
        if not path.exists():
            print(f"备份文件不存在: {path}")
            return 1
        count = await restore_plans(path)
        print(f"已回滚 {count} 个模板")
        return 0

    plans = await collect_plans()
    print_report(plans)

    if not args.apply:
        print("\n干跑结束（未修改任何数据）。加 --apply 才会写库。")
        return 0

    backup_path = Path(args.backup)
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    count = await apply_plans(plans, backup_path)
    print(f"\n已改写 {count} 个模板，备份: {backup_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
