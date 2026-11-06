#!/usr/bin/env python3
"""把存量经营档案的「广告分成率」反解成「目标 ROI」（阶段 3）。

默认是**干跑**：只打印将要做什么，不写库。必须显式传 ``--apply`` 才会写。

业务逻辑在服务层 ``backend/services/product_target_roi_backfill_service.py``
（复用页面同一个利润试算函数，保证反解出来的数与运营在页面上看到的一致），
本脚本只做 CLI 包装。

用法::

    python scripts/migrate_legacy_ad_rate_to_target_roi.py            # 干跑
    python scripts/migrate_legacy_ad_rate_to_target_roi.py --apply    # 写库

写库前会逐行**自证等价**：用回算后的 target_roi 再算一遍利润，
与老口径的广告费/利润逐一对比；差超过 1 分就跳过这一行。
幂等：只动 ``target_roi IS NULL`` 的行，跑两遍结果一样。
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
from backend.services.product_target_roi_backfill_service import (  # noqa: E402
    backfill_target_roi_from_legacy_ad_rate,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="真正写库（默认只干跑：只打印将要做什么）",
    )
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    async with AsyncSessionLocal() as session:
        report = await backfill_target_roi_from_legacy_ad_rate(
            session, dry_run=not args.apply
        )
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    if report["skipped"]:
        print(
            f"[提示] {len(report['skipped'])} 行被跳过（原因见 skipped 列表）；"
            "这些行的广告费用仍按老口径计算，不会凭空消失。",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
