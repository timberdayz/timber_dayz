"""同步侧「矛盾行台账」—— 被跳过 / 被降级的行的**行级登记载体**（批次 4.3）。

背景
----
批次 3.7 加了「双基准守卫」: 推送前把**本地**登记信息与**云端**登记信息比一次,
不一致的行**不写云端**、降级成可观测事件(落在 ``ops.pipeline_run_log``)。

但**行级**的明细只活在 ``ops.pipeline_run_log`` 的 ``context->'events'`` 里 ——
那是一段 jsonb **样本**(最多 50 条)、且**整批去重**: 同一批被降级两次, 记两条
几乎一样的事件, 看不出「这一行到底被跳过几次、第一次被跳过是什么时候」。

方案要求
--------
方案(``2026-11-10-shop-identity-future-proofing-and-observability.md`` §批次 4.3)
写得很明确:

* ⚠️ **不要**把检查点推进算法改成「停在第一个矛盾行」—— 那会让
  ``fact_shopee_products_daily`` 永久卡在那 8 行之前(历史不修 ⇒ 那些行的归属
  永远不会被修)⇒ 等于把「漏传」换成「堵死」。
* 正确做法: **保持现有推进算法**(不制造永久卡死), 额外把**被跳过的矛盾行**记进
  台账并标注「已知历史遗留」, 另提供**手工重发入口**。

⇒ 本模块就是那本台账的实现。

台账口径
--------
一行 = 一个矛盾行, 记清:

=========================  ====================================================
字段                       回答的问题
=========================  ====================================================
``source_table_name``      哪张表
``platform_code``          哪个平台
``data_domain``            哪个域
``business_date``          哪个业务日期
``identity_value``         行内那列的值是什么
``resolved_account_id``    本地认出的账号是谁
``resolved_accounts``      本地解析出的账号集合(多账号矛盾时)
``cloud_accounts``         云端解析出的账号集合(双基准降级时)
``reason_code``            为什么判为矛盾(原因码)
``status``                 「已知历史遗留」还是「待人工处理」
``first_seen_at``          第一次见到的时间
``last_seen_at``           最近一次见到的时间
``occurrence_count``       累计出现次数
``resolution_status``      人工处理状态(``open`` / ``in_progress`` / ...)
``resolved_by`` /          处理人 / 处理时间
``resolved_at``
=========================  ====================================================

去重口径(**唯一一处**)
----------------------
同一「(源表, 业务日期, 行内定位, 原因码)」再遇到时**更新**累计次数与最近见到
时间, **不**无限插新行。

⇒ 这四项拼成一个稳定串 :func:`build_dedup_key`, 唯一约束
``uq_shop_identity_conflict_rows_dedup_key`` 建在它上面 ⇒ 幂等由**数据库**兜底,
不靠应用层先查后写。

⚠️ **这一套去重口径同时也是批次 3.7「事件重复写」的修复口径** —— ``ops.pipeline_run_log``
里那条「双基准不一致」事件, 现在**只在本批出现了台账里没有的新行时才记**
(见 :func:`backend.services.cloud_b_class_sync_service.SQLAlchemyCloudWriter.
_report_guard_events`)。**不要**再写第二套去重口径。

「已知历史遗留」的判定
--------------------
与批次 3.2(报表可解析性分档巡检)**同口径**: 以「店铺身份登记信息**对齐生效日**」
(环境变量 ``SHOP_IDENTITY_ALIGNMENT_EFFECTIVE_DATE``)为界。

* 业务日期 **早于**对齐生效日 ⇒ ``known_legacy``(已知历史遗留)——
  那些行的归属**永远不会被修**(历史不修)⇒ 不重发、不报警;
* 业务日期 **不早于**对齐生效日 ⇒ ``pending_manual``(待人工处理)——
  该修台账、修完可以手工重发;
* 对齐生效日**未配置** ⇒ 一律 ``known_legacy``(与批次 3.2 同口径: 宁可不报也不误报)。

⚠️ **对齐生效日必须配**, 否则所有矛盾行都归「历史遗留」, 手工重发入口会挑不出
候选行。判定依据见 :func:`classify_conflict_status`。

只记不阻塞
----------
台账写入**不参与**同步的写入事务(独立 ``begin()`` 块), 且**任何失败都被吞掉**
(表不存在 / 连不上 / 约束冲突 …)⇒ **同步照跑, 结果不变**。

通知出口(默认关)
----------------
批次 3.7 遗留的「告警通道未接」在这里补上, 但**默认关闭**:

* 环境变量 ``SHOP_IDENTITY_CONFLICT_NOTIFY_ENABLED`` 只有**显式**为真时才开;
* 复用批次 3.4 已有的通道 —— ``backend/services/alert_service.py`` 的
  ``send_resource_alert``(webhook / 钉钉)与
  ``backend/domains/platform/routers/notifications.py`` 的
  ``create_notifications_for_admins``(站内信);
* **不另造一套通知实现**, 也**不在同步链路里引入新的外部网络调用**
  (默认关 ⇒ 上线后行为与现在完全一致)。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

from sqlalchemy import text

from modules.core.logger import get_logger
from modules.core.shop_identity_ssot import IDENTITY_SIGNAL_PRIORITY


logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

#: 台账表(``ops`` 域)。
CONFLICT_TABLE = "shop_identity_conflict_rows"
CONFLICT_SCHEMA = "ops"

# ---------------------------------------------------------------------------
# 原因码(机器可读)—— **唯一定义处**
# ---------------------------------------------------------------------------
#
#: 本地台账把行内身份解析出 **>1 个**账号 ⇒ 真矛盾(行内两个身份键指向不同的店)。
REASON_LOCAL_REGISTRY_AMBIGUOUS = "local_registry_ambiguous"
#: 拿不到本地台账时的降级判据: 行内**同形态**的身份键互相不一致。
REASON_LOCAL_TOKEN_MISMATCH = "local_identity_token_mismatch"
#: 本地认出的账号, **云端认不出**。
REASON_CLOUD_UNRESOLVED = "cloud_registry_unresolved"
#: **云端自己**都认不唯一。
REASON_CLOUD_AMBIGUOUS = "cloud_registry_ambiguous"
#: 云端把它**指向了另一个账号**。
REASON_CLOUD_DIFFERENT_ACCOUNT = "cloud_registry_different_account"

#: 全部原因码(供守护测试断言「没有第二套口径」)。
ALL_REASON_CODES = (
    REASON_LOCAL_REGISTRY_AMBIGUOUS,
    REASON_LOCAL_TOKEN_MISMATCH,
    REASON_CLOUD_UNRESOLVED,
    REASON_CLOUD_AMBIGUOUS,
    REASON_CLOUD_DIFFERENT_ACCOUNT,
)

#: 「已知历史遗留」—— 归属永远不会被修(历史不修), **不重发、不报警**。
STATUS_KNOWN_LEGACY = "known_legacy"
#: 「待人工处理」—— 台账修好后可以手工重发。
STATUS_PENDING_MANUAL = "pending_manual"

#: 全部台账状态。
ALL_STATUSES = (STATUS_KNOWN_LEGACY, STATUS_PENDING_MANUAL)

# ---------------------------------------------------------------------------
# 人工处理状态
# ---------------------------------------------------------------------------

RESOLUTION_OPEN = "open"
RESOLUTION_IN_PROGRESS = "in_progress"
RESOLUTION_RESOLVED = "resolved"
RESOLUTION_IGNORED = "ignored"

ALL_RESOLUTION_STATUSES = (
    RESOLUTION_OPEN,
    RESOLUTION_IN_PROGRESS,
    RESOLUTION_RESOLVED,
    RESOLUTION_IGNORED,
)

# ---------------------------------------------------------------------------
# 环境变量
# ---------------------------------------------------------------------------

#: 通知出口开关 —— **默认关**。
#:
#: ⚠️ 只有**显式**为真(``1`` / ``true`` / ``on`` / ``yes``)时才开。
#: 默认关 ⇒ 上线后行为与本批次之前**完全一致**。
CONFLICT_NOTIFY_ENABLED_ENV = "SHOP_IDENTITY_CONFLICT_NOTIFY_ENABLED"

_DISABLED_VALUES = frozenset({"0", "false", "off", "no"})
_ENABLED_VALUES = frozenset({"1", "true", "on", "yes"})

#: ``alert_service.send_resource_alert`` 的 alert_type 前缀。
#:
#: ⚠️ 必须**按表**分一个 alert_type —— 那边的冷却键就是 alert_type,
#: 用同一个会把「不同的表」互相冷却掉。
CONFLICT_ALERT_TYPE_PREFIX = "shop_identity_conflict"

#: 单批最多记多少条矛盾行进台账。
#:
#: ⚠️ 计数是**全量**的(``occurrence_count``), 这里限的是**本批写入的明细条数**,
#: 防止一批几千行冲突把同步拖慢。超出的部分会被记一条 warning。
MAX_LEDGER_RECORDS_PER_BATCH = 1000

#: 行内业务日期的候选列(按优先级)—— 与批次 3.7 的事件负载保持同一份口径。
_BUSINESS_DATE_KEYS = (
    "business_date",
    "metric_date",
    "period_end_date",
    "analytics_date",
)

#: ``row_identity_tokens`` 的键名 → SSOT 信号名 的映射。
#:
#: ⚠️ ``row_identity_tokens`` 把「店铺标签」那一路叫 ``store_label``,
#: 而 SSOT 的信号名叫 ``store_name`` ⇒ 这里做一次**显式**对齐,
#: 免得两处各叫各的。
_TOKEN_KEY_BY_SIGNAL = {
    "shop_account_id": "shop_account_id",
    "platform_shop_id": "platform_shop_id",
    "shop_id": "shop_id",
    "store_name": "store_label",
}


# ---------------------------------------------------------------------------
# 纯函数: 口径
# ---------------------------------------------------------------------------


def extract_business_date(row: Mapping[str, Any]) -> str:
    """取行内**业务日期**(``YYYY-MM-DD``); 取不到返回空串。

    ⚠️ **唯一定义处** —— 批次 3.7 的降级事件负载也用它, 别再抄第二份。
    """
    for key in _BUSINESS_DATE_KEYS:
        value = row.get(key)
        if value:
            text_value = str(value).strip()
            if text_value:
                return text_value
    return ""


def pick_identity_value(identity_tokens: Mapping[str, Any]) -> str:
    """行内那列的值 —— 取身份键里**优先级最高**的那一个。

    ⚠️ 优先级直接引用仓库唯一台账声明
    (:data:`modules.core.shop_identity_ssot.IDENTITY_SIGNAL_PRIORITY`,
    账号章优先)⇒ **不**在这里另写一份「什么算认得出」。
    """
    for signal in IDENTITY_SIGNAL_PRIORITY:
        token_key = _TOKEN_KEY_BY_SIGNAL.get(signal)
        if not token_key:
            continue
        value = str(identity_tokens.get(token_key) or "").strip()
        if value:
            return value
    return ""


def build_row_locator(*, source_row_id: Any = None, data_hash: Any = None) -> str:
    """构造**行内定位** —— 人工定位这一行用的稳定标识。

    用「源行主键 + 冲突键摘要」: 两者都是**这一行**的属性, 跨轮次稳定
    ⇒ 同一行再次被跳过时会算出同一个 locator ⇒ 去重键稳定。
    """
    parts = [str(source_row_id or "").strip(), str(data_hash or "").strip()]
    joined = "|".join(part for part in parts if part)
    return joined or "unknown"


def build_dedup_key(
    *,
    source_table_name: str,
    business_date: str,
    row_locator: str,
    reason_code: str,
) -> str:
    """去重键 = 「(源表, 业务日期, 行内定位, 原因码)」的稳定拼接串。

    ⚠️ **唯一一处去重口径** —— 批次 3.7 的「事件重复写」修复也用它。
    ⚠️ 用 ``|`` 分隔且各段本身不允许出现 ``|``(源行主键与摘要都不含)。
    """
    return "|".join(
        (
            str(source_table_name or "").strip(),
            str(business_date or "").strip(),
            str(row_locator or "").strip(),
            str(reason_code or "").strip(),
        )
    )


def resolve_alignment_effective_date() -> date | None:
    """读「店铺身份登记信息**对齐生效日**」(环境变量)。

    ⚠️ **复用批次 3.2 的那一份实现**
    (:func:`backend.services.data_pipeline.cloud_sync_integrity_service.
    resolve_alignment_effective_date`)⇒ 两处的「历史遗留分档」不会分叉。

    延迟导入: 那个模块在 ``data_pipeline`` 域下, 而本模块在同步域 ⇒
    延迟导入避免把两域在 import 期就绑死。
    """
    try:
        from backend.services.data_pipeline.cloud_sync_integrity_service import (
            resolve_alignment_effective_date as _resolve,
        )
    except Exception:  # pragma: no cover - 极端导入失败 ⇒ 按「未配置」处理
        logger.warning(
            "[ConflictLedger] 读不到对齐生效日的实现, 按「未配置」处理",
            exc_info=True,
        )
        return None
    return _resolve()


def classify_conflict_status(
    *,
    business_date: str,
    alignment_effective_date: date | None,
) -> str:
    """判定这一行是「已知历史遗留」还是「待人工处理」。

    判定依据(与批次 3.2 同口径)
    --------------------------
    * **未配置**对齐生效日 ⇒ 一律 ``known_legacy``
      (宁可不报也不误报 —— 没有基准就分不出「历史」与「新增」);
    * 业务日期**早于**对齐生效日 ⇒ ``known_legacy``
      (那些行的归属永远不会被修 ⇒ 历史不修);
    * 其余 ⇒ ``pending_manual``。

    ⚠️ 业务日期**为空**时, 在已配置对齐生效日的前提下归 ``pending_manual`` ——
    无法证明它早于生效日 ⇒ 交给人工判断(而不是替它断言「历史遗留」)。
    """
    if alignment_effective_date is None:
        return STATUS_KNOWN_LEGACY
    if not str(business_date or "").strip():
        return STATUS_PENDING_MANUAL
    try:
        row_date = date.fromisoformat(str(business_date).strip()[:10])
    except ValueError:
        return STATUS_PENDING_MANUAL
    if row_date < alignment_effective_date:
        return STATUS_KNOWN_LEGACY
    return STATUS_PENDING_MANUAL


def conflict_notify_enabled() -> bool:
    """通知出口是否**启用**(环境变量开关, **默认关**)。"""
    raw = os.getenv(CONFLICT_NOTIFY_ENABLED_ENV)
    if raw is None:
        return False
    value = raw.strip().lower()
    if value in _DISABLED_VALUES:
        return False
    return value in _ENABLED_VALUES


# ---------------------------------------------------------------------------
# 矛盾行记录
# ---------------------------------------------------------------------------


@dataclass
class ConflictRowRecord:
    """一条矛盾行的**台账负载**(还没落库)。"""

    #: 原因码(见 ``ALL_REASON_CODES``)。
    reason_code: str
    #: 行内定位(见 :func:`build_row_locator`)。
    row_locator: str
    source_row_id: str = ""
    platform_code: str = ""
    business_date: str = ""
    identity_value: str = ""
    identity_tokens: dict[str, str] = field(default_factory=dict)
    resolved_account_id: str = ""
    resolved_accounts: list[str] = field(default_factory=list)
    cloud_accounts: list[str] = field(default_factory=list)
    #: 人工处理状态(``open`` 等)。
    resolution_status: str = RESOLUTION_OPEN

    def to_params(
        self, *, source_table_name: str, data_domain: str, now
    ) -> dict[str, Any]:
        """转成 upsert 的绑定参数。"""
        business_date = str(self.business_date or "").strip()
        status = classify_conflict_status(
            business_date=business_date,
            alignment_effective_date=resolve_alignment_effective_date(),
        )
        dedup_key = build_dedup_key(
            source_table_name=source_table_name,
            business_date=business_date,
            row_locator=self.row_locator,
            reason_code=self.reason_code,
        )
        return {
            "dedup_key": dedup_key,
            "source_table_name": source_table_name,
            "platform_code": self.platform_code or None,
            "data_domain": data_domain or None,
            "business_date": business_date or None,
            "row_locator": self.row_locator,
            "source_row_id": self.source_row_id or None,
            "identity_value": self.identity_value or None,
            "identity_tokens": json.dumps(
                self.identity_tokens, ensure_ascii=False, default=str
            ),
            "resolved_account_id": self.resolved_account_id or None,
            "resolved_accounts": json.dumps(
                list(self.resolved_accounts), ensure_ascii=False, default=str
            ),
            "cloud_accounts": json.dumps(
                list(self.cloud_accounts), ensure_ascii=False, default=str
            ),
            "reason_code": self.reason_code,
            "status": status,
            "resolution_status": self.resolution_status or RESOLUTION_OPEN,
            "now": now,
        }


def conflict_record_from_mismatch_event(
    payload: Mapping[str, Any],
) -> ConflictRowRecord:
    """把批次 3.7 的**降级事件负载**转成台账行负载。

    降级事件(``RegistryMismatchEvent.to_payload()``)与台账行的字段名不完全一样
    (``reason`` vs ``reason_code``、没有 ``row_locator`` …)⇒ 这里做一次**显式**
    转换, 别在两处各猜一遍。
    """
    local_accounts = [str(item) for item in (payload.get("local_accounts") or [])]
    cloud_accounts = [str(item) for item in (payload.get("cloud_accounts") or [])]
    identity_tokens = {
        str(key): str(value)
        for key, value in (payload.get("identity_tokens") or {}).items()
    }
    return ConflictRowRecord(
        reason_code=str(payload.get("reason") or ""),
        row_locator=build_row_locator(
            source_row_id=payload.get("source_row_id"),
            data_hash=payload.get("data_hash"),
        ),
        source_row_id=str(payload.get("source_row_id") or ""),
        platform_code=str(payload.get("platform_code") or ""),
        business_date=str(payload.get("business_date") or ""),
        identity_value=pick_identity_value(identity_tokens),
        identity_tokens=identity_tokens,
        resolved_account_id=local_accounts[0] if len(local_accounts) == 1 else "",
        resolved_accounts=local_accounts,
        cloud_accounts=cloud_accounts,
    )


# ---------------------------------------------------------------------------
# 台账写入
# ---------------------------------------------------------------------------

_SELECT_EXISTING_KEYS_SQL = """
SELECT dedup_key
FROM ops.shop_identity_conflict_rows
WHERE dedup_key IN :keys
"""

#: ⚠️ SQL 里**不出现裸 ``%s``**(psycopg2 会把它当占位符)—— 绑定一律走 ``:name``。
_UPSERT_SQL = """
INSERT INTO ops.shop_identity_conflict_rows (
    dedup_key, source_table_name, platform_code, data_domain, business_date,
    row_locator, source_row_id, identity_value, identity_tokens,
    resolved_account_id, resolved_accounts, cloud_accounts,
    reason_code, status, occurrence_count, first_seen_at, last_seen_at,
    resolution_status, created_at, updated_at
) VALUES (
    :dedup_key, :source_table_name, :platform_code, :data_domain,
    CAST(:business_date AS date),
    :row_locator, :source_row_id, :identity_value,
    CAST(:identity_tokens AS jsonb),
    :resolved_account_id,
    CAST(:resolved_accounts AS jsonb),
    CAST(:cloud_accounts AS jsonb),
    :reason_code, :status, 1, :now, :now,
    :resolution_status, :now, :now
)
ON CONFLICT (dedup_key) DO UPDATE SET
    occurrence_count = ops.shop_identity_conflict_rows.occurrence_count + 1,
    last_seen_at = EXCLUDED.last_seen_at,
    updated_at = EXCLUDED.updated_at,
    source_table_name = EXCLUDED.source_table_name,
    platform_code = EXCLUDED.platform_code,
    data_domain = EXCLUDED.data_domain,
    business_date = EXCLUDED.business_date,
    row_locator = EXCLUDED.row_locator,
    source_row_id = EXCLUDED.source_row_id,
    identity_value = EXCLUDED.identity_value,
    identity_tokens = EXCLUDED.identity_tokens,
    resolved_account_id = EXCLUDED.resolved_account_id,
    resolved_accounts = EXCLUDED.resolved_accounts,
    cloud_accounts = EXCLUDED.cloud_accounts,
    reason_code = EXCLUDED.reason_code,
    status = EXCLUDED.status
