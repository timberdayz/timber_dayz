#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""模板 Data Hash 口径体检（**只读**巡检入口）。

为什么需要它
------------
第 1~4 批把模板保存口径和 hash 闸门收紧了，但**闸门只在保存那一刻拦**。
已经存在的模板、以及新建模板时误选的字段，如果没有定期巡检，
就会一直烂在库里，直到某次同步把重复数据写进去才被发现。

这个脚本定期回答四个问题
------------------------
1. **口径不统一**（``non_canonical_identity``）
   ``deduplication_fields`` 里还是中文表头名（``订单号`` 而不是 ``order_id``）
   ⇒ 同一笔业务在不同模板下算出不同 ``data_hash``
   ⇒ 唯一约束撞不上 ⇒ 同一业务被插成多行。
2. **度量字段混进身份键**（``metric_in_identity``）
   把 ``订单状态`` / ``访客数`` 这类"描述行"的字段写进去重字段
   ⇒ 行身份会随业务状态变化而漂移。
3. **存不下来**（``needs_manual_mapping``）
   走一遍工作台提交口径后**仍然过不了保存闸门**
   ⇒ 源文件一变动，用户在工作台更新模板时会被卡住。
4. **能自动修**（``needs_renormalize``）
   已有安全改写方案 ⇒ 跑 ``scripts/normalize_template_deduplication_fields.py`` 即可归一。

判定口径（重要）
----------------
"过不了保存闸门"必须按**工作台提交口径**判断，而不是拿库里的存量字段直接评估：

- 工作台会把**未确认的表头列**剔除；
- 工作台会剔除**解析规则派生**的字段和**不可参与 hash** 的度量字段；
- 工作台会自动**补齐**该数据域必需的身份键。

否则体检结论会和用户在工作台里看到的**对不上**。
这条口径由 ``TemplateSaveReadinessService.build_workbench_effective_deduplication_fields``
实现，与前端 ``deduplicationSelection.js`` / ``TemplateUpdateWorkbenchDrawer.vue`` 一一对应。

安全性
------
* **只读**：全程不写库；
* 默认退出码 0（只报告）；``--strict`` 时有问题返回 1；
  ``--fail-on-new`` 时只对**相对基线新增**的问题返回 1（适合挂 CI 守新增）；
* 支持 ``--baseline`` 与上一次报告对比，看**增量**而不是只看存量。

用法
----
    python scripts/audit_template_hash_hygiene.py
    python scripts/audit_template_hash_hygiene.py --only-issues
    python scripts/audit_template_hash_hygiene.py --json logs/template_hygiene.json
    python scripts/audit_template_hash_hygiene.py --baseline logs/template_hygiene_prev.json
    python scripts/audit_template_hash_hygiene.py --strict
    python scripts/audit_template_hash_hygiene.py --baseline prev.json --fail-on-new
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from sqlalchemy import text  # noqa: E402

from backend.domains.data_platform.routers.field_mapping_templates import (  # noqa: E402
    _normalize_header_bindings,
    _recommended_deduplication_fields,
    _split_existing_deduplication_fields,
)
from backend.models.database import AsyncSessionLocal  # noqa: E402
from backend.services.deduplication_fields_config import (  # noqa: E402
    get_default_deduplication_fields,
)
from backend.services.semantic_field_registry import (  # noqa: E402
    SEMANTIC_FIELD_META,
    is_canonical_semantic_key,
    normalize_semantic_key,
)
from backend.services.template_hash_policy import (
    TemplateHashPolicyService,
)  # noqa: E402
from backend.services.template_save_readiness_service import (  # noqa: E402
    TemplateSaveReadinessService,
)
from normalize_template_deduplication_fields import (  # noqa: E402
    plan_template_field_mapping,
)

# ---------------------------------------------------------------------------
# 问题分类
# ---------------------------------------------------------------------------
ISSUE_NON_CANONICAL = "non_canonical_identity"
"""去重字段仍是表头名而不是语义键（口径不统一 ⇒ 同一笔业务算不同 hash）。"""

ISSUE_METRIC_IN_IDENTITY = "metric_in_identity"
"""度量字段混进了去重字段（行身份会随状态漂移）。"""

ISSUE_NEEDS_RENORMALIZE = "needs_renormalize"
"""已有安全改写方案（跑 normalize 脚本即可归一）。"""

ISSUE_NEEDS_MANUAL_MAPPING = "needs_manual_mapping"
"""走工作台口径后仍过不了保存闸门（必须人工在工作台确认映射）。"""

