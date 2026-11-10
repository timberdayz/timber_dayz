"""源数据断流的**通知出口**（复用仓库既有通道，不新造通知体系）。

复用的现成通道
--------------
1. **站内信**：``backend/domains/platform/routers/notifications.py``
   里的 ``create_notifications_for_admins``（通知类型 ``NotificationType.SYSTEM_ALERT``
   —— 枚举早就预留好了，只是此前零调用）。
2. **webhook / 钉钉**：``backend/services/alert_service.py`` 的
   ``send_resource_alert``（它自带**进程内冷却**：
   ``RESOURCE_MONITOR_ALERT_COOLDOWN_MINUTES``）。

⚠️ **不用** ``core.alert_rules``（``AlertRule``）那套：它只有 CRUD、**没有求值器**
（前端也写「开发中」）⇒ 当不了现成通道。**别让它继续冒充 SSOT** ——
真要启用它，得先补求值器，那是另一件事。

飞书投影（``backend/services/feishu_projection_service.py``）也**不用**：
它是「业务记录 → 飞书多维表格」的业务投影（entity_type + 表 id + 字段映射），
不是告警消息通道；接它就得新增表与字段映射 = 另造一套通知体系。

去重（不轰炸）
--------------
同一问题连续多轮只通知一次。去重状态落在**既有的运行日志**里：
``ops.pipeline_run_log.context.notified_stale_chains``（该表已有、**不加表不加迁移**）。

- 上一轮已通知过、且本轮仍然断流的链 ⇒ 本轮不再通知；
- 链恢复（不再断流）后再次断流 ⇒ 重新通知（它已不在上一轮的通知集合里）；
- 通知两条通道都失败 ⇒ 不记入已通知集合，下一轮重试。

脱敏
----
通知内容里**只有**：链名、源表名、落后天数、允许滞后上限、巡检 run_id。
连接串、口令、token、原始数据行一律不进通知（见 :func:`mask_sensitive_text`）。
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.logger import get_logger

__all__ = [
    "SOURCE_FRESHNESS_ALERT_TYPE",
    "build_alert_payload",
    "dispatch_source_freshness_alerts",
    "load_notified_stale_chains",
    "mask_sensitive_text",
]

logger = get_logger(__name__)

#: ``alert_service.send_resource_alert`` 的 alert_type（它的冷却键）。
SOURCE_FRESHNESS_ALERT_TYPE = "source_freshness_stale"

_LOAD_NOTIFIED_SQL = """
SELECT context
FROM ops.pipeline_run_log
WHERE pipeline_name = :pipeline_name
ORDER BY started_at DESC, id DESC
LIMIT 1
"""

_URL_CREDENTIALS_PATTERN = re.compile(r"://[^\s/@:]+:[^\s/@]+@")
_SECRET_KV_PATTERN = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key)\s*=\s*[^\s;,&]+"
)


def mask_sensitive_text(value: str) -> str:
    """把连接串口令 / token / 密钥形态的内容替换掉。

    通知内容会进站内信 / 钉钉 / 邮件，**不能**带凭据。
    这里只做「形态级」的兜底脱敏（不是 DLP）—— 真正的规则是：
    **不要把连接串、口令、原始数据写进通知**。
    """
    masked = value or ""
    masked = _URL_CREDENTIALS_PATTERN.sub("://***:***@", masked)
    masked = _SECRET_KV_PATTERN.sub(lambda match: f"{match.group(1)}=***", masked)
    return masked


def _extract_previous_notified(context: Any) -> set[str]:
    """从上一轮运行日志的 context 里取「已通知过的链」。"""
    if context is None:
        return set()
    payload: Any = context
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8", errors="replace")
    if isinstance(payload, str):
        text_value = payload.strip()
        if not text_value:
            return set()
        try:
            payload = json.loads(text_value)
        except (TypeError, ValueError):
            return set()
    if not isinstance(payload, dict):
        return set()
    raw = payload.get("notified_stale_chains")
    if not isinstance(raw, (list, tuple, set)):
        return set()
    return {str(item) for item in raw if str(item or "").strip()}


async def load_notified_stale_chains(
    db: AsyncSession, *, pipeline_name: str
) -> set[str]:
    """读上一轮巡检「已通知过的链」集合（读不到就当空集合 ⇒ 该轮全部新问题）。"""
    try:
        result = await db.execute(
            text(_LOAD_NOTIFIED_SQL), {"pipeline_name": pipeline_name}
        )
        rows = result.fetchall()
    except Exception as exc:  # noqa: BLE001 —— 读不到就当没有历史，不让巡检挂掉
        logger.warning(
            "[SourceFreshnessNotify] 读上一轮通知状态失败，按「无历史」处理: %s", exc
        )
        return set()

    if not rows:
        return set()
    first = rows[0]
    context = first[0] if isinstance(first, (tuple, list)) else first
    return _extract_previous_notified(context)


def build_alert_payload(report: Any, chain_labels: Iterable[str]) -> dict[str, Any]:
    """构造通知载荷（**脱敏**：只有链名/表名/天数/上限/run_id）。"""
    wanted = {str(label) for label in chain_labels}
    chains: list[dict[str, Any]] = []
    for row in getattr(report, "stale_rows", []) or []:
        label = getattr(row, "chain_label", "")
        if label not in wanted:
            continue
        chains.append(
            {
                "chain": label,
                "table_name": getattr(row, "table_name", ""),
                "business_age_days": getattr(row, "business_age_days", None),
                "max_age_days": getattr(row, "max_age_days", None),
                "latest_metric_date": (
                    getattr(row, "max_metric_date", None).isoformat()
                    if getattr(row, "max_metric_date", None)
                    else None
                ),
            }
        )

    return {
        "pipeline": getattr(report, "pipeline_name", "source_freshness_check"),
        "run_id": getattr(report, "run_id", ""),
        "chains": chains,
    }


def _build_alert_text(payload: dict[str, Any]) -> tuple[str, str]:
    """(标题, 正文)。正文只列链名/表名/天数，不含任何原始数据。"""
    chains = payload.get("chains") or []
    title = f"[源数据断流] {len(chains)} 条业务链超过新鲜度上限"
    lines = [
        "以下业务链的最新业务日期已超过允许滞后天数（且仍在当前采集范围内）：",
        "",
    ]
    for item in chains:
        age = item.get("business_age_days")
        limit = item.get("max_age_days")
        age_text = "未知" if age is None else f"{age} 天"
        limit_text = "未知" if limit is None else f"{limit} 天"
        lines.append(
            f"- {item.get('chain')}：落后 {age_text}（上限 {limit_text}），"
            f"源表 {item.get('table_name')}"
        )
    lines.append("")
    lines.append(f"巡检 run_id：{payload.get('run_id')}")
    lines.append("已停采（不在当前采集范围）的链不在本通知里，它们不拉高整体红灯。")
    return title, mask_sensitive_text("\n".join(lines))


async def _dispatch_in_app(
    db: AsyncSession, title: str, content: str, payload: dict[str, Any]
) -> bool:
    """站内信（管理员）。"""
    from backend.domains.platform.routers.notifications import (
        create_notifications_for_admins,
    )
    from backend.schemas.notification import NotificationType

    notifications = await create_notifications_for_admins(
        db=db,
        notification_type=NotificationType.SYSTEM_ALERT,
        title=title,
        content=content,
        extra_data=payload,
        priority="high",
    )
    count = len(notifications or [])
    if count == 0:
        logger.warning("[SourceFreshnessNotify] 没有管理员账号，站内信未送达")
    return True


async def dispatch_source_freshness_alerts(
    db: AsyncSession,
    report: Any,
    chain_labels: Iterable[str],
) -> set[str]:
    """把「本轮新出现的断流」推送到现成通道。

    返回**已成功投递**的链标签集合（两条通道都失败 ⇒ 空集合 ⇒ 下一轮重试）。
    """
    labels = [str(label) for label in chain_labels if str(label or "").strip()]
    if not labels:
        return set()

    payload = build_alert_payload(report, labels)
    title, content = _build_alert_text(payload)

    in_app_ok = False
    try:
        await _dispatch_in_app(db, title, content, payload)
        in_app_ok = True
    except Exception as exc:  # noqa: BLE001 —— 通知失败不能拖垮巡检
        logger.error("[SourceFreshnessNotify] 站内信发送失败: %s", exc, exc_info=True)
        # 站内信是数据库写入 ⇒ 失败后当前事务已处于失败状态，必须回滚，
        # 否则后面写 ops 运行日志会跟着炸。
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            logger.error("[SourceFreshnessNotify] 回滚失败", exc_info=True)

    webhook_ok = False
    try:
        from backend.services import alert_service

        await alert_service.send_resource_alert(SOURCE_FRESHNESS_ALERT_TYPE, content)
        webhook_ok = True
    except Exception as exc:  # noqa: BLE001
        logger.error("[SourceFreshnessNotify] webhook/钉钉告警发送失败: %s", exc)

    if in_app_ok or webhook_ok:
        return set(labels)
    return set()
