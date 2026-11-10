"""采集失败**主动告警**（批次 3.4 / 任务单 P2-5）的通知出口。

复用的现成通道
--------------
1. **站内信**：``backend/domains/platform/routers/notifications.py`` 里的
   ``create_notifications_for_admins``（通知类型 ``NotificationType.SYSTEM_ALERT``
   —— 枚举早就预留好了，只是此前零调用）。
2. **webhook / 钉钉**：``backend/services/alert_service.py`` 的
   ``send_resource_alert``（自带**进程内冷却**：
   ``RESOURCE_MONITOR_ALERT_COOLDOWN_MINUTES``）。

⚠️ **不用** ``core.alert_rules``（``AlertRule``）那套：它只有 CRUD、**没有求值器**
（前端也写「开发中」）⇒ 当不了现成通道。**别让它继续冒充 SSOT** —— 真要启用它，
得先补求值器，那是另一件事（本批次不做）。

飞书投影（``backend/services/feishu_projection_service.py``）也**不用**：它是
「业务记录 → 飞书多维表格」的业务投影（entity_type + 表 id + 字段映射），不是告警
消息通道；接它就得新增表与字段映射 = 另造一套通知体系。

什么时候才告警
--------------
只有**任务真的落到失败终态**（``collection_task_status.STATUS.FAILED``）才告警：

- ``partial_success``（部分域成功）**不算失败告警** —— 它是「采到了一部分」，
  属于另一档。本模块只把它**单独记一档**（运行日志里的
  ``partial_success_clusters``），**不发通知** ⇒ 半夜不会被半成功刷屏。
- 「等待验证码回填」**单独归类**（``category=verification_wait``），
  **不与步骤失败混在一起**：它的终态本来就是 ``paused`` /
  ``manual_intervention_required``（不是 ``failed``）⇒ 不触发失败告警，
  只在运行日志里单独记一档。

同一轮聚类
----------
「一轮」= 一次采集轮次（``CollectionConfigRun``）。同一轮里 7 个店挂在同一个错误上
⇒ 按**归一化错误指纹**聚成 **1 条**通知，而不是 7 条。

跨轮去重
--------
同一问题连续多轮只通知一次。去重状态落在**既有的运行日志**里：
``ops.pipeline_run_log``（该表已有、**不加表不加迁移**）的
``context.notified_collection_failures``。

- 上一轮已通知过、且本轮仍然失败 ⇒ 本轮不再通知；
- 恢复（本轮不再失败）后再次失败 ⇒ 重新通知（它已不在上一轮的通知集合里）；
- 两条通道都失败 ⇒ 不记入已通知集合，下一轮重试。

脱敏
----
通知内容里**只有**：平台、脱敏后的店铺标识、数据域、错误指纹、脱敏后的错误样例、
轮次键。连接串、口令、token、原始数据行一律不进通知（见 :func:`mask_sensitive_text`）。
店铺标识做**中段遮蔽**（``sh***-1``）—— 名字本身是业务事实，整段抹掉就没法定位问题，
但也不该在告警里明文铺开。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.collection_task_status import STATUS
from modules.core.logger import get_logger

# 脱敏**复用批次 3.3 已落地的同一份实现**（``source_freshness_notify``）——
# 形态级脱敏口径只有一处，别再抄第二份。
# TODO(V2)：该工具函数应上移到中立模块（当前住在 ``data_pipeline`` 域下），
# 记入上线后 V2 重建的清单，不在本批次顺手改。
from backend.services.data_pipeline.source_freshness_notify import mask_sensitive_text

__all__ = [
    "CATEGORY_STEP_FAILURE",
    "CATEGORY_VERIFICATION_WAIT",
    "COLLECTION_FAILURE_ALERT_TYPE_PREFIX",
    "PIPELINE_NAME",
    "CollectionFailure",
    "CollectionFailureAlertOutcome",
    "CollectionFailureCluster",
    "alert_collection_run_failures",
    "alert_collection_task_failure",
    "classify_failure_category",
    "cluster_failures",
    "error_fingerprint",
    "mask_sensitive_text",
    "mask_shop_label",
    "normalize_error_text",
]

logger = get_logger(__name__)

#: 本模块在 ``ops.pipeline_run_log`` 里的 pipeline_name（去重状态挂在这张表上）。
PIPELINE_NAME = "collection_failure_alert"

#: ``alert_service.send_resource_alert`` 的 alert_type 前缀。
#: ⚠️ 必须**每个错误指纹一个 alert_type** —— 那边的冷却键就是 alert_type，
#: 用同一个会把「不同的错误」互相冷却掉。
COLLECTION_FAILURE_ALERT_TYPE_PREFIX = "collection_failure"

#: 失败分类：步骤/数据域失败（真正的失败终态）。
CATEGORY_STEP_FAILURE = "step_failure"
#: 失败分类：等待验证码/人工回填（**不是**失败终态，单独一档）。
CATEGORY_VERIFICATION_WAIT = "verification_wait"

_TASK_STATUS_FAILED = STATUS.FAILED
_TASK_STATUS_PARTIAL_SUCCESS = STATUS.PARTIAL_SUCCESS

#: 「等待验证码回填」的判定标记 —— 命中即归到 ``verification_wait`` 那一档，
#: 绝不与步骤失败混聚。
_VERIFICATION_WAIT_MARKERS = (
    "验证码等待超时",
    "等待验证码",
    "需要验证码",
    "等待人工处理超时",
    "等待人工处理",
    "verification required",
    "verification_required",
)

_LOAD_RUN_TASKS_SQL = """
SELECT task_id, platform, account, status, failed_domains, error_message
FROM core.collection_tasks
WHERE config_run_id = :config_run_id
  AND status IN (:failed_status, :partial_status)