ISSUE_MISSING_IDENTITY_KEY = "missing_identity_key"
"""去重字段里缺该数据域必需的身份键（hash 口径不全 ⇒ 同一业务可能算成多行）。"""

ISSUE_NO_DEDUP_FIELDS = "no_dedup_fields"
"""没有配置去重字段（同步时回落到域默认口径）。"""

ISSUE_LABELS = {
    ISSUE_NON_CANONICAL: "去重字段仍是表头名（口径不统一 ⇒ 同一笔业务算不同 hash）",
    ISSUE_METRIC_IN_IDENTITY: "度量字段混进了去重字段（行身份会随状态漂移）",
    ISSUE_NEEDS_RENORMALIZE: "已有安全改写方案（跑 normalize 脚本即可归一）",
    ISSUE_NEEDS_MANUAL_MAPPING: "过不了保存闸门（源文件一变动就无法在工作台更新）",
    ISSUE_MISSING_IDENTITY_KEY: "缺该域必需的身份键（hash 口径不全）",
    ISSUE_NO_DEDUP_FIELDS: "没有配置去重字段（同步时回落到域默认口径）",
}

# 阻塞级问题：模板在工作台里存不下来 ⇒ 源文件一变就卡住同步链路。
BLOCKING_ISSUES = frozenset({ISSUE_NEEDS_MANUAL_MAPPING})

# 告警级问题：不影响保存，但会让 hash 口径不干净。
WARNING_ISSUES = frozenset(
    {
        ISSUE_NON_CANONICAL,
        ISSUE_METRIC_IN_IDENTITY,
        ISSUE_NEEDS_RENORMALIZE,
        ISSUE_MISSING_IDENTITY_KEY,
    }
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="模板 Data Hash 口径体检（只读巡检）")
    parser.add_argument(
        "--json",
        dest="json_path",
        help="把报告写到该 JSON 文件（便于跨次对比）",
    )
    parser.add_argument(
        "--baseline",
        help="与上一次报告 JSON 对比，输出新增/已修复的问题",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="有问题时返回退出码 1（CI 用）",
    )
    parser.add_argument(
        "--fail-on-new",
        action="store_true",
        help="只对**相对基线新增**的问题返回退出码 1（守住增量）",
    )
    parser.add_argument(
        "--only-issues",
        action="store_true",
        help="只打印有问题的模板",
    )
    parser.add_argument(
        "--status",
        help="只看某个状态的模板（如 published / archived）",
    )
    return parser.parse_args()


def _metric_like_semantic_keys() -> set[str]:
    """所有"度量类"语义键：kind == metric 或明确不可参与 hash。"""
    return {
        key
        for key, meta in SEMANTIC_FIELD_META.items()
        if str(meta.get("kind") or "") == "metric" or meta.get("hash_eligible") is False
    }


def _resolve_columns(
    header_columns: Optional[List[str]],
    header_bindings: Optional[List[Dict[str, Any]]],
) -> List[str]:
    """表头列名。

    ``header_columns`` 为空时（老模板只留了绑定没留表头），
    用存量绑定里的 ``raw_name`` 兜底，否则重推断会得到空绑定 → 误判为"过不了闸门"。
    """
    columns = [
        str(item).strip() for item in (header_columns or []) if str(item).strip()
    ]
    if columns:
        return columns
    return [
        str(item.get("raw_name") or "").strip()
        for item in (header_bindings or [])
        if isinstance(item, dict) and str(item.get("raw_name") or "").strip()
    ]


