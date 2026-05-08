from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from sqlalchemy import create_engine, text

from modules.utils.sessions.device_fingerprint import DeviceFingerprintManager


@dataclass(frozen=True)
class ShopSessionScope:
    platform: str
    shop_account_id: str
    main_account_id: str


def _normalized_platform(platform: str) -> str:
    return str(platform or "").strip().lower()


def _is_legacy_shop_scope(scope: ShopSessionScope) -> bool:
    shop_account_id = str(scope.shop_account_id or "").strip()
    main_account_id = str(scope.main_account_id or "").strip()
    return bool(shop_account_id and main_account_id and shop_account_id != main_account_id)


def collect_legacy_shop_artifact_paths(
    project_root: Path,
    scopes: Iterable[ShopSessionScope],
) -> list[Path]:
    root = Path(project_root)
    fingerprint_manager = DeviceFingerprintManager(base_path=root / "data" / "device_fingerprints")
    found: set[Path] = set()

    for scope in scopes:
        if not _is_legacy_shop_scope(scope):
            continue

        platform = _normalized_platform(scope.platform)
        shop_account_id = str(scope.shop_account_id or "").strip()
        if not platform or not shop_account_id:
            continue

        candidates = [
            root / "data" / "sessions" / platform / shop_account_id,
            root / "profiles" / platform / shop_account_id,
            root / "data" / "session_profiles" / platform / shop_account_id,
            fingerprint_manager.get_fingerprint_file(platform, shop_account_id),
        ]

        for candidate in candidates:
            if candidate.exists():
                found.add(candidate)

    return sorted(found)


def load_active_shop_session_scopes(database_url: str) -> list[ShopSessionScope]:
    engine = create_engine(database_url)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                select platform, shop_account_id, main_account_id
                from core.shop_accounts
                where enabled = true
                order by platform, shop_account_id
                """
            )
        ).fetchall()
    return [
        ShopSessionScope(
            platform=str(platform or ""),
            shop_account_id=str(shop_account_id or ""),
            main_account_id=str(main_account_id or ""),
        )
        for platform, shop_account_id, main_account_id in rows
    ]


def collect_legacy_shop_artifacts_for_active_shops(
    project_root: Path,
    database_url: str,
) -> list[Path]:
    scopes = load_active_shop_session_scopes(database_url)
    return collect_legacy_shop_artifact_paths(project_root, scopes)
