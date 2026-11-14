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

import os
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

# ── template_status: 文件与模板的关系 ─────────────────────────────────
TEMPLATE_STATUS_READY = "ready"
TEMPLATE_STATUS_ALIAS_ONLY = "alias_only"
TEMPLATE_STATUS_UPDATE_REQUIRED = "update_required"
TEMPLATE_STATUS_MISSING = "missing"
TEMPLATE_STATUS_MISSING_VARIANT = "missing_variant"
TEMPLATE_STATUS_SEMANTIC_INVALID = "semantic_invalid"
TEMPLATE_STATUS_FILE_MISSING = "file_missing"
TEMPLATE_STATUS_PARSE_FAILED = "parse_failed"

# [*] 批次 B 新增: 值形态漂移。
#
# 与 ``update_required`` 的区别:
#   * ``update_required`` = **列名**对不上(表头漂移)
#   * ``format_drift``   = **列名**对得上, 但**值的形态**变了
#     (例如日期列从 ``01/10/2026`` 变成 ``01-10-2026``)
#
# 它是「事前」判出来的: 漂移检测用样本行试解析声明的日期格式,
# 解不出来就落这个状态 —— 而不是等入库时整份文件炸掉。
TEMPLATE_STATUS_FORMAT_DRIFT = "format_drift"

TEMPLATE_STATUSES = (
    TEMPLATE_STATUS_READY,
    TEMPLATE_STATUS_ALIAS_ONLY,
    TEMPLATE_STATUS_UPDATE_REQUIRED,
    TEMPLATE_STATUS_MISSING,
    TEMPLATE_STATUS_MISSING_VARIANT,
    TEMPLATE_STATUS_SEMANTIC_INVALID,
    TEMPLATE_STATUS_FILE_MISSING,
    TEMPLATE_STATUS_PARSE_FAILED,
    TEMPLATE_STATUS_FORMAT_DRIFT,
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

# [*] 批次 B 新增: 值形态漂移(列名对得上, 值的形态变了)。详见
# :data:`TEMPLATE_STATUS_FORMAT_DRIFT` 的说明。
GOVERNANCE_STATUS_FORMAT_DRIFT = "format_drift"

GOVERNANCE_STATUSES = (
    GOVERNANCE_STATUS_READY,
    GOVERNANCE_STATUS_NON_BREAKING_DRIFT,
    GOVERNANCE_STATUS_BREAKING_DRIFT,
    GOVERNANCE_STATUS_MISSING_FAMILY,
    GOVERNANCE_STATUS_MISSING_VARIANT,
    GOVERNANCE_STATUS_SEMANTIC_INVALID,
    GOVERNANCE_STATUS_FILE_MISSING,
    GOVERNANCE_STATUS_PARSE_FAILED,
    GOVERNANCE_STATUS_FORMAT_DRIFT,
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
    TEMPLATE_STATUS_FORMAT_DRIFT: GOVERNANCE_STATUS_FORMAT_DRIFT,
}


# ── 阻断性(需要人工介入才能推进)的治理状态 ──────────────────────────
BLOCKING_GOVERNANCE_STATUSES = frozenset(
    {
        GOVERNANCE_STATUS_BREAKING_DRIFT,
        GOVERNANCE_STATUS_MISSING_FAMILY,
        GOVERNANCE_STATUS_MISSING_VARIANT,
        GOVERNANCE_STATUS_SEMANTIC_INVALID,
        # [*] 值形态漂移阻断: 文件的日期值已经变成模板声明格式解不出来的样子,
        # 继续入库只会整份失败 —— 必须先改模板(换格式或改用自动判定)。
        GOVERNANCE_STATUS_FORMAT_DRIFT,
    }
)


# ── 中文标签(接口与面板展示) ─────────────────────────────────────────
TEMPLATE_STATUS_LABELS: Dict[str, str] = {
    TEMPLATE_STATUS_READY: "模板匹配",
    TEMPLATE_STATUS_ALIAS_ONLY: "别名可匹配",
    # [*] 2026-11-14: 阻断的唯一理由是「核心字段(需求)没满足」,
    #     不再是「列对不上」—— 多一列/少一列现在都不阻断。
    TEMPLATE_STATUS_UPDATE_REQUIRED: "核心字段待补齐",
    TEMPLATE_STATUS_MISSING: "缺少模板",
    TEMPLATE_STATUS_MISSING_VARIANT: "缺少模板变体",
    TEMPLATE_STATUS_SEMANTIC_INVALID: "语义异常",
    TEMPLATE_STATUS_FILE_MISSING: "源文件缺失",
    TEMPLATE_STATUS_PARSE_FAILED: "解析失败",
    TEMPLATE_STATUS_FORMAT_DRIFT: "值形态漂移",
}

GOVERNANCE_STATUS_LABELS: Dict[str, str] = {
    GOVERNANCE_STATUS_READY: "就绪",
    # [*] 2026-11-14: 非阻断漂移 = 「多了新列 / 少了非核心列」⇒ 不影响入库。
    GOVERNANCE_STATUS_NON_BREAKING_DRIFT: "列有变化(不影响入库)",
    # [*] 2026-11-14: 阻断漂移 = 核心字段(需求)没满足。
    GOVERNANCE_STATUS_BREAKING_DRIFT: "核心字段缺失",
    GOVERNANCE_STATUS_MISSING_FAMILY: "缺少模板族",
    GOVERNANCE_STATUS_MISSING_VARIANT: "缺少模板变体",
    GOVERNANCE_STATUS_SEMANTIC_INVALID: "语义异常",
    GOVERNANCE_STATUS_FILE_MISSING: "源文件缺失",
    GOVERNANCE_STATUS_PARSE_FAILED: "解析失败",
    GOVERNANCE_STATUS_FORMAT_DRIFT: "值形态漂移",
}


def governance_status_for(template_status: Optional[str]) -> str:
    """由 template_status 推出 governance_status(唯一入口)。

    未知取值原样返回 —— 不猜测, 也不静默变成 ready。
    """
    if not template_status:
        return GOVERNANCE_STATUS_PARSE_FAILED
    return TEMPLATE_STATUS_TO_GOVERNANCE.get(str(template_status), str(template_status))


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
        str(status)
        in {GOVERNANCE_STATUS_BREAKING_DRIFT, SEMANTIC_CONTRACT_STATUS_BREAKING_DRIFT}
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
        "drift_rules": list(DRIFT_RULE_IDS),
    }


