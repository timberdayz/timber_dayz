#!/usr/bin/env python3
"""Create one opt-in local development administrator for an empty local database."""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.utils.project_env import load_project_env

load_project_env(ROOT_DIR)

from backend.models.database import AsyncSessionLocal
from backend.services.auth_service import auth_service
from backend.services.system_role_service import DEFAULT_SYSTEM_ROLES
from modules.core.db import DimRole, DimUser

TRUE_VALUES = {"1", "true", "yes", "on"}
LOOPBACK_DATABASE_HOSTS = {"127.0.0.1", "::1", "localhost"}


@dataclass(frozen=True)
class LocalDevAdminConfig:
    username: str
    password: str
    email: str


def load_local_dev_admin_config(
    environment: Mapping[str, str] | None = None,
) -> LocalDevAdminConfig | None:
    environment = environment or os.environ
    enabled = environment.get("LOCAL_DEV_BOOTSTRAP_ADMIN", "").strip().lower()
    if enabled not in TRUE_VALUES:
        return None

    password = environment.get("LOCAL_DEV_ADMIN_PASSWORD", "")
    if not password:
        raise ValueError(
            "LOCAL_DEV_ADMIN_PASSWORD is required when LOCAL_DEV_BOOTSTRAP_ADMIN=true"
        )

    username = environment.get("LOCAL_DEV_ADMIN_USERNAME", "xihong").strip()
    if not username:
        raise ValueError("LOCAL_DEV_ADMIN_USERNAME must not be empty")
    email = environment.get("LOCAL_DEV_ADMIN_EMAIL", f"{username}@local.test").strip()
    if not email:
        raise ValueError("LOCAL_DEV_ADMIN_EMAIL must not be empty")
    return LocalDevAdminConfig(username=username, password=password, email=email)


def ensure_local_database_target(database_url: str) -> None:
    parsed = urlparse(database_url)
    if parsed.scheme.split("+", 1)[0] != "postgresql" or (
        parsed.hostname or ""
    ).lower() not in LOOPBACK_DATABASE_HOSTS:
        raise ValueError("LOCAL_DEV_BOOTSTRAP_ADMIN requires a loopback PostgreSQL target")


async def ensure_local_dev_admin(
    db: AsyncSession,
    config: LocalDevAdminConfig,
    password_hasher=auth_service.hash_password,
) -> str:
    existing_user = (
        await db.execute(select(DimUser).where(DimUser.username == config.username))
    ).scalar_one_or_none()
    if existing_user is not None:
        return "existing"

    admin_role = (
        await db.execute(select(DimRole).where(DimRole.role_code == "admin"))
    ).scalar_one_or_none()
    if admin_role is None:
        role_spec = DEFAULT_SYSTEM_ROLES["admin"]
        admin_role = DimRole(
            role_code="admin",
            role_name=role_spec["role_name"],
            description=role_spec["description"],
            permissions='["*"]',
            data_scope=role_spec["data_scope"],
            is_active=True,
            is_system=True,
        )
        db.add(admin_role)

    user = DimUser(
        username=config.username,
        email=config.email,
        password_hash=password_hasher(config.password),
        full_name="Local Development Administrator",
        status="active",
        is_active=True,
        is_superuser=True,
    )
    user.roles = [admin_role]
    db.add(user)
    await db.flush()
    return "created"


async def main() -> int:
    config = load_local_dev_admin_config()
    if config is None:
        print("[local-dev-admin] skipped")
        return 0

    ensure_local_database_target(os.getenv("DATABASE_URL", ""))

    async with AsyncSessionLocal() as db:
        try:
            result = await ensure_local_dev_admin(db, config)
            await db.commit()
        except Exception:
            await db.rollback()
            raise

    print(f"[local-dev-admin] {result}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except ValueError as exc:
        print(f"[local-dev-admin] configuration error: {exc}")
        raise SystemExit(1) from exc
