"""统一模板漂移判定与计数服务 (SSOT)

背景
----
「模板待更新」在系统里曾有三条互不相干的判定路径:

1. ``GET /data-sync/governance/stats``
   直接统计 ``catalog_files.status = 'template_update_required'``
2. ``GET /data-sync/governance/detailed-coverage``
   重新采样文件, 用**当前**模板实时比对表头
3. ``GET /data-sync/files`` 行级 ``template_update_required`` 字段
   再次实时比对表头

三条路径口径不同, 于是同一时刻会出现三个互相矛盾的数字, 并且第 2/3 条路径
都会在「模板已被更新」之后把漂移证据抹掉 —— 模板一更新, 治理面板的
「需要更新」列表就变空, 而真正被卡住的文件仍然滞留在
``catalog_files.status = 'template_update_required'``.

本服务是唯一的判定与计数入口:

* 文件级: :meth:`DataSyncTemplateDriftService.resolve_file_state`
* 组合级: :meth:`DataSyncTemplateDriftService.list_drift_groups`
* 计数:   :meth:`DataSyncTemplateDriftService.count_files_requiring_update`

同时负责**漂移快照**的写入与读取: 快照记录「判定发生时」的模板版本与表头差异,
使得模板更新之后仍然可以回答「这个组合什么时候、因为哪一列变化而过不了校验」.

术语
----
* 漂移文件 (drift file): ``catalog_files.status = 'template_update_required'``
* 漂移快照 (drift snapshot): ``file_metadata['template_drift']``
* 组合 (group): ``(platform_code, data_domain, granularity, sub_domain)``
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select

from modules.core.db import CatalogFile

# file_metadata 中存放漂移快照的顶层键
DRIFT_SNAPSHOT_KEY = "template_drift"

# catalog_files.status 中表示「模板待更新」的取值
TEMPLATE_UPDATE_REQUIRED_STATUS = "template_update_required"

# 分组时单次扫描的最大文件数, 防止异常数据把内存打满
DRIFT_GROUP_SCAN_LIMIT = 5000


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DataSyncTemplateDriftService:
    """模板漂移的唯一判定 / 计数 / 快照入口。"""

    def __init__(self, db):
        self.db = db

    # ------------------------------------------------------------------
    # 漂移快照
    # ------------------------------------------------------------------
    @staticmethod
    def build_snapshot(
        status_info: Dict[str, Any],
        *,
        template: Any = None,
        catalog_file: Any = None,
        message: Optional[str] = None,
    ) -> Dict[str, Any]:
        """把一次判定结果整理成可持久化的漂移快照。"""
        header_changes = status_info.get("header_changes") or {}
        if not isinstance(header_changes, dict):
            header_changes = {}

        snapshot: Dict[str, Any] = {
            "detected_at": _utc_now_iso(),
            "template_status": status_info.get("template_status"),
            "governance_status": status_info.get("governance_status"),
            "reason": message
            or status_info.get("update_reason")
            or "模板表头与文件不一致",
            "added_fields": list(header_changes.get("added_fields") or []),
            "removed_fields": list(header_changes.get("removed_fields") or []),
            "match_rate": header_changes.get("match_rate"),
            "blocking_changes": list(header_changes.get("blocking_changes") or []),
            "non_blocking_changes": list(header_changes.get("non_blocking_changes") or []),
            # [*] 漂移来源: 区分「源文件结构变了」与「我们自己升级了模板」
            "drift_origin": status_info.get("drift_origin"),
            "template_baseline": status_info.get("template_baseline"),
            "baseline_template_id": status_info.get("baseline_template_id"),
            "baseline_template_version": status_info.get("baseline_template_version"),
            "template_outdated": bool(status_info.get("template_outdated")),
        }

        if template is not None:
            snapshot.update(
                {
                    "template_id": getattr(template, "id", None),
                    "template_name": getattr(template, "template_name", None),
                    "template_version": getattr(template, "version", None),
                    "template_header_row": getattr(template, "header_row", None),
                }
            )

        if catalog_file is not None:
            snapshot.update(
                {
                    "source_file_id": getattr(catalog_file, "id", None),
                    "source_file_name": getattr(catalog_file, "file_name", None),
                }
            )

        return snapshot

    @staticmethod
    def read_snapshot(catalog_file: Any) -> Optional[Dict[str, Any]]:
        """读取文件上已保存的漂移快照; 没有则返回 None。"""
        if catalog_file is None:
            return None
        metadata = getattr(catalog_file, "file_metadata", None) or {}
        if not isinstance(metadata, dict):
            return None
        snapshot = metadata.get(DRIFT_SNAPSHOT_KEY)
        if not isinstance(snapshot, dict):
            return None
        return snapshot

    @staticmethod
    def persist_snapshot(
        catalog_file: CatalogFile,
        status_info: Dict[str, Any],
        *,
        template: Any = None,
        message: Optional[str] = None,
    ) -> Dict[str, Any]:
        """把漂移快照写入 ``file_metadata``(不落盘, 由调用方决定 commit 时机)。"""
        snapshot = DataSyncTemplateDriftService.build_snapshot(
            status_info,
            template=template,
            catalog_file=catalog_file,
            message=message,
        )
        metadata = dict(catalog_file.file_metadata or {})
        metadata[DRIFT_SNAPSHOT_KEY] = snapshot
        catalog_file.file_metadata = metadata
        return snapshot

    # ------------------------------------------------------------------
    # 文件级判定
    # ------------------------------------------------------------------
    @staticmethod
    def resolve_file_state(
        catalog_file: CatalogFile,
        live_status: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """合并「持久化状态」与「实时判定」, 给出唯一的模板待更新结论。

        持久化状态优先: 文件一旦被标记为待更新, 即使当前模板已经更新到能匹配
        该文件, 它依然是一个**尚未处理完的待办**, 不能因为重算结果变成 ready
        就凭空消失。
        """
        live_status = live_status or {}
        snapshot = DataSyncTemplateDriftService.read_snapshot(catalog_file)

        persisted_requires_update = (
            getattr(catalog_file, "status", None) == TEMPLATE_UPDATE_REQUIRED_STATUS
        )
        live_requires_update = bool(live_status.get("template_update_required"))
        requires_update = persisted_requires_update or live_requires_update

        if persisted_requires_update and snapshot:
            update_reason = snapshot.get("reason")
            drift_source = "persisted"
        elif live_requires_update:
            update_reason = live_status.get("update_reason")
            drift_source = "live"
        else:
            update_reason = live_status.get("update_reason")
            drift_source = None

        return {
            "template_update_required": requires_update,
            "template_status": live_status.get("template_status"),
            "governance_status": live_status.get("governance_status"),
            "update_reason": update_reason,
            "drift_source": drift_source,
            "drift_snapshot": snapshot,
        }

    # ------------------------------------------------------------------
    # 组合级聚合
    # ------------------------------------------------------------------
    async def list_drift_groups(self) -> List[Dict[str, Any]]:
        """按组合聚合所有被标记为漂移的文件。

        这是「需要更新」列表的**唯一**数据来源: 以被标记漂移的文件为准,
        而不是拿当前模板去重新比对历史文件 —— 后者会在模板更新后把待办抹掉。
        """
        result = await self.db.execute(
            select(CatalogFile)
            .where(CatalogFile.status == TEMPLATE_UPDATE_REQUIRED_STATUS)
            .order_by(CatalogFile.first_seen_at.desc(), CatalogFile.id.desc())
            .limit(DRIFT_GROUP_SCAN_LIMIT)
        )
        rows = list(result.scalars().all())

        groups: Dict[Tuple[Any, Any, Any, Any], Dict[str, Any]] = {}
        for catalog_file in rows:
            key = (
                catalog_file.platform_code,
                catalog_file.data_domain,
                catalog_file.granularity,
                catalog_file.sub_domain,
            )
            snapshot = self.read_snapshot(catalog_file) or {}
            group = groups.get(key)
            if group is None:
                group = {
                    "platform": catalog_file.platform_code,
                    "domain": catalog_file.data_domain,
                    "sub_domain": catalog_file.sub_domain,
                    "granularity": catalog_file.granularity,
                    "file_count": 0,
                    "template_id": snapshot.get("template_id"),
                    "template_name": snapshot.get("template_name"),
                    "template_version": snapshot.get("template_version"),
                    "update_reason": snapshot.get("reason"),
                    "added_fields": list(snapshot.get("added_fields") or []),
                    "removed_fields": list(snapshot.get("removed_fields") or []),
                    "match_rate": snapshot.get("match_rate"),
                    "sample_file_id": catalog_file.id,
                    "sample_file_name": catalog_file.file_name,
                    "detected_at": snapshot.get("detected_at"),
                    "drift_origin": snapshot.get("drift_origin"),
                    "template_baseline": snapshot.get("template_baseline"),
                    "template_outdated": bool(snapshot.get("template_outdated")),
                    "drift_snapshot": snapshot or None,
                }
                groups[key] = group
                group["file_count"] += 1
                continue

            group["file_count"] += 1
            # [*] 组合里可能只有部分文件带漂移快照(快照功能上线前被标记的文件没有)。
            # 用带快照的文件补齐模板信息与原因, 否则待办原因会是空的。
            if not group.get("drift_snapshot") and snapshot:
                group["template_id"] = snapshot.get("template_id")
                group["template_name"] = snapshot.get("template_name")
                group["template_version"] = snapshot.get("template_version")
                group["update_reason"] = snapshot.get("reason")
                group["added_fields"] = list(snapshot.get("added_fields") or [])
                group["removed_fields"] = list(snapshot.get("removed_fields") or [])
                group["match_rate"] = snapshot.get("match_rate")
                group["detected_at"] = snapshot.get("detected_at")
                group["drift_origin"] = snapshot.get("drift_origin")
                group["template_baseline"] = snapshot.get("template_baseline")
                group["template_outdated"] = bool(snapshot.get("template_outdated"))
                group["drift_snapshot"] = snapshot

        return list(groups.values())

    async def count_files_requiring_update(self) -> int:
        """「模板待更新」的文件数(单一口径)。"""
        result = await self.db.execute(
            select(func.count(CatalogFile.id)).where(
                CatalogFile.status == TEMPLATE_UPDATE_REQUIRED_STATUS
            )
        )
        return int(result.scalar() or 0)


def get_drift_service(db) -> DataSyncTemplateDriftService:
    return DataSyncTemplateDriftService(db)
