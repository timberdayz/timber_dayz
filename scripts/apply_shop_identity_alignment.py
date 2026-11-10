#!/usr/bin/env python3
"""批次 2：按批次 0 的对账结果对齐店铺身份主数据。

输入是批次 0 脚本产出的对账 JSON（``scripts/verify_shop_identity_reconciliation.py``），
输出并执行两类变更：

1. **T1 → 修正 ``core.shop_accounts.platform_shop_id``**
   默认方向：**本地 → 云端**（云端是历史基准，与方案文档批次 2 步骤 2.1 一致）。
   ⚠ 默认**只动** ``platform_shop_id`` 一个字段 —— T1 另外比对的 5 个字段
   （``platform_shop_id_status`` / ``store_name`` / ``enabled`` / ``business_role``
   / ``updated_by``）**只报告不改**：
   改名是业务决定、停用是运营开关、自动覆盖它们等于替业务做决定。
   需要一并对齐时用 ``--also`` 显式点名。

2. **T2 → 删除错别名**
   只删 ``alias_kind`` 属于 ``self_alias`` / ``self_and_cross`` / ``cross_account_claim``
   的 ``former_platform_shop_id`` 别名。删除前先做**身份来源检查**：
   若该别名值是某个账号**唯一**的身份来源（该账号自己没有有效 ``platform_shop_id``），
   则**拒绝删除**并报告。
   事实行里出现同值**不阻断**——按「历史不修」的边界，那些行的归属早已固化、
   不再查别名表，且语义层别名路不认领平台编号，删别名不改变其解析结果；
   这种情况只作为人工确认依据列出。

安全设计：

- **默认 dry-run**：不加 ``--apply`` 只打印计划，绝不写库。
- **先快照后写入**：执行前把 ``core.shop_accounts`` 与待删别名行落盘，供回滚。
- **单事务**：所有改动在一个事务里，任一步失败整体回滚。
- 写入的 ``updated_by`` 记为**人工修复**（不是 ``system``），避免再被自动流程覆盖。

用法::

    # 1) 看计划（不写库）
    python scripts/apply_shop_identity_alignment.py --plan output/reconciliation-20261110.json

    # 2) 真正执行
    python scripts/apply_shop_identity_alignment.py --plan output/reconciliation-20261110.json --apply

退出码：``0`` 正常（dry-run 产出计划 / apply 成功）、``2`` 执行失败或前置检查不通过。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

PROJECT_ROOT = Path(__file__).resolve().parents[1]

#: 默认允许被自动对齐的字段（方案文档批次 2 步骤 2.1 只要求这一个）
DEFAULT_ALIGN_FIELDS = ("platform_shop_id",)

#: T1 报告里会列出的全部比对字段
T1_COMPARE_COLUMNS = (
    "platform_shop_id",
    "platform_shop_id_status",
    "store_name",
    "enabled",
    "business_role",
    "updated_by",
)

#: 判定「必须删除」的别名类别
DELETABLE_ALIAS_KINDS = ("self_alias", "self_and_cross", "cross_account_claim")

#: 允许出现在动态标识符里的字符（information_schema 取回的表名/列名）
SAFE_IDENTIFIER = set("abcdefghijklmnopqrstuvwxyz0123456789_")


# --------------------------------------------------------------------------- #
# 环境与连接（与批次 0 脚本同一套口径：先到先得、不覆盖）
# --------------------------------------------------------------------------- #
def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_env_files(project_root: Path) -> None:
    for name in (".env", ".env.local", ".env.collection.local"):
        _load_env_file(project_root / name)


def _engine_from_env(name: str):
    url = os.getenv(name)
    if not url:
        raise RuntimeError(f"{name} is not configured")
    return create_engine(url)


def describe_connection(url: str) -> dict[str, Any]:
    parsed = make_url(url)
    return {
        "driver": parsed.drivername,
        "host": parsed.host,
        "port": parsed.port,
        "database": parsed.database,
    }


def _fetch_all(
    engine, sql: str, params: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        return [
            dict(row) for row in conn.execute(text(sql), params or {}).mappings().all()
        ]


def _safe_identifier(name: str) -> str:
    lowered = name.lower()
    if not lowered or not set(lowered) <= SAFE_IDENTIFIER:
        raise ValueError(f"不安全的标识符: {name!r}")
    return lowered


# --------------------------------------------------------------------------- #
# 计划生成
# --------------------------------------------------------------------------- #
def build_account_plan(
    plan: dict[str, Any], align_fields: tuple[str, ...]
) -> list[dict[str, Any]]:
    """从 T1 结果里挑出需要改的行（默认只改 ``platform_shop_id``）。"""
    rows = (plan.get("T1") or {}).get("rows") or []
    updates: list[dict[str, Any]] = []
    for row in rows:
        if row.get("status") != "inconsistent":
            continue
        diff = set(row.get("diff_columns") or [])
        if not diff & set(align_fields):
            continue
        local = row.get("local") or {}
        cloud = row.get("cloud") or {}
        updates.append(
            {
                "shop_account_id": row.get("shop_account_id"),
                "platform": row.get("platform"),
                "changed_fields": sorted(diff & set(align_fields)),
                "reported_only_fields": sorted(diff - set(align_fields)),
                "before": {field: local.get(field) for field in align_fields},
                "after": {field: cloud.get(field) for field in align_fields},
                "local_snapshot": {
                    field: local.get(field) for field in T1_COMPARE_COLUMNS
                },
            }
        )
    return updates


def build_alias_plan(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """从 T2 结果里挑出要删的别名。"""
    side = (plan.get("T2") or {}).get("local") or {}
    candidates = side.get("delete_candidates") or []
    return [
        {
            "alias_id": item.get("alias_id"),
            "owner_shop_account_id": item.get("owner_shop_account_id"),
            "alias_value": item.get("alias_value"),
            "alias_normalized": item.get("alias_normalized"),
            "alias_kind": item.get("alias_kind"),
            "is_active": item.get("is_active"),
            "claimed_by": item.get("claimed_by"),
        }
        for item in candidates
        if item.get("alias_kind") in DELETABLE_ALIAS_KINDS
    ]


# --------------------------------------------------------------------------- #
# 历史行依赖检查
# --------------------------------------------------------------------------- #
def find_identity_columns(engine) -> list[tuple[str, str]]:
    """找出事实层里可能承载身份值的列（``b_class.fact_*`` 的 platform_shop_id / shop_id）。"""
    rows = _fetch_all(
        engine,
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'b_class'
          AND table_name LIKE 'fact_%'
          AND column_name IN ('platform_shop_id', 'shop_id')
        ORDER BY table_name, column_name
        """,
    )
    return [
        (_safe_identifier(r["table_name"]), _safe_identifier(r["column_name"]))
        for r in rows
    ]


