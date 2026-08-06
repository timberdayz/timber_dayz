from __future__ import annotations

import argparse
import json
import os
import secrets
import socket
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any, Callable, Sequence

import psutil
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.local_console_processes import (  # noqa: E402
    INSPECTION_PANEL,
    LOCAL_COLLECTION,
    LocalProcessSupervisor,
    ProcessOwnershipError,
)

TOKEN_HEADER = "X-Local-Console-Token"
STATIC_DIR = PROJECT_ROOT / "scripts" / "local_console_static"
INDEX_PATH = STATIC_DIR / "index.html"
PORT_RANGE = range(8740, 8765)
STATE_FILENAME = "local-console-state.json"
LOCK_FILENAME = "local-console.lock"

def build_app(
    *,
    supervisor: Any,
    token: str,
    index_path: Path = INDEX_PATH,
) -> FastAPI:
    app = FastAPI(
        title="Xihong ERP Local Console",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    static_dir = index_path.parent

    @app.middleware("http")
    async def add_security_headers(request, call_next):  # noqa: ANN001
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
            "base-uri 'none'; frame-ancestors 'none'"
        )
        return response

    def require_token(
        supplied_token: str | None = Header(default=None, alias=TOKEN_HEADER),
    ) -> None:
        if supplied_token is None or not secrets.compare_digest(
            supplied_token, token
        ):
            raise HTTPException(status_code=401, detail="无效的本地控制台凭据")

    def run_action(action: Callable[[], Any]) -> Any:
        try:
            return action()
        except ProcessOwnershipError:
            raise HTTPException(
                status_code=409,
                detail="该进程不受本控制台管理，操作已拒绝",
            ) from None
        except RuntimeError:
            raise HTTPException(
                status_code=409, detail="服务尚未就绪，请稍后重试"
            ) from None
        except Exception:
            raise HTTPException(
                status_code=500,
                detail="操作失败，请查看本地控制台窗口",
            ) from None

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return index_path.read_text(encoding="utf-8")

    @app.get("/assets/styles.css", include_in_schema=False)
    def styles() -> FileResponse:
        return FileResponse(static_dir / "styles.css", media_type="text/css")

    @app.get("/assets/app.js", include_in_schema=False)
    def script() -> FileResponse:
        return FileResponse(
            static_dir / "app.js", media_type="application/javascript"
        )

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> Response:
        return Response(status_code=204)

    @app.get("/api/status", dependencies=[Depends(require_token)])
    def status() -> dict[str, Any]:
        return {"services": supervisor.all_statuses()}

    @app.post(
        "/api/services/local-collection/start",
        dependencies=[Depends(require_token)],
    )
    def start_local_collection() -> Any:
        return run_action(lambda: supervisor.start(LOCAL_COLLECTION))

    @app.post(
        "/api/services/local-collection/open",
        dependencies=[Depends(require_token)],
    )
    def open_local_collection() -> Any:
        return run_action(lambda: supervisor.open(LOCAL_COLLECTION))

    @app.post(
        "/api/services/local-collection/stop",
        dependencies=[Depends(require_token)],
    )
    def stop_local_collection() -> Any:
        return run_action(lambda: supervisor.stop(LOCAL_COLLECTION))

    @app.post(
        "/api/services/inspection-panel/start",
        dependencies=[Depends(require_token)],
    )
    def start_inspection_panel() -> Any:
        return run_action(lambda: supervisor.start(INSPECTION_PANEL))

    @app.post(
        "/api/services/inspection-panel/open",
        dependencies=[Depends(require_token)],
    )
    def open_inspection_panel() -> Any:
        return run_action(lambda: supervisor.open(INSPECTION_PANEL))

    @app.post(
        "/api/services/inspection-panel/stop",
        dependencies=[Depends(require_token)],
    )
    def stop_inspection_panel() -> Any:
        return run_action(lambda: supervisor.stop(INSPECTION_PANEL))

    @app.post("/api/services/stop-all", dependencies=[Depends(require_token)])
    def stop_all() -> Any:
        return run_action(supervisor.stop_all)

    return app


def runtime_directory() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir())
    return base / "XihongERP"


def load_state_document(state_path: Path) -> dict[str, Any]:
    try:
        content = json.loads(state_path.read_text(encoding="utf-8"))
        return content if isinstance(content, dict) else {}
    except (OSError, TypeError, ValueError):
        return {}