# ══════════════════════════════════════════════════════════════════════
# 漂移判定(L3):「什么算漂移、什么算阻断」的**唯一入口**
# ══════════════════════════════════════════════════════════════════════
#
# 为什么要有这一层
# ----------------
# 判定口径曾经散落在**三处**, 且彼此会漂移:
#
#   1. ``template_matcher._classify_header_changes`` —— 自己把列差异分成
#      blocking / non_blocking, 还硬编码了一个平台三元组特判;
#   2. ``semantic_field_contract_service.evaluate`` —— 又算了一套
#      ``should_block`` / ``missing_required_keys``;
#   3. 本模块 —— 只定义「状态叫什么」, 不管「什么算漂移」。
#
# ⇒ 同一事实三份定义, 于是 Shopee 订单月报只能用 ``if`` 打补丁,
#    而 TikTok 订单多一列照样被卡住(2026-11-13 实测)。
#
# 业务口径(本模块是它的唯一实现)
# -------------------------------
# **核心字段 = 需求。** 只有「需求没被满足」才阻断。
#
# | 情形 | 判定 |
# |---|---|
# | 核心字段(``required=true``)缺失 | **阻断** |
# | 域级契约的必填语义键缺失 | **阻断** |
# | 值形态漂移(列名没变、值形态变了) | **阻断** |
# | 多了新列 | **不阻断**, 原样入 ``raw_data`` |
# | 少了一列, 但它**不在**核心字段清单里 | **不阻断** |
# | 少了一列, 清单里 ``required=false`` | **不阻断** |
# | 少了一列, 缺的是列名(别名救回) | **不阻断** |
#
# 为什么「多一列」**不**阻断(2026-11-14 口径回退)
# ---------------------------------------------------
# 2026-11-13(v7.26.0)曾把「多一列 ⇒ 阻断」写成硬规则, 理由是:
#   「模板没声明的列**不会写进事实表** ⇒ 放行等于**静默丢数据**」。
#
# **该前提在批次 E/F 之后已经不成立**:
#   * 非核心列的完整内容留在 ``raw_data`` JSONB 里
#     (``backend/services/raw_data_importer.py``: ``"raw_data": row``);
#   * 只为核心字段建物理列, 其余不建(批次 F「落库列收窄」);
#   * 下游语义视图**全部**从 ``raw_data->>'某列'`` 取值
#     (``sql/semantic/*.sql``; 护栏 ``test_core_fields_storage_guardrails.py``)。
#
# ⇒ 新列的数据**不会丢**, 它原样躺在 ``raw_data`` 里, 等语义层接入。
# ⇒ 这正是 2026-11-07 规格的原话
#   (``docs/superpowers/plans/2026-11-07-semantic-core-field-spec.md`` §1.4):
#   「核心字段没变, 只是**多了新列** ⇒ **不阻断, 照常入库**;
#     新列先原样存着, 等有空再决定它是什么」。
#
# 代价(业务已于 2026-11-14 确认接受):
#   * 新列的**语义接入会滞后** —— 数据在 ``raw_data`` 里, 下游语义视图要人再接一次;
#   * **已入库的历史行不会**因为后来模板纳入该列而自动补列。
#
# 「核心字段清单还没配置」的域(2026-11-14 业务拍板 B1)
# --------------------------------------------------
# 没有清单 = 还没有定义过「我要哪些数据」⇒ 无从判定少列是否可缺。
# ⇒ 阻断一次并明确提示「该维度尚未定义核心字段清单」
#   (这是**配置缺口**, 不是数据问题), 而不是逐列阻断, 也不是静默放行
#   (那等于放弃校验; 规格 §7: 「不引入系统自动猜一个语义键然后静默使用
#   —— 定不了就报警」)。
# 实测: 当前 **27 个 published 模板全部已配置**清单 ⇒ 该口径当前不误伤任何模板。
#
# ``ignored_extra_fields`` 的新语义(2026-11-14)
# -----------------------------------------
# 它曾经是「多列阻断的唯一豁免」; 现在多列已经不阻断 ⇒
# 它的作用**降级为已阅标记**(让面板不再把它当噪音反复报出来),
# **不再参与阻断判定**。
#
# 历史包袱(已清理)
# ----------------
# 旧实现对 ``shopee/orders/monthly`` 单开了一个口子:「新增列不阻断」。
# 那是 2026-06-17 的救火补丁(提交 ``e1c7cfca``), 后果是
# **shopee 订单月报的新列会被静默丢弃** —— 与其它所有域不一致, 且丢数据。
# ⇒ 2026-11-14 起该平台特判与全局口径**一致**: 多列一律不阻断,
#   且新列完整留在 ``raw_data``(不再丢数据)。
#

