#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.models.database import AsyncSessionLocal
from backend.services.template_semantic_binding_backfill import (
    backfill_published_shopee_orders_template_bindings,
)


async def main() -> int:
    async with AsyncSessionLocal() as session:
        result = await backfill_published_shopee_orders_template_bindings(session)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
