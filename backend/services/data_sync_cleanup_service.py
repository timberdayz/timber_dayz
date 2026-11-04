from __future__ import annotations

import logging
from pathlib import Path
import re
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import CatalogFile, ShopAccount
from modules.core.path_manager import to_absolute_path


logger = logging.getLogger(__name__)


def _is_missing_relation_error(exc: BaseException) -> bool:
    """这个异常是不是「表/视图不存在」。

    只放过这一类：其它数据库错误必须照常抛出（不能把真故障吞成告警）。
    """
    message = str(getattr(exc, "orig", exc)).lower()
    return (
        "no such table" in message
        or "does not exist" in message
        or "undefined table" in message
    )


_SAFE_IDENTIFIER_RE = re.compile(r"^[a-z0-9_]+$")
_RESETTABLE_STATUSES = {"ingested", "partial_success"}
_INSPECTED_STATUSES = {"ingested", "partial_success", "failed", "processing"}
_REBUILD_RECOMMENDATION = {
    "recommended_rebuild_mode": "controlled_auto_ingest",
    "recommended_batch_size": 20,
    "recommended_max_concurrent": 1,
}


class DataSyncCleanupService:
    """Clear fact data and only requeue catalog files that can be rebuilt."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def analyze_cleanup_impact(self) -> dict[str, Any]:
        fact_table_counts = await self._count_fact_tables()
        file_impact = await self._analyze_catalog_files()
        return {
            "fact_table_counts": fact_table_counts,
            "total_fact_rows": sum(fact_table_counts.values()),
            **_REBUILD_RECOMMENDATION,
            **file_impact,
        }

    async def _load_disabled_shop_keys(self) -> set[tuple[str, str]]:
        """停用店铺账号的全部身份键（``(platform_code, key)``）。

        为什么要有这个：停用店**不再采集**，但它们历史留下的采集文件
        仍然躺在 ``catalog_files`` 里。清空事实数据时如果把这些文件也重置成
        ``pending``，重采就会去连那些已经停用的店铺账号 —— 一边是白跑采集，
        一边是重新往库里灌停用店的数据。

        采集文件上的 ``shop_id`` 可能落在 ``platform_shop_id``，也可能落在
        ``shop_account_id``（历史文件两种都有），所以**两种键都要收** ——
        漏一个就等于漏掉一批停用店。

        另外把主键 ``id`` 也收进去：键位统一后（见 ``resolve_dim_shop_id``），
        内部维度键就是账号主键。
        """
        try:
            result = await self.db.execute(
                select(ShopAccount).where(ShopAccount.enabled.is_not(True))
            )
            accounts = list(result.scalars().all())
        except SQLAlchemyError as exc:
            # 店铺账号表读不到（某些精简库里不存在）⇒ 退化成「没有已知停用店」。
            # 只放过「表不存在」这一类；其它数据库错误必须照常抛出。
            if not _is_missing_relation_error(exc):
                raise
            logger.warning(
                "[DataSyncCleanup] 读不到 core.shop_accounts，跳过停用店过滤: %s", exc
            )
            return set()

        keys: set[tuple[str, str]] = set()
        for account in accounts:
            platform = str(account.platform or "").strip().lower()
            if not platform:
                continue
            for raw_key in (
                account.platform_shop_id,
                account.shop_account_id,
                str(account.id),
            ):
                key = str(raw_key or "").strip()
                if key:
                    keys.add((platform, key))
        return keys

    def _file_belongs_to_disabled_shop(
        self,
        file_record: CatalogFile,
        disabled_keys: set[tuple[str, str]],
    ) -> bool:
        if not disabled_keys:
            return False
        platform = str(file_record.platform_code or "").strip().lower()
        if not platform:
            return False
        for raw_key in (
            file_record.shop_id,
            file_record.platform_shop_id,
            file_record.shop_account_id,
        ):
            key = str(raw_key or "").strip()
            if key and (platform, key) in disabled_keys:
                return True
        return False

    async def cleanup_database(self) -> dict[str, Any]:
        impact = await self.analyze_cleanup_impact()
        deleted_counts = await self._delete_fact_tables()
        status_result = await self._apply_catalog_status_changes()
        await self.db.commit()

        total_deleted_rows = sum(
            count for count in deleted_counts.values() if count > 0
        )
        return {
            **impact,
            **status_result,
            "deleted_counts": deleted_counts,
            "total_deleted_rows": total_deleted_rows,
        }

    async def _list_fact_tables(self) -> list[str]:
        dialect_name = self.db.bind.dialect.name if self.db.bind is not None else ""
        if dialect_name == "sqlite":
            result = await self.db.execute(
                text(
                    """
                    SELECT name
                    FROM b_class.sqlite_master
                    WHERE type = 'table' AND name LIKE 'fact_%'
                    ORDER BY name
                    """
                )
            )
        else:
            result = await self.db.execute(
                text(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'b_class'
                      AND table_type = 'BASE TABLE'
                      AND table_name LIKE 'fact\\_%' ESCAPE '\\'
                    ORDER BY table_name
                    """
                )
            )

        table_names = [str(row[0]) for row in result.fetchall()]
        return [
            table_name
            for table_name in table_names
            if _SAFE_IDENTIFIER_RE.match(table_name)
        ]

    async def _count_fact_tables(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for table_name in await self._list_fact_tables():
            result = await self.db.execute(
                text(f'SELECT COUNT(*) FROM b_class."{table_name}"')
            )
            counts[table_name] = int(result.scalar() or 0)
        return counts

    async def _delete_fact_tables(self) -> dict[str, int]:
        deleted_counts: dict[str, int] = {}
        for table_name in await self._list_fact_tables():
            before_result = await self.db.execute(
                text(f'SELECT COUNT(*) FROM b_class."{table_name}"')
            )
            before_count = int(before_result.scalar() or 0)
            if before_count > 0:
                await self.db.execute(text(f'DELETE FROM b_class."{table_name}"'))
            deleted_counts[table_name] = before_count
        return deleted_counts

    async def _analyze_catalog_files(self) -> dict[str, Any]:
        files = await self._load_inspected_catalog_files()
        disabled_keys = await self._load_disabled_shop_keys()
        impact = self._empty_file_impact()

        for file_record in files:
            status = (file_record.status or "").lower()
            impact["status_distribution"][status] = (
                impact["status_distribution"].get(status, 0) + 1
            )

            if status == "failed":
                impact["skipped_failed_count"] += 1
                continue
            if status == "processing":
                impact["skipped_processing_count"] += 1
                continue
            if status not in _RESETTABLE_STATUSES:
                continue

            # 停用店的文件不排重采 —— 否则又去连已经停掉的店。
            if self._file_belongs_to_disabled_shop(file_record, disabled_keys):
                impact["skipped_disabled_shop_count"] += 1
                continue

            file_exists, meta_exists = self._catalog_paths_exist(file_record)
            if file_exists and meta_exists:
                impact["resettable_files_count"] += 1
                continue

            impact["source_missing_files_count"] += 1
            if not file_exists:
                impact["file_missing_files_count"] += 1
            if not meta_exists:
                impact["meta_missing_files_count"] += 1
            if not file_exists and not meta_exists:
                impact["file_and_meta_missing_files_count"] += 1

        return impact

    async def _apply_catalog_status_changes(self) -> dict[str, int]:
        files = await self._load_inspected_catalog_files()
        disabled_keys = await self._load_disabled_shop_keys()
        reset_files_count = 0
        marked_source_missing_count = 0
        skipped_failed_count = 0
        skipped_processing_count = 0
        skipped_disabled_shop_count = 0

        for file_record in files:
            status = (file_record.status or "").lower()
            if status == "failed":
                skipped_failed_count += 1
                continue
            if status == "processing":
                skipped_processing_count += 1
                continue
            if status not in _RESETTABLE_STATUSES:
                continue

            # ⚠️ 停用店不重采。
            # 以前这些文件会被一起重置成 pending ⇒ 重采去连已停用的店铺账号，
            # 一边白跑，一边把停用店的数据重新灌回事实表。
            if self._file_belongs_to_disabled_shop(file_record, disabled_keys):
                skipped_disabled_shop_count += 1
                continue

            file_exists, meta_exists = self._catalog_paths_exist(file_record)
            if file_exists and meta_exists:
                file_record.status = "pending"
                file_record.error_message = None
                reset_files_count += 1
            else:
                file_record.status = "source_missing"
                file_record.error_message = self._build_source_missing_message(
                    file_exists=file_exists,
                    meta_exists=meta_exists,
                )
                marked_source_missing_count += 1

        return {
            "reset_files_count": reset_files_count,
            "marked_source_missing_count": marked_source_missing_count,
            "skipped_failed_count": skipped_failed_count,
            "skipped_processing_count": skipped_processing_count,
            "skipped_disabled_shop_count": skipped_disabled_shop_count,
        }

    async def _load_inspected_catalog_files(self) -> list[CatalogFile]:
        result = await self.db.execute(
            select(CatalogFile).where(
                CatalogFile.status.in_(sorted(_INSPECTED_STATUSES))
            )
        )
        return list(result.scalars().all())

    def _catalog_paths_exist(self, file_record: CatalogFile) -> tuple[bool, bool]:
        file_path = self._resolve_optional_path(file_record.file_path)
        meta_path = self._resolve_optional_path(file_record.meta_file_path)
        if meta_path is None and file_path is not None:
            meta_path = file_path.with_suffix(".meta.json")
        return bool(file_path and file_path.exists()), bool(
            meta_path and meta_path.exists()
        )

    def _resolve_optional_path(self, path_value: str | None) -> Path | None:
        if not path_value:
            return None
        path_obj = Path(path_value)
        if path_obj.is_absolute():
            return path_obj
        return to_absolute_path(path_value)

    def _build_source_missing_message(
        self, *, file_exists: bool, meta_exists: bool
    ) -> str:
        missing_parts = []
        if not file_exists:
            missing_parts.append("原始文件缺失")
        if not meta_exists:
            missing_parts.append("伴生文件缺失")
        return f"清空事实数据时跳过：{'、'.join(missing_parts)}，无法自动重建"

    def _empty_file_impact(self) -> dict[str, Any]:
        return {
            "resettable_files_count": 0,
            "source_missing_files_count": 0,
            "file_missing_files_count": 0,
            "meta_missing_files_count": 0,
            "file_and_meta_missing_files_count": 0,
            "skipped_failed_count": 0,
            "skipped_processing_count": 0,
            "skipped_disabled_shop_count": 0,
            "status_distribution": {},
        }