#: 漂移规则编号(便于守护测试与接口自省逐条引用)。
DRIFT_RULE_IDS = (
    "format_drift_blocks",
    "missing_required_key_blocks",
    "removed_required_column_blocks",
    "removed_unconfigured_dimension_blocks",
    "added_column_never_blocks",
    "optional_column_never_blocks",
    "column_order_change_never_blocks",
    "added_column_blocks_under_legacy_caliber",
)


# ── 漂移口径开关(紧急回退保险) ────────────────────────────────────────
#
#: 环境变量名。取值 ``legacy`` ⇒ 回到 2026-11-13 的旧口径。
DRIFT_CALIBER_ENV = "TEMPLATE_DRIFT_CALIBER"

#: 当前口径(默认): 核心字段 = 需求 ⇒ 多一列不阻断。
DRIFT_CALIBER_CURRENT = "current"

#: 旧口径(2026-11-13 / v7.26.0): 多一列 ⇒ 阻断。
DRIFT_CALIBER_LEGACY = "legacy"


def drift_caliber() -> str:
    """当前生效的漂移判定口径。

    为什么要有这个开关
    ------------------
    2026-11-14 的口径回退是本次**唯一的业务口径变更**
    (其余都是 bug 修复与工具链)。万一上线后发现判断与预期不符,
    运维需要一条**不需要改代码、不需要重新构建镜像**的回退路径:
    改一个环境变量 + 重启容器即可。

    ⇒ 开关只挂在「多一列」这一条规则上, 其余规则(核心字段缺失阻断、
      值形态漂移阻断、清单未配置阻断)两套口径完全一致, 不受开关影响。
    """
    raw = str(os.getenv(DRIFT_CALIBER_ENV, "") or "").strip().lower()
    if raw == DRIFT_CALIBER_LEGACY:
        return DRIFT_CALIBER_LEGACY
    return DRIFT_CALIBER_CURRENT


