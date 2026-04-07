#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from statistics import mean
from typing import Any

import httpx


BASE_URL = "http://127.0.0.1:8001"
OUTPUT_DIR = Path("temp/outputs")

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
        "params": {"granularity": "monthly", "dimension": "shop", "date_value": "2026-03-01"},
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


def summarize_probe_results(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in results:
        grouped.setdefault(item["name"], []).append(item)

    summary: dict[str, dict[str, Any]] = {}
    for name, items in grouped.items():
        elapsed = [float(item.get("elapsed_ms", 0.0)) for item in items]
        summary[name] = {
            "count": len(items),
            "failed": sum(1 for item in items if not item.get("ok")),
            "success_rate": round(sum(1 for item in items if item.get("ok")) / len(items) * 100.0, 2) if items else 0.0,
            "avg_ms": round(mean(elapsed), 2) if elapsed else 0.0,
            "p95_ms": round(percentile(elapsed, 0.95), 2) if elapsed else 0.0,
            "statuses": {},
        }
        statuses: dict[str, int] = {}
        for item in items:
            key = str(item.get("status", 0))
            statuses[key] = statuses.get(key, 0) + 1
        summary[name]["statuses"] = statuses
    return summary


async def probe_once(client: httpx.AsyncClient, endpoint: dict[str, Any]) -> dict[str, Any]:
    started = asyncio.get_running_loop().time()
    try:
        response = await client.get(f"{BASE_URL}{endpoint['path']}", params=endpoint["params"])
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


async def run_probe(rounds: int) -> dict[str, Any]:
    timeout = httpx.Timeout(70.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        results: list[dict[str, Any]] = []
        for _ in range(rounds):
            batch = await asyncio.gather(*(probe_once(client, endpoint) for endpoint in BUSINESS_OVERVIEW_ENDPOINTS))
            results.extend(batch)
    return {
        "rounds": rounds,
        "results": results,
        "summary": summarize_probe_results(results),
    }


def write_output(payload: dict[str, Any]) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / "business_overview_split_probe_latest.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BusinessOverview split probe")
    parser.add_argument("--rounds", type=int, default=10)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = asyncio.run(run_probe(args.rounds))
    path = write_output(payload)
    print(str(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
