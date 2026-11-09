#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""模板 Data Hash 口径体检（P3）的自测。

**体检脚本自己最怕变成一个永远绿的摆设** —— 所以这里覆盖三件事：

1. 「工作台提交口径」的计算是否与前端规则一致（剔除未确认列 / 派生列 / 不可参与 hash 的键，
   自动补齐域必需身份键）；
   ⚠️ 度量列**不在剔除名单**里：按规格 D1（见下）度量字段可以参与 hash，
   只是不推荐 + 带后果提示 ⇒ 这里断言的是「保留且被标记」，不是「被剔除」；
2. 前后端的**域必需身份键**是否一致（前端 ``DOMAIN_REQUIRED_IDENTITY_KEYS``
   与后端 ``required_identity_keys`` 漂移 ⇒ 工作台补的字段和闸门要的字段对不上）；
3. 报告与基线对比（增量检测）是否可靠。

**度量字段能不能进 hash（口径来源，别凭印象改）**
--------------------------------------------------
``docs/superpowers/plans/2026-11-07-semantic-core-field-spec.md`` §0 决策记录 **D1**
（2026-11-07 业务拍板）：指标类字段**能**参与 ``data_hash``，放开为自由勾选。
理由：业务概念是「日期 + 订单数 + 店铺 = 这一行是什么」的**复合业务键**，不是实体身份。

⇒ 度量字段**合法但不被推荐**（指标值变化会被当成新行，而不是更新），
所以：工作台**不剔除**它、闸门**不拦**它，只会**带提示**。

⚠️ 这两条口径是在「批次 E / 规格 D1」落地的（``a2dd3e93``），
本文件里度量相关的两条用例当时**没有跟着更新**，一直红到今天才被发现 ——
它们断言的还是 D1 之前的旧口径（「度量字段一律被剔除」）。

不依赖数据库。
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT_PATH = REPO_ROOT / "scripts" / "audit_template_hash_hygiene.py"
FRONTEND_DRAWER = (
    REPO_ROOT
    / "frontend"
    / "src"
    / "components"
    / "dataSync"
    / "TemplateUpdateWorkbenchDrawer.vue"
)


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


audit = _load_module("audit_template_hash_hygiene", AUDIT_PATH)

from backend.services.template_hash_policy import (
    TemplateHashPolicyService,
)  # noqa: E402
from backend.services.template_save_readiness_service import (  # noqa: E402
    TemplateSaveReadinessService,
)


def _binding(
    raw_name: str, semantic_key: str | None, status: str = "confirmed_semantic"
) -> dict:
    return {
        "raw_name": raw_name,
        "display_name": raw_name,
        "semantic_key": semantic_key,
        "semantic_role": None,
        "aliases": [],
        "required": False,
        "semantic_review_status": status,
        "semantic_review_source": "user",
    }


def _effective(
    *,
    domain: str = "products",
    granularity: str | None = "daily",
    sub_domain: str | None = None,
    fields=None,
    bindings=None,
    rules=None,
) -> list[str]:
    service = TemplateSaveReadinessService()
    return service.build_workbench_effective_deduplication_fields(
        data_domain=domain,
        granularity=granularity,
        sub_domain=sub_domain,
        deduplication_fields=fields if fields is not None else [],
        header_bindings=bindings if bindings is not None else [],
        field_parse_rules=rules if rules is not None else [],
    )


# ---------------------------------------------------------------------------
# 1. 工作台提交口径
# ---------------------------------------------------------------------------
def test_unconfirmed_raw_column_is_dropped():
    """没确认过的表头列不进 hash（与前端 normalizeDeduplicationSelection 一致）。"""
    result = _effective(
        fields=["商品编号"],
        bindings=[_binding("商品编号", "product_id", status="pending")],
    )
    assert "product_id" not in result
    assert "商品编号" not in result


def test_confirmed_raw_column_maps_to_semantic_key():
    result = _effective(
        fields=["商品编号"],
        bindings=[_binding("商品编号", "product_id")],
    )
    assert result == ["product_id"]


