"""批次 F 护栏测试: 落库列收窄(``core_fields`` → 物理列)的口径护栏。

锁住五件事
----------

1. **建列口径 = 原始列名** —— 建列必须用清单里的 ``raw_name``(物理列名),
   不能用 ``semantic_key``(标准含义)。否则表里会多出一批 ``product_id``
   之类的英文列, 而原有的 ``商品编号`` 列还在 ⇒ **同一业务字段存两份**,
   正是批次 F 要消除的那个问题。
2. **只有清单里的列建物理列** —— ``ensure_columns_exist(core_columns=...)``
   只为核心字段建列; ``core_columns=None`` 时保持旧行为(可一键回退)。
3. **非核心列不再 UPDATE**(F-2) —— 非核心字段的完整内容留在
   ``raw_data`` JSONB 里, 不再往物理列写值。
4. **接线完整** —— ``core_columns`` 必须从入库主链路一路传到建列处,
   中间任何一段漏传都会让收窄静默失效。
5. **下游不依赖物理动态列** —— 这是 F 能安全上线的**前提**:
   ``sql/semantic/*.sql`` 里的 view 只选系统列 + ``raw_data``。
   一旦有人改成直查业务动态列, 收窄就会让语义层/看板取不到数 ⇒ 必须拦住。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Set

import pytest

from backend.services.core_fields_service import (
    CORE_FIELDS_COLUMNS_ENV_KEY,
    core_field_storage_column_names,
    core_fields_columns_enabled,
    normalize_core_fields,
)
from backend.services.dynamic_column_manager import DynamicColumnManager

REPO_ROOT = Path(__file__).resolve().parents[3]

#: 建物理列时, 系统列之外的业务列只进 ``raw_data`` JSONB。
#: 这里只列「系统列」白名单, 用来守护第 5 条。
SYSTEM_COLUMN_WHITELIST: Set[str] = {
    "id",
    "platform_code",
    "shop_id",
    "data_domain",
    "granularity",
    "sub_domain",
    "metric_date",
    "period_start_date",
    "period_end_date",
    "period_start_time",
    "period_end_time",
    "file_id",
    "template_id",
    "raw_data",
    "header_columns",
    "data_hash",
    "ingest_timestamp",
    "currency_code",
    "resolved_shop_account_id",
    "identity_candidate_count",
}


# ---------------------------------------------------------------------------
# 1) 建列口径 = 原始列名
# ---------------------------------------------------------------------------


def test_storage_column_names_use_raw_name_not_semantic_key():
    """建列用 ``raw_name``; 只有 ``semantic_key`` 的条目不参与建列。

    ``metric_date`` 这类条目的 ``raw_name`` 为空(它是系统字段, 表里本来就有列),
    语义键 ``product_id`` 也不等于文件里的物理列名 ⇒ 都建不了列。
    """
    core_fields = [
        {"semantic_key": "product_id", "raw_name": "商品编号", "required": False, "in_hash": True},
        {"semantic_key": "metric_date", "raw_name": None, "required": True, "in_hash": True},
        {"semantic_key": "sales_amount", "raw_name": "销售额", "required": False, "in_hash": True},
    ]

    assert core_field_storage_column_names(core_fields) == ["商品编号", "销售额"]


def test_storage_column_names_dedup_and_keep_order():
    core_fields = [
        {"semantic_key": None, "raw_name": "商品编号", "required": False, "in_hash": True},
        {"semantic_key": "product_id", "raw_name": "商品编号", "required": False, "in_hash": True},
        {"semantic_key": None, "raw_name": "仓库", "required": False, "in_hash": True},
    ]

    assert core_field_storage_column_names(core_fields) == ["商品编号", "仓库"]


def test_storage_column_names_accept_legacy_string_list():
    """旧形态(字符串数组)按物理列名处理。"""
    assert core_field_storage_column_names(["商品编号", "仓库"]) == ["商品编号", "仓库"]
    assert core_field_storage_column_names(None) == []
    assert core_field_storage_column_names([]) == []


# ---------------------------------------------------------------------------
# 2) 收窄开关
# ---------------------------------------------------------------------------


def test_columns_switch_defaults_to_on(monkeypatch):
    """落库列收窄默认**开启**。

    与批次 E 的 hash 开关相反: hash 开关默认关是因为「改 hash 口径 ⇒ 历史行
    被当成新行」是不可逆的数据污染; 而列收窄只影响**新写入**的行,
    历史数据仍在 ``raw_data`` 里, 且下游语义层只读系统列 + ``raw_data``。
    """
    monkeypatch.delenv(CORE_FIELDS_COLUMNS_ENV_KEY, raising=False)
    assert core_fields_columns_enabled() is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "OFF", "False"])
def test_columns_switch_can_be_turned_off(monkeypatch, value):
    """一键回退: 显式关掉就恢复旧行为(所有表头列都建)。"""
    monkeypatch.setenv(CORE_FIELDS_COLUMNS_ENV_KEY, value)
    assert core_fields_columns_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "ON"])
def test_columns_switch_can_be_turned_on(monkeypatch, value):
    monkeypatch.setenv(CORE_FIELDS_COLUMNS_ENV_KEY, value)
    assert core_fields_columns_enabled() is True


# ---------------------------------------------------------------------------
# 3) 建列行为
# ---------------------------------------------------------------------------


class _FakeDB:
    """只记录 DDL 的假 session(``ensure_columns_exist`` 只需要 execute/commit)。"""

    def __init__(self) -> None:
        self.statements: List[str] = []

    def execute(self, statement: Any) -> Any:
        self.statements.append(str(statement))
        return None

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


def _build_manager(monkeypatch, existing: Set[str]) -> DynamicColumnManager:
    db = _FakeDB()
    manager = DynamicColumnManager(db)  # type: ignore[arg-type]
    monkeypatch.setattr(manager, "get_existing_columns", lambda _table: set(existing))
    return manager


def _added_columns(db: _FakeDB) -> List[str]:
    columns: List[str] = []
    for statement in db.statements:
        match = re.search(r'ADD COLUMN IF NOT EXISTS "([^"]+)"', statement)
        if match:
            columns.append(match.group(1))
    return columns


def test_ensure_columns_exist_only_creates_core_columns(monkeypatch):
    """给了 ``core_columns`` ⇒ 只为核心字段建物理列。"""
    db = _FakeDB()
    manager = DynamicColumnManager(db)  # type: ignore[arg-type]
    monkeypatch.setattr(manager, "get_existing_columns", lambda _table: set())

    manager.ensure_columns_exist(
        table_name="fact_shopee_products_daily",
        header_columns=["商品编号", "商品", "销售额", "规格编号"],
        core_columns=["商品编号", "销售额"],
    )

    assert sorted(_added_columns(db)) == ["商品编号", "销售额"]


def test_ensure_columns_exist_keeps_legacy_behavior_without_core_columns(monkeypatch):
    """不传 ``core_columns`` ⇒ 旧行为(所有表头列都建列), 一键回退成立。"""
    db = _FakeDB()
    manager = DynamicColumnManager(db)  # type: ignore[arg-type]
    monkeypatch.setattr(manager, "get_existing_columns", lambda _table: set())

    manager.ensure_columns_exist(
        table_name="fact_shopee_products_daily",
        header_columns=["商品编号", "商品", "销售额", "规格编号"],
    )

    assert sorted(_added_columns(db)) == sorted(["商品编号", "商品", "销售额", "规格编号"])


def test_ensure_columns_exist_keeps_existing_legacy_columns(monkeypatch):
    """历史已建的列**保留**(规格 §6.2: 不物理删) ⇒ 存量数据仍可读。"""
    db = _FakeDB()
    manager = DynamicColumnManager(db)  # type: ignore[arg-type]
    monkeypatch.setattr(
        manager,
        "get_existing_columns",
        lambda _table: {"商品编号", "商品"},
    )

    manager.ensure_columns_exist(
        table_name="fact_shopee_products_daily",
        header_columns=["商品编号", "商品", "销售额"],
        core_columns=["商品编号", "销售额"],
    )

    # 「商品编号」已存在 ⇒ 不再 ADD;「商品」是历史遗留列 ⇒ 保留不动
    assert _added_columns(db) == ["销售额"]


def test_ensure_columns_exist_normalizes_both_sides(monkeypatch):
    """清单侧与表头侧都过一次归一化 ⇒ 能对上「清单带货币代码」的情况。"""
    db = _FakeDB()
    manager = DynamicColumnManager(db)  # type: ignore[arg-type]
    monkeypatch.setattr(manager, "get_existing_columns", lambda _table: set())

    manager.ensure_columns_exist(
        table_name="fact_shopee_products_daily",
        header_columns=["销售额", "商品编号"],
        core_columns=["销售额 (SGD)"],
    )

    assert _added_columns(db) == ["销售额"]


# ---------------------------------------------------------------------------
# 3b) 目标物理列必须落在历史主列上(实测踩过的坑)
# ---------------------------------------------------------------------------


def _manager_without_db() -> DynamicColumnManager:
    return DynamicColumnManager.__new__(DynamicColumnManager)  # type: ignore[arg-type]


def test_resolve_target_column_prefers_existing_raw_name_column():
    """核心列必须落在**历史主列**上, 不能新建重复列。

    实测(2026-11-07, ``b_class.fact_miaoshou_inventory_snapshot``):
    同一业务字段在表里同时存在 ``商品SKU``(原始口径) 与 ``商品``(剥货币口径)
    —— 这就是批次 F 要消除的「同一业务字段存两份」。

    清单写的是 ``*商品SKU``, 若按剥货币口径匹配会算成 ``商品`` ⇒
    核心列匹配不上 ⇒ 新建重复列、且真正的核心列不再更新。

    ⇒ 目标列解析必须**优先复用已有的原始口径列**。
    """
    manager = _manager_without_db()
    existing = {"商品SKU", "商品", "商品名称", "仓库", "销售额_已下订单"}

    assert manager.resolve_target_column("*商品SKU", existing) == "商品SKU"
    assert manager.resolve_target_column("*商品名称", existing) == "商品名称"
    # 剥货币口径的重复列不再被选中 ⇒ 它会自然停更(不删, 读兼容)
    assert manager.resolve_target_column("商品", existing) == "商品"
    # 带货币代码的表头 ⇒ 落在既有的剥货币口径列上
    assert (
        manager.resolve_target_column("销售额（已下订单） (SGD)", existing)
        == "销售额_已下订单"
    )


def test_resolve_target_column_new_table_uses_currency_stripped_name():
    """新表(没有任何已有列)⇒ 用剥货币口径新建。

    这与「动态列管理的历史行为」一致 —— 历史表里 ``商品`` 这一列就是
    动态列管理建出来的 ⇒ 同一套列名口径, 表结构同构。
    """
    manager = _manager_without_db()

    assert manager.resolve_target_column("*商品SKU", set()) == "商品"
    assert manager.resolve_target_column("销售额（已下订单） (SGD)", set()) == (
        "销售额_已下订单"
    )


def test_identifier_column_name_does_not_strip_currency_codes():
    """标识符口径**不剥货币代码** ⇒ ``SKU`` 不会被当成 ISO 代码。"""
    manager = _manager_without_db()

    assert manager.identifier_column_name("*商品SKU") == "商品SKU"
    assert manager.identifier_column_name("销售额（已下订单） (SGD)") == (
        "销售额_已下订单_SGD"
    )
    # 对照: 剥货币口径确实会把 SKU 当成 ISO 代码剥掉
    assert manager.normalize_column_name("*商品SKU") == "商品"


# ---------------------------------------------------------------------------
# 4) 接线完整 + 非核心列不再 UPDATE
# ---------------------------------------------------------------------------


def _read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def test_ingestion_passes_core_columns_down_to_importer():
    """入库主链路必须把 ``core_columns`` 传给 importer。"""
    source = _read("backend/services/data_ingestion_service.py")

    assert "core_columns=effective_core_columns" in source
    assert "core_field_storage_column_names" in source
    # 空清单 ⇒ 不收窄(避免空配置丢数据)
    assert "保持旧行为(不收窄建列)" in source


def test_importer_passes_core_columns_to_both_column_managers():
    """两个建列入口都要传 ``core_columns``。

    ``raw_data_importer`` 里有**两处**建列调用(主路径 + v4.14.0 备用路径),
    漏掉任何一处都会让收窄静默失效(备用路径会把所有表头列都建出来)。
    """
    source = _read("backend/services/raw_data_importer.py")

    assert source.count("core_columns=core_columns") >= 2


def test_importer_only_updates_core_columns():
    """F-2: 非核心列不再 UPDATE, 内容留在 ``raw_data`` JSONB。"""
    source = _read("backend/services/raw_data_importer.py")

    assert "批次 F-2: 非核心列不再 UPDATE" in source
    assert "core_column_set is not None" in source


def test_core_columns_reaches_sync_table_columns():
    source = _read("backend/services/platform_table_manager.py")
    assert "core_columns=core_columns" in source


# ---------------------------------------------------------------------------
# 5) 下游不依赖物理动态列(F 的上线前提)
# ---------------------------------------------------------------------------


def test_semantic_views_only_select_system_columns():
    """``sql/semantic/*.sql`` 的 view 只选系统列 + ``raw_data``。

    这是批次 F 能安全收窄的**前提**: 语义层 / mart / api 整条链路都从
    ``raw_data`` JSONB 取数, 不读业务动态列 ⇒ 收窄不会让看板取不到数。

    一旦有人改成直查 ``b_class.fact_*.商品编号`` 这类业务列, 本测试会红 ——
    那时必须先把下游改成走 ``raw_data``, 再收窄。
    """
    pattern = re.compile(
        r"SELECT\s+(?P<cols>[^;]+?)\s+FROM\s+b_class\.fact_",
        re.IGNORECASE | re.DOTALL,
    )
    offenders: List[str] = []
    for sql_path in sorted((REPO_ROOT / "sql" / "semantic").glob("*.sql")):
        text = sql_path.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            raw_cols = match.group("cols")
            for raw_col in raw_cols.split(","):
                col = raw_col.strip().strip('"')
                if not col:
                    continue
                if col.lower() not in SYSTEM_COLUMN_WHITELIST:
                    offenders.append(f"{sql_path.name}: {col}")

    assert not offenders, (
        "semantic view 开始引用业务动态列 ⇒ 落库列收窄会断链: " + "; ".join(offenders)
    )


def test_core_fields_normalization_keeps_raw_name():
    """清单规整后 ``raw_name`` 必须保留(它是建列与降级匹配的依据)。"""
    normalized = normalize_core_fields(
        [{"semantic_key": "product_id", "raw_name": "商品编号", "required": False, "in_hash": True}]
    )

    assert normalized[0]["raw_name"] == "商品编号"
    assert normalized[0]["semantic_key"] == "product_id"


def test_storage_column_names_ignore_duplicate_semantic_entries():
    """同一个语义键出现多次时, 建列口径仍然只保留物理列名一次。"""
    core_fields: List[Dict[str, Any]] = [
        {"semantic_key": None, "raw_name": "商品编号", "required": False, "in_hash": True},
        {"semantic_key": None, "raw_name": "商品编号", "required": True, "in_hash": False},
    ]

    assert core_field_storage_column_names(core_fields) == ["商品编号"]
