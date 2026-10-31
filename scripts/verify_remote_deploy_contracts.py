#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Verify remote deployment script avoids server-side image builds."""

from __future__ import annotations

from pathlib import Path


SCRIPT_PATH = Path("scripts/deploy_remote_production.sh")
DOCKERFILE_BACKEND_PATH = Path("Dockerfile.backend")


REQUIRED_LITERALS = [
    "migrate:",
    "celery-worker:",
    "celery-beat:",
    "backend-api:",
    "backend-api python3 /app/scripts/run_current_schema_migrations.py",
    "run_current_schema_migrations.py --preflight-only",
    "capture_running_application_containers",
    "trap handle_deploy_exit EXIT",
    "DEPLOYMENT_CUTOVER_COMPLETE=1",
    "run --rm --no-deps backend-api python3 /app/scripts/bootstrap_production.py",
    "run --rm --no-deps backend-api python3 /app/scripts/verify_system_role_integrity.py --repair",
    "run --rm --no-deps backend-api python3 /app/scripts/bootstrap_postgresql_dashboard.py",
    # [VIEW REBUILD] 视图**定义**变更必须显式重建：数据刷新与 bootstrap 都会跳过
    # 已存在的普通视图，生产又关掉了启动自愈 ⇒ 少了这一步，改过的 sql/ 资产不会生效。
    "run --rm --no-deps backend-api python3 /app/scripts/rebuild_views.py",
    "DEPLOY_REBUILD_VIEW_TARGETS",
    "api.clearance_ranking_module",
    # 重建后必须再确认目标视图确实存在（rebuild_views.py 对「目标不在库里」
    # 会跳过并返回 0，那是静默成功）。
    "rebuild_dashboard_view_definitions",
    "-e REBUILD_VERIFY_TARGETS",
    # [INVENTORY LAYERS] 库存两层都要在部署时重建：
    #   库龄层(mart.inventory_age_*) 与状态层(mart.inventory_state)。
    # 状态层是「距上次进货天数」的唯一来源 —— 它是**表**不是视图，
    # SQL 资产重建灌不进数据，只有 InventoryStateRefreshService 的 upsert 能写。
    # 少了状态层这一步 → 空表 → 滞销榜恒 0 行（§3.9.11）。
    "python3 /app/scripts/rebuild_inventory_age_from_snapshots.py --full-rebuild",
    "python3 /app/scripts/rebuild_inventory_state_from_snapshots.py --full-rebuild",
    "up -d --no-build --no-deps backend-api celery-worker celery-beat",
    "up -d --no-build --no-deps frontend",
    "up -d --no-build --no-deps nginx",
]

REQUIRED_BACKEND_IMAGE_FILES = [
    "scripts/bootstrap_production.py",
    "scripts/verify_system_role_integrity.py",
    "scripts/bootstrap_postgresql_dashboard.py",
    "scripts/rebuild_views.py",
    "scripts/rebuild_inventory_age_from_snapshots.py",
    "scripts/rebuild_inventory_state_from_snapshots.py",
]


def _dockerfile_copies_file(dockerfile_source: str, repo_rel_path: str) -> bool:
    # Accept both explicit file COPY and directory COPY for scripts/.
    # We keep this intentionally simple: it's a release gate, not a full parser.
    needle_explicit = f"COPY {repo_rel_path} "
    if needle_explicit in dockerfile_source:
        return True
    if (
        "COPY scripts/ /app/scripts" in dockerfile_source
        or "COPY scripts/ /app/scripts/" in dockerfile_source
    ):
        return True
    return False


def verify_remote_deploy_contracts(
    script_path: Path = SCRIPT_PATH,
    dockerfile_backend_path: Path = DOCKERFILE_BACKEND_PATH,
) -> bool:
    source = script_path.read_text(encoding="utf-8")
    for literal in REQUIRED_LITERALS:
        if literal not in source:
            raise RuntimeError(f"Missing deploy contract literal: {literal}")

    dockerfile_source = dockerfile_backend_path.read_text(encoding="utf-8")
    for rel_path in REQUIRED_BACKEND_IMAGE_FILES:
        if not _dockerfile_copies_file(dockerfile_source, rel_path):
            raise RuntimeError(
                f"Dockerfile.backend must COPY {rel_path} into backend image for deploy-time scripts"
            )
    return True


def main() -> int:
    ok = verify_remote_deploy_contracts()
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
