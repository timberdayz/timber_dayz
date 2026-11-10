#!/usr/bin/env python3
"""店铺身份只读对账（批次 0）。

同时连接「本地库」与「云端库」，输出四张对比表：

- **T1 登记信息逐条比对** —— ``core.shop_accounts`` 两边按 ``shop_account_id``（业务键，
  跨库唯一）对齐，比对 ``platform_shop_id`` / ``platform_shop_id_status`` / ``store_name``
  / ``enabled`` / ``business_role`` / ``updated_by``。
- **T2 错别名清单** —— ``core.shop_account_aliases`` 中
  ``alias_type='former_platform_shop_id'`` 的全量，按**官方候选池口径**
  （``sql/semantic/shop_identity_resolution_candidates_v2_mv.sql:148-155``）标注
  「自别名 / 跨账号认领 / 无人认领」。T2 直接产出批次 2 的删除清单。
- **T3 双认领检查** —— 同一 ``(platform, identity_value)`` 指向 >1 个账号的清单。
  ``identity_value`` = 账号自己的 ``platform_shop_id`` ∪ 活跃别名的 ``alias_normalized``。
- **T4 探测记录近 N 天分布** —— ``core.platform_shop_discoveries`` 按 status / created_at
  分布，并统计近 N 天**新增**的 ``former_platform_shop_id`` 别名数
  （「把正确编号降级为别名」的写入是否已绝迹的关键指标）。

只读保证：本脚本**只执行 SELECT**，不做任何写入；连接串一律从 ``.env`` 读取（无硬编码），
输出里的连接串摘要一律脱敏。

用法::

    python scripts/verify_shop_identity_reconciliation.py
    python scripts/verify_shop_identity_reconciliation.py --sections T1,T2 --days 30
    python scripts/verify_shop_identity_reconciliation.py --output output/reconciliation.json

退出码：``0`` 正常产出、``2`` 执行失败（连不上库 / 缺表缺列）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

PROJECT_ROOT = Path(__file__).resolve().parents[1]

#: T1 逐条比对的列（任一列取值不同即算「不一致」）
T1_COMPARE_COLUMNS: tuple[str, ...] = (
    "platform_shop_id",
    "platform_shop_id_status",
    "store_name",
    "enabled",
    "business_role",
    "updated_by",
)

#: 三个目标表的期望列（用于 schema 自检；列名以 current 迁移链为准）
EXPECTED_COLUMNS: dict[str, tuple[str, ...]] = {
    "core.shop_accounts": (
        "shop_account_id",
        "platform",
        "platform_shop_id",
        "platform_shop_id_status",
        "store_name",
        "enabled",
        "business_role",
        "updated_by",
    ),
    "core.shop_account_aliases": (
        "shop_account_id",
        "platform",
        "alias_value",
        "alias_normalized",
        "alias_type",
        "source",
        "is_active",
        "is_primary",
    ),
    "core.platform_shop_discoveries": (
        "platform",
        "main_account_id",
        "detected_platform_shop_id",
        "candidate_shop_account_ids",
        "status",
        "created_at",
    ),
}

ALL_SECTIONS = ("schema", "T1", "T2", "T3", "T4")


# --------------------------------------------------------------------------- #
# 环境与连接
# --------------------------------------------------------------------------- #
def _load_env_file(path: Path) -> None:
    """把 env 文件里的键值灌进 ``os.environ``（**先到先得，不覆盖**）。

    为什么不用 ``backend.utils.project_env.load_project_env``：它的默认 ``override=True``
    会让 ``.env.local`` 覆盖 ``.env``，而本机 ``.env.local`` 里的
    ``CLOUD_DATABASE_URL=`` 是**空值** ⇒ 云端连接串会被覆盖成空。
    这里用 ``setdefault`` 语义，``.env`` 优先。
    """
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_env_files(project_root: Path) -> list[str]:
    """按 ``.env`` → ``.env.local`` → ``.env.collection.local`` 顺序加载（先到先得）。"""
    loaded: list[str] = []
    for name in (".env", ".env.local", ".env.collection.local"):
        path = project_root / name
        if path.exists():
            _load_env_file(path)
            loaded.append(name)
    return loaded


def _engine_from_env(name: str):
    url = os.getenv(name)
    if not url:
        raise RuntimeError(f"{name} is not configured")
    return create_engine(url)


def describe_connection(url: str) -> dict[str, Any]:
    """连接串的**脱敏**摘要（不含用户名与口令）。"""
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


# --------------------------------------------------------------------------- #
# schema 自检
# --------------------------------------------------------------------------- #
def check_schema(engine) -> dict[str, Any]:
    """确认三张目标表存在且关键列齐全，同时取当前 schema 版本戳。"""
    tables = _fetch_all(
        engine,
        """
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE (table_schema, table_name) IN (
            ('core', 'shop_accounts'),
            ('core', 'shop_account_aliases'),
            ('core', 'platform_shop_discoveries')
        )
        """,
    )
    present = {f"{row['table_schema']}.{row['table_name']}" for row in tables}

    columns: dict[str, list[str]] = {}
    for full_name in EXPECTED_COLUMNS:
        schema, table = full_name.split(".", 1)
        rows = _fetch_all(
            engine,
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = :schema AND table_name = :table
            """,
            {"schema": schema, "table": table},
        )
        columns[full_name] = sorted(row["column_name"] for row in rows)

    missing_tables = sorted(set(EXPECTED_COLUMNS) - present)
    missing_columns: dict[str, list[str]] = {}
    for full_name, expected in EXPECTED_COLUMNS.items():
        gap = sorted(set(expected) - set(columns.get(full_name, [])))
        if gap:
            missing_columns[full_name] = gap

    revisions: list[str] = []
    for row in _fetch_all(
        engine,
        """
        SELECT table_schema
        FROM information_schema.tables
        WHERE table_name = 'alembic_version'
        ORDER BY table_schema
        """,
    ):
        schema = row["table_schema"]
        revisions.extend(
            item["version_num"]
            for item in _fetch_all(
                engine, f'SELECT version_num FROM "{schema}".alembic_version'
            )
        )

    return {
        "missing_tables": missing_tables,
        "missing_columns": missing_columns,
        "schema_revisions": sorted(revisions),
        "ok": not missing_tables and not missing_columns,
    }