def analyze_alias_usage(
    engine, alias_values: list[str]
) -> dict[str, dict[str, list[Any]]]:
    """分析每个别名值的**阻断性使用**与**提示性引用**。

    **阻断（不能删）**：该别名值是某个账号**唯一**的身份来源 —— 即该账号自己没有
    有效的 ``platform_shop_id``，而这条活跃别名是它仅存的映射。删了它，这个账号
    就再也没有任何身份锚点。

    **提示（可以删，但要留痕）**：事实行的 ``shop_id`` / ``platform_shop_id`` 列里
    出现了该值。按「历史不修」的边界，这些行是**历史事实**、归属早已固化，
    **不再查别名表**；且 20261112 之后语义层候选池的别名路明确**不认领平台编号**
    （``sql/semantic/shop_identity_resolution_candidates_v2_mv.sql:145-155``），
    因此删别名**不改变**任何历史行的解析结果 —— 这里只作为人工确认的依据列出，
    不阻断删除。

    ⚠ 早期版本把「事实行里值相同」当作阻断条件，会让该清的别名被历史值永久挡死
    （实测某自别名被 4000+ 行历史引用挡住，而它本来就该清）。边界按上面重划。
    """
    columns = find_identity_columns(engine)
    usage: dict[str, dict[str, list[Any]]] = {}
    for value in alias_values:
        normalized = (value or "").strip().lower()

        blocking_rows = _fetch_all(
            engine,
            """
            SELECT o.shop_account_id
            FROM core.shop_accounts o
            WHERE o.enabled IS TRUE
              AND o.business_role = 'operating_store'
              AND NULLIF(TRIM(COALESCE(o.platform_shop_id, '')), '') IS NULL
              AND EXISTS (
                  SELECT 1
                  FROM core.shop_account_aliases saa
                  WHERE saa.shop_account_id = o.id
                    AND saa.is_active IS TRUE
                    AND LOWER(NULLIF(TRIM(COALESCE(saa.alias_normalized, '')), '')) = :value
              )
            ORDER BY o.shop_account_id
            """,
            {"value": normalized},
        )

        fact_references: list[dict[str, Any]] = []
        for table, column in columns:
            rows = _fetch_all(
                engine,
                f'SELECT COUNT(*) AS n FROM b_class."{table}" '
                f"WHERE LOWER(NULLIF(TRIM(COALESCE(\"{column}\", '')), '')) = :value",
                {"value": normalized},
            )
            count = int(rows[0]["n"]) if rows else 0
            if count:
                fact_references.append(
                    {"table": f"b_class.{table}", "column": column, "rows": count}
                )

        usage[value] = {
            "blocking_accounts": [row["shop_account_id"] for row in blocking_rows],
            "fact_references": fact_references,
        }
    return usage


