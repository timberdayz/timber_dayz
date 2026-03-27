from __future__ import annotations

from pathlib import Path

from backend.services.collection_component_topology import is_legacy_component_filename, is_versioned_component_filename


ACTIVE_COMPONENT_NAMES = (
    "miaoshou/login",
    "miaoshou/orders_export",
)


def list_active_component_names() -> list[str]:
    return list(ACTIVE_COMPONENT_NAMES)


def is_active_component_name(name: str) -> bool:
    return str(name or "").strip() in ACTIVE_COMPONENT_NAMES


def is_archive_only_file(path_or_name: str) -> bool:
    raw = str(path_or_name or "").replace("\\", "/").strip()
    if not raw:
        return False
    if "/archive/" in raw:
        return True

    filename = Path(raw).name
    if is_versioned_component_filename(filename):
        return False
    return is_legacy_component_filename(filename)
