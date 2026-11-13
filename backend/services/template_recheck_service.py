"""模板变更后的「受影响文件重检与放行」服务 (SSOT)。

背景
----
历史上, 「发布模板」与「重检文件」是**两件互不相干**的事:

* 发布模板 = 手动动作, 只写 ``core.field_mapping_templates``;
* 重检文件 = 定时动作, 跑在 ``auto_ingest_pending_files`` 里
  (Celery Beat 每 15 分钟一次, 每轮最多处理 20 个文件)。

⇒ 运营在界面上改完模板并保存, 界面**仍然**显示「模板已保存, 但该样本文件
仍未通过治理复核」—— 因为文件根本没被重新检查过, 它的漂移快照还在。
用户做对了却看不到效果, 要等一整轮巡检(积压时更久)。

业务上正确的模型
----------------
**一次模板变更的完成标准, 不是「新模板已保存」, 而是「受它影响的文件已经
重新评估过」。** 变更天然带一个「影响面复核」的后半段。

本服务就是那个后半段:

    保存模板 ⇒ 立刻重检同维度的待更新文件 ⇒ 能过的当场放行并解除待办

判定口径只有一份
----------------
重检**复用** ``DataSyncService.get_file_sync_readiness`` —— 与入库前置校验、
治理面板走的是同一条链路。**绝不另写一套判定**:
否则会出现「面板说过了、入库说没过」这种更难查的问题。

会话纪律
--------
判定在**独立只读会话**里做, 落库由**调用方的事务**统一做:
两个会话同时改同一行 ``file_metadata`` 会互相覆盖(后写的赢),
契约晋升会被外层的旧快照冲掉。
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from modules.core.db import CatalogFile, FieldMappingTemplate
from modules.core.logger import get_logger
from backend.services.data_sync_template_drift_service import (
    DataSyncTemplateDriftService,
)
from backend.services.template_contract_service import (
    CONTRACT_SOURCE_PROMOTION,
    build_template_contract,
    write_template_contract,
)

logger = get_logger(__name__)


#: 单次重检最多处理多少个文件(与定时巡检共用同一口径)。
TEMPLATE_RECHECK_MAX_FILES = max(
    1, int(os.getenv("AUTO_INGEST_TEMPLATE_RECHECK_MAX_FILES", "20"))
)

#: 重检扫描窗口倍数: 队列按「最近一次重检时间」轮转,
#: 扫描窗口必须大于单次处理上限, 否则永久阻塞的文件会一直占满前面的名额,
#: 把后面的文件饿死(实测: 27 个待更新文件里, analytics 的 2 个排在第 24/27 位,
#: 永远不被重检)。
TEMPLATE_RECHECK_SCAN_FACTOR = max(
    1, int(os.getenv("AUTO_INGEST_TEMPLATE_RECHECK_SCAN_FACTOR", "5"))
)

#: 连续重检仍阻塞多少轮后, 降级为「需要人工处理模板」。
TEMPLATE_RECHECK_MAX_BLOCKED_ROUNDS = max(
    1, int(os.getenv("AUTO_INGEST_TEMPLATE_RECHECK_MAX_ROUNDS", "3"))
)

#: 文件处于「模板待更新」的状态值。
TEMPLATE_UPDATE_REQUIRED_STATUS = "template_update_required"


class TemplateRecheckService:
    """受影响文件的重检与放行。"""

    # ------------------------------------------------------------------
    # 只读评估
    # ------------------------------------------------------------------
    @staticmethod
    async def evaluate_files(file_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        """对一批文件做**只读**评估。

        判定走 ``DataSyncService.get_file_sync_readiness``
        (= 与入库前置校验、治理面板同一条链路), 并把「待落库的晋升契约」
        一并算出来 —— 落库由调用方的事务统一做。
        """
        from backend.models.database import AsyncSessionLocal
        from backend.services.data_sync_service import DataSyncService

        results: Dict[int, Dict[str, Any]] = {}
        if not file_ids:
            return results

        db_local = AsyncSessionLocal()
        try:
            for file_id in file_ids:
                try:
                    readiness = await DataSyncService(db_local).get_file_sync_readiness(
                        file_id,
                        use_template_header_row=True,
                    )
                    results[file_id] = readiness if isinstance(readiness, dict) else {}
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "[TemplateRecheck] 重检失败 file_id=%s: %s",
                        file_id,
                        exc,
                        exc_info=True,
                    )
                    results[file_id] = {
                        "should_auto_sync": False,
                        "update_reason": str(exc),
                        "promoted_contract": None,
                    }
                # 契约晋升: 判定链路发现「契约基准已解释不了这个文件,
                # 当前已发布模板可以」时, 会给出 contract_promotion 信号。
                # 这里把新契约**算出来**(不落库)。
                results[file_id]["promoted_contract"] = (
                    await TemplateRecheckService.build_promoted_contract(
                        db_local,
                        results[file_id],
                    )
                )
        finally:
            try:
                await db_local.close()
            except Exception:  # noqa: BLE001
                pass
        return results

    @staticmethod
    async def build_promoted_contract(
        db,
        readiness: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """按判定链路的 ``contract_promotion`` 信号算出新契约(**不落库**)。

        为什么单独一步
        --------------
        判定链路发现「契约指向的模板已经解释不了这个文件, 而当前已发布模板
        可以」时, 会给出 ``contract_promotion`` 信号。这里把新契约**算出来**
        交给外层同步会话写入 —— 两个会话同时改同一行 ``file_metadata`` 会
        互相覆盖(后写的赢), 契约晋升会被外层的旧快照冲掉。

        落库后契约就指向了「当前能解释这个文件的那一版模板」, 基准重新稳定;
        否则契约会一直把文件钉在旧模板上, 下一轮重检又被打回。
        """
        promotion = (readiness or {}).get("contract_promotion")
        if not isinstance(promotion, dict):
            return None
        to_template_id = promotion.get("to_template_id")
        if to_template_id is None:
            return None
        try:
            template = await db.get(FieldMappingTemplate, int(to_template_id))
        except (TypeError, ValueError):
            return None
        if template is None:
            return None
        contract = build_template_contract(
            template,
            source=CONTRACT_SOURCE_PROMOTION,
        )
        if not contract:
            return None
        logger.info(
            "[TemplateRecheck] 契约晋升: 模板 v%s -> v%s (%s)",
            promotion.get("from_template_version"),
            promotion.get("to_template_version"),
            getattr(template, "template_name", None),
        )
        return contract

    # ------------------------------------------------------------------
    # 落库
    # ------------------------------------------------------------------
    @staticmethod
    def apply_recheck(file_record: Any, readiness: Dict[str, Any]) -> bool:
        """把重检结论落到文件行上(调用方负责 commit)。

        Returns:
            ``True`` = 已放行(文件回到 ``pending``, 待办解除);
            ``False`` = 仍被模板阻塞(已刷新漂移快照与阻塞轮次)。
        """
        if file_record is None:
            return False

        now = datetime.now(timezone.utc)
        meta = dict(getattr(file_record, "file_metadata", None) or {})
        auto_meta = dict(meta.get("auto_ingest") or {})

        if (readiness or {}).get("should_auto_sync") is True:
            auto_meta["last_status"] = "readiness_recovered"
            auto_meta["last_recovered_at"] = now.isoformat()
            auto_meta["last_recovered_from"] = TEMPLATE_UPDATE_REQUIRED_STATUS
            auto_meta["current_task_id"] = None
            auto_meta["last_template_status"] = readiness.get("template_status")
            auto_meta["last_governance_status"] = readiness.get("governance_status")
            # 漂移已解决: 快照移入历史, 不再占用当前漂移位。
            # 历史文件可能本来就没有快照(快照功能上线前被标记的),
            # 这时也要把「本次重检确认已放行」的信息留痕, 便于追溯。
            previous_snapshot = meta.pop("template_drift", None)
            resolved_snapshot = previous_snapshot or {
                "detected_at": now.isoformat(),
                "template_status": readiness.get("template_status"),
                "governance_status": readiness.get("governance_status"),
                "reason": "模板已更新，重检确认可正常入库",
                "source_file_id": getattr(file_record, "id", None),
                "source_file_name": getattr(file_record, "file_name", None),
            }
            auto_meta["last_resolved_drift"] = resolved_snapshot
            auto_meta.pop("blocked_rounds", None)
            auto_meta.pop("needs_manual_template_update", None)
            meta["auto_ingest"] = auto_meta
            file_record.file_metadata = meta

            # 契约晋升落库: 契约基准已解释不了这个文件, 当前已发布模板可以 ——
            # 把契约改写成当前版本, 否则契约会继续把文件钉在旧模板上,
            # 下一轮重检又被打回(而且入库会按旧模板解析, 丢掉新增字段)。
            promoted_contract = (readiness or {}).get("promoted_contract")
            if promoted_contract:
                write_template_contract(file_record, promoted_contract)

            file_record.status = "pending"
            file_record.error_message = None
            return True

        # 仍被阻塞: 刷新阻塞轮次与漂移快照, 让人看得见「还差什么」。
        reason = (
            readiness.get("update_reason")
            or readiness.get("message")
            or readiness.get("error_code")
            # 已有更具体的报错就沿用它(比如「无模板(platform=…, domain=…)」),
            # 别把信息降级成一句 error_code。
            or getattr(file_record, "error_message", None)
            or "template update required before ingest"
        )
        auto_meta["last_status"] = TEMPLATE_UPDATE_REQUIRED_STATUS
        auto_meta["last_reason"] = str(reason)
        auto_meta["last_rechecked_at"] = now.isoformat()
        auto_meta["current_task_id"] = None
        auto_meta["last_template_status"] = readiness.get("template_status")
        auto_meta["last_governance_status"] = readiness.get("governance_status")
        # 连续重检仍阻塞 -> 降级为「需要人工处理模板」, 避免永久静默占用队列
        blocked_rounds = int(auto_meta.get("blocked_rounds") or 0) + 1
        auto_meta["blocked_rounds"] = blocked_rounds
        if blocked_rounds >= TEMPLATE_RECHECK_MAX_BLOCKED_ROUNDS:
            auto_meta["needs_manual_template_update"] = True
            auto_meta["last_status"] = "needs_manual_template_update"
            logger.warning(
                "[TemplateRecheck] 文件连续%d轮重检仍被模板阻塞, 降级为需人工处理模板: %s (%s)",
                blocked_rounds,
                getattr(file_record, "file_name", None),
                reason,
            )
        meta["auto_ingest"] = auto_meta
        file_record.file_metadata = meta

        # 回填/刷新漂移快照: 让治理面板能展示「漂移发生时」的模板版本与表头差异
        try:
            DataSyncTemplateDriftService.persist_snapshot(
                file_record,
                readiness,
                message=str(reason),
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "[TemplateRecheck] persist drift snapshot skipped for %s: %s",
                getattr(file_record, "file_name", None),
                exc,
            )
        return False

    # ------------------------------------------------------------------
    # 对外入口
    # ------------------------------------------------------------------
    @classmethod
    async def recheck_dimension(
        cls,
        db,
        *,
        platform: str,
        data_domain: str,
        granularity: Optional[str] = None,
        sub_domain: Optional[str] = None,
        account: Optional[str] = None,
        limit: int = TEMPLATE_RECHECK_MAX_FILES,
    ) -> Dict[str, Any]:
        """模板发布后: 重检同维度待更新的文件并放行。

        Args:
            db: 调用方的会话(``AsyncSession``)。落库由调用方事务负责。
            platform / data_domain / granularity / sub_domain / account:
                受本次发布影响的维度。``sub_domain`` / ``account`` 为空表示不限定。

        Returns:
            ``{"checked": int, "released": int, "still_blocked": int, "file_ids": [...]}``
        """
        try:
            stmt = select(CatalogFile).where(
                CatalogFile.status == TEMPLATE_UPDATE_REQUIRED_STATUS,
                CatalogFile.platform_code == platform,
                CatalogFile.data_domain == data_domain,
            )
            if granularity:
                stmt = stmt.where(CatalogFile.granularity == granularity)
            if sub_domain:
                stmt = stmt.where(CatalogFile.sub_domain == sub_domain)
            if account:
                stmt = stmt.where(CatalogFile.account == account)
            stmt = stmt.order_by(CatalogFile.first_seen_at.asc()).limit(
                max(1, int(limit))
            )
            result = await db.execute(stmt)
            files = list(result.scalars().all())
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[TemplateRecheck] 受影响文件查询失败 platform=%s domain=%s: %s",
                platform,
                data_domain,
                exc,
            )
            return {"checked": 0, "released": 0, "still_blocked": 0, "file_ids": []}

        if not files:
            return {"checked": 0, "released": 0, "still_blocked": 0, "file_ids": []}

        file_ids = [
            int(item.id) for item in files if getattr(item, "id", None) is not None
        ]
        readiness_by_id = await cls.evaluate_files(file_ids)

        released = 0
        still_blocked = 0
        for file_record in files:
            readiness = readiness_by_id.get(int(file_record.id), {})
            if cls.apply_recheck(file_record, readiness):
                released += 1
            else:
                still_blocked += 1

        logger.info(
            "[TemplateRecheck] 维度重检完成 platform=%s domain=%s granularity=%s: "
            "checked=%s released=%s still_blocked=%s",
            platform,
            data_domain,
            granularity,
            len(file_ids),
            released,
            still_blocked,
        )
        return {
            "checked": len(file_ids),
            "released": released,
            "still_blocked": still_blocked,
            "file_ids": file_ids,
        }
