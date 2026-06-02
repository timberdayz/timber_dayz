#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Verify and optionally repair system role integrity."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.models.database import AsyncSessionLocal
from backend.services.rbac_service import parse_permission_ids
from backend.services.system_role_service import DEFAULT_SYSTEM_ROLES, ensure_system_roles
from modules.core.db import DimRole


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify system role permissions and metadata")
    parser.add_argument(
        "--repair",
        action="store_true",
        help="Repair empty system role permissions before verification.",
    )
    return parser


def _is_missing_permissions(value: Any) -> bool:
    if value in (None, "", "[]", "null", "None"):
        return True
    return len(parse_permission_ids(value)) == 0


async def _async_main(repair: bool) -> int:
    async with AsyncSessionLocal() as db:
        repaired = []
        if repair:
            repaired = await ensure_system_roles(db)

        result = await db.execute(
            select(DimRole).where(DimRole.role_code.in_(list(DEFAULT_SYSTEM_ROLES.keys())))
        )
        roles = {role.role_code: role for role in result.scalars().all()}

        missing_roles = [role_code for role_code in DEFAULT_SYSTEM_ROLES if role_code not in roles]
        empty_permission_roles = [
            role_code
            for role_code, role in roles.items()
            if _is_missing_permissions(getattr(role, "permissions", None))
        ]

        if missing_roles or empty_permission_roles:
            print("system_role_integrity=failed")
            print(f"missing_roles={missing_roles}")
            print(f"empty_permission_roles={empty_permission_roles}")
            return 1

        print("system_role_integrity=ok")
        if repaired:
            print(f"repaired_roles={repaired}")
        else:
            print("repaired_roles=[]")
        return 0


def main() -> int:
    args = build_parser().parse_args()
    return asyncio.run(_async_main(args.repair))


if __name__ == "__main__":
    raise SystemExit(main())