def classify_template(
    *,
    template_id: int,
    template_name: str,
    data_domain: str,
    granularity: Optional[str],
    sub_domain: Optional[str],
    status: str,
    deduplication_fields: Optional[List[str]],
    header_bindings: Optional[List[Dict[str, Any]]],
    header_columns: Optional[List[str]],
    field_parse_rules: Optional[List[Dict[str, Any]]],
    hash_service: TemplateHashPolicyService,
    readiness_service: TemplateSaveReadinessService,
) -> Dict[str, Any]:
    """体检单个模板，返回问题清单（纯函数，不碰数据库）。"""
    fields = list(deduplication_fields or [])
    issues: List[str] = []
    details: Dict[str, Any] = {}

    if not fields:
        issues.append(ISSUE_NO_DEDUP_FIELDS)
        details["no_deduplication_fields"] = True

    # ① 口径不统一：去重字段里还有非规范语义键
    non_canonical = [f for f in fields if not is_canonical_semantic_key(f)]
    if non_canonical:
        issues.append(ISSUE_NON_CANONICAL)
        details["non_canonical_fields"] = non_canonical

    # ② 度量字段混进身份键
    metric_keys = _metric_like_semantic_keys()
    metric_fields = [
        f for f in fields if (normalize_semantic_key(f) or "") in metric_keys
    ]
    if metric_fields:
        issues.append(ISSUE_METRIC_IN_IDENTITY)
        details["metric_fields"] = metric_fields

    # ③ 保存闸门：按**工作台提交口径**判定
    #
    # ⚠️ 这里的绑定必须用**域限定重推断**后的结果，而不是模板里存量的绑定：
    # 保存接口（``save_mapping_template``）拿到的是工作台回传的绑定，
    # 而工作台的绑定是后端按**当前源文件表头 + 数据域**重新推断出来的。
    # 体检口径必须和闸门口径一致，否则体检出来的结论和实际保存行为对不上。
    #
    # 工作台的完整链路（后端侧可复用的三段）：
    #   1) ``_split_existing_deduplication_fields`` → 存量去重字段里还认得出的部分；
    #   2) ``_recommended_deduplication_fields`` → 认不出时用域默认字段兜底；
    #   3) ``build_workbench_effective_deduplication_fields`` → 剔除未确认/派生/度量字段，
    #      并自动补齐域必需身份键。
    columns = _resolve_columns(header_columns, header_bindings)
    effective_bindings = _normalize_header_bindings(
        list(header_bindings or []),
        columns,
        {},
        data_domain=data_domain,
    )
    available_fields, _missing_fields, _matches = _split_existing_deduplication_fields(
        fields,
        columns,
        effective_bindings,
        existing_header_bindings=list(header_bindings or []),
        data_domain=data_domain,
        granularity=granularity,
        sub_domain=sub_domain,
    )
    recommended_fields = _recommended_deduplication_fields(
        get_default_deduplication_fields(data_domain, sub_domain),
        columns,
        effective_bindings,
    )
    initial_selection = available_fields if available_fields else recommended_fields
    effective_fields = readiness_service.build_workbench_effective_deduplication_fields(
        data_domain=data_domain,
        granularity=granularity,
        sub_domain=sub_domain,
        deduplication_fields=initial_selection,
        header_bindings=effective_bindings,
        field_parse_rules=list(field_parse_rules or []),
    )
    readiness = readiness_service.assess(
        data_domain=data_domain,
        granularity=granularity,
        sub_domain=sub_domain,
        deduplication_fields=effective_fields,
        header_columns=columns,
        header_bindings=effective_bindings,
        field_parse_rules=list(field_parse_rules or []),
    )
    details["workbench_effective_fields"] = list(effective_fields)
    details["can_save"] = bool(readiness.can_save)
    if not readiness.can_save:
        issues.append(ISSUE_NEEDS_MANUAL_MAPPING)
        details["blocking_errors"] = list(readiness.blocking_errors)
        details["unresolved_deduplication_fields"] = list(
            readiness.unresolved_deduplication_fields or []
        )
        details["missing_required_groups"] = [
            group.get("key")
            for group in (readiness.hash_policy.missing_required_groups or [])
        ]

    # ④ hash 口径体检：存量去重字段里有没有该域必需的身份键
    #
    # 这是"hash 口径"最核心的一条：缺了身份键 ⇒ 同一笔业务在不同周期/不同文件里
    # 可能算出同一个 hash（互相覆盖）或算出不同 hash（重复入库）。
    required_keys = hash_service.required_identity_keys(data_domain, sub_domain)
    normalized_fields = {
        normalize_semantic_key(field) or "" for field in fields if str(field).strip()
    }
    missing_identity_keys = [
        key for key in required_keys if key not in normalized_fields
    ]
    if missing_identity_keys:
        issues.append(ISSUE_MISSING_IDENTITY_KEY)
        details["missing_identity_keys"] = missing_identity_keys

    # ⑤ 是否已有安全改写方案
    #
    # ⚠️ 这里用**模板存量绑定**而不是重推断后的绑定：
    # 只改 ``deduplication_fields`` 而不同步写 ``header_bindings`` 是**危险的** ——
    # hash 计算靠绑定把语义键落到具体列上，绑定缺了 semantic_key，
    # 该字段就会被静默漏出 hash（所有行算出同一个 hash）。
    plan = plan_template_field_mapping(
        template_id=template_id,
        template_name=template_name,
        data_domain=data_domain,
        granularity=granularity,
        status=status,
        deduplication_fields=fields,
        header_bindings=list(header_bindings or []),
        header_columns=list(header_columns or []),
        field_parse_rules=list(field_parse_rules or []),
        sub_domain=sub_domain,
        hash_service=hash_service,
        readiness_service=readiness_service,
    )
    if plan.needs_change:
        issues.append(ISSUE_NEEDS_RENORMALIZE)
        details["planned_fields"] = list(plan.planned_fields)
        details["skipped_reason"] = plan.skipped_reason
    elif plan.skipped_reason and plan.skipped_reason.startswith("改写后未通过保存校验"):
        # 自动改写本身可行，但改完仍缺身份键 ⇒ 只能人工在工作台确认映射。
        details["skipped_reason"] = plan.skipped_reason
        details["missing_identity_keys"] = list(plan.missing_identity_keys)

    return {
        "template_id": template_id,
        "template_name": template_name,
        "data_domain": data_domain,
        "granularity": granularity,
        "sub_domain": sub_domain,
        "status": status,
        "issues": issues,
        "details": details,
    }


