from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa


DEFAULT_DATABASE_URL = "postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp"


@dataclass(frozen=True)
class MainAccountRow:
    platform: str
    main_account_id: str
    main_account_name: str
    username: str


PLATFORM_HELPERS = {
    "miaoshou": {
        "open": "Open-PwcliMiaoshou",
        "save": "Save-PwcliMiaoshouState",
        "show": "Show-PwcliPaths -Platform miaoshou",
        "title": "妙手",
    },
    "shopee": {
        "open": "Open-PwcliShopee",
        "save": "Save-PwcliShopeeState",
        "show": "Show-PwcliPaths -Platform shopee",
        "title": "Shopee",
    },
    "tiktok": {
        "open": "Open-PwcliTiktok",
        "save": "Save-PwcliTiktokState",
        "show": "Show-PwcliPaths -Platform tiktok",
        "title": "TikTok",
    },
}


def database_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL).strip()


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", str(value or "").strip().lower())
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
    return cleaned or "account"


def work_tag(platform: str, account_id: str) -> str:
    return f"{slugify(platform)}-{slugify(account_id)}-inspect"


def quote_ps(value: str) -> str:
    return str(value or "").replace("'", "''")


def display_name(row: MainAccountRow) -> str:
    account_id = row.main_account_id.strip()
    main_name = row.main_account_name.strip()
    username = row.username.strip()
    if main_name and main_name != account_id:
        return main_name
    if username and username != account_id:
        return f"{account_id} ({username})"
    return account_id


def load_accounts() -> list[MainAccountRow]:
    query = sa.text(
        """
        select
            platform,
            main_account_id,
            coalesce(main_account_name, '') as main_account_name,
            coalesce(username, '') as username
        from core.main_accounts
        where enabled = true
        order by platform, main_account_id
        """
    )
    engine = sa.create_engine(database_url())
    with engine.connect() as conn:
        return [
            MainAccountRow(
                platform=str(row.platform or "").strip().lower(),
                main_account_id=str(row.main_account_id or "").strip(),
                main_account_name=str(row.main_account_name or "").strip(),
                username=str(row.username or "").strip(),
            )
            for row in conn.execute(query)
        ]


def build_inspection_accounts(rows: list[MainAccountRow]) -> tuple[list[dict[str, Any]], list[str]]:
    accounts: list[dict[str, Any]] = []
    skipped: list[str] = []
    for row in rows:
        if row.platform not in PLATFORM_HELPERS:
            skipped.append(f"{row.platform}:{row.main_account_id}")
            continue
        accounts.append(
            {
                "platform": row.platform,
                "display_name": display_name(row),
                "account_id": row.main_account_id,
                "work_tag": work_tag(row.platform, row.main_account_id),
            }
        )
    return accounts, skipped
