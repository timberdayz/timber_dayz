from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import re

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import CatalogFile, DataQuarantine, StagingInventory, StagingOrders, StagingProductMetrics
from modules.core.path_manager import to_absolute_path


_SAFE_IDENTIFIER_RE = re.compile(r"^[a-z0-9_]+$")


class CatalogFileDeleteNotFoundError(Exception):
    pass


@dataclass
class CatalogFileDeleteImpact:
    file_id: int
    file_name: str
    platform_code: str | None
    source_platform: str | None
    data_domain: str | None
    granularity: str | None
    status: str | None
    local_file_exists: bool
    meta_file_exists: bool
    quarantine_rows: int
    staging_rows: int
    fact_table_name: str | None
    fact_rows: int
    can_delete: bool
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CatalogFileDeleteResult:
    file_id: int
    fact_table_name: str | None
    deleted_file: bool
    deleted_meta: bool
    deleted_catalog: bool
    deleted_quarantine_rows: int
    deleted_staging_rows: int
    deleted_fact_rows: int
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class CatalogFileDeleteService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def analyze_delete_impact(self, file_id: int) -> CatalogFileDeleteImpact:
        catalog = await self._get_catalog_file(file_id)
        fact_table_name = self._resolve_fact_table_name(catalog)
        local_path = self._resolve_optional_path(catalog.file_path)
        meta_path = self._resolve_optional_path(catalog.meta_file_path)
        quarantine_rows = await self._count_quarantine_rows(file_id)
        staging_rows = await self._count_staging_rows(file_id)
        fact_rows = await self._count_fact_rows(fact_table_name, file_id)
        warnings: list[str] = []

        if (catalog.status or "").lower() in {"ingested", "partial_success"}:
            warnings.append("该文件已同步，删除将同时清理关联入库数据")

        return CatalogFileDeleteImpact(
            file_id=catalog.id,
            file_name=catalog.file_name,
            platform_code=catalog.platform_code,
            source_platform=catalog.source_platform,
            data_domain=catalog.data_domain,
            granularity=catalog.granularity,
            status=catalog.status,
            local_file_exists=bool(local_path and local_path.exists()),
            meta_file_exists=bool(meta_path and meta_path.exists()),
            quarantine_rows=quarantine_rows,
            staging_rows=staging_rows,
            fact_table_name=fact_table_name,
            fact_rows=fact_rows,
            can_delete=True,
            warnings=warnings,
        )

    async def delete_catalog_file(self, file_id: int, force: bool = True) -> CatalogFileDeleteResult:
        catalog = await self._get_catalog_file(file_id)
        impact = await self.analyze_delete_impact(file_id)
        local_path = self._resolve_optional_path(catalog.file_path)
        meta_path = self._resolve_optional_path(catalog.meta_file_path)

        deleted_fact_rows = await self._delete_fact_rows(impact.fact_table_name, file_id)
        deleted_staging_rows = await self._delete_staging_rows(file_id)
        deleted_quarantine_rows = await self._delete_quarantine_rows(file_id)

        await self.db.delete(catalog)
        await self.db.commit()

        deleted_file, file_warning = self._delete_local_path(local_path)
        deleted_meta, meta_warning = self._delete_local_path(meta_path)
        warnings = list(impact.warnings)
        if file_warning:
            warnings.append(file_warning)
        if meta_warning:
            warnings.append(meta_warning)

        return CatalogFileDeleteResult(
            file_id=file_id,
            fact_table_name=impact.fact_table_name,
            deleted_file=deleted_file,
            deleted_meta=deleted_meta,
            deleted_catalog=True,
            deleted_quarantine_rows=deleted_quarantine_rows,
            deleted_staging_rows=deleted_staging_rows,
            deleted_fact_rows=deleted_fact_rows,
            warnings=warnings,
        )

    async def _get_catalog_file(self, file_id: int) -> CatalogFile:
        result = await self.db.execute(select(CatalogFile).where(CatalogFile.id == file_id))
        catalog = result.scalar_one_or_none()
        if catalog is None:
            raise CatalogFileDeleteNotFoundError(f"catalog file not found: {file_id}")
        return catalog

    def _resolve_fact_table_name(self, catalog: CatalogFile) -> str | None:
        platform = (catalog.platform_code or "").strip().lower()
        data_domain = (catalog.data_domain or "").strip().lower()
        granularity = (catalog.granularity or "").strip().lower()
        sub_domain = (catalog.sub_domain or "").strip().lower()

        if not platform or not data_domain or not granularity:
            return None

        parts = ["fact", platform, data_domain]
        if sub_domain:
            parts.append(sub_domain)
        parts.append(granularity)
        table_name = "_".join(parts)

        if not _SAFE_IDENTIFIER_RE.match(table_name):
            raise ValueError(f"unsafe fact table name: {table_name}")
        return table_name

    def _resolve_optional_path(self, path_value: str | None) -> Path | None:
        if not path_value:
            return None
        path_obj = Path(path_value)
        if path_obj.is_absolute():
            return path_obj
        return to_absolute_path(path_value)

    async def _count_quarantine_rows(self, file_id: int) -> int:
        result = await self.db.execute(
            select(text("count(*)")).select_from(DataQuarantine).where(DataQuarantine.catalog_file_id == file_id)
        )
        return int(result.scalar() or 0)

    async def _count_staging_rows(self, file_id: int) -> int:
        total = 0
        for table in (StagingOrders, StagingProductMetrics, StagingInventory):
            result = await self.db.execute(
                select(text("count(*)")).select_from(table).where(table.file_id == file_id)
            )
            total += int(result.scalar() or 0)
        return total

    async def _count_fact_rows(self, table_name: str | None, file_id: int) -> int:
        if not table_name or not await self._fact_table_exists(table_name):
            return 0
        result = await self.db.execute(
            text(f'SELECT COUNT(*) FROM b_class."{table_name}" WHERE file_id = :file_id'),
            {"file_id": file_id},
        )
        return int(result.scalar() or 0)

    async def _fact_table_exists(self, table_name: str) -> bool:
        dialect_name = self.db.bind.dialect.name if self.db.bind is not None else ""
        if dialect_name == "sqlite":
            result = await self.db.execute(
                text("SELECT name FROM b_class.sqlite_master WHERE type='table' AND name = :table_name"),
                {"table_name": table_name},
            )
            return result.first() is not None

        result = await self.db.execute(
            text("SELECT to_regclass(:full_name)"),
            {"full_name": f"b_class.{table_name}"},
        )
        return result.scalar() is not None

    async def _delete_fact_rows(self, table_name: str | None, file_id: int) -> int:
        if not table_name or not await self._fact_table_exists(table_name):
            return 0
        result = await self.db.execute(
            text(f'DELETE FROM b_class."{table_name}" WHERE file_id = :file_id'),
            {"file_id": file_id},
        )
        return int(result.rowcount or 0)

    async def _delete_staging_rows(self, file_id: int) -> int:
        total = 0
        for table in (StagingOrders, StagingProductMetrics, StagingInventory):
            result = await self.db.execute(delete(table).where(table.file_id == file_id))
            total += int(result.rowcount or 0)
        return total

    async def _delete_quarantine_rows(self, file_id: int) -> int:
        result = await self.db.execute(
            delete(DataQuarantine).where(DataQuarantine.catalog_file_id == file_id)
        )
        return int(result.rowcount or 0)

    def _delete_local_path(self, path_obj: Path | None) -> tuple[bool, str | None]:
        if path_obj is None:
            return False, None
        if not path_obj.exists():
            return False, None
        try:
            path_obj.unlink()
            return True, None
        except Exception as exc:
            return False, f"删除本地文件失败: {path_obj} ({exc})"
