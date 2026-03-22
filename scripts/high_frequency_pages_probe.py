#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any

import httpx

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

BASE_URL = os.getenv("PERF_BASE_URL", "http://127.0.0.1:8001")
ADMIN_USERNAME = os.getenv("PERF_LOGIN_USERNAME", "perf_load_admin")
ADMIN_PASSWORD = os.getenv("PERF_LOGIN_PASSWORD", "PerfLoadAdmin#2026")
OUTPUT_DIR = Path("temp/outputs")
CURRENT_YEAR_MONTH = datetime.now().strftime("%Y-%m")
CURRENT_YEAR = datetime.now().strftime("%Y")

PAGE_SCENARIOS = [
    {
        "name": "user_management",
        "requests": [
            {"path": "/api/users/", "params": {"page": 1, "page_size": 20}},
            {"path": "/api/roles/"},
        ],
    },
    {
        "name": "user_approval",
        "requests": [
            {"path": "/api/users/pending", "params": {"page": 1, "page_size": 20}},
            {"path": "/api/roles/"},
        ],
    },
    {
        "name": "role_management",
        "requests": [
            {"path": "/api/roles/"},
            {"path": "/api/roles/permissions/available"},
        ],
    },
    {
        "name": "account_management",
        "requests": [
            {"path": "/api/accounts/"},
            {"path": "/api/accounts/stats/summary"},
        ],
    },
    {
        "name": "data_sync_files",
        "requests": [
            {"path": "/api/data-sync/files", "params": {"page": 1, "page_size": 20}},
            {"path": "/api/data-sync/governance/stats"},
            {"path": "/api/data-sync/tasks", "params": {"page": 1, "page_size": 20}},
        ],
    },
    {
        "name": "data_quarantine",
        "requests": [
            {"path": "/api/data-quarantine/files"},
            {"path": "/api/data-quarantine/stats"},
        ],
    },
    {
        "name": "collection_tasks",
        "requests": [
            {"path": "/api/collection/tasks"},
            {"path": "/api/collection/accounts"},
        ],
    },
    {
        "name": "collection_history",
        "requests": [
            {"path": "/api/collection/history", "params": {"page": 1, "page_size": 20}},
            {"path": "/api/collection/history/stats"},
        ],
    },
    {
        "name": "system_notifications",
        "requests": [
            {"path": "/api/notifications", "params": {"page": 1, "page_size": 20}},
        ],
    },
    {
        "name": "sessions",
        "requests": [
            {"path": "/api/users/me/sessions"},
        ],
    },
    {
        "name": "notification_preferences",
        "requests": [
            {"path": "/api/users/me/notification-preferences"},
        ],
    },
    {
        "name": "system_config",
        "requests": [
            {"path": "/api/system/config"},
        ],
    },
    {
        "name": "database_config",
        "requests": [
            {"path": "/api/system/database/config"},
        ],
    },
    {
        "name": "security_settings",
        "requests": [
            {"path": "/api/system/security/password-policy"},
            {"path": "/api/system/security/login-restrictions"},
            {"path": "/api/system/security/ip-whitelist"},
            {"path": "/api/system/security/session-config"},
            {"path": "/api/system/security/2fa-config"},
        ],
    },
    {
        "name": "system_logs",
        "requests": [
            {"path": "/api/system/logs", "params": {"page": 1, "page_size": 20}},
        ],
    },
    {
        "name": "data_backup",
        "requests": [
            {"path": "/api/system/backup/backups"},
            {"path": "/api/system/backup/config"},
        ],
    },
    {
        "name": "system_maintenance",
        "requests": [
            {"path": "/api/system/maintenance/cache/status"},
            {"path": "/api/system/maintenance/data/status"},
            {"path": "/api/system/maintenance/upgrade/check"},
        ],
    },
    {
        "name": "account_alignment",
        "requests": [
            {"path": "/api/account-alignment/stats"},
            {"path": "/api/account-alignment/distinct-raw-stores"},
            {"path": "/api/account-alignment/list-aliases"},
        ],
    },
    {
        "name": "notification_config",
        "requests": [
            {"path": "/api/system/notification/smtp-config"},
            {"path": "/api/system/notification/templates"},
            {"path": "/api/system/notification/alert-rules"},
        ],
    },
    {
        "name": "permission_management",
        "requests": [
            {"path": "/api/system/permissions"},
            {"path": "/api/roles/"},
            {"path": "/api/users/", "params": {"page": 1, "page_size": 20}},
        ],
    },
    {
        "name": "data_sync_templates",
        "requests": [
            {"path": "/api/data-sync/platforms"},
            {"path": "/api/data-sync/governance/detailed-coverage"},
            {"path": "/api/field-mapping/governance/overview"},
            {"path": "/api/field-mapping/governance/missing-templates"},
            {"path": "/api/field-mapping/templates/list"},
            {"path": "/api/data-sync/files", "params": {"page": 1, "page_size": 20}},
        ],
    },
    {
        "name": "expense_management",
        "requests": [
            {"path": "/api/expenses/shops"},
            {
                "path": "/api/expenses",
                "params": {
                    "year_month": CURRENT_YEAR_MONTH,
                    "page": 1,
                    "page_size": 20,
                },
            },
            {"path": "/api/expenses/summary/yearly", "params": {"year": CURRENT_YEAR}},
        ],
    },
]


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * p
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return ordered[lower]
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def summarize_page_results(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in results:
        grouped.setdefault(item["page"], []).append(item)

    summary: dict[str, dict[str, Any]] = {}
    for name, items in grouped.items():
        elapsed = [float(item.get("elapsed_ms", 0.0)) for item in items]
        statuses: dict[str, int] = {}
        for item in items:
            key = str(item.get("status", 0))
            statuses[key] = statuses.get(key, 0) + 1
        summary[name] = {
            "count": len(items),
            "failed": sum(1 for item in items if not item.get("ok")),
            "success_rate": (
                round(
                    sum(1 for item in items if item.get("ok")) / len(items) * 100.0, 2
                )
                if items
                else 0.0
            ),
            "avg_ms": round(mean(elapsed), 2) if elapsed else 0.0,
            "p95_ms": round(percentile(elapsed, 0.95), 2) if elapsed else 0.0,
            "statuses": statuses,
        }
    return summary


async def login_admin(client: httpx.AsyncClient) -> dict[str, str]:
    from backend.services.auth_service import auth_service

    for _ in range(3):
        try:
            response = await client.post(
                f"{BASE_URL}/api/auth/login",
                json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
            )
            response.raise_for_status()
            payload = response.json()
            return {"Authorization": f"Bearer {payload['access_token']}"}
        except Exception:
            await asyncio.sleep(1)
    token = auth_service.create_access_token(
        {
            "user_id": 285,
            "username": ADMIN_USERNAME,
            "roles": ["admin"],
        }
    )
    return {"Authorization": f"Bearer {token}"}


async def request_once(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    page_name: str,
    spec: dict[str, Any],
) -> dict[str, Any]:
    started = asyncio.get_running_loop().time()
    try:
        response = await client.get(
            f"{BASE_URL}{spec['path']}",
            params=spec.get("params"),
            headers=headers,
        )
        elapsed_ms = (asyncio.get_running_loop().time() - started) * 1000
        return {
            "page": page_name,
            "path": spec["path"],
            "status": response.status_code,
            "ok": response.status_code == 200,
            "elapsed_ms": elapsed_ms,
        }
    except Exception as exc:
        elapsed_ms = (asyncio.get_running_loop().time() - started) * 1000
        return {
            "page": page_name,
            "path": spec["path"],
            "status": 0,
            "ok": False,
            "elapsed_ms": elapsed_ms,
            "error": str(exc),
        }


async def run_probe(rounds: int) -> dict[str, Any]:
    timeout = httpx.Timeout(30.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        headers = await login_admin(client)
        results: list[dict[str, Any]] = []
        for _ in range(rounds):
            batch = []
            for scenario in PAGE_SCENARIOS:
                for spec in scenario["requests"]:
                    batch.append(request_once(client, headers, scenario["name"], spec))
            results.extend(await asyncio.gather(*batch))
    return {
        "rounds": rounds,
        "results": results,
        "summary": summarize_page_results(results),
    }


def write_output(payload: dict[str, Any]) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / "high_frequency_pages_probe_latest.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe next batch of real high-frequency pages"
    )
    parser.add_argument("--rounds", type=int, default=5)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = asyncio.run(run_probe(args.rounds))
    path = write_output(payload)
    print(str(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
