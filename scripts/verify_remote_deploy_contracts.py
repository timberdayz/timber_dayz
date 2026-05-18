#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Verify remote deployment script avoids server-side image builds."""

from __future__ import annotations

from pathlib import Path


SCRIPT_PATH = Path("scripts/deploy_remote_production.sh")


REQUIRED_LITERALS = [
    'migrate:',
    'celery-worker:',
    'celery-beat:',
    'run --rm --no-build --no-deps backend alembic history',
    'run --rm --no-build --no-deps backend alembic upgrade heads',
    'run --rm --no-build --no-deps backend python3 /app/scripts/bootstrap_production.py',
    'up -d --no-build backend celery-worker celery-beat',
    'up -d --no-build frontend',
    'up -d --no-build nginx',
]


def verify_remote_deploy_contracts(script_path: Path = SCRIPT_PATH) -> bool:
    source = script_path.read_text(encoding="utf-8")
    for literal in REQUIRED_LITERALS:
        if literal not in source:
            raise RuntimeError(f"Missing deploy contract literal: {literal}")
    return True


def main() -> int:
    ok = verify_remote_deploy_contracts()
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
