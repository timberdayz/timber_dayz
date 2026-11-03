from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Sequence

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.pwcli_account_inventory import (
    build_inspection_accounts_with_proxy,
    load_accounts,
)


LAST_STDOUT = ""
LAST_STDERR = ""


def _write_stdout(text: str) -> None:
    global LAST_STDOUT
    LAST_STDOUT = text
    print(text)


def _write_stderr(text: str) -> None:
    global LAST_STDERR
    LAST_STDERR = text
    print(text, file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PWCLI daily inspection helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_accounts = subparsers.add_parser("list-accounts", help="List enabled inspection accounts")
    list_accounts.add_argument(
        "--format",
        choices=("json",),
        default="json",
        help="Output format",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    global LAST_STDOUT, LAST_STDERR
    LAST_STDOUT = ""
    LAST_STDERR = ""

    # 本命令的 stdout 是**机器可读 JSON**（PowerShell 侧 ConvertFrom-Json 直接消费）。
    # 解析账号代理要用 backend 服务，那条 import 链会往 stdout 打 INFO 日志 ->
    # JSON 会被污染，PowerShell 侧直接解析失败。这里先关掉 INFO 及以下级别。
    logging.disable(logging.INFO)

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "list-accounts":
        # CLI 清单带代理信息（只在管道里传，不进 HTTP 响应）
        accounts, skipped = build_inspection_accounts_with_proxy(load_accounts())
        if skipped:
            _write_stderr(
                "\n".join(f"Skipping unsupported platform account: {item}" for item in skipped)
            )
        _write_stdout(json.dumps(accounts, ensure_ascii=False))
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
