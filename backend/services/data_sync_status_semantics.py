"""数据同步状态语义 (SSOT)

为什么
----
同一个事实, 系统里有两套名字:

* ``template_status`` —— 描述「文件与模板的关系」(ready / alias_only /
  update_required / missing / missing_variant / semantic_invalid /
  file_missing / parse_failed)
* ``governance_status`` —— 描述「治理视角的结论」(ready / non_breaking_drift /
  breaking_drift / missing_family / missing_variant / semantic_invalid /
  file_missing / parse_failed)

两套名字**一一对应但由不同地方定义**:

* ``backend/services/data_sync_template_status_service.py`` 直接写死对应关系
* ``backend/services/data_sync_service.py::_normalize_governance_status`` 又抄了一份映射表

⇒ 两份映射表可能漂移; 而且旧的那份**漏了 ``semantic_invalid``**,
只能靠「取不到就原样返回」碰巧对上。

本模块把「模板状态 ↔ 治理状态」的对应关系收敛成唯一一张表,
所有产出点与消费点都引用它, 杜绝第二份定义。

另外提供**阻断性判定**与**中文标签**, 供接口与前端共用。
"""

from __future__ import annotations

from typing import Dict, Optional

# ── template_status: 文件与模板的关系 ─────────────────────────────────
TEMPLATE_STATUS_READY = "ready"
TEMPLATE_STATUS_ALIAS_ONLY = "alias_only"
TEMPLATE_STATUS_UPDATE_REQUIRED = "update_required"
TEMPLATE_STATUS_MISSING = "missing"
TEMPLATE_STATUS_MISSING_VARIANT = "missing_variant"
TEMPLATE_STATUS_SEMANTIC_INVALID = "semantic_invalid"
TEMPLATE_STATUS_FILE_MISSING = "file_missing"
TEMPLATE_STATUS_PARSE_FAILED = "parse_failed"

TEMPLATE_STATUSES = (
    TEMPLATE_STATUS_READY,
    TEMPLATE_STATUS_ALIAS_ONLY,
    TEMPLATE_STATUS_UPDATE_REQUIRED,
    TEMPLATE_STATUS_MISSING,
    TEMPLATE_STATUS_MISSING_VARIANT,
    TEMPLATE_STATUS_SEMANTIC_INVALID,
    TEMPLATE_STATUS_FILE_MISSING,
    TEMPLATE_STATUS_PARSE_FAILED,
)

# ── governance_status: 治理视角的结论 ────────────────────────────────
GOVERNANCE_STATUS_READY = "ready"
GOVERNANCE_STATUS_NON_BREAKING_DRIFT = "non_breaking_drift"
GOVERNANCE_STATUS_BREAKING_DRIFT = "breaking_drift"
GOVERNANCE_STATUS_MISSING_FAMILY = "missing_family"
GOVERNANCE_STATUS_MISSING_VARIANT = "missing_variant"
GOVERNANCE_STATUS_SEMANTIC_INVALID = "semantic_invalid"
GOVERNANCE_STATUS_FILE_MISSING = "file_missing"
GOVERNANCE_STATUS_PARSE_FAILED = "parse_failed"

GOVERNANCE_STATUSES = (
    GOVERNANCE_STATUS_READY,
    GOVERNANCE_STATUS_NON_BREAKING_DRIFT,
    GOVERNANCE_STATUS_BREAKING_DRIFT,
    GOVERNANCE_STATUS_MISSING_FAMILY,
    GOVERNANCE_STATUS_MISSING_VARIANT,
    GOVERNANCE_STATUS_SEMANTIC_INVALID,
    GOVERNANCE_STATUS_FILE_MISSING,
    GOVERNANCE_STATUS_PARSE_FAILED,
)


