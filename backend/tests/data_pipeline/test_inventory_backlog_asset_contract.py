"""积压资产链的**结构契约**测试。

这三个契约都是踩过坑之后补上的，每一条都对应一次真实故障：

1. `mart.inventory_backlog_base` 删列 → 必须 DROP 重建 → DROP 会连带删掉下游 api 视图。
   只 DROP 本视图会被 PostgreSQL 拒绝（"cannot drop view ... because other objects
   depend on it"）→ bootstrap 整条链失败 → 资产指纹不更新 → 业务概览永久降级。
2. 采集后的 refresh pipeline 也重建基表 → 它只重建「列出来的」目标 →
   少列一个下游就少重建一个 → 采集跑完视图却 missing。
3. 库存增量窗口必须走**两个平铺的字符串键**：任务响应的 date_range 契约是
   Dict[str, str]，塞嵌套 dict 会让采集任务列表接口直接 500。
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]

BACKLOG_SQL = ROOT / "sql" / "mart" / "inventory_backlog_base.sql"
REGISTRY = ROOT / "backend" / "services" / "data_pipeline" / "refresh_registry.py"
BOOTSTRAP = ROOT / "backend" / "services" / "data_pipeline" / "dashboard_bootstrap.py"
CONTRACTS = ROOT / "backend" / "services" / "collection_contracts.py"

DOWNSTREAM_VIEWS = (
    "api.business_overview_inventory_backlog_module",
    "api.inventory_backlog_summary_module",
    "api.clearance_ranking_module",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _strip_comments(sql_text: str) -> str:
    return "\n".join(
        line for line in sql_text.splitlines() if not line.strip().startswith("--")
    )


def test_backlog_base_drops_its_downstream_views_before_itself():
    """删列重建基表前，必须先删依赖它的下游视图。"""
    code = _strip_comments(_read(BACKLOG_SQL))

    own_drop = code.index("DROP VIEW IF EXISTS mart.inventory_backlog_base;")
    for view in DOWNSTREAM_VIEWS:
        assert view in code, f"{view} 没被 DROP —— 基表重建会失败"
        assert (
            code.index(f"DROP VIEW IF EXISTS {view};") < own_drop
        ), f"{view} 必须在 DROP 基表**之前**删掉"


def test_refresh_pipeline_rebuilds_every_downstream_view():
    """采集后的 refresh pipeline 必须重建全部下游（少一个就少重建一个）。"""
    source = _read(REGISTRY)
    start = source.index("def _extra_targets_for_refresh_domain")
    block = source[
        start : source.index("def resolve_refresh_targets_for_source_table", start)
    ]
    for view in DOWNSTREAM_VIEWS + ("api.sku_clearance_ranking_module",):
        assert (
            view in block
        ), f"refresh pipeline 没带 {view} —— 采集后会把它删掉且不重建"


def test_backlog_asset_group_stays_in_one_module():
    """基表与它的全部下游必须**同属一个模块**。

    两条执行路径（bootstrap 与采集后刷新/安全网自愈）都只重建「自己计划里
    列出来的」目标 → 谁重建基表，谁就必须能重建它的全部下游。
    跨模块拆分 = 后跑的模块把先跑的模块的视图删掉且不重建。
    """
    from backend.services.data_pipeline.dashboard_bootstrap import (
        DASHBOARD_MODULE_TARGETS,
    )

    owners: dict[str, list[str]] = {}
    for module_name, module in DASHBOARD_MODULE_TARGETS.items():
        for target in module["core_targets"]:
            owners.setdefault(target, []).append(module_name)

    base_owners = owners.get("mart.inventory_backlog_base", [])
    assert len(base_owners) == 1, f"基表被多个模块持有：{base_owners}"
    owner = base_owners[0]

    for view in DOWNSTREAM_VIEWS + ("api.sku_clearance_ranking_module",):
        assert owners.get(view) == [
            owner
        ], f"{view} 必须与基表同属模块 {owner}，实际 {owners.get(view)}"


def test_incremental_range_keys_are_flat_strings():
    """增量窗口必须是两个平铺的字符串键，不能是嵌套 dict。"""
    from backend.services.collection_contracts import (
        INCREMENTAL_RANGE_END_KEY,
        INCREMENTAL_RANGE_START_KEY,
    )

    assert INCREMENTAL_RANGE_START_KEY != INCREMENTAL_RANGE_END_KEY
    assert INCREMENTAL_RANGE_START_KEY in _read(CONTRACTS)
    assert INCREMENTAL_RANGE_END_KEY in _read(CONTRACTS)


@pytest.mark.parametrize(
    "payload",
    [
        {"inventory_incremental_range": {"start": "x", "end": "y"}},
        {"inventory_incremental_range": {"start": "x", "end": "y", "gap_days": 0}},
    ],
)
def test_task_date_range_contract_rejects_nested_incremental_payload(payload):
    """任务响应的 date_range 契约是 Dict[str, str] —— 嵌套 dict 会让接口 500。"""
    from backend.schemas.collection import TaskResponse

    base = {
        "task_id": "t-1",
        "platform": "miaoshou",
        "status": "pending",
        "created_at": "2026-10-25T00:00:00",
    }
    with pytest.raises(Exception):
        TaskResponse(**base, date_range=payload)
