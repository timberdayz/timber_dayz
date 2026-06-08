from __future__ import annotations

import os
from typing import Any

from cryptography.fernet import Fernet


def _parse_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _collect_encryption_health() -> dict[str, str]:
    key = os.getenv("ACCOUNT_ENCRYPTION_KEY", "").strip()
    if not key:
        return {"status": "error", "reason": "ACCOUNT_ENCRYPTION_KEY missing"}

    try:
        Fernet(key.encode())
    except Exception as exc:
        return {"status": "error", "reason": f"ACCOUNT_ENCRYPTION_KEY invalid: {exc}"}

    return {"status": "configured"}


def _collect_playwright_health() -> dict[str, str]:
    try:
        from playwright.async_api import async_playwright  # noqa: F401
    except Exception as exc:
        return {"status": "error", "reason": f"playwright unavailable: {exc}"}
    return {"status": "available"}


def _collect_redis_health(settings: Any) -> dict[str, str]:
    redis_url = os.getenv("REDIS_URL", "").strip() or str(
        getattr(settings, "REDIS_URL", "") or ""
    ).strip()
    if not redis_url:
        return {"status": "error", "reason": "REDIS_URL missing"}

    try:
        import redis

        client = redis.from_url(
            redis_url,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        client.ping()
    except Exception as exc:
        return {"status": "error", "reason": f"redis unavailable: {exc}"}

    return {"status": "connected"}


def collect_collection_runtime_health(app: Any, settings: Any) -> dict[str, Any]:
    app_state = getattr(app, "state", None)
    runtime_mode = str(
        getattr(app_state, "runtime_mode", "") or os.getenv("APP_RUNTIME_MODE", "")
    ).strip().lower()
    deployment_role = os.getenv("DEPLOYMENT_ROLE", "").strip().lower()
    enable_collection = _parse_bool(os.getenv("ENABLE_COLLECTION"), default=True)

    leader_lock_acquired = getattr(app_state, "collection_leader_lock_acquired", None)
    if leader_lock_acquired is True:
        leader_lock_status = "acquired"
    elif leader_lock_acquired is False:
        leader_lock_status = "standby"
    else:
        leader_lock_status = "unknown"

    scheduler_expected = enable_collection and deployment_role in {"collector", "local", "all"}
    queue_runner_expected = scheduler_expected

    scheduler = getattr(app_state, "collection_scheduler", None)
    queue_runner = getattr(app_state, "collection_queue_runner", None)

    checks: dict[str, dict[str, str]] = {
        "redis": _collect_redis_health(settings),
        "encryption": _collect_encryption_health(),
        "playwright": _collect_playwright_health(),
        "leader_lock": {"status": leader_lock_status},
    }

    if not scheduler_expected:
        checks["scheduler"] = {"status": "disabled"}
    elif leader_lock_status == "standby":
        checks["scheduler"] = {"status": "standby"}
    else:
        checks["scheduler"] = {
            "status": "running" if scheduler is not None else "error"
        }

    if not queue_runner_expected:
        checks["queue_runner"] = {"status": "disabled"}
    elif leader_lock_status == "standby":
        checks["queue_runner"] = {"status": "standby"}
    else:
        checks["queue_runner"] = {
            "status": "running" if queue_runner is not None else "error"
        }

    ready = all(
        item.get("status") not in {"error", "missing"}
        for item in checks.values()
    )

    return {
        "status": "ready" if ready else "unready",
        "runtime_mode": runtime_mode or "collector",
        "deployment_role": deployment_role or "collector",
        "checks": checks,
    }
