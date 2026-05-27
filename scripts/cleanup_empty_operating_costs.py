#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
清理 a_class.operating_costs 中的空壳记录。

默认 dry-run，只打印命中的记录与数量。
使用 --execute 才会实际删除。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import MetaData, Table, create_engine, delete, select

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from backend.utils.config import get_settings


def safe_print(message: str) -> None:
    try:
        print(message, flush=True)
    except UnicodeEncodeError:
        print(message.encode("gbk", errors="ignore").decode("gbk"), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Cleanup empty operating_costs rows")
    parser.add_argument("--execute", action="store_true", help="Delete matched rows")
    args = parser.parse_args()

    engine = create_engine(get_settings().DATABASE_URL, pool_pre_ping=True)
    metadata = MetaData()
    operating_costs = Table(
        "operating_costs",
        metadata,
        schema="a_class",
        autoload_with=engine,
    )

    with engine.begin() as conn:
        raw_rows = conn.execute(select(operating_costs)).mappings().all()
        rows = [
            {
                "id": row.get("id"),
                "platform_code": row.get("platform_code"),
                "shop_id": row.get("店铺ID"),
                "year_month": row.get("年月"),
                "total_cost": row.get("成本合计"),
            }
            for row in raw_rows
            if row.get("店铺ID") is None
            and row.get("年月") is None
            and row.get("租金") is None
            and row.get("营销费用") is None
            and row.get("水电费") is None
            and row.get("AI Token费用") is None
            and row.get("其他成本") is None
            and row.get("成本合计") is None
            and row.get("备注") is None
            and row.get("附件") is None
            and row.get("是否锁定") is None
        ]
        safe_print(f"[INFO] Matched empty operating_costs rows: {len(rows)}")
        for row in rows:
            safe_print(str(row))

        if not args.execute:
            safe_print("[DRY-RUN] No rows deleted. Re-run with --execute to apply cleanup.")
            return 0

        if rows:
            ids = [row["id"] for row in rows]
            conn.execute(
                delete(operating_costs).where(operating_costs.c.id.in_(ids))
            )
            safe_print(f"[OK] Deleted rows: {len(ids)}")
        else:
            safe_print("[OK] No rows needed cleanup.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
