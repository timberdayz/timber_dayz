from __future__ import annotations

import argparse
import secrets
import socket
import subprocess
import sys
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from scripts.pwcli_account_inventory import (
    build_inspection_accounts,
    load_accounts,
    quote_ps,
)


STATIC_DIR = PROJECT_ROOT / "scripts" / "pwcli_inspection_panel_static"
INDEX_PATH = STATIC_DIR / "index.html"
OPEN_HELPERS = {
    "miaoshou": "Open-PwcliMiaoshou",
    "shopee": "Open-PwcliShopee",
    "tiktok": "Open-PwcliTiktok",
}
SAVE_HELPERS = {
    "miaoshou": "Save-PwcliMiaoshouState",
    "shopee": "Save-PwcliShopeeState",
    "tiktok": "Save-PwcliTiktokState",
}


class AccountRequest(BaseModel):
    platform: str
    account_id: str


@dataclass(frozen=True)
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str


def run_subprocess_command(command: list[str], cwd: Path | None = None) -> CommandResult:
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(cwd or PROJECT_ROOT),
    )
    return CommandResult(
        exit_code=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


@dataclass
class PanelState:
    token: str
    account_rows_loader: Callable[[], Any] = load_accounts
    command_runner: Callable[[list[str]], CommandResult] = run_subprocess_command
    repo_root: Path = PROJECT_ROOT
    statuses: dict[tuple[str, str], str] = field(default_factory=dict)
    logs: list[dict[str, str]] = field(default_factory=list)

    def accounts(self) -> list[dict[str, Any]]:
        accounts, _skipped = build_inspection_accounts(self.account_rows_loader())
        result: list[dict[str, Any]] = []
        for account in accounts:
            key = (account["platform"], account["account_id"])
            result.append({**account, "status": self.statuses.get(key, "idle")})
        return result

    def find_account(self, platform: str, account_id: str) -> dict[str, Any]:
        for account in self.accounts():
            if account["platform"] == platform and account["account_id"] == account_id:
                return account
        raise HTTPException(status_code=404, detail="Unknown inspection account")

    def record(self, action: str, account: dict[str, Any], status: str, message: str = "") -> None:
        self.logs.append(
            {
                "action": action,
                "platform": str(account["platform"]),
                "account_id": str(account["account_id"]),
                "status": status,
                "message": message,
            }
        )
        if len(self.logs) > 50:
            del self.logs[: len(self.logs) - 50]


def build_pwcli_action_command(action: str, account: dict[str, Any], repo_root: Path) -> list[str]:
    platform = str(account["platform"])
    utf8_prefix = (
        "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); "
        "$OutputEncoding=[Console]::OutputEncoding; "
    )
    if action == "open":
        helper = OPEN_HELPERS.get(platform)
        if not helper:
            raise ValueError(f"Unsupported platform: {platform}")
        command = (
            utf8_prefix
            + f"Set-Location -LiteralPath '{quote_ps(str(repo_root))}'; "
            f". '{quote_ps(str(repo_root / 'scripts' / 'pwcli_helpers.ps1'))}'; "
            f"{helper} -WorkTag '{quote_ps(str(account['work_tag']))}' "
            f"-AccountId '{quote_ps(str(account['account_id']))}'"
        )
    elif action == "save":
        helper = SAVE_HELPERS.get(platform)
        if not helper:
            raise ValueError(f"Unsupported platform: {platform}")
        command = (
            utf8_prefix
            + f"Set-Location -LiteralPath '{quote_ps(str(repo_root))}'; "
            f". '{quote_ps(str(repo_root / 'scripts' / 'pwcli_helpers.ps1'))}'; "
            f"{helper} -AccountId '{quote_ps(str(account['account_id']))}'"
        )
    else:
        raise ValueError(f"Unsupported action: {action}")

    return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command]


def find_available_port(start: int = 8765, end: int = 8780) -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
        return port
    raise RuntimeError(f"No available local port in range {start}-{end}")


def build_app(state: PanelState) -> FastAPI:
    app = FastAPI(title="PWCLI Local Inspection Panel")

    def require_token(token: str | None = Query(default=None)) -> None:
        if token != state.token:
            raise HTTPException(status_code=401, detail="Invalid panel token")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return INDEX_PATH.read_text(encoding="utf-8")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> Response:
        return Response(status_code=204)

    @app.get("/api/status", dependencies=[Depends(require_token)])
    def status() -> dict[str, Any]:
        return {"ok": True, "logs": state.logs[-20:]}

    @app.get("/api/accounts", dependencies=[Depends(require_token)])
    def accounts() -> list[dict[str, Any]]:
        return state.accounts()

    def run_action(action: str, request: AccountRequest) -> dict[str, Any]:
        account = state.find_account(request.platform, request.account_id)
        pending = "opening" if action == "open" else "saving"
        success = "opened" if action == "open" else "saved"
        key = (account["platform"], account["account_id"])
        state.statuses[key] = pending
        command = build_pwcli_action_command(action, account, state.repo_root)
        result = state.command_runner(command)
        if result.exit_code != 0:
            state.statuses[key] = "error"
            message = (result.stderr or result.stdout or "Command failed").strip()
            state.record(action, account, "error", message)
            raise HTTPException(status_code=500, detail=message)
        state.statuses[key] = success
        state.record(action, account, success, (result.stdout or "").strip())
        return {**account, "status": success}

    @app.post("/api/accounts/open", dependencies=[Depends(require_token)])
    def open_account(request: AccountRequest) -> dict[str, Any]:
        return run_action("open", request)

    @app.post("/api/accounts/save", dependencies=[Depends(require_token)])
    def save_account(request: AccountRequest) -> dict[str, Any]:
        return run_action("save", request)

    @app.post("/api/accounts/skip", dependencies=[Depends(require_token)])
    def skip_account(request: AccountRequest) -> dict[str, Any]:
        account = state.find_account(request.platform, request.account_id)
        key = (account["platform"], account["account_id"])
        state.statuses[key] = "skipped"
        state.record("skip", account, "skipped")
        return {**account, "status": "skipped"}

    return app


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Start the local PWCLI inspection panel")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)

    import uvicorn

    port = find_available_port(args.port, 8780)
    token = secrets.token_urlsafe(24)
    url = f"http://127.0.0.1:{port}/?token={token}"
    print(f"PWCLI inspection panel: {url}")
    if not args.no_browser:
        webbrowser.open(url)
    uvicorn.run(build_app(PanelState(token=token)), host="127.0.0.1", port=port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
