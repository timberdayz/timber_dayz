#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Smoke-check PostgreSQL dashboard routes.

Example:
    python scripts/smoke_postgresql_dashboard_routes.py --base-url http://localhost:8000
"""

from __future__ import annotations

import argparse
import json
from typing import Any

import httpx


def build_smoke_plan() -> list[dict[str, Any]]:
    return [
        {
            "name": "business_overview_kpi",
            "path": "/api/dashboard/business-overview/kpi",
            "params": {"month": "2026-03-01"},
        },
        {
            "name": "business_overview_comparison",
            "path": "/api/dashboard/business-overview/comparison",
            "params": {"granularity": "monthly", "date": "2026-03-01"},
        },
        {
            "name": "business_overview_shop_racing",
            "path": "/api/dashboard/business-overview/shop-racing",
            "params": {"granularity": "monthly", "date": "2026-03-01", "group_by": "shop"},
        },
        {
            "name": "business_overview_operational_metrics",
            "path": "/api/dashboard/business-overview/operational-metrics",
            "params": {"month": "2026-03-01"},
        },
        {
            "name": "annual_summary_kpi",
            "path": "/api/dashboard/annual-summary/kpi",
            "params": {"granularity": "yearly", "period": "2026"},
        },
        {
            "name": "annual_summary_trend",
            "path": "/api/dashboard/annual-summary/trend",
            "params": {"granularity": "yearly", "period": "2026"},
        },
        {
            "name": "annual_summary_platform_share",
            "path": "/api/dashboard/annual-summary/platform-share",
            "params": {"granularity": "yearly", "period": "2026"},
        },
        {
            "name": "annual_summary_by_shop",
            "path": "/api/dashboard/annual-summary/by-shop",
            "params": {"granularity": "yearly", "period": "2026"},
        },
        {
            "name": "annual_summary_target_completion",
            "path": "/api/dashboard/annual-summary/target-completion",
            "params": {"granularity": "yearly", "period": "2026"},
        },
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-check PostgreSQL dashboard routes")
    parser.add_argument("--base-url", required=True, help="Base URL, e.g. http://localhost:8000")
    parser.add_argument("--timeout", type=float, default=10.0, help="Per-request timeout in seconds")
    return parser.parse_args()


def main(argv: list[str] | None = None) -> int:
    if argv is not None:
        import sys
        sys.argv = [sys.argv[0], *argv]

    args = parse_args()
    base_url = args.base_url.rstrip("/")
    plan = build_smoke_plan()

    overall_ok = True
    with httpx.Client(timeout=args.timeout) as client:
        for step in plan:
            url = f"{base_url}{step['path']}"
            response = client.get(url, params=step["params"])
            ok = response.status_code == 200
            if not ok:
                overall_ok = False
            try:
                body = response.json()
            except Exception:
                body = {"raw": response.text[:200]}
            print(
                json.dumps(
                    {
                        "name": step["name"],
                        "url": url,
                        "status_code": response.status_code,
                        "ok": ok,
                        "body_preview": body,
                    },
                    ensure_ascii=False,
                )
            )

    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
