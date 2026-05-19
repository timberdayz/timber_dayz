#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Verify remote deployment script avoids server-side image builds."""

from __future__ import annotations

from pathlib import Path


SCRIPT_PATH = Path("scripts/deploy_remote_production.sh")
DOCKERFILE_BACKEND_PATH = Path("Dockerfile.backend")


REQUIRED_LITERALS = [
    'migrate:',
    'celery-worker:',
    'celery-beat:',
    'run --rm --no-deps backend alembic history',
    'run --rm --no-deps backend alembic upgrade heads',
    'run --rm --no-deps backend python3 /app/scripts/bootstrap_production.py',
    'run --rm --no-deps backend python3 /app/scripts/bootstrap_postgresql_dashboard.py',
    'up -d --no-build backend celery-worker celery-beat',
    'up -d --no-build frontend',
    'up -d --no-build nginx',
]

REQUIRED_BACKEND_IMAGE_FILES = [
    "scripts/bootstrap_production.py",
    "scripts/bootstrap_postgresql_dashboard.py",
]


def _dockerfile_copies_file(dockerfile_source: str, repo_rel_path: str) -> bool:
    # Accept both explicit file COPY and directory COPY for scripts/.
    # We keep this intentionally simple: it's a release gate, not a full parser.
    needle_explicit = f"COPY {repo_rel_path} "
    if needle_explicit in dockerfile_source:
        return True
    if "COPY scripts/ /app/scripts" in dockerfile_source or "COPY scripts/ /app/scripts/" in dockerfile_source:
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
