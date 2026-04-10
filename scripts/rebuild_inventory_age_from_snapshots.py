from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.models.database import AsyncSessionLocal
from backend.services.data_pipeline.inventory_age_refresh_service import (
    InventoryAgeRefreshService,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Refresh snapshot-continuous inventory aging SQL targets."
    )
    parser.add_argument(
        "--full-rebuild",
        action="store_true",
        help="Replay all keys into persisted inventory age tables.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print the refresh targets in dependency order.",
    )
    return parser


async def _async_main(args: argparse.Namespace) -> int:
    service = InventoryAgeRefreshService(db=None)
    targets = service.build_refresh_targets()

    if args.dry_run:
        print("inventory_age_refresh_targets")
        for target in targets:
            print(target)
        return 0

    async with AsyncSessionLocal() as session:
        service = InventoryAgeRefreshService(db=session)
        result = await service.refresh(force_full=args.full_rebuild)
        await session.commit()
        print(f"inventory_age_refresh_result={result}")
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