def test_metric_field_is_kept_but_flagged_as_not_recommended():
    """度量字段**不被工作台剔除**（规格 D1），但必须被标记成「不推荐 + 带后果提示」。

    为什么要盯这一条
    --------------
    前端 ``deduplicationSelection.js`` 的 ``isHashEligible`` **不自己判**，
    它直接读后端返回的 ``hash_options[].eligible`` 列表
    ⇒ 「度量字段到底会不会被前端剔除」这件事，**唯一的权威口径在后端策略层**。

    D1 之前后端对 ``kind == "metric"`` 硬性拒绝（eligible=False）⇒ 前端会剔除它。
    D1 之后放开成 eligible=True（但 recommended=False + warning）⇒ 前端保留它。

    所以这条用例锁的是**策略层判定**，不是某个实现的偶然行为。
    """
    service = TemplateSaveReadinessService()
    bindings = [
        _binding("商品编号", "product_id"),
        _binding("访客数", "visitor_count"),
    ]
    result = service.build_workbench_effective_deduplication_fields(
        data_domain="products",
        granularity="daily",
        deduplication_fields=["商品编号", "访客数"],
        header_bindings=bindings,
        field_parse_rules=[],
    )
    assert "product_id" in result
    assert "visitor_count" in result, "D1 之后度量字段应保留在工作台提交口径里"

    readiness = service.assess(
        data_domain="products",
        granularity="daily",
        sub_domain=None,
        deduplication_fields=result,
        header_columns=["商品编号", "访客数"],
        header_bindings=bindings,
        field_parse_rules=[],
    )
    option = next(
        item
        for item in readiness.hash_options
        if item["semantic_key"] == "visitor_count"
    )
    assert option["eligible"] is True, "前端按 eligible 列表判定 ⇒ 不该剔除度量字段"
    assert option["recommended"] is False, "允许 ≠ 推荐"
    assert option["warning"], "允许参与 hash 必须带上后果提示"


def test_metric_only_template_is_blocked_by_the_gate():
    """只剩度量字段时闸门仍然拦 —— 但拦截理由是「缺域必需身份键」，不是「度量不能进 hash」。

    D1 之后度量字段本身合法 ⇒ 唯一能拦它的理由是
    products daily 必须能定位到 ``product_id``（以及 ``metric_date``）。
    这条用例同时钉住两件事：

    1. 拦得住（``can_save is False``），且说清**缺的是什么**（点名 ``product_id``）；
    2. 度量字段**不是**拦截理由 —— 它只是「不推荐」的告警。
    """
    service = TemplateSaveReadinessService()
    effective = service.build_workbench_effective_deduplication_fields(
        data_domain="products",
        granularity="daily",
        deduplication_fields=["访客数"],
        header_bindings=[_binding("访客数", "visitor_count")],
        field_parse_rules=[],
    )
    assert effective == ["visitor_count"]
    readiness = service.assess(
        data_domain="products",
        granularity="daily",
        sub_domain=None,
        deduplication_fields=effective,
        header_columns=["访客数"],
        header_bindings=[_binding("访客数", "visitor_count")],
        field_parse_rules=[],
    )
    assert readiness.can_save is False
    assert any("product_id" in error for error in readiness.blocking_errors), (
        "拦截必须点名缺的是哪个身份键：" f"{readiness.blocking_errors}"
    )
    assert not any("visitor_count" in error for error in readiness.blocking_errors), (
        "度量字段按 D1 合法，不该出现在拦截理由里：" f"{readiness.blocking_errors}"
    )
    assert any(
        "指标" in warning for warning in readiness.warnings
    ), f"度量字段参与 hash 必须有后果提示：{readiness.warnings}"


def test_parse_rule_derived_field_is_dropped():
    """文件伴生日期派生出来的字段不作为去重字段提交。"""
    result = _effective(
        fields=["metric_date"],
        bindings=[],
        rules=[{"target_field": "metric_date", "source_column": "__file_date_from__"}],
    )
    assert result == []


def test_domain_identity_key_is_auto_added():
    """文件里认得出 product_id 时，工作台自动把它补进去重字段。"""
    result = _effective(
        domain="products",
        fields=[],
        bindings=[_binding("商品编号", "product_id")],
    )
    assert "product_id" in result