# ── semantic_contract_status: 语义契约层的结论 ────────────────────────
#
# 语义契约是治理结论的**子信号**, 与 governance_status 共用同一套漂移词汇
# (ready / non_breaking_drift / breaking_drift), 差别只是少了「缺模板」一类。
# 之前它自成一套字面量, 与 governance_status 的漂移词汇混用时容易看错。
SEMANTIC_CONTRACT_STATUS_NOT_CONFIGURED = "not_configured"
SEMANTIC_CONTRACT_STATUS_READY = "ready"
SEMANTIC_CONTRACT_STATUS_NON_BREAKING_DRIFT = "non_breaking_drift"
SEMANTIC_CONTRACT_STATUS_BREAKING_DRIFT = "breaking_drift"

SEMANTIC_CONTRACT_STATUSES = (
    SEMANTIC_CONTRACT_STATUS_NOT_CONFIGURED,
    SEMANTIC_CONTRACT_STATUS_READY,
    SEMANTIC_CONTRACT_STATUS_NON_BREAKING_DRIFT,
    SEMANTIC_CONTRACT_STATUS_BREAKING_DRIFT,
)


# ── template_baseline: 「拿哪一版模板做比较基准」 ──────────────────────
#
# contract             : 文件自带的模板契约(采集当时生效的那一版)
# cross_family_variant : 由**其他粒度**的变体接管解释(跨 family 变体接管)
# current              : 没有契约也没有接管, 只能拿当前已发布模板
# none                 : 连当前已发布模板都没有
TEMPLATE_BASELINE_CONTRACT = "contract"
TEMPLATE_BASELINE_CROSS_FAMILY_VARIANT = "cross_family_variant"
TEMPLATE_BASELINE_CURRENT = "current"
TEMPLATE_BASELINE_NONE = "none"

TEMPLATE_BASELINES = (
    TEMPLATE_BASELINE_CONTRACT,
    TEMPLATE_BASELINE_CROSS_FAMILY_VARIANT,
    TEMPLATE_BASELINE_CURRENT,
    TEMPLATE_BASELINE_NONE,
)

TEMPLATE_BASELINE_LABELS: Dict[str, str] = {
    TEMPLATE_BASELINE_CONTRACT: "文件契约",
    TEMPLATE_BASELINE_CROSS_FAMILY_VARIANT: "跨粒度变体接管",
    TEMPLATE_BASELINE_CURRENT: "当前已发布模板",
    TEMPLATE_BASELINE_NONE: "无基准",
}


# ── 唯一映射表 (SSOT) ───────────────────────────────────────────────
TEMPLATE_STATUS_TO_GOVERNANCE: Dict[str, str] = {
    TEMPLATE_STATUS_READY: GOVERNANCE_STATUS_READY,
    TEMPLATE_STATUS_ALIAS_ONLY: GOVERNANCE_STATUS_NON_BREAKING_DRIFT,
    TEMPLATE_STATUS_UPDATE_REQUIRED: GOVERNANCE_STATUS_BREAKING_DRIFT,
    TEMPLATE_STATUS_MISSING: GOVERNANCE_STATUS_MISSING_FAMILY,
    TEMPLATE_STATUS_MISSING_VARIANT: GOVERNANCE_STATUS_MISSING_VARIANT,
    TEMPLATE_STATUS_SEMANTIC_INVALID: GOVERNANCE_STATUS_SEMANTIC_INVALID,
    TEMPLATE_STATUS_FILE_MISSING: GOVERNANCE_STATUS_FILE_MISSING,
    TEMPLATE_STATUS_PARSE_FAILED: GOVERNANCE_STATUS_PARSE_FAILED,
}


# ── 阻断性(需要人工介入才能推进)的治理状态 ──────────────────────────
BLOCKING_GOVERNANCE_STATUSES = frozenset(
    {
        GOVERNANCE_STATUS_BREAKING_DRIFT,
        GOVERNANCE_STATUS_MISSING_FAMILY,
        GOVERNANCE_STATUS_MISSING_VARIANT,
        GOVERNANCE_STATUS_SEMANTIC_INVALID,
    }
)


