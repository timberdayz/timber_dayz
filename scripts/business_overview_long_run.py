#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from statistics import mean
from typing import Any

import httpx


BASE_URL = "http://127.0.0.1:8001"
OUTPUT_DIR = Path("temp/outputs")
TIMEOUT_SECONDS = 70.0
ADMIN_USERNAME = os.getenv("PERF_LOGIN_USERNAME", "perf_load_admin")
ADMIN_PASSWORD = os.getenv("PERF_LOGIN_PASSWORD", "PerfLoadAdmin#2026")

BUSINESS_OVERVIEW_ENDPOINTS = [
    {
        "name": "kpi",
        "path": "/api/dashboard/business-overview/kpi",
        "params": {"month": "2026-03-01"},
    },
    {
        "name": "comparison",
        "path": "/api/dashboard/business-overview/comparison",
        "params": {"granularity": "monthly", "date": "2026-03"},
    },
    {
        "name": "shop_racing",
        "path": "/api/dashboard/business-overview/shop-racing",
        "params": {"granularity": "monthly", "date": "2026-03-01", "group_by": "shop"},
    },
    {
        "name": "traffic_ranking",
        "path": "/api/dashboard/business-overview/traffic-ranking",
        "params": {
            "granularity": "monthly",
            "dimension": "shop",
            "date_value": "2026-03-01",
        },
    },
    {
        "name": "operational_metrics",
        "path": "/api/dashboard/business-overview/operational-metrics",
        "params": {"month": "2026-03-01"},
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


def summarize_rounds(rounds: list[dict[str, Any]]) -> dict[str, Any]:
    page_elapsed = [float(item.get("elapsed_ms", 0.0)) for item in rounds]
    successful_rounds = sum(1 for item in rounds if item.get("ok"))
    endpoint_buckets: dict[str, list[dict[str, Any]]] = {}
    failure_samples: list[str] = []

    for item in rounds:
        for endpoint in item.get("endpoint_results", []):
            endpoint_buckets.setdefault(endpoint["name"], []).append(endpoint)
            if not endpoint.get("ok") and len(failure_samples) < 10:
                failure_samples.append(
                    endpoint.get("error")
                    or f"HTTP {endpoint.get('status', 0)} {endpoint.get('name')}"
                )

    endpoint_summary: dict[str, Any] = {}
    for name, items in endpoint_buckets.items():
        elapsed = [float(item.get("elapsed_ms", 0.0)) for item in items]
        statuses: dict[str, int] = {}
        for item in items:
            key = str(item.get("status", 0))
            statuses[key] = statuses.get(key, 0) + 1
        endpoint_summary[name] = {
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

    return {
        "round_count": len(rounds),
        "successful_rounds": successful_rounds,
        "failed_rounds": len(rounds) - successful_rounds,
        "page_success_rate": (
            round(successful_rounds / len(rounds) * 100.0, 2) if rounds else 0.0
        ),
        "page_avg_ms": round(mean(page_elapsed), 2) if page_elapsed else 0.0,
        "page_p95_ms": (
            round(percentile(page_elapsed, 0.95), 2) if page_elapsed else 0.0
        ),
        "endpoints": endpoint_summary,
        "failure_samples": failure_samples,
    }


def summarize_resource_samples(samples: list[dict[str, Any]]) -> dict[str, Any]:
    if not samples:
        return {
            "sample_count": 0,
            "cpu_peak": 0.0,
            "memory_peak": 0.0,
            "thread_peak": 0,
            "sync_pool_checked_out_peak": 0,
            "sync_pool_overflow_peak": 0,
            "async_pool_checked_out_peak": 0,
            "async_pool_overflow_peak": 0,
        }

    return {
        "sample_count": len(samples),
        "cpu_peak": max(float(item.get("cpu_usage", 0.0)) for item in samples),
        "memory_peak": max(float(item.get("memory_usage", 0.0)) for item in samples),
        "thread_peak": max(int(item.get("thread_count", 0) or 0) for item in samples),
        "sync_pool_checked_out_peak": max(
            int((item.get("sync_pool") or {}).get("checked_out", 0) or 0)
            for item in samples
        ),
        "sync_pool_overflow_peak": max(
            int((item.get("sync_pool") or {}).get("overflow", 0) or 0)
            for item in samples
        ),
        "async_pool_checked_out_peak": max(
            int((item.get("async_pool") or {}).get("checked_out", 0) or 0)
            for item in samples
        ),
        "async_pool_overflow_peak": max(
            int((item.get("async_pool") or {}).get("overflow", 0) or 0)
            for item in samples
        ),
    }


async def run_endpoint(
    client: httpx.AsyncClient, endpoint: dict[str, Any]
) -> dict[str, Any]:
    started = asyncio.get_running_loop().time()
    try:
        response = await client.get(
            f"{BASE_URL}{endpoint['path']}", params=endpoint["params"]
        )
        elapsed_ms = (asyncio.get_running_loop().time() - started) * 1000
        return {
            "name": endpoint["name"],
            "status": response.status_code,
            "ok": response.status_code == 200,
            "elapsed_ms": elapsed_ms,
        }
    except Exception as exc:
        elapsed_ms = (asyncio.get_running_loop().time() - started) * 1000
        return {
            "name": endpoint["name"],
            "status": 0,
            "ok": False,
            "elapsed_ms": elapsed_ms,
            "error": str(exc),
        }


async def login_admin(client: httpx.AsyncClient) -> dict[str, str]:
    response = await client.post(
        f"{BASE_URL}/api/auth/login",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
    )
    response.raise_for_status()
    payload = response.json()
    return {"Authorization": f"Bearer {payload['access_token']}"}


async def sample_resources(
    client: httpx.AsyncClient, headers: dict[str, str]
) -> dict[str, Any]:
    resource_response = await client.get(
        f"{BASE_URL}/api/system/resource-usage", headers=headers
    )
    pool_response = await client.get(
        f"{BASE_URL}/api/system/db-pool-stats", headers=headers
    )
    resource_response.raise_for_status()
    pool_response.raise_for_status()
    resource_payload = resource_response.json()
    pool_payload = pool_response.json()
    return {
        "cpu_usage": resource_payload.get("cpu_usage", 0.0),
        "memory_usage": resource_payload.get("memory_usage", 0.0),
        "process_count": resource_payload.get("process_count", 0),
        "thread_count": resource_payload.get("thread_count", 0),
        "sync_pool": pool_payload.get("sync_pool", {}),
        "async_pool": pool_payload.get("async_pool", {}),
    }


async def run_round(client: httpx.AsyncClient, round_number: int) -> dict[str, Any]:
    started = asyncio.get_running_loop().time()
    endpoint_results = await asyncio.gather(
        *(run_endpoint(client, endpoint) for endpoint in BUSINESS_OVERVIEW_ENDPOINTS)
    )
    elapsed_ms = (asyncio.get_running_loop().time() - started) * 1000
    return {
        "round": round_number,
        "ok": all(item["ok"] for item in endpoint_results),
        "elapsed_ms": elapsed_ms,
        "endpoint_results": endpoint_results,
    }


async def run_long(duration_seconds: int, interval_seconds: int) -> dict[str, Any]:
    rounds: list[dict[str, Any]] = []
    resource_samples: list[dict[str, Any]] = []
    timeout = httpx.Timeout(TIMEOUT_SECONDS)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + duration_seconds

    async with httpx.AsyncClient(timeout=timeout) as client:
        admin_headers = await login_admin(client)
        round_number = 1
        while loop.time() < deadline:
            started = loop.time()
            rounds.append(await run_round(client, round_number))
            try:
                resource_samples.append(await sample_resources(client, admin_headers))
            except Exception as exc:
                resource_samples.append({"sampling_error": str(exc)})
            round_number += 1
            elapsed = loop.time() - started
            sleep_for = max(0.0, interval_seconds - elapsed)
            if sleep_for:
                await asyncio.sleep(sleep_for)

    summary = summarize_rounds(rounds)
    resources = summarize_resource_samples(resource_samples)
    return {
        "duration_seconds": duration_seconds,
        "interval_seconds": interval_seconds,
        "rounds": rounds,
        "summary": summary,
        "resource_samples": resource_samples,
        "resource_summary": resources,
    }


def write_output(payload: dict[str, Any]) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / "business_overview_long_run_latest.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stable BusinessOverview long-run probe"
    )
    parser.add_argument("--duration-seconds", type=int, default=600)
    parser.add_argument("--interval-seconds", type=int, default=30)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = asyncio.run(run_long(args.duration_seconds, args.interval_seconds))
    path = write_output(payload)
    print(str(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
