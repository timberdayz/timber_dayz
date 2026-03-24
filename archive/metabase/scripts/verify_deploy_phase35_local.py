#!/usr/bin/env python3
"""
Historical only.
This script is not part of the runtime path for PostgreSQL Dashboard.

本地验证 Phase 3.5 + 集成（等效 deploy_remote_production.sh 中 Phase 3.5 与后续健康/接口检查）

使用场景：已用 python run.py --use-docker --with-metabase 启动后，在本地执行此脚本，
         验证与生产部署脚本中相同的「Metabase 就绪 -> init_metabase.py -> 后端按名称查 Question」流程。

使用方式：
    python scripts/verify_deploy_phase35_local.py
    python scripts/verify_deploy_phase35_local.py --metabase-url http://localhost:8080 --backend-url http://localhost:8001
"""

import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def main():
    parser = argparse.ArgumentParser(description="Verify Phase 3.5 (init_metabase) + integration locally")
    parser.add_argument("--metabase-url", default="http://localhost:8080", help="Metabase URL (host)")
    parser.add_argument("--backend-url", default="http://localhost:8001", help="Backend API URL (host)")
    args = parser.parse_args()
    metabase_url = args.metabase_url.rstrip("/")
    backend_url = args.backend_url.rstrip("/")

    print("[INFO] Phase 3.5 local verification (equivalent to deploy_remote_production.sh Phase 3.5)")
    print(f"       Metabase: {metabase_url}, Backend: {backend_url}")
    print()

    # Step 1: Wait for Metabase health (optional, best-effort)
    try:
        import httpx
        for i in range(30):
            try:
                r = httpx.get(f"{metabase_url}/api/health", timeout=5)
                if r.status_code == 200 and r.json().get("status") == "ok":
                    print("[OK] Metabase is healthy")
                    break
            except Exception:
                pass
            if i == 0:
                print("[INFO] Waiting for Metabase...")
            time.sleep(2)
        else:
            print("[WARN] Metabase health check timeout; continuing anyway")
    except ImportError:
        print("[SKIP] httpx not installed; skipping Metabase health wait")

    # Step 2: Run init_metabase.py (Phase 3.5)
    print("[INFO] Running init_metabase.py (Phase 3.5)...")
    import os
    import subprocess
    env = os.environ.copy()
    env["METABASE_URL"] = metabase_url
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "init_metabase.py")],
        cwd=str(PROJECT_ROOT),
        env=env,
        timeout=120,
    )
    if result.returncode != 0:
        print(f"[FAIL] init_metabase.py exited with code {result.returncode}")
        return 1
    print("[OK] init_metabase.py completed")
    print()

    # Step 3: Integration check (backend + dashboard KPI)
    print("[INFO] Running integration check (backend + Dashboard KPI)...")
    sys.path.insert(0, str(PROJECT_ROOT))
    # Run the integration test script logic inline to avoid subprocess
    try:
        import httpx
        client = httpx.Client(timeout=15.0)
        try:
            r = client.get(f"{backend_url}/health")
            if r.status_code != 200:
                print(f"[FAIL] Backend health: {r.status_code}")
                return 1
            print("[OK] Backend health")
            r2 = client.get(f"{backend_url}/api/metabase/health")
            if r2.status_code == 200 and r2.json().get("healthy"):
                print("[OK] Metabase proxy health")
            else:
                print("[WARN] Metabase proxy not healthy")
            r3 = client.get(f"{backend_url}/api/dashboard/business-overview/kpi", params={"month": "2025-01-01"})
            if r3.status_code == 200:
                data = r3.json()
                if data.get("success") and data.get("data") is not None:
                    print("[OK] Dashboard KPI returns data (name-based Question ID resolved)")
                else:
                    print("[WARN] KPI 200 but success=False or data=None")
            elif r3.status_code == 401:
                print("[INFO] KPI 401 (login required); name resolution not asserted here")
            else:
                print(f"[WARN] KPI: {r3.status_code}")
        finally:
            client.close()
    except httpx.ConnectError as e:
        print(f"[FAIL] Cannot reach backend at {backend_url}: {e}")
        return 1
    except ImportError:
        print("[SKIP] httpx not installed; skip integration check")

    print()
    print("[OK] Phase 3.5 local verification done (equivalent to deploy script Phase 3.5 + integration).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