def test_services_shop_level_sub_domain_does_not_require_service_id():
    """店铺级服务报表不需要 service_id（业务已拍板）。"""
    service = TemplateSaveReadinessService()
    result = service.build_workbench_effective_deduplication_fields(
        data_domain="services",
        granularity="monthly",
        sub_domain="ai_assistant",
        deduplication_fields=[],
        header_bindings=[_binding("日期", "metric_date")],
        field_parse_rules=[],
    )
    assert "service_id" not in result


def test_unknown_field_is_kept_for_review():
    """找不到绑定的字段**保留**并汇报，避免静默丢弃用户的选择。"""
    result = _effective(fields=["未识别的列"], bindings=[])
    assert result == ["未识别的列"]


# ---------------------------------------------------------------------------
# 2. 前后端契约：域必需身份键必须一致
# ---------------------------------------------------------------------------
def _frontend_domain_required_identity_keys() -> dict[str, list[str]]:
    source = FRONTEND_DRAWER.read_text(encoding="utf-8")
    match = re.search(
        r"const\s+DOMAIN_REQUIRED_IDENTITY_KEYS\s*=\s*\{(.*?)\}",
        source,
        re.DOTALL,
    )
    assert match, "前端工作台里找不到 DOMAIN_REQUIRED_IDENTITY_KEYS"
    body = match.group(1)
    result: dict[str, list[str]] = {}
    for domain, values in re.findall(r"(\w+)\s*:\s*\[([^\]]*)\]", body):
        result[domain] = [
            item.strip().strip("'\"") for item in values.split(",") if item.strip()
        ]
    return result


def test_frontend_and_backend_required_identity_keys_match():
    """前端补的字段和后端闸门要的字段必须一致，否则工作台会补了也过不了闸门。"""
    frontend = _frontend_domain_required_identity_keys()
    policy = TemplateHashPolicyService()
    for domain, keys in frontend.items():
        assert policy.required_identity_keys(domain) == keys, (
            f"{domain} 域的前后端必需身份键不一致："
            f"前端 {keys}，后端 {policy.required_identity_keys(domain)}"
        )


def test_backend_required_identity_keys_cover_all_domains():
    policy = TemplateHashPolicyService()
    assert policy.required_identity_keys("products") == ["product_id"]
    assert policy.required_identity_keys("orders") == ["order_id"]
    assert policy.required_identity_keys("services") == ["service_id"]
    assert policy.required_identity_keys("services", "ai_assistant") == []
    assert policy.required_identity_keys("services", "agent") == []
    assert policy.required_identity_keys("analytics") == []


# ---------------------------------------------------------------------------
# 3. 报告与基线对比
# ---------------------------------------------------------------------------
def _result(template_id: int, issues: list[str]) -> dict:
    return {
        "template_id": template_id,
        "template_name": f"tpl_{template_id}",
        "data_domain": "products",
        "granularity": "daily",
        "sub_domain": None,
        "status": "published",
        "issues": issues,
        "details": {},
    }


def test_report_counts_and_blocking_split():
    results = [
        _result(1, [audit.ISSUE_NON_CANONICAL]),
        _result(2, [audit.ISSUE_NEEDS_MANUAL_MAPPING]),
        _result(3, []),
    ]
    report = audit.build_report(results)
    assert report["total_templates"] == 3
    assert len(report["templates"]) == 2
    assert report["summary"][audit.ISSUE_NON_CANONICAL] == 1
    assert report["blocking_template_ids"] == [2]
    assert report["by_status"]["published"]["total"] == 3
    assert report["by_status"]["published"]["blocking"] == 1


def test_baseline_comparison_reports_new_and_fixed(tmp_path: Path):
    baseline_report = audit.build_report(
        [
            _result(1, [audit.ISSUE_NON_CANONICAL]),
            _result(5, [audit.ISSUE_NEEDS_MANUAL_MAPPING]),
        ]
    )
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps(baseline_report, ensure_ascii=False), encoding="utf-8"
    )

    current = audit.build_report(
        [
            _result(1, [audit.ISSUE_NON_CANONICAL]),
            _result(7, [audit.ISSUE_METRIC_IN_IDENTITY]),
        ]
    )
    diff = audit.compare_with_baseline(current, str(baseline_path))
    assert diff["new_problem_template_ids"] == [7]
    assert diff["fixed_template_ids"] == [5]
    assert diff["new_blocking_template_ids"] == []
    assert diff["fixed_blocking_template_ids"] == [5]
