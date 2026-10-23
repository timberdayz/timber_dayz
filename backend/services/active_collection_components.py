from __future__ import annotations

from pathlib import Path

from backend.services.collection_component_topology import (
    build_component_name_from_filename,
    is_canonical_component_filename,
    is_legacy_component_filename,
    is_versioned_component_filename,
)


SUPPORTED_ACTIVE_COMPONENT_PLATFORMS = ("shopee", "tiktok", "miaoshou")


def _default_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _discover_active_component_names(
    *,
    project_root: Path | None = None,
    supported_platforms: tuple[str, ...] = SUPPORTED_ACTIVE_COMPONENT_PLATFORMS,
) -> list[str]:
    root = project_root or _default_project_root()
    platforms_dir = root / "modules" / "platforms"
    names: set[str] = set()

    for platform in supported_platforms:
        components_dir = platforms_dir / platform / "components"
        if not components_dir.exists():
            continue
        for py_file in components_dir.glob("*.py"):
            if py_file.name.startswith("__"):
                continue
            if not is_canonical_component_filename(py_file.name):
                continue
            names.add(build_component_name_from_filename(platform, py_file.name))

    return sorted(names)


def list_active_component_names() -> list[str]:
    return _discover_active_component_names()


def is_active_component_name(name: str) -> bool:
    normalized = str(name or "").strip()
    if not normalized:
        return False
    return normalized in _discover_active_component_names()


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


def is_missing_component_file(
    file_path: str, *, project_root: Path | None = None
) -> bool:
    """file_path 指向的组件文件是否已不可用。

    判定：路径为空 / 位于 archive/ 目录 / 文件在磁盘上不存在。

    用于发现「stable 记录指向已归档或缺失文件」的孤儿记录
    （docs/guides/ACTIVE_COLLECTION_COMPONENTS.md「Archive 目录语义 → 前置条件」第 2 条：
      没有 stable ComponentVersion.file_path 指向该文件）。
    """
    raw = str(file_path or "").replace("\\", "/").strip()
    if not raw:
        return True
    if "/archive/" in raw:
        return True
    root = project_root or _default_project_root()
    return not (root / raw).exists()
