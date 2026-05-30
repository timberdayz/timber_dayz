"""
Generate the copy-paste pwcli account command list from enabled main accounts.

Usage:
    python scripts/generate_pwcli_account_commands.py
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import sqlalchemy as sa


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = PROJECT_ROOT / "docs" / "generated" / "PWCLI_ACCOUNT_COMMANDS.md"
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


def _database_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def _slugify(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", str(value or "").strip().lower())
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or "account"


def _work_tag(platform: str, account_id: str) -> str:
    return f"{_slugify(platform)}-{_slugify(account_id)}-inspect"


def _display_name(row: MainAccountRow) -> str:
    name = (row.main_account_name or "").strip()
    username = (row.username or "").strip()
    account_id = (row.main_account_id or "").strip()
    if name and name != account_id:
        return name
    if username and username != account_id:
        return f"{account_id} ({username})"
    return account_id


def _load_accounts() -> list[MainAccountRow]:
    engine = sa.create_engine(_database_url())
    query = sa.text(
        """
        select platform, main_account_id, coalesce(main_account_name, '') as main_account_name,
               coalesce(username, '') as username
        from core.main_accounts
        where enabled = true
        order by platform, main_account_id
        """
    )
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


def _render_account_block(row: MainAccountRow) -> str:
    helpers = PLATFORM_HELPERS[row.platform]
    work_tag = _work_tag(row.platform, row.main_account_id)
    account_id = row.main_account_id.replace("'", "''")
    return f"""### {_display_name(row)}

打开:

```powershell
{helpers["open"]} -WorkTag {work_tag} -AccountId '{account_id}'
```

保存:

```powershell
{helpers["save"]} -AccountId '{account_id}'
```

检查:

```powershell
{helpers["show"]} -AccountId '{account_id}' -WorkTag {work_tag}
```"""


def _render(accounts: list[MainAccountRow]) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines: list[str] = [
        "# PWCLI 账号命令清单",
        "",
        "> 自动生成文件，请勿手工修改。",
        "> 刷新命令: `python scripts/generate_pwcli_account_commands.py`",
        f"> 生成时间: `{generated_at}`",
        f"> 数据来源: `{_database_url()}` 中的 `core.main_accounts where enabled = true`",
        "",
        "本文档提供给业务同事直接复制使用。",
        "",
        "规则:",
        "",
        "1. 先执行“打开命令”。",
        "2. 在打开的浏览器里人工巡店、人工操作。",
        "3. 操作结束后执行“保存命令”。",
        "4. 如需确认路径是否正确，可执行“检查命令”。",
        "",
        "注意:",
        "",
        "1. 同一平台下，不同账号不能使用同一个 `WorkTag`。",
        "2. 本清单已为每个账号分配固定 `WorkTag`，直接复制即可。",
        "3. 必须使用这里的正式 `AccountId`，不要改成旧店铺名、旧别名或历史用户名。",
        "",
        "## 通用模板",
        "",
        "Shopee:",
        "",
        "```powershell",
        "Open-PwcliShopee -WorkTag <固定-worktag> -AccountId '<main-account-id>'",
        "Save-PwcliShopeeState -AccountId '<main-account-id>'",
        "Show-PwcliPaths -Platform shopee -AccountId '<main-account-id>' -WorkTag <固定-worktag>",
        "```",
        "",
        "TikTok:",
        "",
        "```powershell",
        "Open-PwcliTiktok -WorkTag <固定-worktag> -AccountId '<main-account-id>'",
        "Save-PwcliTiktokState -AccountId '<main-account-id>'",
        "Show-PwcliPaths -Platform tiktok -AccountId '<main-account-id>' -WorkTag <固定-worktag>",
        "```",
        "",
        "妙手:",
        "",
        "```powershell",
        "Open-PwcliMiaoshou -WorkTag <固定-worktag> -AccountId '<main-account-id>'",
        "Save-PwcliMiaoshouState -AccountId '<main-account-id>'",
        "Show-PwcliPaths -Platform miaoshou -AccountId '<main-account-id>' -WorkTag <固定-worktag>",
        "```",
        "",
    ]

    for platform in ("miaoshou", "shopee", "tiktok"):
        platform_rows = [row for row in accounts if row.platform == platform]
        if not platform_rows:
            continue
        lines.append(f"## {PLATFORM_HELPERS[platform]['title']}")
        lines.append("")
        for row in platform_rows:
            lines.append(_render_account_block(row))
            lines.append("")

    lines.extend(
        [
            "## 保存时机",
            "",
            "只有在以下场景才建议保存:",
            "",
            "1. 已经稳定进入后台首页。",
            "2. 已经完成验证码或二次验证。",
            "3. 当前页面不是登录页、报错页、验证页。",
            "",
            "不要在以下场景保存:",
            "",
            "1. 刚打开还在跳转。",
            "2. 停留在登录页。",
            "3. 停留在验证码页。",
            "4. 页面明显异常。",
            "",
            "## 更新方式",
            "",
            "本清单基于账号管理中的当前启用主账号自动生成。",
            "",
            "当 `core.main_accounts` 中启用账号有新增、停用或重命名时，执行以下命令刷新:",
            "",
            "```powershell",
            "python scripts/generate_pwcli_account_commands.py",
            "```",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    accounts = _load_accounts()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(_render(accounts), encoding="utf-8")
    print(f"[PASS] Generated {OUTPUT_PATH}")
    print(f"[INFO] Enabled main accounts: {len(accounts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
