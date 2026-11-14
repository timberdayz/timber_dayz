"""语义契约**影响面**查询（只读）。

为什么需要这个脚本
------------------
「改了某个语义字段，会影响谁？」这个问题在本仓库里**没有任何看板**能回答：
``core.semantic_field_contracts`` 是登记表，但全仓**没有任何**查询它的接口
（``semantic_field_contract_service`` 只按 consumer 过滤供**判定链**读，
判定链从不传 ``business_overview`` 以外的 consumer）。

⇒ 这个脚本就是那条**只读**的查询手段：按域 / 语义键 / consumer 查影响面。

用法
----
::

    python scripts/query_semantic_contract_impact.py
    python scripts/query_semantic_contract_impact.py --data-domain inventory
    python scripts/query_semantic_contract_impact.py --data-domain inventory --semantic-key platform_sku
    python scripts/query_semantic_contract_impact.py --consumer low_stock_alert

⚠️ **只读**：本脚本只发 SELECT，不写任何表。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text  # noqa: E402

from backend.models.database import AsyncSessionLocal  # noqa: E402


_QUERY = """
SELECT
    c.data_domain,
    c.consumer,
    c.semantic_key,
    c.importance,
    c.enabled,
    COALESCE(c.platform, '(通用)')       AS platform,
    COALESCE(c.granularity, '(全部)')      AS granularity,
    COALESCE(c.sub_domain, '(全部)')       AS sub_domain,
    COALESCE(c.impact_description, '')     AS impact_description
FROM core.semantic_field_contracts c
WHERE (CAST(:data_domain AS VARCHAR) IS NULL OR c.data_domain = CAST(:data_domain AS VARCHAR))
  AND (CAST(:consumer AS VARCHAR) IS NULL OR c.consumer = CAST(:consumer AS VARCHAR))
  AND (CAST(:semantic_key AS VARCHAR) IS NULL OR c.semantic_key = CAST(:semantic_key AS VARCHAR))
ORDER BY c.data_domain, c.consumer, c.semantic_key
"""


async def _fetch(args: argparse.Namespace) -> list[dict]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text(_QUERY),
            {
                "data_domain": args.data_domain,
                "consumer": args.consumer,
                "semantic_key": args.semantic_key,
            },
        )
        return [dict(row) for row in result.mappings().all()]


def _print(rows: list[dict]) -> int:
    if not rows:
        print("没有匹配的契约行。")
        return 0

    consumers = sorted({row["consumer"] for row in rows})
    domains = sorted({row["data_domain"] for row in rows})
    print(
        "数据域：{0}\n消费方（{1}）：{2}\n契约行：{3}\n".format(
            ", ".join(domains),
            len(consumers),
            ", ".join(consumers),
            len(rows),
        )
    )

    current_domain = None
    for row in rows:
        if row["data_domain"] != current_domain:
            current_domain = row["data_domain"]
            print("── 数据域 {0} ──".format(current_domain))
        line = "  [{consumer}] {key}（{importance}）".format(
            consumer=row["consumer"],
            key=row["semantic_key"],
            importance=row["importance"],
        )
        if not row["enabled"]:
            line += "（已停用）"
        print(line)
        if row["impact_description"]:
            print("      {0}".format(row["impact_description"]))
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="查询语义契约的影响面（只读）",
    )
    parser.add_argument("--data-domain", default=None, help="数据域，如 inventory")
    parser.add_argument("--consumer", default=None, help="消费方，如 low_stock_alert")
    parser.add_argument("--semantic-key", default=None, help="语义键，如 platform_sku")
    args = parser.parse_args()

    if not os.getenv("DATABASE_URL"):
        print("提示：未设置 DATABASE_URL，将使用项目默认配置连接。")
    rows = asyncio.run(_fetch(args))
    _print(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
