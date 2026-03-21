#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

import httpx

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.create_admin_user import create_admin_user


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate local auth payload for frontend smoke tests"
    )
    parser.add_argument("--backend-url", default="http://127.0.0.1:8001")
    parser.add_argument("--username", default="playwright_smoke_admin")
    parser.add_argument("--password", default="PlaywrightSmoke!1")
    parser.add_argument("--email", default="playwright_smoke_admin@test.local")
    parser.add_argument("--full-name", default="Playwright Smoke Admin")
    return parser.parse_args()


async def ensure_admin(args: argparse.Namespace):
    return await create_admin_user(
        username=args.username,
        password=args.password,
        email=args.email,
        full_name=args.full_name,
    )


def login_and_fetch_payload(args: argparse.Namespace, user) -> dict:
    login_url = f"{args.backend_url.rstrip('/')}/api/auth/login"
    response = httpx.post(
        login_url,
        json={"username": args.username, "password": args.password},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()

    data = payload.get("data", payload)
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")

    if not access_token or not refresh_token:
        raise RuntimeError(f"Login payload missing tokens: {payload}")

    user_info = data.get("user_info") or {
        "id": user.user_id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "roles": [
            (getattr(role, "role_code", None) or getattr(role, "role_name", None))
            for role in user.roles
            if (getattr(role, "role_code", None) or getattr(role, "role_name", None))
        ],
    }

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user_info": user_info,
    }


def main() -> int:
    args = parse_args()
    user = asyncio.run(ensure_admin(args))
    payload = login_and_fetch_payload(args, user)
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