"""


class ShopIdentityConflictLedgerRecorder:
    """把矛盾行写进 ``ops.shop_identity_conflict_rows``。

    ⚠️ **只记不阻塞**
    ---------------
    * 写入走**独立**的 ``begin()`` 块 ⇒ **不参与**同步的写入事务;
    * 任何异常(表不存在 / 连不上 / 约束冲突 / 字段不对)都被吞掉, 只记 warning
      ⇒ **同步照跑, 写入结果不变**。

    ⚠️ **幂等**
    ---------
    同一「(源表, 业务日期, 行内定位, 原因码)」再遇到时**更新**累计次数与最近见到
    时间, **不**插新行 ⇒ 由唯一约束兜底, 应用层不先查后写。
    """

    def __init__(self, engine):
        self.engine = engine

    def record_conflicts(
        self,
        *,
        source_table_name: str,
        data_domain: str,
        records: Sequence[ConflictRowRecord] | Iterable[Mapping[str, Any]],
    ) -> dict[str, Any]:
        """记一批矛盾行。

        Returns:
            摘要字典: ``status`` (``recorded`` / ``skipped`` / ``failed``)、
            ``new_rows``(本批**第一次**出现的行数)、``seen_rows``(已见过、
            只是又出现一次的行数)、``total_rows``、``dedup_keys``。
            ⚠️ ``new_rows`` 是「**去重事件**」的判据 —— 批次 3.7 的
            ``ops.pipeline_run_log`` 事件只在本批有**新行**时才记。
        """
        items = [self._coerce(item) for item in records or []]
        if not items:
            return {
                "status": "skipped",
                "reason": "no_conflict_rows",
                "new_rows": 0,
                "seen_rows": 0,
                "total_rows": 0,
                "dedup_keys": [],
            }
        if self.engine is None:
            return {
                "status": "skipped",
                "reason": "no_local_engine",
                "new_rows": 0,
                "seen_rows": 0,
                "total_rows": len(items),
                "dedup_keys": [],
            }

        if len(items) > MAX_LEDGER_RECORDS_PER_BATCH:
            logger.warning(
                "[ConflictLedger] [%s] 本批 %d 条矛盾行超过上限 %d, 只记前 %d 条",
                source_table_name,
                len(items),
                MAX_LEDGER_RECORDS_PER_BATCH,
                MAX_LEDGER_RECORDS_PER_BATCH,
            )
            items = items[:MAX_LEDGER_RECORDS_PER_BATCH]

        now = datetime.now(timezone.utc)
        try:
            params = [
                item.to_params(
                    source_table_name=source_table_name,
                    data_domain=data_domain,
                    now=now,
                )
                for item in items
            ]
            existing = self._existing_keys([p["dedup_key"] for p in params])
            with self.engine.begin() as conn:
                conn.execute(text(_UPSERT_SQL), params)
        except Exception as exc:  # noqa: BLE001 —— 台账写失败绝不阻塞同步
            logger.warning("[ConflictLedger] 矛盾行台账写入失败(不影响同步): %s", exc)
            return {
                "status": "failed",
                "error": str(exc),
                "new_rows": 0,
                "seen_rows": 0,
                "total_rows": len(items),
                "dedup_keys": [],
            }

        dedup_keys = [p["dedup_key"] for p in params]
        new_rows = len([key for key in dedup_keys if key not in existing])
        seen_rows = len(dedup_keys) - new_rows
        logger.info(
            "[ConflictLedger] [%s] 记入矛盾行 %d 条(新 %d / 已见过 %d)",
            source_table_name,
            len(dedup_keys),
            new_rows,
            seen_rows,
        )
        return {
            "status": "recorded",
            "new_rows": new_rows,
            "seen_rows": seen_rows,
            "total_rows": len(dedup_keys),
            "dedup_keys": dedup_keys,
            "source_table_name": source_table_name,
            "data_domain": data_domain,
        }

    @staticmethod
    def _coerce(item: Any) -> ConflictRowRecord:
        """把 dict / dataclass 统一成 :class:`ConflictRowRecord`。"""
        if isinstance(item, ConflictRowRecord):
            return item
        payload = dict(item or {})
        return ConflictRowRecord(
            reason_code=str(payload.get("reason_code") or ""),
            row_locator=str(payload.get("row_locator") or ""),
            source_row_id=str(payload.get("source_row_id") or ""),
            platform_code=str(payload.get("platform_code") or ""),
            business_date=str(payload.get("business_date") or ""),
            identity_value=str(payload.get("identity_value") or ""),
            identity_tokens=dict(payload.get("identity_tokens") or {}),
            resolved_account_id=str(payload.get("resolved_account_id") or ""),
            resolved_accounts=list(payload.get("resolved_accounts") or []),
            cloud_accounts=list(payload.get("cloud_accounts") or []),
            resolution_status=str(payload.get("resolution_status") or RESOLUTION_OPEN),
        )

    def _existing_keys(self, dedup_keys: Sequence[str]) -> set[str]:
        """查哪些去重键**已经**在台账里(用来算「这一批有没有新行」)。"""
        if not dedup_keys:
            return set()
        from sqlalchemy import bindparam

        statement = text(_SELECT_EXISTING_KEYS_SQL).bindparams(
            bindparam("keys", expanding=True)
        )
        with self.engine.connect() as conn:
            result = conn.execute(statement, {"keys": list(dedup_keys)})
            rows = result.fetchall()
        return {str(row[0]) for row in rows}


# ---------------------------------------------------------------------------
# 通知出口(默认关; 复用批次 3.4 的通道)
# ---------------------------------------------------------------------------


def build_conflict_alert_text(summary: Mapping[str, Any]) -> tuple[str, str]:
    """(标题, 正文)。只放**定位信息**, 不放行体、不放连接串。"""
    source_table = str(summary.get("source_table_name") or "(未知表)")
    new_rows = int(summary.get("new_rows") or 0)
    total_rows = int(summary.get("total_rows") or 0)
    reasons = summary.get("reason_codes") or []
    reason_text = "、".join(str(item) for item in reasons) if reasons else "(未分类)"

    title = "[同步矛盾行] %s 新增 %d 行未落云端" % (source_table, new_rows)
    lines = [
        "同步侧矛盾行台账新增了未被写入云端的行（同步本身照常完成，未阻塞）。",
        "",
        "源表：%s" % source_table,
        "本批矛盾行：%d 行（其中第一次出现 %d 行）" % (total_rows, new_rows),
        "原因码：%s" % reason_text,
        "",
        "处理方式：台账里标「待人工处理」的行，修好登记信息后可用",
        "scripts/replay_shop_identity_conflict_rows.py --dry-run 预览，",
        "确认无误再加 --execute 重发。",
        "标「已知历史遗留」的行按既定决策不修。",
    ]
    return title, "\n".join(lines)


async def notify_new_conflict_rows(summary: Mapping[str, Any]) -> dict[str, Any]:
    """把「本批新增了矛盾行」通知出去(**复用批次 3.4 的两条通道**)。

    ⚠️ **默认关** —— 由 :envvar:`CONFLICT_NOTIFY_ENABLED_ENV` 控制。
    ⚠️ **任何异常都不许往外抛** —— 通知失败绝不影响同步主流程。
    """
    if not conflict_notify_enabled():
        return {"status": "skipped", "reason": "notify_disabled"}
    if int(summary.get("new_rows") or 0) <= 0:
        return {"status": "skipped", "reason": "no_new_rows"}

    title, content = build_conflict_alert_text(summary)
    source_table = str(summary.get("source_table_name") or "unknown")

    in_app_ok = False
    try:
        from backend.domains.platform.routers.notifications import (
            create_notifications_for_admins,
        )
        from backend.models.database import AsyncSessionLocal
        from backend.schemas.notification import NotificationType

        async with AsyncSessionLocal() as db:
            notifications = await create_notifications_for_admins(
                db=db,
                notification_type=NotificationType.SYSTEM_ALERT,
                title=title,
                content=content,
                extra_data={
                    "pipeline": "shop_identity_conflict_ledger",
                    "source_table_name": source_table,
                    "new_rows": int(summary.get("new_rows") or 0),
                    "total_rows": int(summary.get("total_rows") or 0),
                    "reason_codes": list(summary.get("reason_codes") or []),
                },
                priority="high",
            )
            await db.commit()
            in_app_ok = bool(notifications)
    except Exception as exc:  # noqa: BLE001 —— 通知失败不能拖垮同步
        logger.warning("[ConflictLedger] 站内信发送失败(不影响同步): %s", exc)

    webhook_ok = False
    try:
        from backend.services import alert_service

        webhook_ok = bool(
            await alert_service.send_resource_alert(
                "%s:%s" % (CONFLICT_ALERT_TYPE_PREFIX, source_table),
                content,
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[ConflictLedger] webhook/钉钉告警发送失败(不影响同步): %s", exc)

    return {
        "status": "notified" if (in_app_ok or webhook_ok) else "failed",
        "in_app": in_app_ok,
        "webhook": webhook_ok,
    }


# ---------------------------------------------------------------------------
# 读取(手工重发入口用)
# ---------------------------------------------------------------------------

_SELECT_CONFLICT_ROWS_SQL = """
SELECT id,
       dedup_key,
       source_table_name,
       platform_code,
       data_domain,
       business_date,
       row_locator,
       source_row_id,
       identity_value,
       identity_tokens,
       resolved_account_id,
       resolved_accounts,
       cloud_accounts,
       reason_code,
       status,
       occurrence_count,
       first_seen_at,
       last_seen_at,
       resolution_status,
       resolved_by,
       resolved_at,
       resolution_note
