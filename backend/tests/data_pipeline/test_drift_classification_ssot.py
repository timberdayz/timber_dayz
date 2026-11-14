"""漂移判定口径的守护测试 (SSOT 收敛后的业务口径锁定)。

背景
----
2026-11-13 之前, 「什么算模板漂移」在系统里有**三份**定义:

1. ``template_matcher._classify_header_changes`` —— 自己把列差异分成
   blocking / non_blocking, 并对 ``shopee/orders/monthly`` 单开了一个口子;
2. ``semantic_field_contract_service.evaluate`` —— 又算了一套
   ``should_block`` / ``missing_required_keys``;
3. ``data_sync_status_semantics`` —— 只定义「状态叫什么」。

⇒ 同一事实三份定义 ⇒ 业务口径靠 ``if`` 打补丁, 且各域行为不一致。

现在收敛成 **L3 唯一入口** ``classify_drift``。本文件把业务口径逐条钉死,
防止再漂回去。

业务口径(一句话)
----------------
**多一列 ⇒ 阻断(直到模板把它纳入), 少了必填字段 ⇒ 阻断, 可选列/顺序变化 ⇒ 不阻断。**
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

STATUS_SEMANTICS = REPO_ROOT / "backend" / "services" / "data_sync_status_semantics.py"
TEMPLATE_MATCHER = REPO_ROOT / "backend" / "services" / "template_matcher.py"
STATUS_SERVICE = (
    REPO_ROOT / "backend" / "services" / "data_sync_template_status_service.py"
)
CONTRACT_SERVICE = (
    REPO_ROOT / "backend" / "services" / "semantic_field_contract_service.py"
)
RECHECK_SERVICE = REPO_ROOT / "backend" / "services" / "template_recheck_service.py"


# ======================================================================
# 1. SSOT 结构: 判定口径只有一份
# ======================================================================


def _defined_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.ClassDef):
            names.add(node.name)
    return names


def test_classify_drift_has_exactly_one_definition():
    """``classify_drift`` 只在 SSOT 模块里定义一次。"""
    definitions = []
    for path in (REPO_ROOT / "backend").rglob("*.py"):
        if "tests" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == "classify_drift":
                    definitions.append(path)
    assert definitions == [
        STATUS_SEMANTICS
    ], f"classify_drift 必须只有一个定义, 实际: {definitions}"


def test_matcher_no_longer_defines_its_own_drift_classifier():
    """匹配器不得再自带一份「什么算阻断」的定义。"""
    names = _defined_names(TEMPLATE_MATCHER)
    assert "_classify_header_changes" not in names, (
        "匹配器不得再自己把列差异分成 blocking/non_blocking —— "
        "判定权已上移到 L3(classify_drift)"
    )


def test_matcher_has_no_platform_specific_drift_special_case():
    """平台特判(shopee/orders/monthly)已被取消, 不得复活。

    历史: 2026-06-17 的救火补丁 ``e1c7cfca`` 给 ``shopee/orders/monthly``
    单开了「新增列不阻断」的口子 ⇒ 后果是**新列的数据被静默丢弃**
    (模板没声明的列不会写进事实表, 且已入库的行不会回头重算)。
    """
    source = TEMPLATE_MATCHER.read_text(encoding="utf-8")
    assert "ORDER_CORE_REQUIRED_FIELDS" not in source
    assert "ORDER_OPTIONAL_FIELDS" not in source
    assert '== "shopee"' not in source, "匹配器里不应再出现按平台分叉的漂移判定"


def test_status_service_consumes_l3_decision():
    """编排层必须消费 L3 的结论, 而不是自己拼状态树。"""
    source = STATUS_SERVICE.read_text(encoding="utf-8")
    assert "drift_decision" in source, "编排层应读取 header_changes['drift_decision']"
    assert "classify_drift" in source, "编排层应 import L3 的判定入口(兜底路径)"


# ======================================================================
# 2. 业务口径: 逐条钉死
# ======================================================================


def _classify(**kwargs):
    from backend.services.data_sync_status_semantics import classify_drift

    return classify_drift(**kwargs)


def test_added_column_never_blocks():
    """多一列 ⇒ **不阻断**(2026-11-14 口径回退, 对齐 11-07 规格 §1.4)。

    旧口径(2026-11-13 v7.26.0)曾断言「多一列 ⇒ 阻断」, 理由是
    「模板没声明的列不会写进事实表 ⇒ 放行等于静默丢数据」。
    **该前提在批次 E/F 之后已不成立**:
    非核心列的完整内容留在 ``raw_data`` JSONB 里(落库列收窄),
    下游语义视图也从 ``raw_data`` 取值 ⇒ **数据不丢**。

    ⇒ 2026-11-14 实测事故(TikTok 订单月报多一列)正是这条旧规则的代价:
    整个维度被卡住, 直到用户手动确认才放行。
    """
    decision = _classify(added_fields=["平台新增辅助字段"])

    assert decision.is_blocking is False
    assert decision.template_status == "alias_only"
    assert decision.governance_status == "non_breaking_drift"
    assert "平台新增辅助字段" in decision.non_blocking_changes


def test_added_column_never_blocks_even_without_core_fields():
    """多一列的结论**与清单是否配置无关** —— 它从来就不是需求问题。"""
    decision = _classify(
        added_fields=["平台新增辅助字段"],
        core_fields_configured=False,
    )

    assert decision.is_blocking is False
    assert decision.template_status == "alias_only"


def test_confirmed_extra_column_never_blocks():
    """用户确认过的新列 ⇒ 不阻断。

    2026-11-14 起它的作用**降级为「已阅标记」**(面板去噪),
    不再参与阻断判定 —— 但结论不变, 仍然不阻断。
    """
    decision = _classify(
        added_fields=["平台新增辅助字段"],
        confirmed_extra_fields=["平台新增辅助字段"],
    )

    assert decision.is_blocking is False
    assert decision.template_status == "alias_only"
    assert decision.governance_status == "non_breaking_drift"
    assert "平台新增辅助字段" in decision.non_blocking_changes


def test_missing_required_semantic_key_blocks():
    """必填语义键解析不出来 ⇒ 阻断(算不出要的业务数字)。"""
    decision = _classify(missing_required_keys=["order_id"])

    assert decision.is_blocking is True
    assert decision.template_status == "update_required"


def test_removed_column_outside_configured_core_fields_never_blocks():
    """少了一列, 但它**不在**核心字段清单里 ⇒ 不阻断(它不是需求)。"""
    decision = _classify(
        removed_fields=["订单号"],
        unmapped_removed_raw_fields=["订单号"],
        core_fields_configured=True,
    )

    assert decision.is_blocking is False
    assert decision.template_status == "alias_only"


def test_removed_column_blocks_when_core_fields_not_configured():
    """清单为空 ⇒ 该维度还没定义过「我要哪些数据」⇒ 阻断(配置缺口, B1)。

    这与「数据不满足需求」是**两回事**: 一个是配置没做, 一个是数据有问题。
    界面必须能区分 ⇒ 文案里要出现「核心字段清单」。
    """
    decision = _classify(
        removed_fields=["订单号"],
        unmapped_removed_raw_fields=["订单号"],
        core_fields_configured=False,
    )

    assert decision.is_blocking is True
    assert decision.template_status == "update_required"
    assert "核心字段清单" in decision.reason


def test_removed_required_core_field_blocks():
    """核心字段清单里 ``required=true`` 的列缺失 ⇒ **阻断**(需求没被满足)。

    规格 §3.1: 「漂移阻断 ← ``core_fields`` 中 ``required=true`` ∪ 域级契约 required」。
    这条是口径回退的**兜底**: 放宽了「少一列」, 但绝不能放宽「核心需求缺失」。
    """
    decision = _classify(
        removed_fields=["订单号"],
        required_core_fields=["订单号"],
        core_fields_configured=True,
    )

    assert decision.is_blocking is True
    assert decision.template_status == "update_required"


def test_removed_optional_core_field_never_blocks():
    """清单里 ``required=false`` 的列缺失 ⇒ 不阻断。"""
    decision = _classify(
        removed_fields=["预估回款金额"],
        optional_raw_fields=["预估回款金额"],
        required_core_fields=["订单号"],
        core_fields_configured=True,
    )

    assert decision.is_blocking is False
    assert decision.template_status == "alias_only"


def test_removed_required_column_blocks_even_with_configured_core_fields():
    """少的是**绑定必填语义键**的列 ⇒ 永远阻断(哪怕清单已配置)。

    业务上少一个订单号维度 ⇒ 算不出要的业务数字 ⇒ 不能放行。
    """
    decision = _classify(
        removed_fields=["订单号"],
        blocking_removed_raw_fields=["订单号"],
        core_fields_configured=True,
    )

    assert decision.is_blocking is True
    assert decision.template_status == "update_required"


def test_removed_optional_column_never_blocks():
    """少了一列**已证明可选** ⇒ 不阻断。"""
    decision = _classify(
        removed_fields=["预估回款金额"],
        optional_removed_raw_fields=["预估回款金额"],
    )

    assert decision.is_blocking is False
    assert decision.template_status == "alias_only"


def test_removed_column_rescued_by_alias_never_blocks():
    """少的是列名、不是数据(别名救回) ⇒ 不阻断。"""
    decision = _classify(
        removed_fields=["订单号"],
        alias_rescued_removed_raw_fields=["订单号"],
    )

    assert decision.is_blocking is False
    assert decision.template_status == "alias_only"


def test_unconfigured_dimension_blocks_on_removed_columns():
    """该维度还没定义核心字段清单 ⇒ 少列阻断(配置缺口)。

    2026-11-14 起归因从「没有语义契约」改成「没有核心字段清单」
    (业务拍板 B1): 判断依据是**用户有没有定义过需求**,
    而不是「系统有没有契约表」。

    「配置没做」必须与「配置做了但数据不满足」区分开, 否则会误放行。
    """
    decision = _classify(
        removed_fields=["退款金额"],
        has_semantic_contract=False,
        core_fields_configured=False,
    )

    assert decision.is_blocking is True
    assert decision.template_status == "update_required"
    assert "核心字段清单" in decision.reason


def test_column_order_change_never_blocks():
    """**列顺序变化** ⇒ 不阻断(入库映射按列名走, 不按位置走)。

    历史 bug: ``is_exact_match`` 要求顺序一致, 而阻断条件又要求
    ``non_blocking_changes`` 非空 ⇒ 纯换序时两边都落空 ⇒ 掉进「阻断漂移」,
    治理面板上显示「匹配率 100.0%」却报阻断漂移。
    """
    decision = _classify(
        added_fields=[],
        removed_fields=[],
        is_exact_match=False,
        is_semantic_match=False,
    )

    assert decision.is_blocking is False
    assert decision.template_status == "alias_only"
    assert decision.governance_status == "non_breaking_drift"


def test_format_drift_blocks():
    """列名没变但值的形态变了 ⇒ 阻断(这份文件入库必然整份失败)。"""
    decision = _classify(
        format_drift_columns=["下单时间"],
        is_exact_match=False,
    )

    assert decision.is_blocking is True
    assert decision.template_status == "format_drift"


def test_exact_match_is_ready():
    """完全一致 ⇒ 就绪。"""
    decision = _classify(is_exact_match=True)

    assert decision.is_blocking is False
    assert decision.template_status == "ready"
    assert decision.governance_status == "ready"


def test_semantic_match_is_alias_only():
    """语义等价(别名命中) ⇒ 非阻断漂移, 不阻断。"""
    decision = _classify(is_semantic_match=True)

    assert decision.is_blocking is False
    assert decision.template_status == "alias_only"


# ======================================================================
# 3. 发布即闭环: 重检服务是唯一实现
# ======================================================================


def test_recheck_service_exists_and_is_the_single_implementation():
    """定时巡检与「模板发布即重检」必须共用同一份重检逻辑。"""
    source = RECHECK_SERVICE.read_text(encoding="utf-8")
    assert "class TemplateRecheckService" in source
    assert "recheck_dimension" in source
    assert "apply_recheck" in source

    scheduled = (REPO_ROOT / "backend" / "tasks" / "scheduled_tasks.py").read_text(
        encoding="utf-8"
    )
    assert (
        "TemplateRecheckService" in scheduled
    ), "定时巡检必须调用共享的重检服务, 不允许再自带一份"


def test_apply_recheck_releases_file_and_moves_drift_snapshot_to_history():
    """重检通过 ⇒ 文件回到 pending, 漂移快照移入历史(待办销账)。"""
    from backend.services.template_recheck_service import TemplateRecheckService

    class _File:
        id = 42
        file_name = "tiktok_orders_monthly.xlsx"
        status = "template_update_required"
        error_message = "template update required before ingest"
        file_metadata = {
            "template_drift": {"reason": "新增1个字段", "template_version": 10},
        }

    record = _File()
    released = TemplateRecheckService.apply_recheck(
        record,
        {
            "should_auto_sync": True,
            "template_status": "ready",
            "governance_status": "ready",
        },
    )

    assert released is True
    assert record.status == "pending"
    assert record.error_message is None
    assert "template_drift" not in record.file_metadata
    auto_meta = record.file_metadata["auto_ingest"]
    assert auto_meta["last_status"] == "readiness_recovered"
    assert auto_meta["last_resolved_drift"]["reason"] == "新增1个字段"


def test_apply_recheck_keeps_blocked_file_and_refreshes_snapshot():
    """重检仍被阻塞 ⇒ 留在待办, 刷新漂移快照与阻塞轮次。"""
    from backend.services.template_recheck_service import TemplateRecheckService

    class _File:
        id = 43
        file_name = "tiktok_orders_monthly.xlsx"
        status = "template_update_required"
        error_message = None
        file_metadata = {}

    record = _File()
    released = TemplateRecheckService.apply_recheck(
        record,
        {
            "should_auto_sync": False,
            "template_status": "update_required",
            "update_reason": "新增1个字段",
        },
    )

    assert released is False
    assert record.status == "template_update_required"
    auto_meta = record.file_metadata["auto_ingest"]
    assert auto_meta["blocked_rounds"] == 1
    assert auto_meta["last_reason"] == "新增1个字段"


# ======================================================================
# 4. 治理接口: 文件级实时结论
# ======================================================================


def test_governance_coverage_row_exposes_file_level_live_verdict():
    """覆盖统计必须同时给出「组合级待办」与「文件级实时结论」。

    少了文件级结论, 前端只能按组合粒度判断 ⇒ 会出现
    「用户刚把这个文件改对, 界面却说它仍未通过治理复核」。

    [*] 2026-11-14 加强: 光断言字符串存在是不够的 ——
    过去文件级结论**只写在「已覆盖」行**, 而前端是在「需要更新」行里
    找这个文件的 ⇒ 拿到了 undefined ⇒ 保守当成「还对不上」⇒ 误报。
    ⇒ 这里必须校验它**真的出现在前端读取的那两个列表**里。
    """
    router = (
        REPO_ROOT / "backend" / "domains" / "data_platform" / "routers" / "data_sync.py"
    ).read_text(encoding="utf-8")

    assert "sample_update_required" in router
    assert "sample_template_status" in router
    assert "live_update_required" in router

    # 「需要更新」行也必须带文件级结论(前端在这里找样本文件)
    needs_update_block = router.split("needs_update_list.append(", 1)[1]
    needs_update_block = needs_update_block[
        : needs_update_block.find("\n            )")
    ]
    for field in (
        "sample_template_status",
        "sample_update_required",
        "sample_governance_status",
        "sample_update_reason",
    ):
        assert (
            f'"{field}"' in needs_update_block
        ), f"「需要更新」行缺少 {field} ⇒ 前端拿不到文件级结论 ⇒ 会误报"


def test_template_save_response_carries_recheck_summary():
    """保存模板的响应要带上重检结果, 前端据此给三态提示。"""
    router = (
        REPO_ROOT
        / "backend"
        / "domains"
        / "data_platform"
        / "routers"
        / "field_mapping_templates.py"
    ).read_text(encoding="utf-8")

    assert "_recheck_after_template_publish" in router
    assert 'save_result["recheck"]' in router


def test_semantic_contract_service_reports_removed_column_verdicts():
    """L2 必须把「少掉的列」分好类, 而不是只给一个笼统的 optional 清单。"""
    source = CONTRACT_SERVICE.read_text(encoding="utf-8")
    for attribute in (
        "optional_removed_raw_fields",
        "blocking_removed_raw_fields",
        "alias_rescued_removed_raw_fields",
        "unmapped_removed_raw_fields",
    ):
        assert attribute in source, f"L2 缺少 {attribute}"


# ---------------------------------------------------------------------------
# 紧急回退保险: 口径开关
# ---------------------------------------------------------------------------
def test_legacy_caliber_switch_reintroduces_added_column_blocking(monkeypatch):
    """``TEMPLATE_DRIFT_CALIBER=legacy`` ⇒ 多一列重新阻断。

    为什么要有这个开关
    ------------------
    2026-11-14 的口径回退是本次**唯一的业务口径变更**。万一上线后
    发现判断与预期不符, 运维需要一条**不改代码、不重新构建镜像**的
    回退路径: 改环境变量 + 重启容器。

    ⇒ 开关只挂在「多一列」这一条规则上, 其余规则两套口径完全一致。
    """
    from backend.services.data_sync_status_semantics import (
        DRIFT_CALIBER_ENV,
        classify_drift,
        legacy_caliber_enabled,
    )

    monkeypatch.delenv(DRIFT_CALIBER_ENV, raising=False)
    assert legacy_caliber_enabled() is False
    current = classify_drift(added_fields=["新列"])
    assert current.is_blocking is False
    assert current.non_blocking_changes == ["新列"]

    monkeypatch.setenv(DRIFT_CALIBER_ENV, "legacy")
    assert legacy_caliber_enabled() is True
    legacy = classify_drift(added_fields=["新列"])
    assert legacy.is_blocking is True
    assert legacy.blocking_changes == ["新列"]


def test_legacy_caliber_still_honors_confirmed_extra_fields(monkeypatch):
    """旧口径下, 用户确认过的新列**仍然**不阻断(旧行为不能丢)。"""
    from backend.services.data_sync_status_semantics import (
        DRIFT_CALIBER_ENV,
        classify_drift,
    )

    monkeypatch.setenv(DRIFT_CALIBER_ENV, "legacy")
    decision = classify_drift(
        added_fields=["新列"],
        confirmed_extra_fields=["新列"],
    )
    assert decision.is_blocking is False
    assert decision.blocking_changes == []


def test_legacy_caliber_does_not_change_core_field_blocking(monkeypatch):
    """开关**只**影响「多一列」; 核心字段缺失在两套口径下都阻断。"""
    from backend.services.data_sync_status_semantics import (
        DRIFT_CALIBER_ENV,
        classify_drift,
    )

    for value in ("", "legacy"):
        if value:
            monkeypatch.setenv(DRIFT_CALIBER_ENV, value)
        else:
            monkeypatch.delenv(DRIFT_CALIBER_ENV, raising=False)
        decision = classify_drift(
            removed_fields=["核心列"],
            required_core_fields=["核心列"],
            core_fields_configured=True,
        )
        assert (
            decision.is_blocking is True
        ), f"口径={value or 'current'} 时核心字段缺失未阻断"
        assert "核心列" in decision.blocking_changes