# --------------------------------------------------------------------------- #
# T1 —— 登记信息逐条比对
# --------------------------------------------------------------------------- #
def fetch_accounts(engine) -> list[dict[str, Any]]:
    return _fetch_all(
        engine,
        """
        SELECT shop_account_id,
               platform,
               platform_shop_id,
               platform_shop_id_status,
               store_name,
               enabled,
               business_role,
               updated_by,
               internal_code,
               shop_region
        FROM core.shop_accounts
        ORDER BY shop_account_id
        """,
    )


def _account_key(row: dict[str, Any]) -> str:
    return str(row.get("shop_account_id") or "")


def compare_t1(
    local_rows: list[dict[str, Any]], cloud_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    local_map = {_account_key(r): r for r in local_rows}
    cloud_map = {_account_key(r): r for r in cloud_rows}
    keys = sorted(set(local_map) | set(cloud_map))

    rows: list[dict[str, Any]] = []
    consistent = 0
    for key in keys:
        local = local_map.get(key)
        cloud = cloud_map.get(key)
        if local is None:
            status = "missing_local"
        elif cloud is None:
            status = "missing_cloud"
        else:
            diff = [
                col
                for col in T1_COMPARE_COLUMNS
                if _normalize_value(local.get(col)) != _normalize_value(cloud.get(col))
            ]
            status = "consistent" if not diff else "inconsistent"
            if not diff:
                consistent += 1
        rows.append(
            {
                "shop_account_id": key,
                "platform": (local or cloud or {}).get("platform"),
                "status": status,
                "diff_columns": [
                    col
                    for col in T1_COMPARE_COLUMNS
                    if local is not None
                    and cloud is not None
                    and _normalize_value(local.get(col))
                    != _normalize_value(cloud.get(col))
                ],
                "local": {col: (local or {}).get(col) for col in T1_COMPARE_COLUMNS},
                "cloud": {col: (cloud or {}).get(col) for col in T1_COMPARE_COLUMNS},
            }
        )

    inconsistent = sum(1 for r in rows if r["status"] == "inconsistent")
    return {
        "compared": len(keys),
        "consistent": consistent,
        "inconsistent": inconsistent,
        "missing_local": sum(1 for r in rows if r["status"] == "missing_local"),
        "missing_cloud": sum(1 for r in rows if r["status"] == "missing_cloud"),
        "compare_columns": list(T1_COMPARE_COLUMNS),
        "rows": rows,
    }


def _normalize_value(value: Any) -> Any:
    """比对用的取值归一化（None / 空串 / 布尔 的口径统一）。"""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip()
    return value


# --------------------------------------------------------------------------- #
# T2 —— 错别名清单
# --------------------------------------------------------------------------- #
def fetch_aliases(engine) -> list[dict[str, Any]]:
    """取 ``alias_type='former_platform_shop_id'`` 全量，并算出「谁认领了这个值」。

    认领判定与官方候选池一致（``shop_identity_resolution_candidates_v2_mv.sql:148-155``）：
    只有 ``enabled IS TRUE AND business_role='operating_store'`` 的账号才算认领方，
    且比较的是 ``LOWER(NULLIF(TRIM(platform_shop_id), ''))`` 对
    ``LOWER(TRIM(alias_normalized))``。
    """
    return _fetch_all(
        engine,
        """
        SELECT saa.id AS alias_id,
               saa.shop_account_id AS owner_pk,
               s.shop_account_id AS owner_shop_account_id,
               s.platform AS owner_platform,
               s.enabled AS owner_enabled,
               s.business_role AS owner_business_role,
               saa.platform AS alias_platform,
               saa.alias_value,
               saa.alias_normalized,
               saa.alias_type,
               saa.source,
               saa.is_active,
               saa.is_primary,
               saa.shop_region,
               saa.created_at,
               (
                   SELECT STRING_AGG(o.shop_account_id, ',' ORDER BY o.shop_account_id)
                   FROM core.shop_accounts o
                   WHERE o.enabled IS TRUE
                     AND o.business_role = 'operating_store'
                     AND LOWER(NULLIF(TRIM(COALESCE(o.platform_shop_id, '')), ''))
                         = LOWER(NULLIF(TRIM(COALESCE(saa.alias_normalized, '')), ''))
               ) AS claimed_by_accounts
        FROM core.shop_account_aliases saa
        JOIN core.shop_accounts s ON s.id = saa.shop_account_id
        WHERE saa.alias_type = 'former_platform_shop_id'
        ORDER BY saa.platform, saa.alias_normalized, saa.id
        """,
    )


def classify_aliases(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """把 T2 分成三类：自别名 / 跨账号认领 / 无人认领。

    - **自别名**：别名值 == 拥有者**自己**当前的 ``platform_shop_id``。
      这是污染的直接形态 —— 同一个账号既认领这个编号、又把该编号存成了别名。
    - **跨账号认领**：别名值 == **别的**账号的 ``platform_shop_id``。
      会让同一串身份值指向两个账号 ⇒ 候选数=2 ⇒ 整行落 unknown。
    - **无人认领**：没有账号认领这个值（可能是正常保留的旧编号）。
    """
    classified: list[dict[str, Any]] = []
    for row in rows:
        claimed = [x for x in (row.get("claimed_by_accounts") or "").split(",") if x]
        owner = str(row.get("owner_shop_account_id") or "")
        is_self = owner in claimed
        is_cross = any(actor != owner for actor in claimed)
        if is_self and is_cross:
            kind = "self_and_cross"
        elif is_self:
            kind = "self_alias"
        elif is_cross:
            kind = "cross_account_claim"
        else:
            kind = "unclaimed"
        classified.append({**row, "alias_kind": kind, "claimed_by": claimed})

    counts: dict[str, int] = {}
    for item in classified:
        counts[item["alias_kind"]] = counts.get(item["alias_kind"], 0) + 1
    return {
        "total": len(classified),
        "kind_counts": counts,
        "delete_candidates": [
            {
                "alias_id": item["alias_id"],
                "owner_shop_account_id": item["owner_shop_account_id"],
                "alias_value": item["alias_value"],
                "alias_normalized": item["alias_normalized"],
                "alias_kind": item["alias_kind"],
                "is_active": item["is_active"],
                "claimed_by": item["claimed_by"],
            }
            for item in classified
            if item["alias_kind"]
            in ("self_alias", "self_and_cross", "cross_account_claim")
        ],
        "rows": classified,
    }


# --------------------------------------------------------------------------- #
# T3 —— 双认领检查
# --------------------------------------------------------------------------- #
def fetch_double_claims(engine) -> list[dict[str, Any]]:
    return _fetch_all(
        engine,
        """
        WITH identity AS (
            SELECT s.platform,
                   LOWER(NULLIF(TRIM(COALESCE(s.platform_shop_id, '')), '')) AS identity_value,
                   s.shop_account_id,
                   'platform_shop_id'::varchar AS source
            FROM core.shop_accounts s
            WHERE s.business_role = 'operating_store'
              AND s.enabled IS TRUE
              AND NULLIF(TRIM(COALESCE(s.platform_shop_id, '')), '') IS NOT NULL
            UNION ALL
            SELECT saa.platform,
                   LOWER(NULLIF(TRIM(COALESCE(saa.alias_normalized, '')), '')),
                   s.shop_account_id,
                   'alias'::varchar AS source
            FROM core.shop_account_aliases saa
            JOIN core.shop_accounts s ON s.id = saa.shop_account_id
            WHERE saa.is_active IS TRUE
              AND s.business_role = 'operating_store'
              AND s.enabled IS TRUE
              AND NULLIF(TRIM(COALESCE(saa.alias_normalized, '')), '') IS NOT NULL
        )
        SELECT platform,
               identity_value,
               COUNT(DISTINCT shop_account_id) AS account_count,
               STRING_AGG(DISTINCT shop_account_id, ',' ORDER BY shop_account_id) AS accounts,
               STRING_AGG(DISTINCT source, ',' ORDER BY source) AS sources
        FROM identity
        GROUP BY platform, identity_value
        HAVING COUNT(DISTINCT shop_account_id) > 1
        ORDER BY platform, identity_value
        """,
    )


# --------------------------------------------------------------------------- #
# T4 —— 探测记录近 N 天分布
# --------------------------------------------------------------------------- #
def fetch_discovery_distribution(engine, since: datetime) -> list[dict[str, Any]]:
    return _fetch_all(
        engine,
        """
        SELECT status,
               date_trunc('day', created_at) AS day,
               COUNT(*) AS row_count
        FROM core.platform_shop_discoveries
        WHERE created_at >= :since
        GROUP BY status, date_trunc('day', created_at)
        ORDER BY day, status
        """,
        {"since": since},
    )


def fetch_recent_discoveries(
    engine, since: datetime, limit: int = 20
) -> list[dict[str, Any]]:
    return _fetch_all(
        engine,
        """
        SELECT id,
               platform,
               main_account_id,
               detected_store_name,
               detected_platform_shop_id,
               detected_region,
               candidate_shop_account_ids,
               status,
               created_at
        FROM core.platform_shop_discoveries
        WHERE created_at >= :since
        ORDER BY created_at DESC
        LIMIT :limit
        """,
        {"since": since, "limit": limit},
    )


def fetch_recent_alias_writes(engine, since: datetime) -> dict[str, Any]:
    """近 N 天**新增**的 former_platform_shop_id 别名（污染是否已绝迹的关键指标）。"""
    rows = _fetch_all(
        engine,
        """
        SELECT COUNT(*) AS row_count,
               MIN(created_at) AS earliest,
               MAX(created_at) AS latest
        FROM core.shop_account_aliases
        WHERE alias_type = 'former_platform_shop_id'
          AND created_at >= :since
        """,
        {"since": since},
    )
    return rows[0] if rows else {"row_count": 0, "earliest": None, "latest": None}


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def reconcile(days: int, sections: tuple[str, ...]) -> dict[str, Any]:
    local_url = os.getenv("DATABASE_URL")
    cloud_url = os.getenv("CLOUD_DATABASE_URL")
    if not local_url:
        raise RuntimeError("DATABASE_URL is not configured")
    if not cloud_url:
        raise RuntimeError("CLOUD_DATABASE_URL is not configured")

    local_engine = _engine_from_env("DATABASE_URL")
    cloud_engine = _engine_from_env("CLOUD_DATABASE_URL")
    since = datetime.now(timezone.utc) - timedelta(days=days)

    result: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "days_window": days,
        "sections": list(sections),
        "connections": {
            "local": describe_connection(local_url),
            "cloud": describe_connection(cloud_url),
        },
    }

    try:
        if "schema" in sections:
            result["schema"] = {
                "local": check_schema(local_engine),
                "cloud": check_schema(cloud_engine),
            }

        if "T1" in sections:
            local_accounts = fetch_accounts(local_engine)
            cloud_accounts = fetch_accounts(cloud_engine)
            t1 = compare_t1(local_accounts, cloud_accounts)
            t1["local_row_count"] = len(local_accounts)
            t1["cloud_row_count"] = len(cloud_accounts)
            result["T1"] = t1

        if "T2" in sections:
            result["T2"] = {
                "local": classify_aliases(fetch_aliases(local_engine)),
                "cloud": classify_aliases(fetch_aliases(cloud_engine)),
            }

        if "T3" in sections:
            result["T3"] = {
                "local": fetch_double_claims(local_engine),
                "cloud": fetch_double_claims(cloud_engine),
            }

        if "T4" in sections:
            result["T4"] = {
                "local": {
                    "distribution": fetch_discovery_distribution(local_engine, since),
                    "recent_alias_writes": fetch_recent_alias_writes(
                        local_engine, since
                    ),
                    "recent_discoveries": fetch_recent_discoveries(local_engine, since),
                },
                "cloud": {
                    "distribution": fetch_discovery_distribution(cloud_engine, since),
                    "recent_alias_writes": fetch_recent_alias_writes(
                        cloud_engine, since
                    ),
                    "recent_discoveries": fetch_recent_discoveries(cloud_engine, since),
                },
            }
    finally:
        local_engine.dispose()
        cloud_engine.dispose()

    result["summary"] = _summarize(result)
    return result


def _summarize(result: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    t1 = result.get("T1")
    if t1:
        summary["T1_inconsistent"] = t1["inconsistent"]
        summary["T1_missing_local"] = t1["missing_local"]
        summary["T1_missing_cloud"] = t1["missing_cloud"]
    t2 = result.get("T2")
    if t2:
        summary["T2_local_kinds"] = t2["local"]["kind_counts"]
        summary["T2_cloud_kinds"] = t2["cloud"]["kind_counts"]
    t3 = result.get("T3")
    if t3:
        summary["T3_local_double_claims"] = len(t3["local"])
        summary["T3_cloud_double_claims"] = len(t3["cloud"])
    t4 = result.get("T4")
    if t4:
        summary["T4_local_recent_alias_writes"] = t4["local"]["recent_alias_writes"][
            "row_count"
        ]
        summary["T4_cloud_recent_alias_writes"] = t4["cloud"]["recent_alias_writes"][
            "row_count"
        ]
    schema = result.get("schema")
    if schema:
        summary["schema_local_ok"] = schema["local"]["ok"]
        summary["schema_cloud_ok"] = schema["cloud"]["ok"]
    return summary


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # pragma: no cover
        pass

    parser = argparse.ArgumentParser(description="店铺身份只读对账（本地库 vs 云端库）")
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="T4 的时间窗口天数（默认 30）",
    )
    parser.add_argument(
        "--sections",
        default="all",
        help=f"要执行的段落，逗号分隔，可选：{','.join(ALL_SECTIONS)}（默认 all）",
    )
    parser.add_argument(
        "--output",
        default="",
        help="把 JSON 结果写到该文件（默认打印到 stdout）",
    )
    args = parser.parse_args()

    if args.sections.strip().lower() == "all":
        sections = ALL_SECTIONS
    else:
        sections = tuple(s.strip() for s in args.sections.split(",") if s.strip())
        unknown = [s for s in sections if s not in ALL_SECTIONS]
        if unknown:
            print(
                f"[FAIL] 未知段落: {', '.join(unknown)}；可选：{', '.join(ALL_SECTIONS)}"
            )
            return 2

    load_env_files(PROJECT_ROOT)

    try:
        result = reconcile(days=args.days, sections=sections)
    except Exception as exc:  # noqa: BLE001 - CLI 边界：任何失败都要可读
        print(f"[FAIL] 对账失败: {type(exc).__name__}: {exc}")
        return 2

    payload = json.dumps(result, ensure_ascii=False, default=str, indent=2)
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(payload + "\n", encoding="utf-8")
        print(f"[OK] 对账结果已写入 {out_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
