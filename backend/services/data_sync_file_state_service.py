"""文件处置状态模型 (SSOT)

为什么
----
「这个文件现在归谁处理、下一步做什么」这个问题, 在系统里被**多处各判一遍**:

* ``backend/tasks/scheduled_tasks.py::_blocked_auto_ingest_status_for_readiness``
  —— 一串 if/elif 猜是"缺模板"还是"缺变体"还是"语义契约"
* ``backend/tasks/scheduled_tasks.py`` 的 ``needs_manual_template_update`` 降级
* ``backend/domains/data_platform/routers/data_sync.py`` 文件行里的
  ``template_update_required`` 展示
* ``backend/services/data_sync_service.py::_is_blocking_header_change``
* 前端 ``DataSyncFiles.vue`` 的 ``fileViewOptions`` 又自己一套分类

⇒ 同一份状态, 不同地方给出不同结论; 而且**状态之间允许怎么迁移没有任何约束**,
  ``ingested → pending``(重置重导)与 ``pending → ingested``(跳步入库)
  混在一起, 出问题时很难判断是正常流程还是异常。

本模块给出唯一的判定:

* :func:`resolve_file_disposition` —— 输入现状, 输出唯一结论
  (文件状态 / 要不要人工 / 下一步动作 / 归谁 / 原因)
* :func:`can_transition` —— 状态迁移是否合法(咨询式, 用于留痕告警)

层次说明
--------
``catalog_files.status``(见 :mod:`modules.core.catalog_status`)是**持久化的处理阶段**;
本模块的 ``file_state`` 是**判定结论**, 由「处理阶段 + 模板/治理状态 + 漂移标记」推导。
两者不是一回事: status 回答"走到哪一步了", file_state 回答"现在该谁管"。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from backend.services.data_sync_status_semantics import (
    GOVERNANCE_STATUS_BREAKING_DRIFT,
    GOVERNANCE_STATUS_FILE_MISSING,
    GOVERNANCE_STATUS_MISSING_FAMILY,
    GOVERNANCE_STATUS_MISSING_VARIANT,
    GOVERNANCE_STATUS_NON_BREAKING_DRIFT,
    GOVERNANCE_STATUS_PARSE_FAILED,
    GOVERNANCE_STATUS_SEMANTIC_INVALID,
    SEMANTIC_CONTRACT_STATUS_BREAKING_DRIFT,
    TEMPLATE_BASELINE_CROSS_FAMILY_VARIANT,
    TEMPLATE_STATUS_MISSING,
    TEMPLATE_STATUS_MISSING_VARIANT,
    TEMPLATE_STATUS_UPDATE_REQUIRED,
)
from modules.core.catalog_status import (
    CATALOG_FILE_STATUS_FAILED,
    CATALOG_FILE_STATUS_INGESTED,
    CATALOG_FILE_STATUS_NEEDS_SHOP,
    CATALOG_FILE_STATUS_PARTIAL_SUCCESS,
    CATALOG_FILE_STATUS_PENDING,
    CATALOG_FILE_STATUS_PROCESSING,
    CATALOG_FILE_STATUS_QUARANTINED,
    CATALOG_FILE_STATUS_SOURCE_MISSING,
    CATALOG_FILE_STATUS_TEMPLATE_UPDATE_REQUIRED,
)


# ── 文件状态 (判定结论) ─────────────────────────────────────────────
FILE_STATE_READY_TO_SYNC = "ready_to_sync"
FILE_STATE_IN_PROGRESS = "in_progress"
FILE_STATE_BLOCKED_TEMPLATE_UPDATE = "blocked_template_update"
FILE_STATE_BLOCKED_MANUAL_TEMPLATE_UPDATE = "blocked_manual_template_update"
FILE_STATE_BLOCKED_MISSING_TEMPLATE = "blocked_missing_template"
FILE_STATE_BLOCKED_MISSING_VARIANT = "blocked_missing_variant"
FILE_STATE_BLOCKED_SEMANTIC_CONTRACT = "blocked_semantic_contract"
FILE_STATE_BLOCKED_SEMANTIC_INVALID = "blocked_semantic_invalid"
FILE_STATE_BLOCKED_PARSE_FAILED = "blocked_parse_failed"
FILE_STATE_SOURCE_MISSING = "source_missing"
FILE_STATE_FAILED = "failed"
FILE_STATE_INGESTED = "ingested"
FILE_STATE_PARTIAL_SUCCESS = "partial_success"
FILE_STATE_QUARANTINED = "quarantined"
FILE_STATE_NEEDS_SHOP = "needs_shop"

FILE_STATES = (
    FILE_STATE_READY_TO_SYNC,
    FILE_STATE_IN_PROGRESS,
    FILE_STATE_BLOCKED_TEMPLATE_UPDATE,
    FILE_STATE_BLOCKED_MANUAL_TEMPLATE_UPDATE,
    FILE_STATE_BLOCKED_MISSING_TEMPLATE,
    FILE_STATE_BLOCKED_MISSING_VARIANT,
    FILE_STATE_BLOCKED_SEMANTIC_CONTRACT,
    FILE_STATE_BLOCKED_SEMANTIC_INVALID,
    FILE_STATE_BLOCKED_PARSE_FAILED,
    FILE_STATE_SOURCE_MISSING,
    FILE_STATE_FAILED,
    FILE_STATE_INGESTED,
    FILE_STATE_PARTIAL_SUCCESS,
    FILE_STATE_QUARANTINED,
    FILE_STATE_NEEDS_SHOP,
)


# ── 下一步动作 ───────────────────────────────────────────────────────
FILE_ACTION_AUTO_SYNC = "auto_sync"
FILE_ACTION_AWAIT_TEMPLATE_UPDATE = "await_template_update"
FILE_ACTION_MANUAL_TEMPLATE_UPDATE = "manual_template_update"
FILE_ACTION_MANUAL_MAPPING = "manual_mapping"
FILE_ACTION_MANUAL_REPAIR = "manual_repair"
FILE_ACTION_RETRY_SYNC = "retry_sync"
FILE_ACTION_NONE = "none"

FILE_ACTIONS = (
    FILE_ACTION_AUTO_SYNC,
    FILE_ACTION_AWAIT_TEMPLATE_UPDATE,
    FILE_ACTION_MANUAL_TEMPLATE_UPDATE,
    FILE_ACTION_MANUAL_MAPPING,
    FILE_ACTION_MANUAL_REPAIR,
    FILE_ACTION_RETRY_SYNC,
    FILE_ACTION_NONE,
)


# ── 归谁处理 ─────────────────────────────────────────────────────────
FILE_OWNER_SYSTEM = "system"
FILE_OWNER_TEMPLATE = "template_owner"
FILE_OWNER_DATA = "data_owner"
FILE_OWNER_NONE = "none"

FILE_OWNERS = (
    FILE_OWNER_SYSTEM,
    FILE_OWNER_TEMPLATE,
    FILE_OWNER_DATA,
    FILE_OWNER_NONE,
)


# ── 状态迁移表 (咨询式) ─────────────────────────────────────────────
#
# 说明: 这张表描述**正常流程**允许的迁移, 用来在写入点留痕告警,
# 而不是硬性拦截 —— 系统里存在合法的例外(例如「重置重导」会把
# ingested 改回 pending), 硬拦会误伤正常操作。
ALLOWED_TRANSITIONS: Dict[str, frozenset] = {
    CATALOG_FILE_STATUS_PENDING: frozenset(
        {
            CATALOG_FILE_STATUS_PROCESSING,
            CATALOG_FILE_STATUS_INGESTED,
            CATALOG_FILE_STATUS_PARTIAL_SUCCESS,
            CATALOG_FILE_STATUS_QUARANTINED,
            CATALOG_FILE_STATUS_FAILED,
            CATALOG_FILE_STATUS_SOURCE_MISSING,
            CATALOG_FILE_STATUS_TEMPLATE_UPDATE_REQUIRED,
            CATALOG_FILE_STATUS_NEEDS_SHOP,
        }
    ),
    CATALOG_FILE_STATUS_PROCESSING: frozenset(
        {
            CATALOG_FILE_STATUS_PENDING,
            CATALOG_FILE_STATUS_INGESTED,
            CATALOG_FILE_STATUS_PARTIAL_SUCCESS,
            CATALOG_FILE_STATUS_QUARANTINED,
            CATALOG_FILE_STATUS_FAILED,
            CATALOG_FILE_STATUS_SOURCE_MISSING,
            CATALOG_FILE_STATUS_TEMPLATE_UPDATE_REQUIRED,
        }
    ),
    CATALOG_FILE_STATUS_TEMPLATE_UPDATE_REQUIRED: frozenset(
        {
            CATALOG_FILE_STATUS_PENDING,
            CATALOG_FILE_STATUS_FAILED,
            CATALOG_FILE_STATUS_INGESTED,
            CATALOG_FILE_STATUS_PARTIAL_SUCCESS,
        }
    ),
    CATALOG_FILE_STATUS_FAILED: frozenset(
        {
            CATALOG_FILE_STATUS_PENDING,
            CATALOG_FILE_STATUS_PROCESSING,
            CATALOG_FILE_STATUS_TEMPLATE_UPDATE_REQUIRED,
            CATALOG_FILE_STATUS_SOURCE_MISSING,
            CATALOG_FILE_STATUS_INGESTED,
        }
    ),
    CATALOG_FILE_STATUS_SOURCE_MISSING: frozenset(
        {
            CATALOG_FILE_STATUS_PENDING,
            CATALOG_FILE_STATUS_FAILED,
            CATALOG_FILE_STATUS_INGESTED,
        }
    ),
    CATALOG_FILE_STATUS_NEEDS_SHOP: frozenset(
        {
            CATALOG_FILE_STATUS_PENDING,
            CATALOG_FILE_STATUS_FAILED,
        }
    ),
    CATALOG_FILE_STATUS_INGESTED: frozenset(
        {
            # 「重置重导」是合法的运维动作
            CATALOG_FILE_STATUS_PENDING,
            CATALOG_FILE_STATUS_FAILED,
        }
    ),
    CATALOG_FILE_STATUS_PARTIAL_SUCCESS: frozenset(
        {CATALOG_FILE_STATUS_PENDING, CATALOG_FILE_STATUS_FAILED}
    ),
    CATALOG_FILE_STATUS_QUARANTINED: frozenset(
        {CATALOG_FILE_STATUS_PENDING, CATALOG_FILE_STATUS_FAILED}
    ),
}


def can_transition(from_status: Optional[str], to_status: Optional[str]) -> bool:
    """判断状态迁移是否属于正常流程。"""
    if not from_status or not to_status:
        return True
    if from_status == to_status:
        return True
    allowed = ALLOWED_TRANSITIONS.get(str(from_status))
    if allowed is None:
        # 未登记的起点不做判断(不猜)
        return True
    return str(to_status) in allowed


def _disposition(
    file_state: str,
    *,
    action: str,
    owner: str,
    needs_manual: bool,
    reason: Optional[str] = None,
    error_code: Optional[str] = None,
    extras: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload = {
        "file_state": file_state,
        "needs_manual_action": needs_manual,
        "next_action": action,
        "owner": owner,
        "reason": reason,
        "error_code": error_code,
    }
    if extras:
        payload.update(extras)
    return payload


def _takeover_extras(
    template_baseline: Optional[str],
    takeover: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """接管相关信号 —— 让治理视图能区分「跨 family 接管」与「真漂移」。

    一个被跨 family 变体接管的文件和一个真的结构漂移的文件, 在
    ``template_status`` 上都可能是 ``update_required``; 但前者的正确处置是
    「模板体系需要补登记 monthly 变体」, 后者是「源文件结构变了」。
    不把接管来源透出来, 治理面板就只能给出同一个笼统结论。
    """
    extras: Dict[str, Any] = {}
    if template_baseline:
        extras["template_baseline"] = template_baseline
    if isinstance(takeover, dict) and takeover:
        extras["takeover"] = {
            "flag": takeover.get("flag"),
            "source_family_id": takeover.get("source_family_id"),
            "source_family_granularity": takeover.get("source_family_granularity"),
            "variant_id": takeover.get("variant_id"),
            "variant_key": takeover.get("variant_key"),
            "match_rate": takeover.get("match_rate"),
            "missing_headers": list(takeover.get("missing_headers") or []),
        }
    return extras


def resolve_file_disposition(
    *,
    catalog_status: Optional[str] = None,
    template_status: Optional[str] = None,
    governance_status: Optional[str] = None,
    semantic_contract_status: Optional[str] = None,
    should_auto_sync: Optional[bool] = None,
    template_update_required: bool = False,
    drift_source: Optional[str] = None,
    auto_meta: Optional[Dict[str, Any]] = None,
    template_baseline: Optional[str] = None,
    takeover: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """给出文件在同步流程中的唯一处置结论。

    Args:
        catalog_status: ``catalog_files.status``
        template_status / governance_status / semantic_contract_status: 见
            :mod:`backend.services.data_sync_status_semantics`
        should_auto_sync: 就绪判定给出的「能否自动入库」
        template_update_required: 漂移判定结果(持久化标记或实时重算)
        drift_source: 漂移来源(``persisted`` / ``live``)
        auto_meta: ``file_metadata['auto_ingest']``, 用于识别「连续重检仍阻塞」
        template_baseline: 比较基准来源(``contract`` / ``cross_family_variant`` /
            ``current``), 用于区分「跨 family 接管」与「真漂移」
        takeover: 接管报告(见
            :func:`backend.services.template_variant_takeover.build_takeover_report`)
    """
    auto_meta = auto_meta if isinstance(auto_meta, dict) else {}
    status = str(catalog_status or "").strip()
    governance = str(governance_status or "").strip()
    template = str(template_status or "").strip()
    semantic_contract = str(semantic_contract_status or "").strip()
    extras = _takeover_extras(template_baseline, takeover)
    takeover_hit = template_baseline == TEMPLATE_BASELINE_CROSS_FAMILY_VARIANT

    # ── 1) 已经完成的 ──────────────────────────────────────────────
    if status == CATALOG_FILE_STATUS_INGESTED:
        return _disposition(
            FILE_STATE_INGESTED,
            action=FILE_ACTION_NONE,
            owner=FILE_OWNER_NONE,
            needs_manual=False,
            extras=extras,
        )
    if status == CATALOG_FILE_STATUS_PARTIAL_SUCCESS:
        return _disposition(
            FILE_STATE_PARTIAL_SUCCESS,
            action=FILE_ACTION_NONE,
            owner=FILE_OWNER_NONE,
            needs_manual=False,
            reason="部分数据入库成功, 另有隔离/失败数据",
            extras=extras,
        )
    if status == CATALOG_FILE_STATUS_QUARANTINED:
        return _disposition(
            FILE_STATE_QUARANTINED,
            action=FILE_ACTION_NONE,
            owner=FILE_OWNER_NONE,
            needs_manual=False,
            reason="数据被隔离(质量不达标)",
            extras=extras,
        )

    # ── 2) 明确需要人工的硬阻塞 ───────────────────────────────────
    if template == TEMPLATE_STATUS_MISSING_VARIANT or (
        governance == GOVERNANCE_STATUS_MISSING_VARIANT
    ):
        return _disposition(
            FILE_STATE_BLOCKED_MISSING_VARIANT,
            action=FILE_ACTION_MANUAL_MAPPING,
            owner=FILE_OWNER_TEMPLATE,
            needs_manual=True,
            reason="缺少模板变体",
            error_code="MISSING_VARIANT",
            extras=extras,
        )
    if template == TEMPLATE_STATUS_MISSING or governance == GOVERNANCE_STATUS_MISSING_FAMILY:
        return _disposition(
            FILE_STATE_BLOCKED_MISSING_TEMPLATE,
            action=FILE_ACTION_MANUAL_MAPPING,
            owner=FILE_OWNER_TEMPLATE,
            needs_manual=True,
            reason="没有可用的模板",
            error_code="MISSING_TEMPLATE",
            extras=extras,
        )
    if governance == GOVERNANCE_STATUS_SEMANTIC_INVALID:
        return _disposition(
            FILE_STATE_BLOCKED_SEMANTIC_INVALID,
            action=FILE_ACTION_MANUAL_REPAIR,
            owner=FILE_OWNER_DATA,
            needs_manual=True,
            reason="文件语义异常",
            error_code="SEMANTIC_INVALID",
            extras=extras,
        )
    if governance == GOVERNANCE_STATUS_FILE_MISSING or status == CATALOG_FILE_STATUS_SOURCE_MISSING:
        return _disposition(
            FILE_STATE_SOURCE_MISSING,
            action=FILE_ACTION_MANUAL_REPAIR,
            owner=FILE_OWNER_DATA,
            needs_manual=True,
            reason="源文件在磁盘上缺失",
            error_code="SOURCE_MISSING",
            extras=extras,
        )
    if governance == GOVERNANCE_STATUS_PARSE_FAILED:
        return _disposition(
            FILE_STATE_BLOCKED_PARSE_FAILED,
            action=FILE_ACTION_MANUAL_REPAIR,
            owner=FILE_OWNER_DATA,
            needs_manual=True,
            reason="文件解析失败",
            error_code="PARSE_FAILED",
            extras=extras,
        )
    if semantic_contract == SEMANTIC_CONTRACT_STATUS_BREAKING_DRIFT:
        # [*] 只有「语义契约本身不满足」才算语义契约阻塞。
        # governance_status == breaking_drift 只是结构漂移的另一种说法,
        # 两者共用漂移词汇但不是一回事 —— 混在一起会让治理面板把
        # 「源文件多了一列」误报成「语义字段缺失」。
        return _disposition(
            FILE_STATE_BLOCKED_SEMANTIC_CONTRACT,
            action=FILE_ACTION_MANUAL_TEMPLATE_UPDATE,
            owner=FILE_OWNER_TEMPLATE,
            needs_manual=True,
            reason="语义契约不满足(必需语义键缺失)",
            error_code="SEMANTIC_CONTRACT_BROKEN",
            extras=extras,
        )

    # ── 3) 漂移待更新 ─────────────────────────────────────────────
    if (
        template_update_required
        or status == CATALOG_FILE_STATUS_TEMPLATE_UPDATE_REQUIRED
        or governance == GOVERNANCE_STATUS_BREAKING_DRIFT
        or template == TEMPLATE_STATUS_UPDATE_REQUIRED
    ):
        needs_manual = bool(auto_meta.get("needs_manual_template_update"))
        if needs_manual:
            return _disposition(
                FILE_STATE_BLOCKED_MANUAL_TEMPLATE_UPDATE,
                action=FILE_ACTION_MANUAL_TEMPLATE_UPDATE,
                owner=FILE_OWNER_TEMPLATE,
                needs_manual=True,
                reason=(
                    "连续重检仍被模板阻塞(已由其他粒度变体接管), 需人工更新模板"
                    if takeover_hit
                    else "连续重检仍被模板阻塞, 需人工更新模板"
                ),
                error_code="TEMPLATE_UPDATE_REQUIRED",
                extras=extras,
        )
        return _disposition(
            FILE_STATE_BLOCKED_TEMPLATE_UPDATE,
            action=FILE_ACTION_AWAIT_TEMPLATE_UPDATE,
            owner=FILE_OWNER_SYSTEM,
            needs_manual=False,
            reason=(
                "模板待更新(已由其他粒度变体接管, 需补登记本粒度变体)"
                if takeover_hit
                else "模板待更新, 等待系统自动重检"
            ),
            error_code="TEMPLATE_UPDATE_REQUIRED",
            extras=extras,
        )

    # ── 4) 其余按处理阶段 ─────────────────────────────────────────
    if status == CATALOG_FILE_STATUS_PROCESSING:
        return _disposition(
            FILE_STATE_IN_PROGRESS,
            action=FILE_ACTION_NONE,
            owner=FILE_OWNER_SYSTEM,
            needs_manual=False,
            reason="正在同步",
            extras=extras,
        )
    if status == CATALOG_FILE_STATUS_FAILED:
        return _disposition(
            FILE_STATE_FAILED,
            action=FILE_ACTION_RETRY_SYNC,
            owner=FILE_OWNER_SYSTEM,
            needs_manual=False,
            reason="上次同步失败, 可重试",
            error_code="SYNC_FAILED",
            extras=extras,
        )
    if status == CATALOG_FILE_STATUS_NEEDS_SHOP:
        return _disposition(
            FILE_STATE_NEEDS_SHOP,
            action=FILE_ACTION_MANUAL_REPAIR,
            owner=FILE_OWNER_DATA,
            needs_manual=True,
            reason="店铺归属待指派",
            error_code="NEEDS_SHOP",
            extras=extras,
        )
    if governance == GOVERNANCE_STATUS_NON_BREAKING_DRIFT:
        # 非阻断漂移: 不阻断入库, 但保留可见性
        return _disposition(
            FILE_STATE_READY_TO_SYNC,
            action=FILE_ACTION_AUTO_SYNC,
            owner=FILE_OWNER_SYSTEM,
            needs_manual=False,
            reason=(
                "由其他粒度的变体接管, 存在非阻断漂移, 不影响入库"
                if takeover_hit
                else "存在非阻断漂移, 不影响入库"
            ),
            extras=extras,
        )
    if should_auto_sync is False and template == "update_required":
        return _disposition(
            FILE_STATE_BLOCKED_TEMPLATE_UPDATE,
            action=FILE_ACTION_AWAIT_TEMPLATE_UPDATE,
            owner=FILE_OWNER_SYSTEM,
            needs_manual=False,
            reason=(
                "模板待更新(已由其他粒度变体接管, 需补登记本粒度变体)"
                if takeover_hit
                else "模板待更新"
            ),
            error_code="TEMPLATE_UPDATE_REQUIRED",
            extras=extras,
        )

    return _disposition(
        FILE_STATE_READY_TO_SYNC,
        action=FILE_ACTION_AUTO_SYNC,
        owner=FILE_OWNER_SYSTEM,
        needs_manual=False,
        reason=(
            "由其他粒度的变体接管解释, 可直接入库" if takeover_hit else None
        ),
        extras=extras,
    )


def disposition_from_catalog_file(
    catalog_file: Any,
    *,
    template_status: Optional[str] = None,
    governance_status: Optional[str] = None,
    semantic_contract_status: Optional[str] = None,
    should_auto_sync: Optional[bool] = None,
    template_update_required: bool = False,
    drift_source: Optional[str] = None,
    template_baseline: Optional[str] = None,
    takeover: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """从 ``catalog_files`` 记录直接推导处置结论。"""
    metadata = getattr(catalog_file, "file_metadata", None) or {}
    auto_meta = metadata.get("auto_ingest") if isinstance(metadata, dict) else None
    return resolve_file_disposition(
        catalog_status=getattr(catalog_file, "status", None),
        template_status=template_status,
        governance_status=governance_status,
        semantic_contract_status=semantic_contract_status,
        should_auto_sync=should_auto_sync,
        template_update_required=template_update_required,
        drift_source=drift_source,
        auto_meta=auto_meta if isinstance(auto_meta, dict) else None,
        template_baseline=template_baseline,
        takeover=takeover,
    )
