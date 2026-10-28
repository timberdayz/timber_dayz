"""历史文件模板契约回填 (D7)

为什么需要
----------
模板契约(D1)是「表头比对的基准」, 但它只在**采集落库登记**那一刻写入。
在此之前入库的历史文件没有契约 —— 判定时只能拿「当前最新已发布模板」当基准,
于是我们每升级一次模板, 这些文件全被判成结构漂移。

跨 family 变体接管(D7)解决了「找谁解释这个文件」, 但它只在**判定时**生效,
不落库 ⇒ 文件的持久化状态仍然是「模板待更新」, 永远进不了自动入库队列。

本服务把两件事合起来:

1. 用**与在线链路完全相同**的判定口径(:func:`resolve_baseline_for_file`)
   算出这个文件该由哪一版模板解释
2. 把结论写成模板契约(含接管来源留痕), 让后续判定有稳定的基准
3. 重检通过的文件把持久化状态复位为 ``pending``, 让它回到自动入库队列

口径一致性是这里最要紧的事 —— 如果离线脚本用另一套规则, 回填出来的契约
可能指向错误的模板, 比不回填还糟。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import CatalogFile
from modules.core.logger import get_logger

from backend.services.data_sync_status_semantics import (
    TEMPLATE_BASELINE_CROSS_FAMILY_VARIANT,
)
from backend.services.template_contract_service import (
    CONTRACT_SOURCE_TAKEOVER,
    build_template_contract,
    read_template_contract,
    write_template_contract,
)
from backend.services.template_matcher import get_template_matcher
from backend.services.template_variant_takeover_service import (
    resolve_baseline_for_file,
)

logger = get_logger(__name__)


# 回填结果的分类
BACKFILL_WRITTEN = "written"
BACKFILL_SKIPPED_HAS_CONTRACT = "skipped_has_contract"
BACKFILL_SKIPPED_NO_TAKEOVER = "skipped_no_takeover"
BACKFILL_SKIPPED_FILE_MISSING = "skipped_file_missing"
BACKFILL_SKIPPED_UNREADABLE = "skipped_unreadable"


class TemplateContractBackfillService:
    """为历史文件回填模板契约。"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.template_matcher = get_template_matcher(db)

    async def _load_targets(
        self,
        *,
        statuses: Sequence[str],
        limit: Optional[int],
    ) -> List[CatalogFile]:
        stmt = select(CatalogFile)
        if statuses:
            stmt = stmt.where(CatalogFile.status.in_(list(statuses)))
        if limit:
            stmt = stmt.limit(int(limit))
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def backfill(
        self,
        *,
        catalog_files: Optional[Sequence[CatalogFile]] = None,
        statuses: Sequence[str] = ("template_update_required",),
        limit: Optional[int] = None,
        dry_run: bool = True,
        reset_status: bool = True,
    ) -> Dict[str, Any]:
        """回填模板契约。

        Args:
            catalog_files: 显式指定要处理的文件(不给则按 statuses 查询)
            statuses: 未指定文件时, 按哪些状态筛选
            limit: 处理条数上限
            dry_run: True = 只演算不落库
            reset_status: 重检通过后是否把持久化状态复位为 ``pending``

        Returns:
            ``{"written": [...], "skipped": {...}, "summary": {...}}``
        """
        from backend.services.spreadsheet_header_reader import (
            get_spreadsheet_header_reader,
        )

        targets = (
            list(catalog_files)
            if catalog_files is not None
            else await self._load_targets(statuses=statuses, limit=limit)
        )

        reader = get_spreadsheet_header_reader(
            log_prefix="ContractBackfill",
            use_cpu_executor=False,
        )

        written: List[Dict[str, Any]] = []
        skipped: Dict[str, List[int]] = {
            BACKFILL_SKIPPED_HAS_CONTRACT: [],
            BACKFILL_SKIPPED_NO_TAKEOVER: [],
            BACKFILL_SKIPPED_FILE_MISSING: [],
            BACKFILL_SKIPPED_UNREADABLE: [],
        }

        for catalog_file in targets:
            file_id = getattr(catalog_file, "id", None)
            if file_id is None:
                continue

            if read_template_contract(catalog_file):
                skipped[BACKFILL_SKIPPED_HAS_CONTRACT].append(file_id)
                continue

            published_template = await self.template_matcher.find_best_template(
                platform=catalog_file.platform_code,
                data_domain=catalog_file.data_domain,
                granularity=catalog_file.granularity,
                sub_domain=(
                    catalog_file.sub_domain if catalog_file.sub_domain else None
                ),
                account=(getattr(catalog_file, "account", None) or None),
            )

            header_cache: Dict[int, Any] = {}

            async def read_at(row: int):
                if row not in header_cache:
                    header_cache[row] = await reader.read_header(
                        str(catalog_file.file_path),
                        header_row=row,
                        nrows=5,
                    )
                return header_cache[row]

            async def read_columns(row: int) -> List[str]:
                cached = await read_at(row)
                if not getattr(cached, "ok", False):
                    error = getattr(cached, "error", None)
                    if error:
                        raise FileNotFoundError(str(error))
                    return []
                return list(cached.columns or [])

            try:
                baseline = await resolve_baseline_for_file(
                    self.db,
                    catalog_file=catalog_file,
                    published_template=published_template,
                    contract_template=None,
                    read_header=read_columns,
                )
            except FileNotFoundError:
                skipped[BACKFILL_SKIPPED_FILE_MISSING].append(file_id)
                continue
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[ContractBackfill] 判定失败 id=%s: %s", file_id, exc
                )
                skipped[BACKFILL_SKIPPED_UNREADABLE].append(file_id)
                continue

            if baseline.get("baseline_kind") != TEMPLATE_BASELINE_CROSS_FAMILY_VARIANT:
                skipped[BACKFILL_SKIPPED_NO_TAKEOVER].append(file_id)
                continue

            baseline_template = baseline.get("baseline_template")
            takeover = baseline.get("takeover") or {}
            if baseline_template is None:
                skipped[BACKFILL_SKIPPED_NO_TAKEOVER].append(file_id)
                continue

            contract = build_template_contract(
                baseline_template,
                source=CONTRACT_SOURCE_TAKEOVER,
                takeover=takeover,
            )
            if not contract:
                skipped[BACKFILL_SKIPPED_NO_TAKEOVER].append(file_id)
                continue

            record = {
                "file_id": file_id,
                "file_name": getattr(catalog_file, "file_name", None),
                "template_id": contract.get("template_id"),
                "template_name": contract.get("template_name"),
                "header_row": contract.get("header_row"),
                "takeover_family_id": takeover.get("source_family_id"),
                "takeover_family_granularity": takeover.get("source_family_granularity"),
                "takeover_variant_key": takeover.get("variant_key"),
                "match_rate": takeover.get("match_rate"),
                "missing_headers": takeover.get("missing_headers"),
            }

            if dry_run:
                written.append({**record, "applied": False})
                continue

            write_template_contract(catalog_file, contract)

            if reset_status:
                record["status_reset"] = await self._reset_status_if_ready(
                    catalog_file,
                    baseline=baseline,
                )

            written.append({**record, "applied": True})

        if not dry_run and written:
            await self.db.commit()

        summary = {
            "total": len(targets),
            "written": sum(1 for item in written if item.get("applied")),
            "planned": sum(1 for item in written if not item.get("applied")),
            "skipped": {key: len(value) for key, value in skipped.items()},
        }
        return {"written": written, "skipped": skipped, "summary": summary}

    async def _reset_status_if_ready(
        self,
        catalog_file: CatalogFile,
        *,
        baseline: Dict[str, Any],
    ) -> bool:
        """回填后重检, 通过则把文件状态复位为 ``pending``。

        复检用与判定链路同一套口径(:func:`resolve_baseline_for_file` +
        表头比对), 不另起一套规则。
        """
        from backend.services.data_sync_template_status_service import (
            DataSyncTemplateStatusService,
        )

        service = DataSyncTemplateStatusService(self.db)
        try:
            status = await service.evaluate_catalog_file(
                catalog_file,
                template=baseline.get("baseline_template"),
                current_columns=baseline.get("header_columns") or [],
                header_row=baseline.get("header_row"),
                takeover=baseline.get("takeover"),
                baseline_template_override=baseline.get("baseline_template"),
                baseline_kind_override=baseline.get("baseline_kind"),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[ContractBackfill] 回填后复检失败 id=%s: %s",
                getattr(catalog_file, "id", None),
                exc,
            )
            return False

        if not status.get("should_auto_sync"):
            return False

        catalog_file.status = "pending"
        catalog_file.error_message = None
        metadata = dict(catalog_file.file_metadata or {})
        auto_meta = dict(metadata.get("auto_ingest") or {})
        auto_meta["last_status"] = "readiness_recovered"
        auto_meta["last_recovered_from"] = "template_update_required"
        auto_meta["last_recovered_by"] = CONTRACT_SOURCE_TAKEOVER
        auto_meta["last_template_status"] = status.get("template_status")
        auto_meta["last_governance_status"] = status.get("governance_status")
        auto_meta["current_task_id"] = None
        metadata["auto_ingest"] = auto_meta
        catalog_file.file_metadata = metadata
        return True


def get_template_contract_backfill_service(
    db: AsyncSession,
) -> TemplateContractBackfillService:
    """获取模板契约回填服务实例。"""
    return TemplateContractBackfillService(db)
