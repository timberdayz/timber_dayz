"""
Generate the copy-paste pwcli account command list from enabled main accounts.

Usage:
    python scripts/generate_pwcli_account_commands.py
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.pwcli_account_inventory import (
    PLATFORM_HELPERS,
    MainAccountRow,
    database_url,
    display_name,
    load_accounts,
    quote_ps,
    work_tag,
)


OUTPUT_PATH = PROJECT_ROOT / "docs" / "generated" / "PWCLI_ACCOUNT_COMMANDS.md"


def render_account_block(row: MainAccountRow) -> str:
    helpers = PLATFORM_HELPERS[row.platform]
    account_id = quote_ps(row.main_account_id)
    tag = work_tag(row.platform, row.main_account_id)
    return "\n".join(
        [
            f"### {display_name(row)}",
            "",
            "\u6253\u5f00:",
            "",
            "```powershell",
            f"{helpers['open']} -WorkTag {tag} -AccountId '{account_id}'",
            "```",
            "",
            "\u4fdd\u5b58:",
            "",
            "```powershell",
            f"{helpers['save']} -AccountId '{account_id}'",
            "```",
            "",
            "\u68c0\u67e5:",
            "",
            "```powershell",
            f"{helpers['show']} -AccountId '{account_id}' -WorkTag {tag}",
            "```",
        ]
    )


def render_summary_table(rows: list[MainAccountRow]) -> list[str]:
    lines = [
        "## \u8d26\u53f7\u603b\u8868",
        "",
        "| \u5e73\u53f0 | \u663e\u793a\u540d | AccountId | WorkTag |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| {platform} | {name} | `{account_id}` | `{tag}` |".format(
                platform=PLATFORM_HELPERS[row.platform]["title"],
                name=display_name(row).replace("|", "\\|"),
                account_id=row.main_account_id,
                tag=work_tag(row.platform, row.main_account_id),
            )
        )
    return lines


def render_document(rows: list[MainAccountRow]) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines: list[str] = [
        "# PWCLI \u8d26\u53f7\u547d\u4ee4\u6e05\u5355",
        "",
        "> \u81ea\u52a8\u751f\u6210\u6587\u4ef6\uff0c\u8bf7\u52ff\u624b\u5de5\u4fee\u6539\u3002",
        "> \u5237\u65b0\u547d\u4ee4: `python scripts/generate_pwcli_account_commands.py`",
        f"> \u751f\u6210\u65f6\u95f4: `{generated_at}`",
        f"> \u6570\u636e\u6765\u6e90: `{database_url()}` \u4e2d\u7684 `core.main_accounts where enabled = true`",
        "",
        "\u672c\u6587\u6863\u63d0\u4f9b\u7ed9\u4e1a\u52a1\u540c\u4e8b\u76f4\u63a5\u590d\u5236\u4f7f\u7528\u3002",
        "",
        "\u9996\u6b21\u4f7f\u7528\u6216\u65b0\u6253\u5f00 PowerShell \u7a97\u53e3\u65f6\uff0c\u8bf7\u5148\u5728\u4ed3\u5e93\u6839\u76ee\u5f55\u6267\u884c:",
        "",
        "```powershell",
        ". .\\scripts\\pwcli_helpers.ps1",
        "```",
        "",
        "## 推荐日常方式",
        "",
        "日常人工巡店优先使用本地网页巡店面板，减少复制命令和手写账号参数:",
        "",
        "```powershell",
        "python scripts\\pwcli_inspection_panel.py",
        "```",
        "",
        "网页面板只监听本机 `127.0.0.1`，通过按钮打开账号会话，并在人工确认后保存。",
        "",
        "如果网页面板不可用，可使用 CLI 菜单兜底:",
        "",
        "```powershell",
        ". .\\scripts\\pwcli_helpers.ps1",
        "Start-PwcliDailyInspection",
        "```",
        "",
        "这些工具只负责打开账号会话和等待人工确认保存，不会自动点击页面、关闭弹窗或处理验证码。",
        "",
        "\u89c4\u5219:",
        "",
        "1. \u5148\u6267\u884c\u201c\u6253\u5f00\u547d\u4ee4\u201d",
        "2. \u5728\u6253\u5f00\u7684\u6d4f\u89c8\u5668\u91cc\u4eba\u5de5\u5de1\u5e97\u3001\u4eba\u5de5\u64cd\u4f5c",
        "3. \u64cd\u4f5c\u7ed3\u675f\u540e\u6267\u884c\u201c\u4fdd\u5b58\u547d\u4ee4\u201d",
        "4. \u5982\u9700\u786e\u8ba4\u8def\u5f84\u662f\u5426\u6b63\u786e\uff0c\u53ef\u6267\u884c\u201c\u68c0\u67e5\u547d\u4ee4\u201d",
        "",
        "\u6ce8\u610f:",
        "",
        "1. \u540c\u4e00\u5e73\u53f0\u4e0b\uff0c\u4e0d\u540c\u8d26\u53f7\u4e0d\u80fd\u4f7f\u7528\u540c\u4e00\u4e2a `WorkTag`",
        "2. \u672c\u6e05\u5355\u5df2\u4e3a\u6bcf\u4e2a\u8d26\u53f7\u5206\u914d\u56fa\u5b9a `WorkTag`\uff0c\u76f4\u63a5\u590d\u5236\u5373\u53ef",
        "3. \u5fc5\u987b\u4f7f\u7528\u8fd9\u91cc\u7684\u6b63\u5f0f `AccountId`\uff0c\u4e0d\u8981\u6539\u6210\u65e7\u5e97\u94fa\u540d\u3001\u65e7\u522b\u540d\u6216\u5386\u53f2\u7528\u6237\u540d",
        "",
        "## \u901a\u7528\u6a21\u677f",
        "",
        "Shopee:",
        "",
        "```powershell",
        "Open-PwcliShopee -WorkTag <fixed-worktag> -AccountId '<main-account-id>'",
        "Save-PwcliShopeeState -AccountId '<main-account-id>'",
        "Show-PwcliPaths -Platform shopee -AccountId '<main-account-id>' -WorkTag <fixed-worktag>",
        "```",
        "",
        "TikTok:",
        "",
        "```powershell",
        "Open-PwcliTiktok -WorkTag <fixed-worktag> -AccountId '<main-account-id>'",
        "Save-PwcliTiktokState -AccountId '<main-account-id>'",
        "Show-PwcliPaths -Platform tiktok -AccountId '<main-account-id>' -WorkTag <fixed-worktag>",
        "```",
        "",
        "\u5999\u624b:",
        "",
        "```powershell",
        "Open-PwcliMiaoshou -WorkTag <fixed-worktag> -AccountId '<main-account-id>'",
        "Save-PwcliMiaoshouState -AccountId '<main-account-id>'",
        "Show-PwcliPaths -Platform miaoshou -AccountId '<main-account-id>' -WorkTag <fixed-worktag>",
        "```",
        "",
    ]

    lines.extend(render_summary_table(rows))

    for platform in ("miaoshou", "shopee", "tiktok"):
        platform_rows = [row for row in rows if row.platform == platform]
        if not platform_rows:
            continue
        lines.extend(["", f"## {PLATFORM_HELPERS[platform]['title']}"])
        for row in platform_rows:
            lines.extend(["", render_account_block(row)])

    lines.extend(
        [
            "",
            "## \u4fdd\u5b58\u65f6\u673a",
            "",
            "\u53ea\u6709\u5728\u4ee5\u4e0b\u573a\u666f\u624d\u5efa\u8bae\u4fdd\u5b58:",
            "",
            "1. \u5df2\u7ecf\u7a33\u5b9a\u8fdb\u5165\u540e\u53f0\u9996\u9875",
            "2. \u5df2\u7ecf\u5b8c\u6210\u9a8c\u8bc1\u7801\u6216\u4e8c\u6b21\u9a8c\u8bc1",
            "3. \u5f53\u524d\u9875\u9762\u4e0d\u662f\u767b\u5f55\u9875\u3001\u62a5\u9519\u9875\u3001\u9a8c\u8bc1\u9875",
            "",
            "\u4e0d\u8981\u5728\u4ee5\u4e0b\u573a\u666f\u4fdd\u5b58:",
            "",
            "1. \u521a\u6253\u5f00\u8fd8\u5728\u8df3\u8f6c",
            "2. \u505c\u7559\u5728\u767b\u5f55\u9875",
            "3. \u505c\u7559\u5728\u9a8c\u8bc1\u7801\u9875",
            "4. \u9875\u9762\u660e\u663e\u5f02\u5e38",
            "",
            "## \u66f4\u65b0\u65b9\u5f0f",
            "",
            "\u672c\u6e05\u5355\u57fa\u4e8e\u8d26\u53f7\u7ba1\u7406\u4e2d\u7684\u5f53\u524d\u542f\u7528\u4e3b\u8d26\u53f7\u81ea\u52a8\u751f\u6210\u3002",
            "",
            "\u5f53 `core.main_accounts` \u4e2d\u542f\u7528\u8d26\u53f7\u6709\u65b0\u589e\u3001\u505c\u7528\u6216\u91cd\u547d\u540d\u65f6\uff0c\u8bf7\u6267\u884c:",
            "",
            "```powershell",
            "python scripts/generate_pwcli_account_commands.py",
            "```",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    rows = load_accounts()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(render_document(rows), encoding="utf-8")
    print(f"[PASS] Generated {OUTPUT_PATH}")
    print(f"[INFO] Active main accounts: {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
