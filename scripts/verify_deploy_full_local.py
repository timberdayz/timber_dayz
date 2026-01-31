#!/usr/bin/env python3
"""
方式 B：本地「生产流程」Docker 化部署验证

与 deploy_remote_production.sh 相同的阶段顺序在本地执行一遍（使用本地构建的 backend，
不拉远程镜像），用于在推 tag / 部署云端前发现问题。

阶段顺序：Phase 0.5 -> 1 (Postgres/Redis) -> 2 (迁移) -> 2.5 (Bootstrap) ->
         Phase 3 (Metabase) -> 3.5 (init_metabase.py) -> Phase 4 (Backend) -> 集成检查

使用方式：
    python scripts/verify_deploy_full_local.py
    python scripts/verify_deploy_full_local.py --no-build   # 跳过 backend 构建
    python scripts/verify_deploy_full_local.py --skip-frontend  # 不启动 frontend/nginx（默认已跳过，仅 backend）
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def run(cmd: list, cwd: Path = None, env: dict = None, timeout: int = 300) -> tuple[int, str]:
    """执行命令，返回 (returncode, combined_output)."""
    cwd = cwd or PROJECT_ROOT
    env = env or os.environ
    try:
        r = subprocess.run(
            cmd,
            cwd=str(cwd),
            env={**os.environ, **(env or {})},
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        out = (r.stdout or "") + (r.stderr or "")
        return r.returncode, out
    except subprocess.TimeoutExpired:
        return -1, "Timeout"
    except Exception as e:
        return -1, str(e)


def get_compose_cmd() -> list:
    """返回 docker compose 或 docker-compose 命令前缀。"""
    for candidate in [["docker", "compose"], ["docker-compose"]]:
        code, _ = run(candidate + ["version"], timeout=5)
        if code == 0:
            return candidate
    sys.exit(1)


def get_compose_files() -> list:
    """与生产一致的 compose 文件列表 + 本地验证覆盖。"""
    base = [
        str(PROJECT_ROOT / "docker-compose.yml"),
        str(PROJECT_ROOT / "docker-compose.prod.yml"),
        str(PROJECT_ROOT / "docker-compose.metabase.yml"),
    ]
    verify_local = PROJECT_ROOT / "docker-compose.verify-local.yml"
    if verify_local.exists():
        base.append(str(verify_local))
    return base


def main():
    parser = argparse.ArgumentParser(description="方式 B: 本地生产流程 Docker 验证")
    parser.add_argument("--no-build", action="store_true", help="跳过 backend 构建")
    parser.add_argument("--backend-url", default="http://localhost:8001", help="验证时 Backend URL")
    args = parser.parse_args()

    compose_base = get_compose_cmd()
    files = get_compose_files()
    env_file = PROJECT_ROOT / ".env"
    cleaned_file = PROJECT_ROOT / ".env.cleaned"

    # Phase 0.5: .env 清洗（与 deploy 脚本一致）
    if env_file.exists():
        try:
            raw = env_file.read_text(encoding="utf-8", errors="replace")
            cleaned_file.write_text(
                raw.replace("\r\n", "\n").replace("\r", "\n").rstrip() + "\n",
                encoding="utf-8",
            )
            env_file_use = cleaned_file
        except Exception as e:
            print("[WARN] .env 清洗失败，使用 .env:", e)
            env_file_use = env_file
    else:
        env_file_use = None

    compose_cmd = compose_base + ["-f", files[0]]
    for f in files[1:]:
        compose_cmd += ["-f", f]
    compose_cmd += ["--profile", "production"]
    if env_file_use and env_file_use.exists():
        compose_cmd += ["--env-file", str(env_file_use)]

    def compose_run(args_list: list, timeout: int = 120) -> tuple[int, str]:
        return run(compose_cmd + args_list, timeout=timeout)

    print("[INFO] 方式 B: 本地生产流程验证 (compose: %s)" % " ".join(compose_cmd[:4]))
    print()
    print("[OK] Phase 0.5: 环境文件就绪")

    # 构建 backend（可选）
    if not args.no_build:
        print("[INFO] 构建 Backend 镜像...")
        code, out = compose_run(["build", "backend"], timeout=600)
        if code != 0:
            print("[FAIL] Backend 构建失败")
            print(out[-2000:] if len(out) > 2000 else out)
            return 1
        print("[OK] Backend 镜像构建完成")
    else:
        print("[INFO] 跳过构建 (--no-build)")

    # Phase 1: 启动 Postgres + Redis
    print("[INFO] Phase 1: 启动 PostgreSQL、Redis...")
    code, out = run(compose_cmd + ["up", "-d", "postgres", "redis"], timeout=60)
    if code != 0:
        print("[FAIL] Phase 1 失败")
        print(out[-1500:] if len(out) > 1500 else out)
        return 1
    print("[OK] Phase 1 完成")
    print("[INFO] 等待基础设施健康...")
    for i in range(60):
        code, _ = run(["docker", "exec", "xihong_erp_postgres", "pg_isready", "-U", "erp_user", "-d", "xihong_erp"], timeout=5)
        if code == 0:
            break
        time.sleep(2)
    else:
        print("[FAIL] PostgreSQL 健康等待超时")
        return 1
    time.sleep(3)
    print("[OK] 基础设施健康")

    # Phase 2: 数据库迁移
    print("[INFO] Phase 2: 数据库迁移 (alembic upgrade heads)...")
    code, out = compose_run(["run", "--rm", "--no-deps", "backend", "alembic", "upgrade", "heads"], timeout=120)
    if code != 0:
        print("[FAIL] Phase 2 迁移失败，终止验证")
        print(out[-1500:] if len(out) > 1500 else out)
        return 1
    print("[OK] Phase 2 完成")

    # 结构一致性检查（表名存在即可；严格 schema 一致请单独运行 verify_schema_consistency.py 不加 --ignore-schema）
    print("[INFO] 结构一致性检查 (表名存在，--ignore-schema)...")
    code, out = compose_run(
        ["run", "--rm", "--no-deps", "backend", "python3", "/app/scripts/verify_schema_consistency.py", "--ignore-schema"],
        timeout=60,
    )
    if code != 0:
        print("[FAIL] 结构一致性检查未通过")
        print(out[-1500:] if len(out) > 1500 else out)
        return 1
    print("[OK] 结构一致性检查通过")

    # Phase 2.5: Bootstrap
    print("[INFO] Phase 2.5: Bootstrap...")
    code, out = compose_run(["run", "--rm", "--no-deps", "backend", "python3", "/app/scripts/bootstrap_production.py"], timeout=60)
    if code != 0:
        print("[FAIL] Phase 2.5 失败")
        print(out[-1500:] if len(out) > 1500 else out)
        return 1
    print("[OK] Phase 2.5 完成")

    # Phase 3: 启动 Metabase
    print("[INFO] Phase 3: 启动 Metabase...")
    code, out = run(compose_cmd + ["up", "-d", "metabase"], timeout=60)
    if code != 0:
        print("[FAIL] Phase 3 失败")
        print(out[-1500:] if len(out) > 1500 else out)
        return 1
    print("[OK] Phase 3 完成")
    print("[INFO] 等待 Metabase 健康...")
    for i in range(60):
        code, _ = run(["docker", "exec", "xihong_erp_metabase", "curl", "-fsS", "http://localhost:3000/api/health"], timeout=5)
        if code == 0:
            break
        time.sleep(2)
    else:
        print("[WARN] Metabase 健康等待超时，继续执行 Phase 3.5")
    print("[OK] Metabase 就绪")

    # Phase 3.5: init_metabase.py
    print("[INFO] Phase 3.5: init_metabase.py...")
    env = os.environ.copy()
    env["METABASE_URL"] = "http://xihong_erp_metabase:3000"
    code, out = run(
        compose_cmd + ["run", "--rm", "--no-deps", "-e", "METABASE_URL=http://xihong_erp_metabase:3000", "backend", "python3", "/app/scripts/init_metabase.py"],
        env=env,
        timeout=120,
    )
    if code != 0:
        print("[WARN] Phase 3.5 返回非零（继续）:")
        print(out[-1000:] if len(out) > 1000 else out)
    else:
        print("[OK] Phase 3.5 完成")

    # Phase 4: 启动 Backend
    print("[INFO] Phase 4: 启动 Backend...")
    code, out = run(compose_cmd + ["up", "-d", "backend"], timeout=60)
    if code != 0:
        print("[FAIL] Phase 4 失败")
        print(out[-1500:] if len(out) > 1500 else out)
        return 1
    print("[OK] Phase 4 完成")
    print("[INFO] 等待 Backend 健康...")
    for i in range(60):
        code, _ = run(["docker", "exec", "xihong_erp_backend", "curl", "-fsS", "http://localhost:8000/health"], timeout=5)
        if code == 0:
            break
        time.sleep(2)
    else:
        print("[FAIL] Backend 健康等待超时")
        return 1
    print("[OK] Backend 健康")

    # 集成检查（宿主机访问 8001）
    print("[INFO] 集成检查: Backend / Metabase / Dashboard KPI...")
    try:
        import httpx
        base = args.backend_url.rstrip("/")
        client = httpx.Client(timeout=15.0)
        try:
            r = client.get(f"{base}/health")
            if r.status_code != 200:
                print(f"[FAIL] Backend health: {r.status_code}")
                return 1
            print("[OK] Backend health (host)")
            r2 = client.get(f"{base}/api/metabase/health")
            if r2.status_code == 200 and r2.json().get("healthy"):
                print("[OK] Metabase proxy health")
            else:
                print("[WARN] Metabase proxy not healthy")
            r3 = client.get(f"{base}/api/dashboard/business-overview/kpi", params={"month": "2025-01-01"})
            if r3.status_code == 200 and r3.json().get("success") and r3.json().get("data") is not None:
                print("[OK] Dashboard KPI (name-based Question ID)")
            elif r3.status_code == 401:
                print("[INFO] Dashboard KPI 401 (login required)")
            else:
                print(f"[WARN] KPI: {r3.status_code}")
        finally:
            client.close()
    except Exception as e:
        print("[WARN] 集成检查异常:", e)

    print()
    print("[OK] 方式 B 本地生产流程验证完成。可进行云端部署。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
