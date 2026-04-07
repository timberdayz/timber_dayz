from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.collection_contracts import iter_domain_targets, normalize_domain_subtypes
from backend.services.active_collection_components import (
    is_active_component_name,
    is_archive_only_file,
)
from backend.services.component_name_utils import build_component_name
from backend.services.component_version_service import ComponentVersionService


class ComponentRuntimeResolverError(Exception):
    """Base error for formal collection runtime component resolution."""


class NoStableComponentVersionError(ComponentRuntimeResolverError):
    """Raised when a formal runtime component has no stable version."""

    def __init__(self, component_name: str):
        self.component_name = component_name
        super().__init__(f"No stable component version found for {component_name}")


class MultipleStableComponentVersionsError(ComponentRuntimeResolverError):
    """Raised when a formal runtime component has more than one stable version."""

    def __init__(self, component_name: str):
        self.component_name = component_name
        super().__init__(f"Multiple stable component versions found for {component_name}")


class MissingStableComponentFileError(ComponentRuntimeResolverError):
    """Raised when the stable component points to a missing file path."""

    def __init__(self, component_name: str, file_path: str):
        self.component_name = component_name
        self.file_path = file_path
        super().__init__(
            f"Stable component file does not exist for {component_name}: {file_path}"
        )


@dataclass(frozen=True)
class RuntimeComponentManifest:
    component_name: str
    version: str
    file_path: str
    platform: str
    component_type: str
    data_domain: Optional[str] = None
    sub_domain: Optional[str] = None


class ComponentRuntimeResolver:
    """Resolve formal collection runtime components from stable version records."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        project_root: Optional[Path] = None,
    ) -> None:
        self.db = db
        self.project_root = project_root or Path(__file__).resolve().parents[2]

    @classmethod
    def from_async_session(
        cls,
        db: AsyncSession,
        *,
        project_root: Optional[Path] = None,
    ) -> "ComponentRuntimeResolver":
        return cls(db, project_root=project_root)

    async def resolve_login_component(self, platform: str) -> RuntimeComponentManifest:
        component_name = build_component_name(platform=platform, component_type="login")
        return await self._resolve_component(
            component_name=component_name,
            platform=platform,
            component_type="login",
        )

    async def resolve_export_component(
        self,
        *,
        platform: str,
        data_domain: str,
        sub_domain: Optional[str],
    ) -> RuntimeComponentManifest:
        component_name = build_component_name(
            platform=platform,
            component_type="export",
            data_domain=data_domain,
            sub_domain=sub_domain,
        )
        return await self._resolve_component(
            component_name=component_name,
            platform=platform,
            component_type="export",
            data_domain=data_domain,
            sub_domain=sub_domain,
        )

    async def resolve_task_manifests(
        self,
        *,
        platform: str,
        data_domains: list[str],
        sub_domains: Optional[dict[str, list[str]] | list[str]] = None,
        domain_subtypes: Optional[dict[str, list[str]]] = None,
    ) -> dict[str, Any]:
        login_manifest = await self.resolve_login_component(platform)
        exports: list[RuntimeComponentManifest] = []
        exports_by_domain: dict[str, RuntimeComponentManifest] = {}

        normalized_subtypes = normalize_domain_subtypes(
            data_domains=data_domains,
            domain_subtypes=domain_subtypes,
            sub_domains=sub_domains,
        )
        for data_domain, sub_domain, domain_key in iter_domain_targets(
            data_domains,
            normalized_subtypes,
        ):
            export_manifest = await self.resolve_export_component(
                platform=platform,
                data_domain=data_domain,
                sub_domain=sub_domain,
            )
            exports.append(export_manifest)
            exports_by_domain[domain_key] = export_manifest

        return {
            "login": login_manifest,
            "exports": exports,
            "exports_by_domain": exports_by_domain,
        }

    async def _resolve_component(
        self,
        *,
        component_name: str,
        platform: str,
        component_type: str,
        data_domain: Optional[str] = None,
        sub_domain: Optional[str] = None,
    ) -> RuntimeComponentManifest:
        if not is_active_component_name(component_name):
            raise NoStableComponentVersionError(component_name)

        stable_versions = await self._load_stable_versions(component_name)

        if not stable_versions:
            raise NoStableComponentVersionError(component_name)

        if len(stable_versions) > 1:
            raise MultipleStableComponentVersionsError(component_name)

        stable_version = stable_versions[0]
        file_path = str(stable_version["file_path"])
        if is_archive_only_file(file_path):
            raise MissingStableComponentFileError(component_name, file_path)
        absolute_path = self.project_root / file_path
        if not absolute_path.exists():
            raise MissingStableComponentFileError(component_name, file_path)

        return RuntimeComponentManifest(
            component_name=component_name,
            version=str(stable_version["version"]),
            file_path=file_path,
            platform=platform,
            component_type=component_type,
            data_domain=data_domain,
            sub_domain=sub_domain,
        )

    async def _load_stable_versions(self, component_name: str) -> list[dict[str, Any]]:
        def _query(sync_session):
            service = ComponentVersionService(sync_session)
            return [
                {
                    "component_name": row.component_name,
                    "version": row.version,
                    "file_path": row.file_path,
                }
                for row in service.get_all_stable_versions(component_name)
            ]

        return list(await self.db.run_sync(_query))
