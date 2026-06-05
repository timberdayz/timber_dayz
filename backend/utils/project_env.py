from __future__ import annotations

import os
from pathlib import Path


def resolve_env_profile(profile: str | None = None) -> str:
    raw_value = profile if profile is not None else os.getenv("XIHONG_ENV_PROFILE", "")
    return raw_value.strip().lower()


def resolve_project_env_files(
    project_root: str | Path,
    *,
    profile: str | None = None,
) -> list[Path]:
    root = Path(project_root)
    files = [
        root / ".env",
        root / ".env.local",
    ]

    if resolve_env_profile(profile) == "collection":
        files.append(root / ".env.collection.local")

    return [path for path in files if path.exists()]


def load_project_env(
    project_root: str | Path,
    *,
    profile: str | None = None,
    override: bool = True,
) -> list[Path]:
    loaded_files: list[Path] = []
    try:
        from dotenv import load_dotenv
    except ImportError:
        return loaded_files

    for env_file in resolve_project_env_files(project_root, profile=profile):
        try:
            load_dotenv(env_file, encoding="utf-8", override=override)
        except TypeError:
            load_dotenv(env_file, override=override)
        loaded_files.append(env_file)

    return loaded_files