# --------------------------------------------------------------------------- #
# 快照与执行
# --------------------------------------------------------------------------- #
def take_snapshot(engine, snapshot_dir: Path, alias_ids: list[int]) -> Path:
    """把 ``core.shop_accounts`` 与待删别名行落盘（回滚依据）。"""
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    accounts = _fetch_all(
        engine,
        """
        SELECT id, shop_account_id, platform, platform_shop_id, platform_shop_id_status,
               store_name, enabled, business_role, updated_by, internal_code, shop_region
        FROM core.shop_accounts
        ORDER BY id
        """,
    )
    aliases: list[dict[str, Any]] = []
    if alias_ids:
        rows = _fetch_all(
            engine,
            """
            SELECT id, shop_account_id, platform, alias_value, alias_normalized,
                   alias_type, source, is_active, is_primary, shop_region, created_at
            FROM core.shop_account_aliases
            WHERE id = ANY(:ids)
            ORDER BY id
            """,
            {"ids": alias_ids},
        )
        aliases = rows
    path = snapshot_dir / f"shop_accounts_snapshot_{stamp}.json"
    path.write_text(
        json.dumps(
            {
                "taken_at": datetime.now(timezone.utc).isoformat(),
                "shop_accounts": accounts,
                "shop_account_aliases": aliases,
            },
            ensure_ascii=False,
            default=str,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def apply_account_updates(
    engine, updates: list[dict[str, Any]], updated_by: str
) -> int:
    """把 ``platform_shop_id`` 对齐到云端取值（单事务）。"""
    changed = 0
    with engine.begin() as conn:
        for item in updates:
            fields = item["changed_fields"]
            assignments = ", ".join(f'"{field}" = :{field}' for field in fields)
            params: dict[str, Any] = {
                field: item["after"].get(field) for field in fields
            }
            params["shop_account_id"] = item["shop_account_id"]
            params["updated_by"] = updated_by
            result = conn.execute(
                text(
                    f"UPDATE core.shop_accounts SET {assignments}, updated_by = :updated_by "
                    "WHERE shop_account_id = :shop_account_id"
                ),
                params,
            )
            changed += int(result.rowcount or 0)
    return changed


def delete_aliases(engine, alias_ids: list[int]) -> int:
    if not alias_ids:
        return 0
    with engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM core.shop_account_aliases WHERE id = ANY(:ids)"),
            {"ids": alias_ids},
        )
        return int(result.rowcount or 0)


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # pragma: no cover
        pass

    parser = argparse.ArgumentParser(description="批次 2：按对账结果对齐店铺身份主数据")
    parser.add_argument("--plan", required=True, help="批次 0 产出的对账 JSON")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="真正写库（不加这个只做 dry-run，不改任何数据）",
    )
    parser.add_argument(
        "--also",
        default="",
        help="除 platform_shop_id 外还要对齐的字段（逗号分隔），默认一个都不加",
    )
    parser.add_argument(
        "--snapshot-dir",
        default="output/snapshots",
        help="快照输出目录（默认 output/snapshots）",
    )
    parser.add_argument(
        "--updated-by",
        default="manual_fix_batch2",
        help="写入 updated_by 的值（默认 manual_fix_batch2，标记为人工修复）",
    )
    args = parser.parse_args()

    plan_path = Path(args.plan)
    if not plan_path.exists():
        print(f"[FAIL] 对账结果文件不存在: {plan_path}")
        return 2
    plan = json.loads(plan_path.read_text(encoding="utf-8"))

    align_fields = list(DEFAULT_ALIGN_FIELDS)
    for field in (f.strip() for f in args.also.split(",") if f.strip()):
        if field not in T1_COMPARE_COLUMNS:
            print(f"[FAIL] 未知字段 {field}；可选: {', '.join(T1_COMPARE_COLUMNS)}")
            return 2
        if field == "updated_by":
            print("[FAIL] updated_by 由脚本统一写入，不接受来自云端的对齐值")
            return 2
        if field not in align_fields:
            align_fields.append(field)

    load_env_files(PROJECT_ROOT)
    local_url = os.getenv("DATABASE_URL")
    if not local_url:
        print("[FAIL] DATABASE_URL is not configured")
        return 2

    account_updates = build_account_plan(plan, tuple(align_fields))
    alias_plan = build_alias_plan(plan)

    print(f"[INFO] 计划: 对齐字段 = {', '.join(align_fields)}")
    print(
        f"[INFO] T1 待对齐账号 = {len(account_updates)}；T2 待删别名 = {len(alias_plan)}"
    )

    engine = _engine_from_env("DATABASE_URL")
    try:
        blocked: list[dict[str, Any]] = []
        referenced: list[dict[str, Any]] = []
        if alias_plan:
            values = [str(item.get("alias_normalized") or "") for item in alias_plan]
            usage = analyze_alias_usage(engine, values)
            for item in alias_plan:
                info = usage.get(str(item.get("alias_normalized") or ""), {})
                blocking_accounts = info.get("blocking_accounts") or []
                fact_refs = info.get("fact_references") or []
                if blocking_accounts:
                    blocked.append({**item, "blocking_accounts": blocking_accounts})
                elif fact_refs:
                    referenced.append({**item, "fact_references": fact_refs})
            for item in blocked:
                print(
                    f"[BLOCK] 别名 {item['alias_id']} ({item['alias_normalized']}) "
                    f"是账号 {item['blocking_accounts']} 的唯一身份来源，不能删"
                )
            for item in referenced:
                total = sum(ref["rows"] for ref in item["fact_references"])
                print(
                    f"[INFO] 别名 {item['alias_id']} ({item['alias_normalized']}) "
                    f"出现在 {total} 行历史事实里 —— 按「历史不修」边界，"
                    f"这些行的归属早已固化、且语义层别名路不认领平台编号，"
                    f"删除不改变其解析结果；列此仅供人工确认"
                )
        deletable = [item for item in alias_plan if item not in blocked]

        if not args.apply:
            print("[DRY-RUN] 未加 --apply，以下只是计划，不写库：")
            for item in account_updates:
                print(
                    f"  UPDATE core.shop_accounts SET {item['changed_fields']} "
                    f"<-- 云端取值 WHERE shop_account_id = {item['shop_account_id']}"
                )
                if item["reported_only_fields"]:
                    print(f"      （仅报告不改: {item['reported_only_fields']}）")
            for item in deletable:
                print(
                    f"  DELETE FROM core.shop_account_aliases WHERE id = {item['alias_id']}"
                )
            if blocked:
                print(
                    f"[WARN] {len(blocked)} 条别名因「唯一身份来源」被挡下，需人工确认"
                )
            print(f"[INFO] 连接: {describe_connection(local_url)}")
            return 0

        snapshot_path = take_snapshot(
            engine,
            Path(args.snapshot_dir),
            [
                int(item["alias_id"])
                for item in deletable
                if item.get("alias_id") is not None
            ],
        )
        print(f"[INFO] 快照已保存: {snapshot_path}")

        changed = apply_account_updates(engine, account_updates, args.updated_by)
        removed = delete_aliases(
            engine,
            [
                int(item["alias_id"])
                for item in deletable
                if item.get("alias_id") is not None
            ],
        )
        print(f"[OK] 已更新账号 {changed} 条、删除别名 {removed} 条")
        if blocked:
            print(f"[WARN] {len(blocked)} 条别名因「唯一身份来源」被挡下，需人工确认")
        print("[NEXT] 请复跑批次 0 对账脚本确认 T1 已一致")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
