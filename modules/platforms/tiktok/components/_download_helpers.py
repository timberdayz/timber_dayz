from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_EXPORT_TIMEOUT_MS = 90000


@dataclass
class DownloadCapture:
    latest_download: Any | None
    page_handler: Any | None
    context_handler: Any | None


def resolve_export_timeout_ms(
    config: dict[str, Any] | None,
    *,
    default_timeout_ms: int = DEFAULT_EXPORT_TIMEOUT_MS,
) -> int:
    cfg = config or {}
    try:
        timeout = int(cfg.get("export_timeout_ms") or 0)
    except Exception:
        timeout = 0
    return timeout if timeout > 0 else default_timeout_ms


def create_download_capture(page: Any) -> DownloadCapture:
    capture = DownloadCapture(latest_download=None, page_handler=None, context_handler=None)

    def _page_handler(download: Any) -> None:
        capture.latest_download = download

    def _context_handler(download: Any) -> None:
        capture.latest_download = download

    try:
        page.on("download", _page_handler)
        capture.page_handler = _page_handler
    except Exception:
        capture.page_handler = None

    try:
        page.context.on("download", _context_handler)
        capture.context_handler = _context_handler
    except Exception:
        capture.context_handler = None

    return capture


def cleanup_download_capture(page: Any, capture: DownloadCapture) -> None:
    if capture.page_handler is not None:
        try:
            page.off("download", capture.page_handler)
        except Exception:
            pass

    if capture.context_handler is not None:
        try:
            page.context.off("download", capture.context_handler)
        except Exception:
            pass


async def save_download_to_target(download: Any, target: Path) -> Path | None:
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        await download.save_as(str(target))
    except Exception:
        return None

    try:
        if not target.exists():
            return None
        if target.stat().st_size <= 0:
            return None
    except OSError:
        return None

    return target
