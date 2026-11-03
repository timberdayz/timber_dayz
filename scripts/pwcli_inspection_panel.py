from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
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

from backend.services.main_account_session_lock import (
    MainAccountSessionLock,
    MainAccountSessionLockTimeoutError,
    MainAccountSessionLockUnavailableError,
)
from scripts.pwcli_account_inventory import (
    account_proxy_config,
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

#: 账号会话锁被占用时的提示（直接给运维看，不要让 Chromium 报 ProcessSingleton）。
ACCOUNT_BUSY_MESSAGE = "该账号正在采集中，请稍后再打开巡店窗口"

#: 巡店浏览器存活期间，锁持有者轮询 pid 的间隔（秒）。
DEFAULT_SESSION_POLL_INTERVAL_SECONDS = 5.0

#: 代理凭据只走环境变量：命令行在进程列表里可见。
PROXY_USERNAME_ENV = "PWCLI_PROXY_USERNAME"
PROXY_PASSWORD_ENV = "PWCLI_PROXY_PASSWORD"


class AccountRequest(BaseModel):
    platform: str
    account_id: str


@dataclass(frozen=True)
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str


def run_subprocess_command(
    command: list[str],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> CommandResult:
    process_env = None
    if env:
        process_env = {**os.environ, **env}
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(cwd or PROJECT_ROOT),
        env=process_env,
    )
    return CommandResult(
        exit_code=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def build_proxy_env(proxy: dict[str, str] | None) -> dict[str, str]:
    """代理凭据 -> 子进程环境变量。

    凭据**不能**进命令行（进程列表可见），因此这里只准备环境变量，
    由 pwcli_native 侧读取。代理地址本身不含凭据，可以走命令行。
    """
    if not proxy:
        return {}
    env: dict[str, str] = {}
    username = str(proxy.get("username") or "").strip()
    password = str(proxy.get("password") or "").strip()
    if username:
        env[PROXY_USERNAME_ENV] = username
    if password:
        env[PROXY_PASSWORD_ENV] = password
    return env


class _AccountLockHandle:
    """账号会话锁的持有者（生命周期跨请求：开到浏览器关闭为止）。"""

    def __init__(self, stack: contextlib.AsyncExitStack) -> None:
        self._stack = stack
        self._released = False

    async def release(self) -> None:
        if self._released:
            return
        self._released = True
        await self._stack.aclose()


@dataclass
class _LockHolding:
    handle: _AccountLockHandle
    watch_task: asyncio.Task | None = None
    pid: int | None = None


@dataclass
class PanelState:
    token: str
    account_rows_loader: Callable[[], Any] = load_accounts
    command_runner: Callable[..., CommandResult] = run_subprocess_command
    repo_root: Path = PROJECT_ROOT
    statuses: dict[tuple[str, str], str] = field(default_factory=dict)
    logs: list[dict[str, str]] = field(default_factory=list)
    session_lock: Any = None
    session_poll_interval_seconds: float = DEFAULT_SESSION_POLL_INTERVAL_SECONDS
    lock_holdings: dict[tuple[str, str], _LockHolding] = field(default_factory=dict)

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

    def account_proxy(self, platform: str, account_id: str) -> dict[str, str] | None:
        """账号级代理（Playwright 形态）；没配代理返回 None。

        代理配置坏了必须**显式失败**（ValueError），不能静默直连 ——
        静默直连等于账号从宿主 IP 出现，登录与采集的 IP 不一致。
        """
        for row in self.account_rows_loader():
            if (
                str(getattr(row, "platform", "")) == platform
                and str(getattr(row, "main_account_id", "")) == account_id
            ):
                return account_proxy_config(row)
        return None

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

    # -- 账号会话锁 -------------------------------------------------------

    async def acquire_account_lock(self, platform: str, main_account_id: str) -> _AccountLockHandle:
        """拿账号会话锁（与采集同一把）；被占用时抛 409。

        巡店开的是**采集同一个 profile 目录** -> 采集持锁期间再开就是 Chromium
        ProcessSingleton 冲突（更糟：双开写坏 profile）。所以这里必须用同一把
        ``MainAccountSessionLock``，锁 key = ``build_lock_key(platform, main_account_id)``。
        """
        key = (platform, main_account_id)
        existing = self.lock_holdings.get(key)
        if existing is not None:
            # 同一账号重复点「打开巡店」：复用已持有的锁（新的浏览器会顶掉旧的）
            return existing.handle
        if self.session_lock is None:
            self.session_lock = MainAccountSessionLock()
        stack = contextlib.AsyncExitStack()
        try:
            await stack.enter_async_context(
                self.session_lock.acquire(platform, main_account_id, timeout=0)
            )
        except MainAccountSessionLockTimeoutError as exc:
            await stack.aclose()
            raise HTTPException(status_code=409, detail=ACCOUNT_BUSY_MESSAGE) from exc
        except MainAccountSessionLockUnavailableError as exc:
            await stack.aclose()
            raise HTTPException(
                status_code=503, detail=f"账号会话锁服务不可用: {exc}"
            ) from exc
        except Exception as exc:
            await stack.aclose()
            raise HTTPException(
                status_code=500, detail=f"账号会话锁获取失败: {exc}"
            ) from exc
        handle = _AccountLockHandle(stack)
        self.lock_holdings[key] = _LockHolding(handle=handle)
        return handle

    async def release_account_lock(self, key: tuple[str, str]) -> None:
        """放锁（幂等）。"""
        holding = self.lock_holdings.pop(key, None)
        if holding is None:
            return
        current = asyncio.current_task()
        task = holding.watch_task
        if task is not None and task is not current and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        await holding.handle.release()

    async def start_browser_watch(self, key: tuple[str, str], pid: int) -> None:
        """轮询浏览器进程；进程消失即放锁（正常关闭 -> 刷盘 -> 再放锁）。

        ``pwcli open`` 是一次性命令：Python 进程退出后 Chromium 还活着 -> 当前架构里
        没有自然持有者，所以由常驻的面板持锁并轮询 pid。
        """
        holding = self.lock_holdings.get(key)
        if holding is None:
            return
        previous = holding.watch_task
        if previous is not None and not previous.done():
            previous.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await previous
        holding.pid = pid
        holding.watch_task = asyncio.create_task(self._watch_browser_process(key, pid))

    async def _watch_browser_process(self, key: tuple[str, str], pid: int) -> None:
        try:
            while True:
                await asyncio.sleep(self.session_poll_interval_seconds)
                if not await asyncio.to_thread(_is_process_alive, pid):
                    break
        except asyncio.CancelledError:
            raise
        finally:
            holding = self.lock_holdings.get(key)
            if holding is not None and holding.pid == pid:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await self.release_account_lock(key)

    # -- 浏览器 pid -------------------------------------------------------

    def read_browser_pid(self, account: dict[str, Any]) -> int | None:
        """从 pwcli 的会话元数据里读浏览器 pid（决定什么时候放锁）。"""
        from modules.utils import pwcli_native

        session = f"{account['platform']}-{account['work_tag']}"
        path = pwcli_native.session_meta_path_for(self.repo_root, session)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        try:
            return int(payload.get("pid"))
        except (TypeError, ValueError):
            return None


def _is_process_alive(pid: int) -> bool:
    from modules.utils.pwcli_native import is_process_alive

    return is_process_alive(pid)


def build_pwcli_action_command(
    action: str,
    account: dict[str, Any],
    repo_root: Path,
    *,
    proxy_server: str | None = None,
) -> list[str]:
    platform = str(account["platform"])
    utf8_prefix = (
        "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); "
        "$OutputEncoding=[Console]::OutputEncoding; "
    )
    if action != "open":
        raise ValueError(f"Unsupported action: {action}")
    helper = OPEN_HELPERS.get(platform)
    if not helper:
        raise ValueError(f"Unsupported platform: {platform}")
    command = (
        utf8_prefix
        + f"Set-Location -LiteralPath '{quote_ps(str(repo_root))}'; "
        + f". '{quote_ps(str(repo_root / 'scripts' / 'pwcli_helpers.ps1'))}'; "
        + f"{helper} -WorkTag '{quote_ps(str(account['work_tag']))}' "
        + f"-AccountId '{quote_ps(str(account['account_id']))}'"
    )
    if proxy_server:
        command += f" -ProxyServer '{quote_ps(str(proxy_server))}'"
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

    async def run_action(action: str, request: AccountRequest) -> dict[str, Any]:
        account = state.find_account(request.platform, request.account_id)
        key = (account["platform"], account["account_id"])
        state.statuses[key] = "opening"

        try:
            proxy = state.account_proxy(account["platform"], account["account_id"])
        except ValueError as exc:
            state.statuses[key] = "error"
            message = f"账号代理配置无效: {exc}"
            state.record(action, account, "error", message)
            raise HTTPException(status_code=500, detail=message)

        await state.acquire_account_lock(account["platform"], account["account_id"])
        command = build_pwcli_action_command(
            action,
            account,
            state.repo_root,
            proxy_server=(proxy or {}).get("server") if proxy else None,
        )
        env = build_proxy_env(proxy)
        try:
            result = await asyncio.to_thread(state.command_runner, command, env=env)
        except Exception:
            await state.release_account_lock(key)
            raise
        combined_output = "\n".join(
            part for part in (result.stdout, result.stderr) if part and part.strip()
        ).strip()
        if result.exit_code != 0 or not combined_output:
            state.statuses[key] = "error"
            message = combined_output or f"Command failed with exit code {result.exit_code}"
            state.record(action, account, "error", message)
            await state.release_account_lock(key)
            raise HTTPException(status_code=500, detail=message)
        state.statuses[key] = "opened"
        state.record(action, account, "opened", combined_output)

        pid = state.read_browser_pid(account)
        if pid:
            await state.start_browser_watch(key, pid)
        else:
            # 读不到 pid -> 判断不了浏览器何时退出 -> 立即放锁
            # （宁可少保护，也不要永久占着账号锁让采集排队）
            await state.release_account_lock(key)

        return {**account, "status": "opened", "message": combined_output}

    @app.post("/api/accounts/open", dependencies=[Depends(require_token)])
    async def open_account(request: AccountRequest) -> dict[str, Any]:
        return await run_action("open", request)

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
