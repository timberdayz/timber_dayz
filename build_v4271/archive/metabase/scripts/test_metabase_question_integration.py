#!/usr/bin/env python3
"""
Historical only.
This script is not part of the runtime path for PostgreSQL Dashboard.

Metabase Question 集成测试（可选）

前提：后端与 Metabase 已启动（如 docker-compose 或本地 run.py）。
用途：验证按名称查 Question ID 后，Dashboard API 能正常返回数据。

使用方式：
    python scripts/test_metabase_question_integration.py [--base-url http://localhost:8000]
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    import httpx
except ImportError:
    print("[SKIP] httpx not installed; pip install httpx to run this script")
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="Test Dashboard/Metabase Question API integration")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Backend base URL")
    parser.add_argument("--no-auth", action="store_true", help="Skip auth (for /health or public endpoints)")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    client = httpx.Client(timeout=15.0)
    try:
        # 1. 后端健康
        try:
            r = client.get(f"{base}/health")
        except httpx.ConnectError as e:
            print(f"[SKIP] Backend not reachable at {base}: {e}")
            print("       Start backend (e.g. python run.py --backend-only) then re-run this script.")
            return 0
        if r.status_code != 200:
            print(f"[FAIL] Backend health: {r.status_code}")
            return 1
        print("[OK] Backend health")

        # 2. Metabase 代理健康（可选）
        r2 = client.get(f"{base}/api/metabase/health")
        if r2.status_code == 200 and r2.json().get("healthy"):
            print("[OK] Metabase proxy health")
        else:
            print("[WARN] Metabase not healthy or not configured; Question API may still use env fallback")

        # 3. Dashboard KPI（需按名称查 Question；未登录可能 401）
        r3 = client.get(f"{base}/api/dashboard/business-overview/kpi", params={"month": "2025-01-01"})
        if r3.status_code == 200:
            data = r3.json()
            if data.get("success") and data.get("data") is not None:
                print("[OK] Dashboard KPI returns data (name-based Question ID resolved)")
            else:
                print("[WARN] KPI returned 200 but success=False or data=None:", data.get("message"))
        elif r3.status_code == 401:
            print("[INFO] KPI returned 401 (login required); name resolution not tested here")
        else:
            print(f"[WARN] KPI: {r3.status_code} - {r3.text[:200]}")
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
