#!/usr/bin/env python3
"""基准售价体检（阶段 4 工具 4）：偏差校验 + 过期巡检。

默认是**干跑**：只打印体检结果，不写任何数据。这个脚本**不写库** ——
基准售价是运营自己填的，系统不替业务判断价格（方案 §6 的归属决策 Q6），
所以它的产出是一份**给运营看的清单**，不是一次自动修改。

它回答两个问题：

1. **哪些 SKU 的基准售价与历史成交价差得离谱？**
   （基准售价填错的最典型形态是「多打了一个零」）
2. **哪些 SKU 的基准售价太久没人确认了？**
   （确认日期超过 90 天 ⇒ 纪律线用的价格可能已经失真）

用法::

    python scripts/check_selling_price_deviation.py                      # 全部
    python scripts/check_selling_price_deviation.py --sku-id 751          # 只看一个
    python scripts/check_selling_price_deviation.py --no-deviation        # 只做过期巡检（快）
    python scripts/check_selling_price_deviation.py --json out.json       # 另存 JSON

⚠️ 偏差校验要扫订单事实表（语义视图里有店铺身份解析），**一次调用几十秒**；
   过期巡检是纯计算，瞬时返回。
⚠️ 「算不出历史成交价」的 SKU 会单独列在 ``unverified`` 里 ——
   **算不出来不等于没问题**，那些 SKU 需要人工看一眼。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.models.database import AsyncSessionLocal  # noqa: E402
from backend.services.product_selling_price_service import (  # noqa: E402
    assess_selling_price_deviation,
    compute_selling_price_age,
)
from backend.services.product_transaction_price_service import (  # noqa: E402
    load_transaction_price_bands,
)
from modules.core.db import DimErpSku  # noqa: E402
from sqlalchemy import select  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sku-id", type=int, default=None, help="只查某一个 SKU")
    parser.add_argument(
        "--no-deviation",
        action="store_true",
        help="跳过偏差校验（只做过期巡检，瞬时返回）",
    )
    parser.add_argument(
        "--json", dest="json_path", default=None, help="把结果另存为 JSON"
    )
    return parser.parse_args()


async def main() -> int:
    args = parse_args()

    async with AsyncSessionLocal() as session:
        statement = select(DimErpSku).where(
            DimErpSku.reference_selling_price.isnot(None)
        )
        if args.sku_id is not None:
            statement = statement.where(DimErpSku.sku_id == args.sku_id)
        rows = (
            (await session.execute(statement.order_by(DimErpSku.sku_key)))
            .scalars()
            .all()
        )

        bands = {}
        if not args.no_deviation and rows:
            bands = await load_transaction_price_bands(
                session, [row.sku_id for row in rows]
            )

        deviations: list[dict] = []
        stales: list[dict] = []
        unverified: list[dict] = []

        for row in rows:
            age_days, stale = compute_selling_price_age(row.selling_price_confirmed_at)
            if stale:
                stales.append(
                    {
                        "sku_id": row.sku_id,
                        "sku_key": row.sku_key,
                        "reference_selling_price": row.reference_selling_price,
                        "age_days": age_days,
                        "selling_price_confirmed_at": row.selling_price_confirmed_at,
                    }
                )
            band = bands.get(row.sku_id)
            verdict = assess_selling_price_deviation(
                row.reference_selling_price,
                band.get("median_price") if band else None,
            )
            item = {
                "sku_id": row.sku_id,
                "sku_key": row.sku_key,
                "reference_selling_price": row.reference_selling_price,
                "selling_price_source": row.selling_price_source,
                "median_transaction_price": (
                    float(band["median_price"]) if band else None
                ),
                "sample_size": band.get("sample_size") if band else None,
                "deviation_pct": verdict["deviation_pct"],
                "exceeds_threshold": verdict["exceeds_threshold"],
            }
            if not verdict["available"]:
                unverified.append({**item, "reason": verdict["reason"]})
            elif verdict["exceeds_threshold"]:
                deviations.append(item)

    report = {
        "checked": len(rows),
        "deviation_count": len(deviations),
        "stale_count": len(stales),
        "unverified_count": len(unverified),
        "deviations": deviations,
        "stale": stales,
        "unverified": unverified,
    }

    if args.json_path:
        Path(args.json_path).write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"[写出] {args.json_path}")
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))

    print(
        f"\n[小结] 检查 {report['checked']} 个有基准售价的 SKU："
        f"偏差超阈值 {report['deviation_count']} 个、"
        f"确认过期 {report['stale_count']} 个、"
        f"算不出历史成交价 {report['unverified_count']} 个。",
        file=sys.stderr,
    )
    if report["unverified_count"]:
        print(
            f"[提示] {report['unverified_count']} 个 SKU 算不出历史成交价"
            "（成交记录不足或没有别名映射）——**算不出不等于没问题**，需要人工看一眼。",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