FROM ops.shop_identity_conflict_rows
WHERE 1 = 1
"""


def _decode_json(value: Any) -> Any:
    """jsonb 列在原生 SQL 里可能已经是 list/dict, 也可能是字符串 ⇒ 两种都吃。"""
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return value
    return value


def select_conflict_rows(
    engine,
    *,
    source_table_name: str | None = None,
    statuses: Sequence[str] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    reason_codes: Sequence[str] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """按条件读台账行(手工重发入口用)。

    ⚠️ **只读** —— 这个函数不改任何东西。
    """
    clauses: list[str] = []
    params: dict[str, Any] = {}

    if source_table_name:
        clauses.append("source_table_name = :source_table_name")
        params["source_table_name"] = source_table_name
    if statuses:
        clauses.append("status IN :statuses")
        params["statuses"] = list(statuses)
    if reason_codes:
        clauses.append("reason_code IN :reason_codes")
        params["reason_codes"] = list(reason_codes)
    if date_from:
        clauses.append("business_date >= CAST(:date_from AS date)")
        params["date_from"] = date_from
    if date_to:
        clauses.append("business_date <= CAST(:date_to AS date)")
        params["date_to"] = date_to

    statement = _SELECT_CONFLICT_ROWS_SQL
    if clauses:
        statement += " AND " + " AND ".join(clauses)
    statement += " ORDER BY last_seen_at DESC, id DESC"
    if limit and int(limit) > 0:
        statement += " LIMIT :row_limit"
        params["row_limit"] = int(limit)

    from sqlalchemy import bindparam

    compiled = text(statement)
    for name in ("statuses", "reason_codes"):
        if name in params:
            compiled = compiled.bindparams(bindparam(name, expanding=True))

    with engine.connect() as conn:
        result = conn.execute(compiled, params)
        rows = result.fetchall()

    output: list[dict[str, Any]] = []
    for row in rows:
        mapping = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
        mapping["identity_tokens"] = _decode_json(mapping.get("identity_tokens"))
        mapping["resolved_accounts"] = _decode_json(mapping.get("resolved_accounts"))
        mapping["cloud_accounts"] = _decode_json(mapping.get("cloud_accounts"))
        output.append(mapping)
    return output