def write_state_document(state_path: Path, document: dict[str, Any]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = state_path.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary_path.replace(state_path)


def write_controller_state(
    state_path: Path,
    *,
    pid: int,
    create_time: float,
    port: int,
    token: str,
) -> None:
    document = load_state_document(state_path)
    document["controller"] = {
        "pid": pid,
        "create_time": create_time,
        "port": port,
        "token": token,
    }
    write_state_document(state_path, document)


def clear_controller_state(state_path: Path, pid: int) -> None:
    document = load_state_document(state_path)
    controller = document.get("controller")
    if isinstance(controller, dict) and controller.get("pid") == pid:
        document.pop("controller", None)
        write_state_document(state_path, document)


def probe_controller(url: str, token: str) -> bool:
    request = urllib.request.Request(url, headers={TOKEN_HEADER: token})
    try:
        with urllib.request.urlopen(request, timeout=0.8) as response:
            return response.status == 200
    except Exception:
        return False


def open_existing_controller(
    state_path: Path,
    *,
    process_resolver: Callable[[int], Any] = psutil.Process,
    readiness_probe: Callable[[str, str], bool] = probe_controller,
    url_opener: Callable[[str], Any] = webbrowser.open,
    open_browser: bool = True,
) -> bool:
    controller = load_state_document(state_path).get("controller")
    if not isinstance(controller, dict):
        return False
    try:
        pid = int(controller["pid"])
        create_time = float(controller["create_time"])
        port = int(controller["port"])
        token = str(controller["token"])
        if not 1 <= port <= 65535 or not token:
            return False
        process = process_resolver(pid)
        if not process.is_running():
            return False
        if abs(float(process.create_time()) - create_time) > 0.01:
            return False
        command_text = " ".join(str(part) for part in process.cmdline()).lower()
        if "local_console.py" not in command_text:
            return False
    except Exception:
        return False

    status_url = f"http://127.0.0.1:{port}/api/status"
    if not readiness_probe(status_url, token):
        return False
    if open_browser:
        url_opener(f"http://127.0.0.1:{port}/?token={token}")
    return True


def acquire_instance_lock(lock_path: Path) -> int | None:
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return None
    os.write(descriptor, str(os.getpid()).encode("ascii"))
    return descriptor


def release_instance_lock(lock_path: Path, descriptor: int) -> None:
    try:
        os.close(descriptor)
    finally:
        try:
            lock_path.unlink()
        except OSError:
            pass


def find_available_port() -> int:
    for port in PORT_RANGE:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
        return port
    raise RuntimeError("本地控制台端口 8740-8764 均被占用")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Start the Xihong ERP local console")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)

    import uvicorn

    runtime_dir = runtime_directory()
    runtime_dir.mkdir(parents=True, exist_ok=True)
    state_path = runtime_dir / STATE_FILENAME
    lock_path = runtime_dir / LOCK_FILENAME
    if open_existing_controller(state_path, open_browser=not args.no_browser):
        return 0

    lock_descriptor = acquire_instance_lock(lock_path)
    if lock_descriptor is None:
        for _ in range(20):
            time.sleep(0.1)
            if open_existing_controller(
                state_path, open_browser=not args.no_browser
            ):
                return 0
        try:
            lock_pid = int(lock_path.read_text(encoding="ascii").strip())
            lock_process = psutil.Process(lock_pid)
            command_text = " ".join(lock_process.cmdline()).lower()
            lock_is_valid = lock_process.is_running() and "local_console.py" in command_text
        except Exception:
            lock_is_valid = False
        if lock_is_valid:
            return 1
        try:
            lock_path.unlink()
        except OSError:
            return 1
        lock_descriptor = acquire_instance_lock(lock_path)
        if lock_descriptor is None:
            return 1

    token = secrets.token_urlsafe(32)
    port = find_available_port()
    url = f"http://127.0.0.1:{port}/?token={token}"
    supervisor = LocalProcessSupervisor(
        repo_root=PROJECT_ROOT,
        state_path=state_path,
        log_dir=PROJECT_ROOT / "logs" / "local-console",
        output_sink=lambda line: print(line, flush=True),
    )
    write_controller_state(
        state_path,
        pid=os.getpid(),
        create_time=psutil.Process(os.getpid()).create_time(),
        port=port,
        token=token,
    )
    if not args.no_browser:
        opener = threading.Timer(0.7, lambda: webbrowser.open(url))
        opener.daemon = True
        opener.start()
    try:
        uvicorn.run(
            build_app(supervisor=supervisor, token=token),
            host="127.0.0.1",
            port=port,
            log_level="warning",
        )
    finally:
        clear_controller_state(state_path, os.getpid())
        release_instance_lock(lock_path, lock_descriptor)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
