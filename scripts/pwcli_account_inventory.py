from __future__ import annotations

import hashlib
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
    """把账号标识转成可安全用于路径与 session 名的短标签。

    非 ASCII 字符（中文账号名）必须保留或参与哈希，否则不同账号会塌成同一个
    slug，导致巡店窗口互相踢、storage_state 互相覆盖（见 spec D9）。
    """
    text = str(value or "").strip().lower()
    if not text:
        return "account"

    ascii_part = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    non_ascii = "".join(ch for ch in text if ord(ch) > 127)

    if not ascii_part:
        # 纯中文账号名：用稳定短哈希区分，避免全部塌成 "account"
        digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
        return f"cn-{digest}"

    if non_ascii:
        digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
        return f"{ascii_part}-{digest}"

    return ascii_part


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


def _cli_work_tag(platform: str, account_id: str) -> int:
    """按账号推导 work tag。

    单独做成 CLI，是为了让 PowerShell 侧（``scripts/pwcli_helpers.ps1`` 的
    ``Resolve-PwcliWorkTag``）拿到**同一个** work tag ——
    规则只此一份，不在两边各实现一遍。

    两边各写一遍迟早会不一致：一旦不一致，同一个账号在「网页面板」和
    「手工命令」下会落到不同的 session 名与工作目录（spec D9）。
    """
    print(work_tag(platform, account_id))
    return 0


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="pwcli_account_inventory",
        description="巡店账号清单工具；work-tag 子命令不访问数据库。",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    tag_parser = sub.add_parser("work-tag", help="打印指定账号的 work tag")
    tag_parser.add_argument("--platform", required=True)
    tag_parser.add_argument("--account-id", required=True)

    args = parser.parse_args(argv)
    if args.command == "work-tag":
        return _cli_work_tag(args.platform, args.account_id)
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