ORDER BY id
"""

_LOAD_TASK_SQL = """
SELECT task_id, platform, account, status, failed_domains, error_message
FROM core.collection_tasks
WHERE task_id = :task_id
"""

_LOAD_NOTIFIED_SQL = """
SELECT context
FROM ops.pipeline_run_log
WHERE pipeline_name = :pipeline_name
ORDER BY id DESC
LIMIT 1
"""

_INSERT_RUN_LOG_SQL = """
INSERT INTO ops.pipeline_run_log (
    run_id, pipeline_name, status, trigger_source,
    started_at, completed_at, error_message, context
) VALUES (
    :run_id, :pipeline_name, :status, :trigger_source,
    :started_at, :completed_at, :error_message, CAST(:context AS jsonb)
)
"""

_URL_PATTERN = re.compile(r"(?i)\bhttps?://\S+")
_UUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_TIMESTAMP_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?"
)
_WINDOWS_PATH_PATTERN = re.compile(r"[A-Za-z]:\\[^\s'\"，,;；]+")
_POSIX_PATH_PATTERN = re.compile(r"/(?:[\w.\-]+/)+[\w.\-]+")
_LONG_HEX_PATTERN = re.compile(r"\b[0-9a-fA-F]{16,}\b")
_NUMBER_PATTERN = re.compile(r"\d+")

#: 错误指纹的最大长度（截断后再进状态集合）。
_FINGERPRINT_MAX_LENGTH = 160
#: 错误样例的最大长度（进通知正文）。
_ERROR_SAMPLE_MAX_LENGTH = 200
#: 通知正文里最多列出多少个店铺标识。
_MAX_SHOP_LABELS_IN_TEXT = 10


@dataclass(frozen=True)
class CollectionFailure:
    """一条失败记录（已归一化；``error`` 仍是脱敏前的原文）。"""

    task_id: str
    platform: str
    account_id: str
    domain: str
    error: str
    fingerprint: str
    category: str


@dataclass
class CollectionFailureCluster:
    """同一轮里**同一个归一化错误指纹**的聚类结果。"""

    fingerprint: str
    label: str
    failures: list[CollectionFailure] = field(default_factory=list)

    @property
    def short_id(self) -> str:
        # 仅作告警标题里的短摘要标识（同一轮聚类的人工可读编号），不用于签名/口令/去重安全边界
        return hashlib.sha1(
            self.fingerprint.encode("utf-8"), usedforsecurity=False
        ).hexdigest()[:8]

    @property
    def platforms(self) -> list[str]:
        return sorted({item.platform for item in self.failures if item.platform})

    @property
    def shop_labels(self) -> list[str]:
        return sorted({mask_shop_label(item.account_id) for item in self.failures})

    @property
    def domains(self) -> list[str]:
        return sorted({item.domain for item in self.failures if item.domain})

    @property
    def error_sample(self) -> str:
        for item in self.failures:
            if item.error:
                return item.error[:_ERROR_SAMPLE_MAX_LENGTH]
        return self.label[:_ERROR_SAMPLE_MAX_LENGTH]


@dataclass
class CollectionFailureAlertOutcome:
    """一次告警派发的结果（供调用方观察，**不参与**采集主流程的成败）。"""

    round_key: str
    notified: list[str] = field(default_factory=list)
    suppressed: list[str] = field(default_factory=list)
    verification_waits: list[str] = field(default_factory=list)
    partial_success_clusters: list[str] = field(default_factory=list)
    skipped: bool = False
    reason: str = ""


# ── 脱敏 ────────────────────────────────────────────────────────────────


def mask_shop_label(account_id: str) -> str:
    """店铺标识**中段遮蔽**（``sh***-1``）。

    整段抹掉就没法定位问题；明文铺开又会把店铺名单泄进外部通道 ⇒ 只遮中段。
    """
    raw = str(account_id or "").strip()
    if not raw:
        return "unknown"
    if len(raw) <= 4:
        return "***"
    return f"{raw[:2]}***{raw[-2:]}"


# ── 归一化与分类 ─────────────────────────────────────────────────────────


def normalize_error_text(error: str) -> str:
    """把错误文本归一化成**可比对**的形态。

    归一化掉的是「每次都不一样」的部分：URL、UUID、时间戳、文件路径、长十六进制 id、
    数字。留下的才是「同一个问题」的稳定特征（例：
    ``TimeoutError: date option was not clicked``）。
    """
    text_value = str(error or "").strip()
    if not text_value:
        return ""
    text_value = _URL_PATTERN.sub("<url>", text_value)
    text_value = _UUID_PATTERN.sub("<uuid>", text_value)
    text_value = _TIMESTAMP_PATTERN.sub("<ts>", text_value)
    text_value = _WINDOWS_PATH_PATTERN.sub("<path>", text_value)
    text_value = _POSIX_PATH_PATTERN.sub("<path>", text_value)
    text_value = _LONG_HEX_PATTERN.sub("<hex>", text_value)
    text_value = _NUMBER_PATTERN.sub("<n>", text_value)
    text_value = re.sub(r"\s+", " ", text_value).strip()
    return text_value[:_FINGERPRINT_MAX_LENGTH]


def error_fingerprint(error: str) -> str:
    """错误指纹：**先脱敏、再归一化**的小写形态。

    - 先脱敏 ⇒ 指纹里不会有口令/连接串凭据（去重状态要落库）；
    - 再归一化 ⇒ 同一个问题不会因「大小写/数字/时间戳/路径」不同而分叉；
    - 小写 ⇒ 大小写差异不产生第二条通知。
    """
    return normalize_error_text(mask_sensitive_text(error)).lower()


def classify_failure_category(error: str) -> str:
    """把失败归到两档之一。

    - ``verification_wait``：等待验证码/人工回填 ⇒ **不是**失败终态；
    - ``step_failure``：步骤/数据域失败。
    """
    raw = str(error or "").strip()
    if not raw:
        return CATEGORY_STEP_FAILURE
    lowered = raw.lower()
    for marker in _VERIFICATION_WAIT_MARKERS:
        if marker in raw or marker in lowered:
            return CATEGORY_VERIFICATION_WAIT
    return CATEGORY_STEP_FAILURE


def _coerce_failed_domains(value: Any) -> list[dict[str, Any]]:
    """把 ``core.collection_tasks.failed_domains``（JSON 列）读成字典列表。

    asyncpg 走 SQLAlchemy 的 json codec ⇒ 通常已经是 ``list``；但原生 SQL 文本查询、
    其它驱动或测试替身可能给回字符串 ⇒ 这里两种都吃。
    """
    payload: Any = value
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8", errors="replace")
    if isinstance(payload, str):
        text_value = payload.strip()
        if not text_value:
            return []
        try:
            payload = json.loads(text_value)
        except (TypeError, ValueError):
            return []
    if not isinstance(payload, (list, tuple)):
        return []
    entries: list[dict[str, Any]] = []
    for item in payload:
        if isinstance(item, dict):
            entries.append(item)
        elif isinstance(item, str):
            entries.append({"domain": "", "error": item})
    return entries


def build_task_failures(row: Sequence[Any]) -> list[CollectionFailure]:
    """把一行任务记录展开成失败条目。

    - ``failed_domains`` 有内容 ⇒ 以它为准（逐数据域）；
    - 没有 ⇒ 退回任务级 ``error_message``（整任务崩了的情形）。

    任务级 ``error_message`` 若与某个数据域错误的指纹相同 ⇒ 不重复计一条。
    """
    task_id = str(row[0] or "")
    platform = str(row[1] or "")
    account_id = str(row[2] or "")
    failed_domains = _coerce_failed_domains(row[4] if len(row) > 4 else None)
    error_message = str(row[5] or "") if len(row) > 5 else ""

    entries: list[tuple[str, str]] = []
    seen_fingerprints: set[str] = set()
    for entry in failed_domains:
        domain = str(entry.get("domain") or "").strip()
        error = str(entry.get("error") or "").strip()
        if not error:
            continue
        fingerprint = error_fingerprint(error)
        if not fingerprint:
            continue
        seen_fingerprints.add(fingerprint)
        entries.append((domain, error))

    if error_message.strip():
        task_fingerprint = error_fingerprint(error_message)
        if task_fingerprint and task_fingerprint not in seen_fingerprints:
            entries.append(("", error_message.strip()))

    failures: list[CollectionFailure] = []
    for domain, error in entries:
        failures.append(
            CollectionFailure(
                task_id=task_id,
                platform=platform,
                account_id=account_id,
                domain=domain,
                error=error,
                fingerprint=error_fingerprint(error),
                category=classify_failure_category(error),
            )
        )
    return failures


def cluster_failures(
    failures: Iterable[CollectionFailure],
) -> list[CollectionFailureCluster]:
    """按归一化错误指纹聚类（同一轮内 7 个店同一错误 ⇒ 1 个簇）。"""
    clusters: dict[str, CollectionFailureCluster] = {}
    for failure in failures:
        if not failure.fingerprint:
            continue
        cluster = clusters.get(failure.fingerprint)
        if cluster is None:
            cluster = CollectionFailureCluster(
                fingerprint=failure.fingerprint,
                label=normalize_error_text(mask_sensitive_text(failure.error)),
            )
            clusters[failure.fingerprint] = cluster
        cluster.failures.append(failure)
    return list(clusters.values())


# ── 运行日志（去重状态） ────────────────────────────────────────────────


def _extract_notified_fingerprints(context: Any) -> set[str]:
    """从运行日志的 context 里取「已通知过且仍在失败」的指纹集合。"""
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
    raw = payload.get("notified_collection_failures")
    if not isinstance(raw, (list, tuple, set)):
        return set()
    return {str(item) for item in raw if str(item or "").strip()}


async def load_notified_fingerprints(db: AsyncSession) -> set[str]:
    """读上一轮告警的「已通知过」指纹集合（读不到就当空集合 ⇒ 该轮全部新问题）。"""
    try:
        result = await db.execute(
            text(_LOAD_NOTIFIED_SQL), {"pipeline_name": PIPELINE_NAME}
        )
        rows = result.fetchall()
    except Exception as exc:  # noqa: BLE001 —— 读不到就当没有历史，不让采集挂掉
        logger.warning(
            "[CollectionFailureAlert] 读上一轮通知状态失败，按「无历史」处理: %s", exc
        )
        return set()

    if not rows:
        return set()
    first = rows[0]
    context = first[0] if isinstance(first, (tuple, list)) else first
    return _extract_notified_fingerprints(context)


async def _insert_alert_run_log(
    db: AsyncSession,
    *,
    run_id: str,
    status: str,
    error_message: str,
    context: dict[str, Any],
    trigger_source: str,
    started_at: datetime,
) -> None:
    await db.execute(
        text(_INSERT_RUN_LOG_SQL),
        {
            "run_id": run_id,
            "pipeline_name": PIPELINE_NAME,
            "status": status,
            "trigger_source": trigger_source,
            "started_at": started_at,
            "completed_at": datetime.now(timezone.utc),
            "error_message": error_message,
            "context": json.dumps(context, ensure_ascii=False, default=str),
        },
    )


# ── 通知派发 ────────────────────────────────────────────────────────────


def _build_alert_text(
    round_key: str, cluster: CollectionFailureCluster
) -> tuple[str, str]:
    """(标题, 正文)。正文只列平台/脱敏店铺/数据域/错误指纹/脱敏错误样例。"""
    platforms = "、".join(cluster.platforms) if cluster.platforms else "未知平台"
    shops = cluster.shop_labels
    shop_text = "、".join(shops[:_MAX_SHOP_LABELS_IN_TEXT])
    if len(shops) > _MAX_SHOP_LABELS_IN_TEXT:
        shop_text = f"{shop_text} 等 {len(shops)} 个"
    domains = "、".join(cluster.domains) if cluster.domains else "（任务级错误）"

    title = f"[采集失败] {len(shops)} 个店铺因同一错误失败（指纹 {cluster.short_id}）"
    lines = [
        "采集失败告警（同一轮内按归一化错误指纹聚类，同一错误只发一条）：",
        "",
        f"平台：{platforms}",
        f"受影响店铺：{len(shops)} 个（{shop_text}）",
        f"涉及数据域：{domains}",
        f"错误指纹：{cluster.short_id}",
        f"错误样例：{mask_sensitive_text(cluster.error_sample)}",
        "",
        f"轮次：{round_key}",
        "连续多轮同一问题不会重复通知；问题恢复后再次失败会重新通知。",
    ]
    return title, mask_sensitive_text("\n".join(lines))


async def _dispatch_in_app(
    db: AsyncSession, title: str, content: str, payload: dict[str, Any]
) -> bool:
    """站内信（管理员）。**只 flush 不 commit** ⇒ 提交由调用方负责。"""
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
        logger.warning("[CollectionFailureAlert] 没有管理员账号，站内信未送达")
        return False
    return True


async def _dispatch_webhook(cluster: CollectionFailureCluster, content: str) -> bool:
    """webhook / 钉钉（每个错误指纹一个 alert_type ⇒ 冷却互不误伤）。"""
    from backend.services import alert_service

    alert_type = f"{COLLECTION_FAILURE_ALERT_TYPE_PREFIX}:{cluster.short_id}"
    delivered = await alert_service.send_resource_alert(alert_type, content)
    return bool(delivered)


async def _dispatch_cluster(
    db: AsyncSession,
    *,
    round_key: str,
    cluster: CollectionFailureCluster,
) -> bool:
    """把一个错误簇推送到两条通道；**至少一条送达**才算通知成功。

    站内信是数据库写入 ⇒ 失败后当前事务已处于失败状态，必须回滚，
    否则后面写 ops 运行日志会跟着炸。
    """
    title, content = _build_alert_text(round_key, cluster)
    payload = {
        "pipeline": PIPELINE_NAME,
        "round_key": round_key,
        "fingerprint": cluster.fingerprint,
        "fingerprint_short": cluster.short_id,
        "platforms": cluster.platforms,
        "shop_count": len(cluster.shop_labels),
        "shop_labels": cluster.shop_labels,
        "domains": cluster.domains,
        "error_sample": mask_sensitive_text(cluster.error_sample),
        "task_count": len({item.task_id for item in cluster.failures}),
    }

    in_app_ok = False
    try:
        in_app_ok = await _dispatch_in_app(db, title, content, payload)
        await db.commit()
    except Exception as exc:  # noqa: BLE001 —— 通知失败不能拖垮采集
        logger.error("[CollectionFailureAlert] 站内信发送失败: %s", exc, exc_info=True)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            logger.error("[CollectionFailureAlert] 回滚失败", exc_info=True)

    webhook_ok = False
    try:
        webhook_ok = await _dispatch_webhook(cluster, content)
    except Exception as exc:  # noqa: BLE001
        logger.error("[CollectionFailureAlert] webhook/钉钉告警发送失败: %s", exc)

    return in_app_ok or webhook_ok


# ── 主流程 ──────────────────────────────────────────────────────────────


async def _alert_from_rows(
    db: AsyncSession,
    *,
    round_key: str,
    rows: Sequence[Sequence[Any]],
    trigger_source: str,
    started_at: datetime,
) -> CollectionFailureAlertOutcome:
    """告警主流程：分类 → 聚类 → 跨轮去重 → 派发 → 落去重状态。

    **任何异常都不许往外抛** —— 通知失败绝不影响采集主流程。
    """
    outcome = CollectionFailureAlertOutcome(round_key=round_key)

    step_failures: list[CollectionFailure] = []
    verification_failures: list[CollectionFailure] = []
    partial_clusters: list[CollectionFailureCluster] = []

    for row in rows:
        status = str(row[3] or "") if len(row) > 3 else ""
        failures = build_task_failures(row)
        if status == _TASK_STATUS_PARTIAL_SUCCESS:
            # 部分成功 = 另一档：**只记录，不通知**。
            partial_clusters.extend(
                cluster_failures(
                    item for item in failures if item.category == CATEGORY_STEP_FAILURE
                )
            )
            continue
        for failure in failures:
            if failure.category == CATEGORY_VERIFICATION_WAIT:
                verification_failures.append(failure)
            else:
                step_failures.append(failure)

    outcome.verification_waits = sorted(
        {item.fingerprint for item in verification_failures}
    )
    outcome.partial_success_clusters = sorted(
        {cluster.fingerprint for cluster in partial_clusters}
    )

    clusters = cluster_failures(step_failures)
    current_fingerprints = {cluster.fingerprint for cluster in clusters}

    previously_notified = await load_notified_fingerprints(db)
    to_notify = [
        cluster
        for cluster in clusters
        if cluster.fingerprint not in previously_notified
    ]
    outcome.suppressed = sorted(current_fingerprints & previously_notified)

    delivered: set[str] = set()
    for cluster in to_notify:
        try:
            ok = await _dispatch_cluster(db, round_key=round_key, cluster=cluster)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "[CollectionFailureAlert] 告警派发异常（不影响采集）: %s",
                exc,
                exc_info=True,
            )
            ok = False
        if ok:
            delivered.add(cluster.fingerprint)
    outcome.notified = sorted(delivered)

    # 跨轮状态：仍在失败且已通知过的指纹**继续留在集合里**（不重复通知）；
    # 本轮不再失败的指纹**移出集合**（恢复后再失败 ⇒ 重新通知）；
    # 两条通道都失败的指纹**不记入** ⇒ 下一轮重试。
    next_state = (previously_notified & current_fingerprints) | delivered

    if (
        not current_fingerprints
        and not previously_notified
        and not partial_clusters
        and not verification_failures
    ):
        # 本轮没有任何失败、也没有历史状态 ⇒ 没什么可记的，不写运行日志。
        outcome.skipped = True
        outcome.reason = "no_failures"
        return outcome

    context: dict[str, Any] = {
        "notified_collection_failures": sorted(next_state),
        "round_key": round_key,
        "notified_this_round": outcome.notified,
        "suppressed_this_round": outcome.suppressed,
        "round_failures": [
            {
                "fingerprint": cluster.fingerprint,
                "fingerprint_short": cluster.short_id,
                "label": cluster.label,
                "platforms": cluster.platforms,
                "shop_count": len(cluster.shop_labels),
                "shop_labels": cluster.shop_labels,
                "domains": cluster.domains,
                "error_sample": mask_sensitive_text(cluster.error_sample),
            }
            for cluster in clusters
        ],
        "verification_waits": [
            {
                "fingerprint": item.fingerprint,
                "task_id": item.task_id,
                "platform": item.platform,
                "shop_label": mask_shop_label(item.account_id),
                "domain": item.domain,
            }
            for item in verification_failures
        ],
        "partial_success_clusters": [
            {
                "fingerprint": cluster.fingerprint,
                "fingerprint_short": cluster.short_id,
                "label": cluster.label,
                "shop_count": len(cluster.shop_labels),
                "domains": cluster.domains,
            }
            for cluster in partial_clusters
        ],
    }

    status = "failed" if current_fingerprints else "success"
    error_message = (
        f"采集失败聚类 {len(clusters)} 个错误指纹,涉及 {len({f.task_id for f in step_failures})} 个任务"
        if current_fingerprints
        else None
    )

    try:
        await _insert_alert_run_log(
            db,
            # run_id 随机 ⇒ 同一轮被重复收尾时不会撞唯一约束；
            # 轮次归属靠 context.round_key 追溯。
            run_id=f"{PIPELINE_NAME}:{uuid4().hex[:12]}",
            status=status,
            error_message=error_message,
            context=context,
            trigger_source=trigger_source,
            started_at=started_at,
        )
        await db.commit()
    except Exception as exc:  # noqa: BLE001 —— 状态写不进去也不能影响采集
        logger.error(
            "[CollectionFailureAlert] 写告警去重状态失败: %s", exc, exc_info=True
        )
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            logger.error("[CollectionFailureAlert] 回滚失败", exc_info=True)

    return outcome


async def alert_collection_run_failures(
    db: AsyncSession,
    *,
    config_run_id: int,
    trigger_source: str = "collection",
) -> CollectionFailureAlertOutcome:
    """采集轮次结束时的失败告警（**同轮聚类**的入口）。

    只处理 ``failed`` 的任务；``partial_success`` 单独记一档但不通知；
    「等待验证码回填」单独归类、不与步骤失败混在一起。
    """
    started_at = datetime.now(timezone.utc)
    round_key = f"config_run:{config_run_id}"
    try:
        result = await db.execute(
            text(_LOAD_RUN_TASKS_SQL),
            {
                "config_run_id": config_run_id,
                "failed_status": _TASK_STATUS_FAILED,
                "partial_status": _TASK_STATUS_PARTIAL_SUCCESS,
            },
        )
        rows = result.fetchall()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[CollectionFailureAlert] 读取采集轮次任务失败，跳过告警: %s", exc
        )
        return CollectionFailureAlertOutcome(
            round_key=round_key, skipped=True, reason="load_failed"
        )

    return await _alert_from_rows(
        db,
        round_key=round_key,
        rows=rows,
        trigger_source=trigger_source,
        started_at=started_at,
    )


async def alert_collection_task_failure(
    db: AsyncSession,
    *,
    task_id: str,
    trigger_source: str = "collection",
) -> CollectionFailureAlertOutcome:
    """单个任务的失败告警（**不属于配置轮次**的快速采集走这条）。

    属于配置轮次的任务不在这里告警 —— 那类任务由轮次结束时统一聚合，
    否则同一轮 7 个店会被拆成 7 条通知。
    """
    started_at = datetime.now(timezone.utc)
    round_key = f"task:{task_id}"
    try:
        result = await db.execute(text(_LOAD_TASK_SQL), {"task_id": task_id})
        rows = result.fetchall()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[CollectionFailureAlert] 读取采集任务失败，跳过告警: %s", exc)
        return CollectionFailureAlertOutcome(
            round_key=round_key, skipped=True, reason="load_failed"
        )

    if not rows:
        return CollectionFailureAlertOutcome(
            round_key=round_key, skipped=True, reason="task_not_found"
        )

    return await _alert_from_rows(
        db,
        round_key=round_key,
        rows=rows,
        trigger_source=trigger_source,
        started_at=started_at,
    )
