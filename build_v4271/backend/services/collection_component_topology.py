from __future__ import annotations

import re
from pathlib import Path


CANONICAL_FIXED_COMPONENTS = frozenset(
    {
        "login",
        "navigation",
        "date_picker",
        "shop_switch",
        "filters",
    }
)

LEGACY_HELPER_FILENAMES = frozenset(
    {
        "overlay_guard.py",
        "config_registry.py",
    }
)

VERSIONED_COMPONENT_PATTERN = re.compile(r".+_v\d+_\d+_\d+\.py$")


def _normalize_filename(filename: str) -> str:
    return Path(str(filename or "").strip()).name


def is_versioned_component_filename(filename: str) -> bool:
    normalized = _normalize_filename(filename)
    return bool(VERSIONED_COMPONENT_PATTERN.fullmatch(normalized))


def is_legacy_component_filename(filename: str) -> bool:
    normalized = _normalize_filename(filename)
    if not normalized.endswith(".py"):
        return False
    if is_versioned_component_filename(normalized):
        return True

    stem = Path(normalized).stem
    if stem.startswith("recorder_") or stem.endswith("_recorder"):
        return True
    if stem.startswith("recorder_test_") or "_test_" in stem:
        return True

    # Recorder-era compatibility files such as miaoshou_login.py should no
    # longer act as canonical component entrypoints.
    if stem.endswith("_login") or stem.endswith("_navigation"):
        return True

    return False


def is_canonical_component_filename(filename: str) -> bool:
    normalized = _normalize_filename(filename)
    if not normalized.endswith(".py"):
        return False
    if normalized in LEGACY_HELPER_FILENAMES:
        return False
    if normalized.endswith("_config.py"):
        return False
    if is_legacy_component_filename(normalized):
        return False

    stem = Path(normalized).stem
    if stem in CANONICAL_FIXED_COMPONENTS:
        return True

    return stem.endswith("_export")


def build_component_name_from_filename(platform: str, filename: str) -> str:
    normalized = _normalize_filename(filename)
    if not is_canonical_component_filename(normalized):
        raise ValueError(f"not a canonical component filename: {normalized}")
    return f"{str(platform or '').strip()}/{Path(normalized).stem}"

