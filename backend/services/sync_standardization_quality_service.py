"""Lightweight post-sync standardization quality checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.logger import get_logger


logger = get_logger(__name__)


@dataclass(frozen=True)
class SyncQualitySnapshot:
    raw_rows: int
    distinct_hashes: int
    semantic_rows: int
    semantic_non_null_rates: Dict[str, float] = field(default_factory=dict)
    mart_rows: int = 0


def build_sync_quality_warnings(snapshot: SyncQualitySnapshot) -> List[str]:
    warnings: List[str] = []
    if snapshot.raw_rows > 1 and snapshot.distinct_hashes <= max(1, int(snapshot.raw_rows * 0.1)):
        warnings.append(
            f"Hash 风险: distinct data_hash 只有 {snapshot.distinct_hashes}/{snapshot.raw_rows}，可能存在身份字段缺失导致覆盖。"
        )
    for field_name, non_null_rate in snapshot.semantic_non_null_rates.items():
        if snapshot.semantic_rows > 0 and non_null_rate <= 0:
            warnings.append(f"标准化异常: {field_name} 非空率为 0，semantic 层可能缺少字段别名。")
    if snapshot.raw_rows > 0 and snapshot.mart_rows == 0:
        warnings.append("标准化异常: mart 层未生成记录。")
    return warnings


class SyncStandardizationQualityService:
    PRODUCT_FIELDS = ["product_id", "product_name", "item_status"]

    async def check_products_file(
        self,
        db: AsyncSession,
        *,
        platform_code: str,
        granularity: str,
        file_ids: Iterable[int],
    ) -> Dict[str, object]:
        ids = [int(file_id) for file_id in file_ids if file_id is not None]
        if not ids:
            return {"warnings": [], "snapshot": None}

        if not platform_code.replace("_", "").isalnum() or not granularity.replace("_", "").isalnum():
            return {"warnings": [], "snapshot": None}
        raw_table = f"b_class.fact_{platform_code}_products_{granularity}"
        try:
            raw_result = await db.execute(
                text(
                    f"""
                    SELECT COUNT(*) AS raw_rows, COUNT(DISTINCT data_hash) AS distinct_hashes
                    FROM {raw_table}
                    WHERE file_id = ANY(:file_ids)
                    """
                ),
                {"file_ids": ids},
            )
            raw_row = raw_result.mappings().one()

            semantic_result = await db.execute(
                text(
                    f"""
                    SELECT
                        COUNT(*) AS semantic_rows,
                        COUNT(product_id)::float / NULLIF(COUNT(*), 0) AS product_id_rate,
                        COUNT(product_name)::float / NULLIF(COUNT(*), 0) AS product_name_rate,
                        COUNT(item_status)::float / NULLIF(COUNT(*), 0) AS item_status_rate
                    FROM semantic.fact_products_atomic
                    WHERE data_hash IN (
                        SELECT data_hash
                        FROM {raw_table}
                        WHERE file_id = ANY(:file_ids)
                    )
                    """
                ),
                {"file_ids": ids},
            )
            semantic_row = semantic_result.mappings().one()

            mart_rows = int(semantic_row["semantic_rows"] or 0)
            if granularity == "daily":
                mart_result = await db.execute(
                    text(
                        f"""
                        SELECT COUNT(*) AS mart_rows
                        FROM mart.product_day_kpi
                        WHERE platform_code = :platform_code
                          AND period_date IN (
                              SELECT DISTINCT metric_date::date
                              FROM {raw_table}
                              WHERE file_id = ANY(:file_ids)
                          )
                        """
                    ),
                    {"file_ids": ids, "platform_code": platform_code},
                )
                mart_row = mart_result.mappings().one()
                mart_rows = int(mart_row["mart_rows"] or 0)
            snapshot = SyncQualitySnapshot(
                raw_rows=int(raw_row["raw_rows"] or 0),
                distinct_hashes=int(raw_row["distinct_hashes"] or 0),
                semantic_rows=int(semantic_row["semantic_rows"] or 0),
                semantic_non_null_rates={
                    "product_id": float(semantic_row["product_id_rate"] or 0),
                    "product_name": float(semantic_row["product_name_rate"] or 0),
                    "item_status": float(semantic_row["item_status_rate"] or 0),
                },
                mart_rows=mart_rows,
            )
            return {"warnings": build_sync_quality_warnings(snapshot), "snapshot": snapshot}
        except SQLAlchemyError as exc:
            logger.warning("[SyncQuality] standardization quality check skipped: %s", exc)
            return {"warnings": [], "snapshot": None}