async def collect_templates() -> List[Dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT id, template_name, data_domain, granularity, sub_domain, status,
                           deduplication_fields, header_bindings, header_columns, field_parse_rules
                    FROM core.field_mapping_templates
                    ORDER BY id
                    """
                )
            )
        ).fetchall()

    result: List[Dict[str, Any]] = []
    for row in rows:
        (
            tid,
            name,
            domain,
            grain,
            sub,
            status,
            dedup,
            bindings,
            columns,
            rules,
        ) = row
        result.append(
            {
                "template_id": tid,
                "template_name": name,
                "data_domain": domain,
                "granularity": grain,
                "sub_domain": sub,
                "status": status,
                "deduplication_fields": list(dedup or []),
                "header_bindings": list(bindings or []),
                "header_columns": list(columns or []),
                "field_parse_rules": list(rules or []),
            }
        )
    return result


def build_report(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    summary = {key: 0 for key in ISSUE_LABELS}
    by_issue: Dict[str, List[int]] = {key: [] for key in ISSUE_LABELS}
    blocking: List[int] = []
    for item in results:
        for issue in item["issues"]:
            summary[issue] += 1
            by_issue[issue].append(item["template_id"])
        if BLOCKING_ISSUES.intersection(item["issues"]):
            blocking.append(item["template_id"])
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_templates": len(results),
        "summary": summary,
        "by_issue": by_issue,
        "blocking_template_ids": blocking,
        "by_status": _breakdown_by_status(results),
        "templates": [item for item in results if item["issues"]],
    }


def _breakdown_by_status(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """按模板状态分组统计。

    ``published``（在线模板）的问题才是**当下会影响同步**的；
    ``archived``（历史模板）的问题是存量欠账，等要用到再清理。
    """
    buckets: Dict[str, Dict[str, int]] = {}
    for item in results:
        status = str(item.get("status") or "unknown")
        bucket = buckets.setdefault(
            status, {"total": 0, "with_issues": 0, "blocking": 0}
        )
        bucket["total"] += 1
        if item["issues"]:
            bucket["with_issues"] += 1
        if BLOCKING_ISSUES.intersection(item["issues"]):
            bucket["blocking"] += 1
    return buckets


def print_report(
    report: Dict[str, Any], results: List[Dict[str, Any]], only_issues: bool
) -> None:
    print("=" * 90)
    print("模板 Data Hash 口径体检（只读巡检）")
    print("=" * 90)
    print(f"  体检模板总数: {report['total_templates']}")
    print(f"  有问题的模板: {len(report['templates'])}")
    print(f"  其中阻塞级（工作台存不下来）: {len(report['blocking_template_ids'])}")
    print("-" * 90)
    for status, bucket in sorted(report.get("by_status", {}).items()):
        print(
            f"  状态 {status:<12} 共 {bucket['total']:>4} 个 | "
            f"有问题 {bucket['with_issues']:>4} 个 | 阻塞 {bucket['blocking']:>4} 个"
        )
    print("-" * 90)
    for issue, label in ISSUE_LABELS.items():
        count = report["summary"].get(issue, 0)
        level = "阻塞" if issue in BLOCKING_ISSUES else "告警"
        print(f"  [{count:>4}] {label}  ({level})")
    print("-" * 90)

    if not only_issues:
        healthy = [item for item in results if not item["issues"]]
        if healthy:
            print(f"  合规模板 {len(healthy)} 个（不逐条列出）")

    for item in report["templates"]:
        print(
            f"\n  [{item['template_id']}] {item['template_name']} "
            f"({item['data_domain']}/{item['granularity']} status={item['status']})"
        )
        for issue in item["issues"]:
            print(f"      - {ISSUE_LABELS[issue]}")
            details = item["details"]
            if issue == ISSUE_NON_CANONICAL:
                print(f"        表头名: {details.get('non_canonical_fields')}")
            elif issue == ISSUE_METRIC_IN_IDENTITY:
                print(f"        度量字段: {details.get('metric_fields')}")
            elif issue == ISSUE_NEEDS_MANUAL_MAPPING:
                print(f"        阻断原因: {details.get('blocking_errors')}")
                if details.get("missing_required_groups"):
                    print(f"        缺要求组: {details.get('missing_required_groups')}")
                print(
                    f"        工作台提交字段: {details.get('workbench_effective_fields')}"
                )
            elif issue == ISSUE_MISSING_IDENTITY_KEY:
                print(f"        缺身份键: {details.get('missing_identity_keys')}")
            elif issue == ISSUE_NEEDS_RENORMALIZE:
                print(f"        建议归一为: {details.get('planned_fields')}")
                if details.get("skipped_reason"):
                    print(f"        跳过原因: {details.get('skipped_reason')}")
            elif issue == ISSUE_NO_DEDUP_FIELDS:
                print("        同步时会回落到该数据域的默认去重字段")


def compare_with_baseline(report: Dict[str, Any], baseline_path: str) -> Dict[str, Any]:
    baseline = json.loads(Path(baseline_path).read_text(encoding="utf-8"))
    base_ids = {
        int(tid) for ids in (baseline.get("by_issue") or {}).values() for tid in ids
    }
    cur_ids = {
        int(tid) for ids in (report.get("by_issue") or {}).values() for tid in ids
    }
    base_blocking = {int(tid) for tid in baseline.get("blocking_template_ids") or []}
    cur_blocking = {int(tid) for tid in report.get("blocking_template_ids") or []}
    return {
        "baseline_generated_at": baseline.get("generated_at"),
        "baseline_issue_templates": len(base_ids),
        "current_issue_templates": len(cur_ids),
        "new_problem_template_ids": sorted(cur_ids - base_ids),
        "fixed_template_ids": sorted(base_ids - cur_ids),
        "new_blocking_template_ids": sorted(cur_blocking - base_blocking),
        "fixed_blocking_template_ids": sorted(base_blocking - cur_blocking),
    }


async def main() -> int:
    args = parse_args()
    hash_service = TemplateHashPolicyService()
    readiness_service = TemplateSaveReadinessService()

    templates = await collect_templates()
    if args.status:
        wanted_status = str(args.status).strip().lower()
        templates = [
            item
            for item in templates
            if str(item.get("status") or "").strip().lower() == wanted_status
        ]
    results = [
        classify_template(
            template_id=item["template_id"],
            template_name=item["template_name"],
            data_domain=item["data_domain"],
            granularity=item["granularity"],
            sub_domain=item["sub_domain"],
            status=item["status"],
            deduplication_fields=item["deduplication_fields"],
            header_bindings=item["header_bindings"],
            header_columns=item["header_columns"],
            field_parse_rules=item["field_parse_rules"],
            hash_service=hash_service,
            readiness_service=readiness_service,
        )
        for item in templates
    ]

    report = build_report(results)
    print_report(report, results, args.only_issues)

    diff: Optional[Dict[str, Any]] = None
    if args.baseline:
        diff = compare_with_baseline(report, args.baseline)
        report["baseline_diff"] = diff
        print("-" * 90)
        print("  与基线对比:")
        print(f"    基线时间: {diff['baseline_generated_at']}")
        print(
            f"    基线问题模板数: {diff['baseline_issue_templates']} → "
            f"当前: {diff['current_issue_templates']}"
        )
        print(f"    新增问题模板: {diff['new_problem_template_ids'] or '无'}")
        print(f"    已修复模板: {diff['fixed_template_ids'] or '无'}")
        print(f"    新增阻塞模板: {diff['new_blocking_template_ids'] or '无'}")
        print(f"    已修复阻塞模板: {diff['fixed_blocking_template_ids'] or '无'}")

    if args.json_path:
        out = Path(args.json_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"\n[INFO] 报告已写入: {out}")

    if args.fail_on_new:
        if not args.baseline:
            print("\n[ERROR] --fail-on-new 需要配合 --baseline 使用")
            return 2
        new_ids = diff["new_problem_template_ids"] if diff else []
        if new_ids:
            print(f"\n[ERROR] 相对基线新增 {len(new_ids)} 个问题模板: {new_ids}")
            return 1
        return 0

    if args.strict:
        problem_count = len(report["templates"])
        if problem_count:
            print(
                f"\n[ERROR] 发现 {problem_count} 个有问题的模板（--strict 模式返回失败）"
            )
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