# ── 中文标签(接口与面板展示) ─────────────────────────────────────────
TEMPLATE_STATUS_LABELS: Dict[str, str] = {
    TEMPLATE_STATUS_READY: "模板匹配",
    TEMPLATE_STATUS_ALIAS_ONLY: "别名可匹配",
    TEMPLATE_STATUS_UPDATE_REQUIRED: "模板待更新",
    TEMPLATE_STATUS_MISSING: "缺少模板",
    TEMPLATE_STATUS_MISSING_VARIANT: "缺少模板变体",
    TEMPLATE_STATUS_SEMANTIC_INVALID: "语义异常",
    TEMPLATE_STATUS_FILE_MISSING: "源文件缺失",
    TEMPLATE_STATUS_PARSE_FAILED: "解析失败",
}

GOVERNANCE_STATUS_LABELS: Dict[str, str] = {
    GOVERNANCE_STATUS_READY: "就绪",
    GOVERNANCE_STATUS_NON_BREAKING_DRIFT: "非阻断漂移",
    GOVERNANCE_STATUS_BREAKING_DRIFT: "阻断漂移",
    GOVERNANCE_STATUS_MISSING_FAMILY: "缺少模板族",
    GOVERNANCE_STATUS_MISSING_VARIANT: "缺少模板变体",
    GOVERNANCE_STATUS_SEMANTIC_INVALID: "语义异常",
    GOVERNANCE_STATUS_FILE_MISSING: "源文件缺失",
    GOVERNANCE_STATUS_PARSE_FAILED: "解析失败",
}


def governance_status_for(template_status: Optional[str]) -> str:
    """由 template_status 推出 governance_status(唯一入口)。

    未知取值原样返回 —— 不猜测, 也不静默变成 ready。
    """
    if not template_status:
        return GOVERNANCE_STATUS_PARSE_FAILED
    return TEMPLATE_STATUS_TO_GOVERNANCE.get(
        str(template_status), str(template_status)
    )


def is_blocking_governance_status(governance_status: Optional[str]) -> bool:
    """该治理状态是否需要人工介入才能推进。"""
    if not governance_status:
        return False
    return str(governance_status) in BLOCKING_GOVERNANCE_STATUSES


def is_breaking_drift(*statuses: Optional[str]) -> bool:
    """给定的若干状态里是否存在「阻断漂移」。

    语义契约状态与治理状态共用漂移词汇, 判断时用同一个函数,
    避免"这个 breaking_drift 和那个 breaking_drift 是不是一回事"的疑问。
    """
    return any(
        str(status) in {GOVERNANCE_STATUS_BREAKING_DRIFT, SEMANTIC_CONTRACT_STATUS_BREAKING_DRIFT}
        for status in statuses
        if status
    )


def template_status_label(template_status: Optional[str]) -> str:
    if not template_status:
        return ""
    return TEMPLATE_STATUS_LABELS.get(str(template_status), str(template_status))


def governance_status_label(governance_status: Optional[str]) -> str:
    if not governance_status:
        return ""
    return GOVERNANCE_STATUS_LABELS.get(str(governance_status), str(governance_status))


def status_semantics_snapshot() -> Dict[str, object]:
    """对外暴露的状态语义快照(接口自省用, 避免前端再写一份映射)。"""
    return {
        "template_status": list(TEMPLATE_STATUSES),
        "governance_status": list(GOVERNANCE_STATUSES),
        "semantic_contract_status": list(SEMANTIC_CONTRACT_STATUSES),
        "template_to_governance": dict(TEMPLATE_STATUS_TO_GOVERNANCE),
        "blocking_governance_status": sorted(BLOCKING_GOVERNANCE_STATUSES),
        "template_status_labels": dict(TEMPLATE_STATUS_LABELS),
        "governance_status_labels": dict(GOVERNANCE_STATUS_LABELS),
        "template_baselines": list(TEMPLATE_BASELINES),
        "template_baseline_labels": dict(TEMPLATE_BASELINE_LABELS),
    }