def legacy_caliber_enabled() -> bool:
    """是否运行在旧口径(紧急回退)下。"""
    return drift_caliber() == DRIFT_CALIBER_LEGACY


#: 兼容存量口径的「可选列名」名单(SSOT)。
#:
#: 背景: 旧实现把「预估回款金额」写死在 ``template_matcher.ORDER_OPTIONAL_FIELDS``
#: 里, 且只对 ``shopee/orders/monthly`` 生效(2026-06-17 救火补丁, 提交 ``e1c7cfca``)。
#: 实测(2026-11-13): shopee 订单月报模板的 ``core_fields`` 只有 4 条语义键、
#: ``header_bindings`` 里没有 ``estimated_settlement_amount``,
#: 而列名「预估回款金额」**确实在模板里** ⇒ 新口径若不留这份名单,
#: 它会从「不阻断」变成「阻断」⇒ 行为回归。
#:
#: ⇒ 这份名单**只**用于存量模板的兜底, 让本次口径调整不改变既有行为。
#: 新的可选列请写进**模板的核心字段清单**或**语义契约**, 不要往这里加。
OPTIONAL_RAW_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "预估回款金额",
    }
)


@dataclass(frozen=True)
class DriftDecision:
    """漂移判定的结论(判定链路的唯一产出形态)。"""

    is_blocking: bool
    template_status: str
    governance_status: str
    blocking_changes: List[str] = field(default_factory=list)
    non_blocking_changes: List[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "is_blocking": self.is_blocking,
            "template_status": self.template_status,
            "governance_status": self.governance_status,
            "blocking_changes": list(self.blocking_changes),
            "non_blocking_changes": list(self.non_blocking_changes),
            "reason": self.reason,
        }


