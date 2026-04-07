from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.platform_login_entry_service import normalize_main_account_login_url


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")

    conn = psycopg2.connect(database_url)
    updated = 0
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                select id, platform, login_url
                from core.main_accounts
                order by id
                """
            )
            rows = cur.fetchall()
            for record_id, platform, login_url in rows:
                try:
                    normalized = normalize_main_account_login_url(platform, login_url)
                except ValueError:
                    continue
                if normalized == (login_url or ""):
                    continue
                cur.execute(
                    """
                    update core.main_accounts
                    set login_url = %s
                    where id = %s
                    """,
                    (normalized, record_id),
                )
                updated += 1
        conn.commit()
    finally:
        conn.close()

    print(f"normalized_main_account_login_urls={updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
