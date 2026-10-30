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
    normalize_semantic_key,
)
from backend.services.template_hash_policy import TemplateHashPolicyService  # noqa: E402
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
    unmapped_fields: List[str] = field(default_factory=list)
    ambiguous_fields: List[str] = field(default_factory=list)
    missing_identity_keys: List[str] = field(default_factory=list)
    skipped_reason: Optional[str] = None

    @property
    def needs_change(self) -> bool:
        return bool(self.replacements or self.removals) and not self.skipped_reason

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


def classify_semantic_key(semantic_key: str) -> str:
    """按语义字段的 kind 判断能否参与 Data Hash。"""
    meta = SEMANTIC_FIELD_META.get(semantic_key, {})
    kind = str(meta.get("kind") or "")
    if kind == "metric":
        return ACTION_REMOVE
    if bool(meta.get("hash_eligible")):
        return ACTION_REPLACE
    return ACTION_UNKNOWN


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
    candidate_index: Optional[Dict[str, List[str]]] = None,
    hash_service: Optional[TemplateHashPolicyService] = None,
    readiness_service: Optional[TemplateSaveReadinessService] = None,
) -> TemplateFieldPlan:
    """计算单个模板的归一方案（纯函数，不碰数据库）。"""
    hash_service = hash_service or TemplateHashPolicyService()
    readiness_service = readiness_service or TemplateSaveReadinessService()
    if candidate_index is None:
        candidate_index = merge_semantic_candidates(
            build_binding_semantic_index(header_bindings),
            build_alias_semantic_index(),
        )

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
            plan.unmapped_fields.append(raw_field)
            planned.append(raw_field)

    # 去重但保持顺序
    deduped: List[str] = []
    seen = set()
    for item in planned:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    plan.planned_fields = deduped

    if not plan.replacements and not plan.removals:
        plan.skipped_reason = "无需改写（已全部是语义键，或无法确凿判定）"
        return plan

    # 改写后必须仍然通过两道闸门，否则整体跳过
    readiness = readiness_service.assess(
        data_domain=data_domain,
        granularity=granularity,
        sub_domain=None,
        deduplication_fields=list(deduped),
        header_columns=list(header_columns or []),
        header_bindings=list(header_bindings or []),
        field_parse_rules=list(field_parse_rules or []),
    )
    if not readiness.can_save:
        plan.missing_identity_keys = _collect_missing_identity_keys(readiness.hash_policy)
        plan.skipped_reason = (
            "改写后未通过保存校验，保持原样："
            + "；".join(readiness.blocking_messages or readiness.blocking_errors)
        )
        return plan

    policy = hash_service.validate(
        data_domain=data_domain,
        granularity=granularity,
        sub_domain=None,
        deduplication_fields=list(deduped),
        header_bindings=list(header_bindings or []),
        field_parse_rules=list(field_parse_rules or []),
    )
    if not policy.passed:
        plan.skipped_reason = (
            "改写后未通过 hash 策略校验，保持原样："
            + "；".join(policy.blocking_messages or policy.blocking_errors)
        )
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
                print(f"    剔除  {item['from']}  ->  {item['to']}   ({item['reason']})")
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
    print("\n提示：把业务属性/度量列写进 deduplication_fields 本身就是配置错误，")
    print("      它们无法区分行；需要按域补齐真正的身份键（见各模板的『还缺这些身份键』）。")


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
