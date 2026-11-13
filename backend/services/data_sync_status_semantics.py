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
    TEMPLATE_STATUS_UPDATE_REQUIRED: "模板待更新",
    TEMPLATE_STATUS_MISSING: "缺少模板",
    TEMPLATE_STATUS_MISSING_VARIANT: "缺少模板变体",
    TEMPLATE_STATUS_SEMANTIC_INVALID: "语义异常",
    TEMPLATE_STATUS_FILE_MISSING: "源文件缺失",
    TEMPLATE_STATUS_PARSE_FAILED: "解析失败",
    TEMPLATE_STATUS_FORMAT_DRIFT: "值形态漂移",
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
# **多一列, 算问题 —— 直到模板把它纳入为止。**
#
# 为什么「多一列」要拦(而不是像直觉那样直接放行)
# ------------------------------------------------
# 直觉是「多一列无害」—— 对**看板上那个数**而言确实无害。但文件入库是**按模板
# 映射**的: 模板没声明的列**不会被写进事实表**。
#
# ⇒ 若放行, 新列的数据会被**静默丢弃**, 而且没有任何人收到提示:
#   * 治理面板不会提示「需要更新模板」(它不是阻断漂移);
#   * 文件已经被入库, 模板再更新也**不会回头重算**已入库的行。
#
# ⇒ 所以「多一列」必须先拦一道, 把「模板落后于源文件」这件事变成一个**待办**;
#   等运营更新模板(新版本把这列纳入)⇒ 契约晋升 ⇒ 文件重新按新模板解释 ⇒
#   **新列的数据这才真正落库**。
#
# 唯一的例外是**用户明确确认过不要的列**(`ignored_extra_fields`):
# 用户说「这列我知道了, 忽略它」⇒ 不阻断, 但它也不会落库(是用户的选择)。
#
# 风险是**有方向**的
# ----------------
# 平台加列是**单向**的 ⇒ 「文件比模板多」是常态、要跟进;
# 而「文件比模板少」是异常、要立刻处理。两条方向不能一样处理。
#
# 阻断条件(任一成立即阻断)
# ------------------------
# 1. ``format_drift_columns`` —— 列名没变但值的形态变了(这份文件入库必失败);
# 2. ``missing_required_keys`` —— 必填语义键解析不出来(算不出要的数字);
# 3. ``removed_fields`` 中**无法证明可选**的那些(见下);
# 4. ``added_fields`` 中**用户没有确认过**的那些(模板落后于源文件)。
#
# 少列的三种归宿
# --------------
# * 声明为可选(核心字段清单 ``required=false`` / 语义契约 optional / 兼容名单)
#   ⇒ **不阻断**;
# * 绑定到必填语义键、且该键**没被解析出来** ⇒ 阻断(已由 ``missing_required_keys`` 覆盖);
# * 绑定到必填语义键、但该键**被别名救回**(文件里还有同义列)
#   ⇒ **不阻断**(缺的是列名, 不是数据);
# * 根本没有语义绑定 ⇒ **阻断**(无法证明它可缺 ⇒ 保守处理)。
#
# 无语义契约的域
# --------------
# 该域没有契约 ⇒ L2 给不出任何语义事实 ⇒ 少列一律按「无法证明可选」处理(阻断),
# 多列仍然阻断。**保守方向永远是「拦下来让人看一眼」。**
#
# 历史包袱(已清理)
# ----------------
# 旧实现对 ``shopee/orders/monthly`` 单开了一个口子:「新增列不阻断」。
# 那是 2026-06-17 的救火补丁(提交 ``e1c7cfca``), 后果是
# **shopee 订单月报的新列会被静默丢弃** —— 与其它所有域不一致, 且丢数据。
# ⇒ 该例外已取消: 「新增列」的判定现在只有一条规则, 对所有域一致。
#

#: 漂移规则编号(便于守护测试与接口自省逐条引用)。
DRIFT_RULE_IDS = (
    "format_drift_blocks",
    "missing_required_key_blocks",
    "removed_unprovable_column_blocks",
    "added_column_blocks_until_template_catches_up",
    "confirmed_extra_column_never_blocks",
    "optional_column_never_blocks",
    "column_order_change_never_blocks",
    "no_contract_domain_conservative",
)

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
    confirmed_extra_fields: Iterable[str] = (),
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
        confirmed_extra_fields: 用户在「已确认的新列」清单里确认过的列
            ⇒ 这些列不再阻断(用户明说不要它们)。

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

    confirmed_set = {str(column) for column in confirmed_extra_fields if str(column)}

    alias_rescued = {
        str(column) for column in alias_rescued_removed_raw_fields if str(column)
    }

    blocking: List[str] = []
    non_blocking: List[str] = []

    # 规则 1: 值形态漂移 —— 这份文件入库必然整份失败。
    blocking.extend(format_columns)

    # 规则 2: 必填语义键解析不出来 —— 业务上算不出要的那几个数。
    blocking.extend(missing_required)

    # 规则 3: 少列 —— 能证明它可选就不阻断, 否则保守阻断。
    for column in removed:
        if column in optional_set:
            non_blocking.append(column)
        elif column in alias_rescued:
            # 绑定到必填语义键、但被别名救回 ⇒ 缺的是列名, 不是数据。
            non_blocking.append(column)
        else:
            # 其余两种: L2 明确判为「无法证明它可缺」, 或者 L2 **没有给出任何结论**
            # (例如该域没有语义契约)⇒ 一律保守阻断。
            blocking.append(column)

    # 规则 4: 多列 —— 默认阻断(模板落后于源文件 ⇒ 新列的数据会丢),
    # 用户已确认要忽略的列除外。
    for column in added:
        if column in confirmed_set:
            non_blocking.append(column)
        else:
            blocking.append(column)

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
        reason = f"有 {len(blocking)} 项阻断漂移"
    else:
        template_status = TEMPLATE_STATUS_ALIAS_ONLY
        if not has_semantic_contract and removed:
            reason = "该域没有语义契约, 少掉的列按保守口径处理"
        elif added:
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
