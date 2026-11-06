"""商品中心「阶段 0 · 稳定性修复」的后端契约测试。

对应上游设计稿
--------------
``docs/superpowers/specs/2026-11-06-product-center-caliber-naming-and-roi-design.md`` §5.4

覆盖的两条后端改动
------------------
B4  ``list_skus`` 接受 ``status`` 过滤参数
    停用 SKU 与在售 SKU 之前是混排的，工具栏又没有状态筛选器，运营只能靠翻页找。

B3  SPU 响应必须带 ``active``（软删标记）
    前端多处依赖它：``row.active === false`` 决定「恢复」按钮是否出现、「删除」按钮
    是否禁用、批量软删选中项过滤、整行灰显。字段不在响应里 ⇒ 这些判断恒为 false ⇒
    已软删的 SPU 看不出自己被删了，「恢复」按钮永远不出现 ⇒ 软删成了不可逆操作。

C2  利润版本的 ``cost_completeness`` 固定取 expected 段
    这一列的语义是「参考成本（预估口径）齐不齐」，取值域 complete/partial/incomplete。
    以前写的是 ``section.get("completeness", "complete")`` —— ``section`` 会随
    ``calculation_basis`` 在 expected / actual_recost 之间变，而 actual_recost 段的
    completeness 是另一套值域（incomplete/estimated/mixed/actual），于是：

    - estimated 版本恒写 "complete"（expected 段以前**根本没有** completeness 键，
      ``.get`` 永远取默认值）；
    - actual_recost 版本写 "estimated"/"mixed"/"actual" —— **违反 schema 的 pattern**，
      也把两种不相干的语义混进了同一列。
"""

from pathlib import Path

from backend.domains.business.routers import product_center as pc_module
from backend.schemas.product_center import ProfitEstimateCreateRequest


ROUTER_PATH = Path(pc_module.__file__).resolve()


def _router_source() -> str:
    return ROUTER_PATH.read_text(encoding="utf-8")


def test_list_skus_accepts_status_filter():
    """list_skus 必须支持按状态过滤。"""
    source = _router_source()
    at = source.index("async def list_skus(")
    signature = source[at : at + 700]
    assert "status" in signature, "list_skus 缺少 status 查询参数"
    assert "DimErpSku.status == status" in source, "list_skus 未按 status 过滤"


def test_cost_completeness_is_written_from_expected_section_only():
    """cost_completeness 必须固定取 expected 段，不能随 basis 变。"""
    import re

    source = _router_source()
    # 注意用词边界：`actual_recost_completeness=` 里也含有 "cost_completeness=" 子串
    match = re.search(r"(?<![a-z_])cost_completeness=(.*)", source)
    assert match, "找不到 cost_completeness 的赋值"
    line = match.group(0)
    assert 'preview["expected"].get("completeness"' in line, (
        "cost_completeness 必须固定取 expected 段，"
        f"否则 actual_recost 版本的 estimated/mixed/actual 会写进这一列；当前：{line.strip()}"
    )
    assert "section.get(" not in line, (
        f"cost_completeness 不能随 calculation_basis 变；当前：{line.strip()}"
    )


def test_spu_response_carries_active_flag():
    """SPU 响应必须带 active —— 否则前端判不出软删，「恢复」按钮永远不出现。"""
    from backend.schemas.product_center import ProductCenterItem
    from modules.core.db import DimSpu

    deleted = ProductCenterItem.model_validate(DimSpu(spu="SPU-DELETED", active=False))
    assert deleted.active is False, (
        "已软删的 SPU 必须能通过响应识别出 active=false，"
        "否则前端不灰显、也不显示「恢复」按钮 —— 软删就成了不可逆操作"
    )

    alive = ProductCenterItem.model_validate(DimSpu(spu="SPU-ALIVE", active=True))
    assert alive.active is True


def test_sku_response_active_stays_none():
    """SKU 没有 active 列（用 status），响应里 active 必须是 None 而不是报错。"""
    from backend.schemas.product_center import ProductCenterItem
    from modules.core.db import DimErpSku

    item = ProductCenterItem.model_validate(
        DimErpSku(sku_id=9101, sku_key="TEST-SKU-NO-ACTIVE", status="active")
    )
    assert item.active is None
    assert item.status == "active"


def test_profit_estimate_request_pattern_covers_reference_cost_domain():
    """请求契约里的 cost_completeness 取值域 = 参考成本口径（不含 actual 那套）。"""
    request = ProfitEstimateCreateRequest(
        sku_id=1,
        assumption_version="test",
        cost_completeness="complete",
    )
    assert request.cost_completeness == "complete"

    for invalid in ("estimated", "mixed", "actual"):
        try:
            ProfitEstimateCreateRequest(
                sku_id=1,
                assumption_version="test",
                cost_completeness=invalid,
            )
        except ValueError:
            continue
        raise AssertionError(
            f"cost_completeness 不应接受 {invalid!r} —— "
            "那是 actual_recost_completeness 的取值域，两列语义必须分开"
        )
