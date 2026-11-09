"""SSOT 守护测试：仓码归一与采集方标识**各只有一个真相点**。

背景
----
本轮改造（2026-11）把两个长期复制粘贴的口径收敛成单点：

1. **仓名 → 规范仓码**
   真相点 = ``core.dim_warehouse_name_aliases``（登记载体）
          + ``semantic.resolve_warehouse_code``（唯一归一实现）
   以前只有 Python 侧（状态层刷新服务）查表归一，语义层 / 快照族 / Metabase 模型
   各自从 ``raw_data`` 取「仓库编码」三个键 —— 妙手导出里**根本没有**这三个键
   ⇒ 语义层 4,111 行仓码**全为 NULL**，云端库存拿不到任何仓维度。

2. **采集方代号 → 必须排除，不算店铺身份**
   真相点 = ``modules/core/fact_identity_columns.py::COLLECTION_SOURCE_IDS``（唯一定义处）
          + ``core.collection_source_identifiers``（登记载体）
          + 候选池构建时的排除（``semantic.shop_identity_resolution_candidates``）
   以前这条规则写在**每条链路各自的 SQL** 里（orders 一份字面量、inventory 干脆没有）
   ⇒ 库存的 4,111 行全部挂在伪店 ``xihong`` 上。

这些断言是**口径守护**：任何一处退回「各写一份」，测试必须红。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from backend.services.data_pipeline.refresh_registry import (
    ASSET_PREREQUISITES,
    LOGICAL_TARGET_OBJECTS,
    PIPELINE_DEPENDENCIES,
    SQL_TARGET_PATHS,
)
from modules.core.fact_identity_columns import COLLECTION_SOURCE_IDS


REPO_ROOT = Path(__file__).resolve().parents[2]

WAREHOUSE_RESOLVER_TARGET = "semantic.warehouse_resolver"
WAREHOUSE_RESOLVER_FUNCTION = "semantic.resolve_warehouse_code"
WAREHOUSE_ALIAS_TABLE = "core.dim_warehouse_name_aliases"
COLLECTION_ID_TABLE = "core.collection_source_identifiers"
COLLECTION_ID_FILTER_TARGET = "semantic.collection_source_filter"
COLLECTION_ID_FILTER_FUNCTION = "semantic.is_collection_source_identifier"

MIGRATION_PATH = (
    REPO_ROOT
    / "current_migrations"
    / "versions"
    / "20261223_collection_source_identifiers.py"
)


def _read_asset(target: str) -> str:
    return (REPO_ROOT / SQL_TARGET_PATHS[target]).read_text(encoding="utf-8")


def _read_repo_file(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def _load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "migration_20261223_collection_source_identifiers", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# A 组：仓码归一 —— 唯一真相点
# ---------------------------------------------------------------------------


def test_warehouse_resolver_is_a_registered_refresh_target() -> None:
    """仓码归一函数必须登记为刷新目标，否则 bootstrap 不会建它。"""
    assert WAREHOUSE_RESOLVER_TARGET in SQL_TARGET_PATHS
    assert (
        LOGICAL_TARGET_OBJECTS[WAREHOUSE_RESOLVER_TARGET] == WAREHOUSE_RESOLVER_FUNCTION
    )
    # 函数不是关系（pg_class 里没有）⇒ 必须登记逻辑对象名，否则存在性核对误报 missing
    assert "semantic.resolve_warehouse_code" in LOGICAL_TARGET_OBJECTS.values()


def test_inventory_chain_depends_on_warehouse_resolver() -> None:
    """库存原子层的正文调用该函数 ⇒ 它必须排在前面，且是建对象前置。"""
    assert (
        WAREHOUSE_RESOLVER_TARGET
        in PIPELINE_DEPENDENCIES["semantic.fact_inventory_snapshot"]
    )
    assert (
        WAREHOUSE_RESOLVER_TARGET
        in ASSET_PREREQUISITES["semantic.fact_inventory_snapshot"]
    )


def test_warehouse_resolver_asset_uses_the_alias_table_as_truth() -> None:
    """归一函数必须查别名表（而不是硬编码映射字面量）。"""
    body = _read_asset(WAREHOUSE_RESOLVER_TARGET)
    assert WAREHOUSE_ALIAS_TABLE in body
    assert "core.dim_warehouse_name_aliases" in body
    # 查不到就留空 —— 绝不静默归到一个仓
    assert "RETURN NULL" in body


def test_semantic_inventory_resolves_warehouse_code() -> None:
    """语义层库存快照必须走归一函数补出仓码。"""
    body = _read_asset("semantic.fact_inventory_snapshot")
    assert f"{WAREHOUSE_RESOLVER_FUNCTION}(" in body


def test_python_resolver_shares_the_sql_implementation() -> None:
    """Python 侧归一器必须调用同一个 SQL 函数，不得再自己查表拼字典。

    两处各写一份归一逻辑 = SSOT 违规（改一边另一边不生效）。
    """
    body = _read_repo_file(
        "backend/services/inventory/inventory_state_warehouse_map_service.py"
    )
    assert f"{WAREHOUSE_RESOLVER_FUNCTION}(" in body, (
        "Python 侧归一器没有调用 semantic.resolve_warehouse_code —— "
        "仓码归一出现第二份实现"
    )
    # 不得再直接 select 别名表的两列自己建映射
    assert "DimWarehouseNameAlias.warehouse_code" not in body


def test_mart_inventory_state_bootstrap_declares_warehouse_code() -> None:
    """bootstrap SQL 必须含 warehouse_code 列。

    该列是迁移 ``current_schema_20261205_warehouse_name_aliases`` 加的，
    而那份 bootstrap 资产当时没同步 ⇒ 用 SQL 建表的新环境会**缺这一列**，
    状态层刷新服务写不进去。这里守住「SQL 资产 == 迁移结果」。
    """
    body = _read_repo_file("sql/mart/inventory_state.sql")
    assert "warehouse_code VARCHAR(128)" in body
    assert "ix_inventory_state_warehouse_code" in body


def test_backlog_base_carries_state_warehouse_code() -> None:
    """滞销基表必须把状态层已归一的仓码带出来（此前整条链拿不到仓）。"""
    body = _read_repo_file("sql/mart/inventory_backlog_base.sql")
    assert "s.warehouse_code" in body, "滞销基表没有取状态层的 warehouse_code"


# ---------------------------------------------------------------------------
# B 组：采集方标识 —— 唯一真相点
# ---------------------------------------------------------------------------


def test_collection_source_identifier_migration_exists() -> None:
    """登记载体的迁移必须在，且挂在当前迁移链的头上。"""
    assert MIGRATION_PATH.exists()
    module = _load_migration_module()
    assert module.revision == "current_schema_20261223_collection_source_identifiers"
    assert module.down_revision == (
        "current_schema_20261222_cloud_sync_receive_log_identity_rows"
    )


def test_migration_seed_matches_python_truth() -> None:
    """迁移播种的清单必须与 Python 权威定义**逐条一致**。

    两处是「一份定义 + 一份派生」：Python 常量是真相点，迁移负责把它落到库里。
    改了一侧忘了另一侧 ⇒ 守护测试变红。
    """
    module = _load_migration_module()
    seeded = {identifier for identifier, _description in module._SEED_IDENTIFIERS}
    assert seeded == set(COLLECTION_SOURCE_IDS)


def test_collection_source_filter_is_defined_inside_candidate_pool_asset() -> None:
    """采集方代号判定函数必须**内联在候选池正本资产的开头**。

    为什么不能是独立资产：候选池正本资产会被迁移
    ``current_schema_20261112_realign_identity_candidates_anchor`` **直接执行**。
    独立资产不在迁移链上 ⇒ 全新库跑迁移链时函数还不存在 ⇒ 建视图报
    "function does not exist"。内联 ⇒ 谁执行正本, 函数先落地。
    """
    body = _read_asset("semantic.shop_identity_resolution_candidates")
    assert f"CREATE OR REPLACE FUNCTION {COLLECTION_ID_FILTER_FUNCTION}" in body
    # 函数定义必须在视图定义**之前**
    assert body.index(f"CREATE OR REPLACE FUNCTION {COLLECTION_ID_FILTER_FUNCTION}") < (
        body.index(
            "CREATE OR REPLACE VIEW semantic.shop_identity_resolution_candidates"
        )
    )


def test_collection_source_filter_degrades_when_table_missing() -> None:
    """登记载体表不存在时，判定函数必须**返回 FALSE**而不是让建视图失败。

    没有这条降级，候选池视图就硬依赖迁移 —— 老库 / 半迁移库 / 只建表的全新库
    建视图会直接失败（测试环境与全新库都会踩到）。
    """
    body = _read_asset("semantic.shop_identity_resolution_candidates")
    assert "to_regclass('core.collection_source_identifiers')" in body
    assert "RETURN FALSE" in body


def test_candidate_pool_excludes_collection_source_ids() -> None:
    """候选池**正本**必须剔除采集方代号。

    这是「采集方代号不算身份」规则的**唯一执行点** —— 链路侧不再各写一份。

    ⚠️ 物化副本（``..._v2_mv``）**刻意不写**这条排除：
    1. 副本的「只收在营经营店」已经**天然**挡住采集方代号（采集方账号的
       business_role 是 collection_source, 不在候选池里）⇒ 内容与正本一致；
    2. 物化视图的**定义变更**需要 ``DROP ... CASCADE``（下游挂着 4 个原子层
       与 4 个 api 模块）⇒ 代价与收益不成比例。
    所以这里只断言正本，副本的一致性由迁移 20261105 的**内容指纹**守护。
    """
    body = _read_asset("semantic.shop_identity_resolution_candidates")
    assert f"{COLLECTION_ID_FILTER_FUNCTION}(" in body, "候选池正本没有剔除采集方代号"


def test_orders_chain_no_longer_carries_local_exclusion_literal() -> None:
    """orders 链路的本地字面量排除必须删掉（收敛到候选池）。"""
    body = _read_asset("semantic.fact_orders_atomic")
    assert (
        "'xihong', 'unknown', 'none'" not in body
    ), "orders 链路又抄了一份采集方代号黑名单 —— 排除规则应该只有候选池一处"


def test_inventory_chain_marks_collection_source_as_unresolved() -> None:
    """库存链路的原始店铺键必须把采集方代号如实表达成「未归属」。"""
    body = _read_asset("semantic.fact_inventory_snapshot")
    assert f"{COLLECTION_ID_FILTER_FUNCTION}(" in body, (
        "库存链路没有用登记载体剔除采集方代号 —— " "4,111 行会继续挂在伪店 'xihong' 上"
    )


def test_python_truth_points_at_the_registry_table() -> None:
    """Python 权威定义必须指明登记载体（否则两边各说各话）。"""
    body = _read_repo_file("modules/core/fact_identity_columns.py")
    assert COLLECTION_ID_TABLE in body


# ---------------------------------------------------------------------------
# C 组：业务事实不许被静默改动
# ---------------------------------------------------------------------------


def test_fact_table_shop_id_column_is_not_rewritten() -> None:
    """语义层不得改写 b_class 事实表的列 shop_id（它参与 upsert 冲突键）。

    改了会插重复行（v7.12.6 踩过）⇒ 这里守住「事实表的列不动」。
    """
    body = _read_asset("semantic.fact_inventory_snapshot")
    assert "UPDATE b_class." not in body.upper()
    assert "ALTER TABLE b_class." not in body.upper()


@pytest.mark.parametrize(
    "table",
    [
        "semantic.fact_inventory_snapshot",
        "semantic.fact_orders_atomic",
    ],
)
def test_chain_keeps_source_key_column(table: str) -> None:
    """每条链路必须保留原始键列（去重分区口径不变）。"""
    assert "source_shop_id" in _read_asset(table)