def _dedupe(values: Iterable[str]) -> List[str]:
    """按出现顺序去重(不改顺序 ⇒ 面板上的展示顺序稳定)。"""
    seen: set[str] = set()
    result: List[str] = []
    for value in values:
        text = str(value)
        if text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def classify_drift(
    *,
    added_fields: Iterable[str] = (),
    removed_fields: Iterable[str] = (),
    format_drift_columns: Iterable[str] = (),
    is_exact_match: bool = False,
    is_semantic_match: bool = False,
    has_semantic_contract: bool = False,
    missing_required_keys: Iterable[str] = (),
    missing_optional_keys: Iterable[str] = (),
    optional_removed_raw_fields: Iterable[str] = (),
    blocking_removed_raw_fields: Iterable[str] = (),
    alias_rescued_removed_raw_fields: Iterable[str] = (),
    unmapped_removed_raw_fields: Iterable[str] = (),
    optional_raw_fields: Iterable[str] = (),
    required_core_fields: Iterable[str] = (),
    confirmed_extra_fields: Iterable[str] = (),
    core_fields_configured: bool = False,
) -> DriftDecision:
    """把「事实 + 语义」判成「阻断与否 / 什么状态 / 为什么」。

    这是**唯一**的判定入口: 判定链路、治理路由、入库前置校验都调它,
    任何地方都不得再自己拼 ``blocking`` / ``non_blocking``。

    Args:
        added_fields: 文件里有、模板里没有的列(多出来的列)。
        removed_fields: 模板里有、文件里没有的列(少掉的列)。
        format_drift_columns: 列名没变、但值的形态变了的列。
        is_exact_match: 列名与顺序都完全一致。
        is_semantic_match: 语义上完全等价(别名命中, 列名可以不同)。
        has_semantic_contract: 该域有没有语义契约(没有 ⇒ L2 给不出语义事实)。
        missing_required_keys: 解析不出来的必填语义键。
        missing_optional_keys: 解析不出来的可选语义键。
        optional_removed_raw_fields: 少掉的列里, **已证明可选**的那些。
        blocking_removed_raw_fields: 少掉的列里, 绑定必填语义键且救不回来的。
        alias_rescued_removed_raw_fields: 少掉的列里, 绑定必填语义键但被别名救回的
            (缺的是列名, 不是数据 ⇒ 不阻断)。
        unmapped_removed_raw_fields: 少掉的列里, 没有任何语义绑定的(保守阻断)。
        optional_raw_fields: 声明为可选的原始列名(核心字段清单 ``required=false``)。
        required_core_fields: 核心字段清单里 ``required=true`` 的**原始列名**
            ⇒ 少掉它就是**需求没被满足** ⇒ **阻断**
            (规格 §3.1: 漂移阻断 ← ``core_fields`` 中 ``required=true``)。
        confirmed_extra_fields: 用户在「已确认的新列」清单里确认过的列。
            **默认口径下不参与阻断判定**(多列已一律不阻断),
            只作为「已阅标记」用于面板去噪;
            **仅在旧口径**(:func:`legacy_caliber_enabled`)下才重新生效 ——
            那时它是「多列阻断」的唯一豁免。
        core_fields_configured: 该模板**是否已定义核心字段清单**。
            True ⇒ 清单外的列都不是需求 ⇒ 少它们**不阻断**;
            False ⇒ 该维度还没定义过需求 ⇒ 少列阻断(配置缺口, 业务拍板 B1)。

    Returns:
        :class:`DriftDecision`
    """
    added = _dedupe(added_fields)
    removed = _dedupe(removed_fields)
    format_columns = _dedupe(format_drift_columns)
    missing_required = _dedupe(missing_required_keys)
    missing_optional = _dedupe(missing_optional_keys)

    optional_set = {
        str(column) for column in optional_removed_raw_fields if str(column)
    }
    optional_set.update(str(column) for column in optional_raw_fields if str(column))
    optional_set.update(OPTIONAL_RAW_FIELD_NAMES)

    # [*] ``confirmed_extra_fields`` 不再参与阻断判定(2026-11-14):
    #     多列已一律不阻断, 「已确认的新列」只剩「已阅标记」的作用
    #     (面板去噪), 判定链路不再消费它。

    alias_rescued = {
        str(column) for column in alias_rescued_removed_raw_fields if str(column)
    }

    #: 少掉的列里, 绑定到**必填语义键**且该键**没被解析出来**的那些
    #: ⇒ 少它就真的少了一个业务维度 ⇒ **永远阻断**。
    binding_required = {
        str(column) for column in blocking_removed_raw_fields if str(column)
    }

    #: 核心字段清单里 ``required=true`` 的原始列名
    #: ⇒ 少它 = **需求没被满足** ⇒ **阻断**(规格 §3.1)。
    required_core = {str(column) for column in required_core_fields if str(column)}

    blocking: List[str] = []
    non_blocking: List[str] = []

    # 规则 1: 值形态漂移 —— 这份文件入库必然整份失败。
    blocking.extend(format_columns)

    # 规则 2: 必填语义键解析不出来 —— 业务上算不出要的那几个数。
    blocking.extend(missing_required)

    # 规则 3: 少列 —— 「能不能证明它可缺」由**核心字段清单**说了算。
    for column in removed:
        if column in optional_set:
            # 清单里 required=false / 语义契约 optional / 兼容名单
            non_blocking.append(column)
        elif column in alias_rescued:
            # 绑定到必填语义键、但被别名救回 ⇒ 缺的是列名, 不是数据。
            non_blocking.append(column)
        elif column in binding_required:
            # 绑定到必填语义键、且该键没被解析出来 ⇒ 阻断。
            blocking.append(column)
        elif column in required_core:
            # [*] 2026-11-14: 核心字段清单里 ``required=true`` 的列缺失
            #     ⇒ **需求没被满足** ⇒ 阻断(规格 §3.1)。
            blocking.append(column)
        elif core_fields_configured:
            # [*] 2026-11-14: 清单已配置 ⇒ 这列**不在需求里** ⇒ 少它不阻断。
            non_blocking.append(column)
        else:
            # [*] 2026-11-14 (业务拍板 B1): 清单为空 ⇒ 该维度还没定义过
            #     「我要哪些数据」⇒ 无从判定少列是否可缺 ⇒ 阻断一次并提示去配置。
            blocking.append(column)

    # 规则 4: 多一列 —— **不阻断**(2026-11-14 口径回退, 对齐 11-07 规格 §1.4)。
    #
    # 新列的完整内容留在 ``raw_data`` 里 ⇒ 数据不丢 ⇒ 没有理由拦下整个维度。
    # 用户在「已确认的新列」里勾过的列**同样不阻断**(它们只是「已阅」标记)。
    #
    # [*] 紧急回退保险: ``TEMPLATE_DRIFT_CALIBER=legacy`` ⇒ 回到 2026-11-13
    #     的旧口径(多一列 ⇒ 阻断, 用户确认过的除外)。
    #     只需要改环境变量并重启容器, 不必改代码、不必重新构建镜像。
    if legacy_caliber_enabled():
        confirmed_set = {
            str(column) for column in confirmed_extra_fields if str(column)
        }
        for column in added:
            if column in confirmed_set:
                non_blocking.append(column)
            else:
                blocking.append(column)
    else:
        non_blocking.extend(added)

    # 规则 5: 可选语义键缺失 —— 不阻断。
    non_blocking.extend(missing_optional)

    blocking = _dedupe(blocking)
    non_blocking = [item for item in _dedupe(non_blocking) if item not in set(blocking)]

    # 状态判定(优先级与历史行为一致, 但判定依据只有这一处)
    if format_columns:
        template_status = TEMPLATE_STATUS_FORMAT_DRIFT
        reason = "列名没变但值的形态变了(入库必然整份失败)"
    elif is_exact_match:
        template_status = TEMPLATE_STATUS_READY
        reason = "列名与顺序完全一致"
    elif is_semantic_match:
        # 语义上完全等价 ⇒ 原始列名的差异只是别名, 不是真缺失。
        template_status = TEMPLATE_STATUS_ALIAS_ONLY
        reason = "语义完全等价(别名命中), 列名差异不影响入库"
    elif blocking:
        template_status = TEMPLATE_STATUS_UPDATE_REQUIRED
        if not core_fields_configured and removed:
            # [*] 配置缺口(不是数据问题): 该维度还没定义过「我要哪些数据」。
            reason = "该维度尚未定义核心字段清单，无法判定哪些列是必需的"
        else:
            reason = f"有 {len(blocking)} 项阻断漂移(缺少必需字段)"
    else:
        template_status = TEMPLATE_STATUS_ALIAS_ONLY
        if added:
            reason = f"只多了 {len(added)} 列, 不影响入库"
        else:
            reason = "存在非阻断漂移"

    governance_status = governance_status_for(template_status)

    return DriftDecision(
        is_blocking=template_status
        in {
            TEMPLATE_STATUS_UPDATE_REQUIRED,
            TEMPLATE_STATUS_FORMAT_DRIFT,
        },
        template_status=template_status,
        governance_status=governance_status,
        blocking_changes=blocking,
        non_blocking_changes=non_blocking,
        reason=reason,
    )
