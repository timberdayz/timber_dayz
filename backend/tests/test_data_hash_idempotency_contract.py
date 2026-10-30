"""``data_hash`` 幂等性与跨模板口径一致的**端到端**契约测试。

为什么要有这个文件
------------------
前面的批次把「模板保存口径」「hash 策略闸门」都收紧了，但**入库层**一直
没有端到端证据：

* ``deduplication_service.calculate_data_hash`` 只有「规范语义键」走语义解析
  （:144），中文表头名走字面匹配；
* ``raw_data_importer`` 入库走 ``ON CONFLICT (platform_code,
  COALESCE(shop_id,''), data_domain, granularity, data_hash)``（:1093）；
* 事实表上的唯一索引 ``uq_<表>_hash`` 早就建好。

⇒ **``data_hash`` 不是"一个可选指纹"，它是数据库唯一约束的输入。**
去重字段写法不统一 ⇒ 同一笔业务算出不同 hash ⇒ 唯一约束撞不上 ⇒ 同一业务
被插入多行。所以「模板口径统一」不是洁癖，它是唯一约束能否真正兜住重复的
前提。

本文件用**真实入库器**（``RawDataImporter``）在隔离库里证明：

1. **幂等**：同一份数据、同一套去重字段，连续导入两次 ⇒ 第二次被唯一约束
   命中，行数不增。
2. **跨源文件口径一致**：同一笔业务，源文件表头写法不同（``订单号`` /
   ``订单编号``），但模板都已归一成语义键 ⇒ 算出**同一个** ``data_hash``
   ⇒ 落到事实表是**同一行**。
3. **归一后的模板是稳定态**：体检脚本判定「无需改写」。

⚠️ 护栏：``backend/tests/conftest.py`` 把 ``DATABASE_URL`` 重定向到一次性
PostgreSQL 容器，本文件只在该隔离库读写，**绝不触碰真实业务库**。
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

import pytest
from sqlalchemy import text

from backend.models.database import SessionLocal
from backend.services.deduplication_service import DeduplicationService
from backend.services.raw_data_importer import RawDataImporter

# 用一个独立的 platform_code，让目标表只属于本文件，避免和别的测试抢表。
TEST_PLATFORM = "idemprobe"
TABLE_NAME = f"fact_{TEST_PLATFORM}_orders_daily"

# 入库时的范围层：系统自动加进 hash，模板不许碰。
SCOPE_VALUES: Dict[str, Any] = {
    "platform_code": TEST_PLATFORM,
    "shop_id": "probe-shop",
    "data_domain": "orders",
    "granularity": "daily",
    "sub_domain": None,
}

# 同一笔业务，两个源文件用不同的表头写法（这是历史上最常见的分裂来源）。
# ``日期`` 列是入库必需的业务日期（不进 hash：没有解析规则时它不参与）。
SOURCE_WITH_订单号: List[Dict[str, Any]] = [
    {
        "订单号": "2605248C2CPGWD",
        "产品ID": "28228309476",
        "销售数量": 2,
        "日期": "2026-10-01",
    }
]
SOURCE_WITH_订单编号: List[Dict[str, Any]] = [
    {
        "订单编号": "2605248C2CPGWD",
        "产品ID": "28228309476",
        "销售数量": 2,
        "日期": "2026-10-01",
    }
]

COLUMNS_WITH_订单号 = ["订单号", "产品ID", "销售数量", "日期"]
COLUMNS_WITH_订单编号 = ["订单编号", "产品ID", "销售数量", "日期"]

# 归一后的模板：去重字段只写语义键。
NORMALIZED_DEDUP_FIELDS = ["order_id", "product_id"]


def _script():
    """加载 ``scripts/normalize_template_deduplication_fields.py``（纯函数部分）。"""
    script_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "normalize_template_deduplication_fields.py"
    )
    spec = importlib.util.spec_from_file_location(
        "normalize_template_deduplication_fields_script", script_path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _hashes(rows: List[Dict[str, Any]], dedup_fields: List[str]) -> List[str]:
    service = DeduplicationService(db=None)
    return service.batch_calculate_data_hash(
        rows,
        deduplication_fields=dedup_fields,
        header_bindings=None,
        scope_values=SCOPE_VALUES,
    )


def _import(rows: List[Dict[str, Any]], data_hashes: List[str], header_columns: List[str]):
    """用**真实入库器**把一批行写进隔离库的目标表。"""
    session = SessionLocal()
    try:
        importer = RawDataImporter(session)
        importer.file_date_from = date(2026, 10, 1)
        importer.file_date_to = date(2026, 10, 1)
        stats = importer.batch_insert_raw_data(
            rows=rows,
            data_hashes=data_hashes,
            data_domain="orders",
            granularity="daily",
            platform_code=TEST_PLATFORM,
            shop_id=SCOPE_VALUES["shop_id"],
            file_id=None,
            header_columns=list(header_columns),
            currency_codes=[None] * len(rows),
            sub_domain=None,
            original_header_columns=list(header_columns),
            template_id=None,
        )
        session.commit()
        return stats
    finally:
        session.close()


def _row_count() -> int:
    session = SessionLocal()
    try:
        return session.execute(text(f'SELECT count(*) FROM b_class."{TABLE_NAME}"')).scalar()
    finally:
        session.close()


def _hashes_in_table() -> List[str]:
    session = SessionLocal()
    try:
        rows = session.execute(
            text(f'SELECT data_hash FROM b_class."{TABLE_NAME}" ORDER BY data_hash')
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        session.close()


@pytest.fixture()
def clean_target_table():
    """每个用例前后都清掉目标表，保证用例之间互不影响。"""
    session = SessionLocal()
    try:
        session.execute(text(f'DROP TABLE IF EXISTS b_class."{TABLE_NAME}"'))
        session.commit()
    finally:
        session.close()
    yield
    session = SessionLocal()
    try:
        session.execute(text(f'DROP TABLE IF EXISTS b_class."{TABLE_NAME}"'))
        session.commit()
    finally:
        session.close()


def test_same_data_imported_twice_stays_single_row(clean_target_table):
    """幂等：同一份数据导两次，第二次必须被唯一约束命中，行数不增。"""
    rows = SOURCE_WITH_订单号
    hashes = _hashes(rows, NORMALIZED_DEDUP_FIELDS)

    first = _import(rows, hashes, COLUMNS_WITH_订单号)
    assert first["inserted"] == 1
    assert first["updated"] == 0
    assert first["total"] == 1
    assert _row_count() == 1

    second = _import(rows, hashes, COLUMNS_WITH_订单号)
    assert second["inserted"] == 0, "第二次导入不应新增行"
    assert second["updated"] == 1, "第二次导入应走 ON CONFLICT DO UPDATE"
    assert _row_count() == 1, "重复导入后行数必须保持不变"
    assert _hashes_in_table() == hashes


def test_different_source_headers_merge_into_one_row(clean_target_table):
    """跨源文件口径一致：表头写法不同，但模板已归一 ⇒ 同一笔业务只落一行。"""
    hash_a = _hashes(SOURCE_WITH_订单号, NORMALIZED_DEDUP_FIELDS)
    hash_b = _hashes(SOURCE_WITH_订单编号, NORMALIZED_DEDUP_FIELDS)

    assert hash_a == hash_b, (
        "模板去重字段已统一为语义键时，'订单号' 与 '订单编号' 两种表头写法"
        "必须算出同一个 data_hash，否则同一笔业务会被写成两行"
    )

    _import(SOURCE_WITH_订单号, hash_a, COLUMNS_WITH_订单号)
    _import(SOURCE_WITH_订单编号, hash_b, COLUMNS_WITH_订单编号)

    assert _row_count() == 1, "同一笔业务必须合并成一行"
    assert _hashes_in_table() == hash_a


def test_unnormalized_template_would_split_the_same_business(clean_target_table):
    """特征化测试：量化「模板没归一」的代价。

    这里断言的是**当前的坏行为**（未归一 ⇒ 同一笔业务两行），目的有两个：

    1. 把「为什么要归一」变成可执行的数字，而不是口头结论；
    2. 如果将来有人把 hash 算法改成按语义归一，这个用例会**失败并提醒**
       ——那时它就该被重写成「两者相同」的正向断言。
    """
    hash_normalized = _hashes(SOURCE_WITH_订单号, NORMALIZED_DEDUP_FIELDS)
    hash_legacy = _hashes(SOURCE_WITH_订单号, ["订单号", "产品ID"])

    assert hash_normalized != hash_legacy, (
        "中文表头名与语义键算出不同 hash —— 这正是历史模板必须归一的原因；"
        "若此断言失效，说明 hash 算法已改为按语义归一，本用例需重写"
    )

    _import(SOURCE_WITH_订单号, hash_normalized, COLUMNS_WITH_订单号)
    _import(SOURCE_WITH_订单号, hash_legacy, COLUMNS_WITH_订单号)

    assert _row_count() == 2, (
        "未归一的模板与已归一的模板写入同一张表时，同一笔业务会变成两行；"
        "这正是唯一约束被架空的表现"
    )


def test_normalized_template_is_stable_under_health_check():
    """归一后的模板是稳定态：体检脚本判定「无需改写」。"""
    script = _script()
    plan = script.plan_template_field_mapping(
        template_id=9001,
        template_name="probe_normalized",
        data_domain="orders",
        granularity="daily",
        status="published",
        deduplication_fields=NORMALIZED_DEDUP_FIELDS,
        header_bindings=[
            {
                "raw_name": "订单号",
                "semantic_key": "order_id",
                "semantic_review_status": "confirmed_semantic",
            },
            {
                "raw_name": "产品ID",
                "semantic_key": "product_id",
                "semantic_review_status": "confirmed_semantic",
            },
        ],
        header_columns=["订单号", "产品ID", "销售数量"],
        field_parse_rules=[],
    )

    assert plan.needs_change is False
    assert plan.planned_fields == NORMALIZED_DEDUP_FIELDS
    assert plan.skipped_reason and "无需改写" in plan.skipped_reason
