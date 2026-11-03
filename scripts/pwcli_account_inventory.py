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
    #: 账号级代理（来自 core.shop_accounts.extra_config["proxy"]）
    proxy_enabled: bool = False
    proxy_server: str = ""
    proxy_username: str = ""
    proxy_password: str = ""


PLATFORM_HELPERS = {
    "miaoshou": {
        "open": "Open-PwcliMiaoshou",
        "show": "Show-PwcliPaths -Platform miaoshou",
        "title": "妙手",
    },
    "shopee": {
        "open": "Open-PwcliShopee",
        "show": "Show-PwcliPaths -Platform shopee",
        "title": "Shopee",
    },
    "tiktok": {
        "open": "Open-PwcliTiktok",
        "show": "Show-PwcliPaths -Platform tiktok",
        "title": "TikTok",
    },
}

#: 账号清单 SQL。
#:
#: 代理在 ``core.shop_accounts.extra_config["proxy"]``，而巡店账号的主表是
#: ``core.main_accounts``（没有 proxy 字段）-> 必须 LEFT JOIN 店铺账号表。
#: 一个主账号可能挂多个店铺账号，这里取**第一个启用的、带代理配置的店铺账号**
#: （按 id 排序，保证结果确定）。
ACCOUNT_QUERY = """
select
    m.platform,
    m.main_account_id,
    coalesce(m.main_account_name, '') as main_account_name,
    coalesce(m.username, '') as username,
    s.extra_config as shop_extra_config
from core.main_accounts m
left join lateral (
    select sa.extra_config
    from core.shop_accounts sa
    where sa.main_account_id = m.main_account_id
      and sa.platform = m.platform
      and sa.enabled = true
      and sa.extra_config is not null
      and sa.extra_config -> 'proxy' is not null
    order by sa.id
    limit 1
) s on true
where m.enabled = true
order by m.platform, m.main_account_id
"""


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


def extract_proxy_fields(extra_config: Any) -> dict[str, Any]:
    """解析店铺账号的代理字段（规则只有一份，见 backend/services/account_proxy_config.py）。"""
    from backend.services.account_proxy_config import extract_proxy_config

    return extract_proxy_config(extra_config)


def account_proxy_config(row: MainAccountRow) -> dict[str, str] | None:
    """账号级代理的 Playwright 形态；没配可用代理返回 None。

    代理配置坏了（拆不出主机）时**抛 ValueError**：必须显式失败，
    静默直连等于账号从宿主 IP 出现，登录与采集的 IP 就不一致了。
    """
    if not row.proxy_enabled or not row.proxy_server:
        return None

    from backend.services.account_proxy_config import resolve_account_proxy

    return resolve_account_proxy(
        {
            "proxy_enabled": row.proxy_enabled,
            "proxy_server": row.proxy_server,
            "proxy_username": row.proxy_username,
            "proxy_password": row.proxy_password,
            "account_id": row.main_account_id,
        }
    )


def load_accounts() -> list[MainAccountRow]:
    engine = sa.create_engine(database_url())
    with engine.connect() as conn:
        rows = conn.execute(sa.text(ACCOUNT_QUERY)).fetchall()

    accounts: list[MainAccountRow] = []
    for row in rows:
        proxy = extract_proxy_fields(row.shop_extra_config)
        accounts.append(
            MainAccountRow(
                platform=str(row.platform or "").strip().lower(),
                main_account_id=str(row.main_account_id or "").strip(),
                main_account_name=str(row.main_account_name or "").strip(),
                username=str(row.username or "").strip(),
                proxy_enabled=bool(proxy["proxy_enabled"]),
                proxy_server=str(proxy["proxy_server"] or "").strip(),
                proxy_username=str(proxy["proxy_username"] or "").strip(),
                proxy_password=str(proxy["proxy_password"] or "").strip(),
            )
        )
    return accounts


def build_inspection_accounts(rows: list[MainAccountRow]) -> tuple[list[dict[str, Any]], list[str]]:
    """公开账号清单。

    **不含代理凭据** —— 这份清单会进 HTTP 响应（面板接口），凭据不能外泄。
    """
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


def build_inspection_accounts_with_proxy(
    rows: list[MainAccountRow],
) -> tuple[list[dict[str, Any]], list[str]]:
    """CLI 清单：额外带代理信息。

    只给**管道传输**的本地 CLI 用（``scripts/pwcli_daily_inspection.py``），
    不要把它接到 HTTP 接口上 —— 那会把代理密码送进浏览器 DOM。
    """
    accounts, skipped = build_inspection_accounts(rows)
    by_key = {(row.platform, row.main_account_id): row for row in rows}
    for account in accounts:
        row = by_key.get((account["platform"], account["account_id"]))
        if row is None:
            continue
        account["proxy_server"] = row.proxy_server
        account["proxy_username"] = row.proxy_username
        account["proxy_password"] = row.proxy_password
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
    import logging

    # 子命令的 stdout 是**机器可读**（PowerShell 直接捕获去空白）：解析账号代理要用
    # backend 服务，那条 import 链会往 stdout 打 INFO 日志 -> 输出会被污染。
    logging.disable(logging.INFO)

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
