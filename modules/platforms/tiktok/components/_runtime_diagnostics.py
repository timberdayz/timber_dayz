from __future__ import annotations

from collections import deque
from typing import Any


_ATTACHED_ATTR = "_tiktok_runtime_diag_attached"
_BUFFER_ATTR = "_tiktok_runtime_diag_buffer"
_MAX_EVENTS = 20


def _ensure_buffer(page: Any) -> deque[dict[str, str]]:
    buffer = getattr(page, _BUFFER_ATTR, None)
    if buffer is None:
        buffer = deque(maxlen=_MAX_EVENTS)
        setattr(page, _BUFFER_ATTR, buffer)
    return buffer


def attach_tiktok_runtime_diagnostics(page: Any) -> None:
    if getattr(page, _ATTACHED_ATTR, False):
        return

    buffer = _ensure_buffer(page)

    def _push(event_type: str, payload: dict[str, str]) -> None:
        item = {"type": event_type}
        item.update(payload)
        buffer.append(item)

    def _on_console(message: Any) -> None:
        try:
            level = str(message.type or "").strip().lower()
            if level not in {"error", "warning"}:
                return
            text = str(message.text or "").strip()
            location = ""
            try:
                location_obj = message.location or {}
                url = str(location_obj.get("url") or "").strip()
                line_number = str(location_obj.get("lineNumber") or "").strip()
                if url:
                    location = f"{url}:{line_number}" if line_number else url
            except Exception:
                location = ""
            _push("console", {"level": level, "text": text[:400], "location": location[:200]})
        except Exception:
            return

    def _on_request_failed(request: Any) -> None:
        try:
            failure = ""
            try:
                failure_obj = request.failure or {}
                failure = str(failure_obj.get("errorText") or "").strip()
            except Exception:
                failure = ""
            _push(
                "requestfailed",
                {
                    "method": str(request.method or "").strip(),
                    "url": str(request.url or "").strip()[:400],
                    "failure": failure[:200],
                },
            )
        except Exception:
            return

    def _on_response(response: Any) -> None:
        try:
            status = int(response.status)
        except Exception:
            return
        if status < 400:
            return
        try:
            request = response.request
            _push(
                "response",
                {
                    "status": str(status),
                    "method": str(getattr(request, "method", "") or "").strip(),
                    "url": str(response.url or "").strip()[:400],
                },
            )
        except Exception:
            return

    page.on("console", _on_console)
    page.on("requestfailed", _on_request_failed)
    page.on("response", _on_response)
    setattr(page, _ATTACHED_ATTR, True)


async def snapshot_tiktok_runtime_diagnostics(page: Any) -> dict[str, Any]:
    current_url = str(getattr(page, "url", "") or "").strip()
    ready_state = "unknown"
    title = ""
    try:
        ready_state = str(await page.evaluate("() => document.readyState") or "unknown").strip()
    except Exception:
        ready_state = "unknown"
    try:
        title = str(await page.title() or "").strip()
    except Exception:
        title = ""

    events = list(getattr(page, _BUFFER_ATTR, []) or [])
    return {
        "url": current_url,
        "ready_state": ready_state,
        "title": title,
        "events": events[-10:],
    }


async def log_tiktok_runtime_diagnostics(page: Any, logger: Any, *, label: str) -> None:
    if logger is None:
        return
    snapshot = await snapshot_tiktok_runtime_diagnostics(page)
    logger.info(
        "tiktok_runtime_diag[%s] url=%s readyState=%s title=%s",
        label,
        snapshot.get("url") or "UNKNOWN",
        snapshot.get("ready_state") or "unknown",
        snapshot.get("title") or "",
    )
    for event in snapshot.get("events") or []:
        event_type = str(event.get("type") or "").strip()
        if event_type == "console":
            logger.info(
                "tiktok_runtime_diag[%s] console level=%s text=%s location=%s",
                label,
                event.get("level") or "",
                event.get("text") or "",
                event.get("location") or "",
            )
            continue
        if event_type == "requestfailed":
            logger.info(
                "tiktok_runtime_diag[%s] requestfailed method=%s url=%s failure=%s",
                label,
                event.get("method") or "",
                event.get("url") or "",
                event.get("failure") or "",
            )
            continue
        if event_type == "response":
            logger.info(
                "tiktok_runtime_diag[%s] response status=%s method=%s url=%s",
                label,
                event.get("status") or "",
                event.get("method") or "",
                event.get("url") or "",
            )
