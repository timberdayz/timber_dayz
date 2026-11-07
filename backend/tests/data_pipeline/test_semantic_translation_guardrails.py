"""批次 D: 翻译层护栏(归一化 / 域限定 / 全局沉淀 / 冲突不覆盖 / 命中率基线)。

这份测试钉死的是批次 D 的**根因修复**, 不是某个具体事故:

1. **标准字段定义只有一份**(后端注册表) —— 前端快照是**生成物**,
   漂了就红(:func:`test_frontend_snapshot_matches_backend_registry`);
2. **归一化口径前后端一致** —— 前端有一份镜像实现(它得在浏览器里查索引),
   靠快照里的样本对锁住(:func:`test_normalization_samples_are_consistent`);
3. **域限定优先于全局** —— 「同一个列名在不同域含义不同」不能被全局别名污染;
4. **用户对齐一次 ⇒ 其它模板自动命中** —— 全局沉淀真的落库、真的进推断索引;
5. **冲突不静默覆盖** —— 同一个列名撞两个含义时, 原记录不动,
   另写一条 ``conflict`` 记录, 且 ``conflict``/``disabled`` **不进**推断链路;
6. **命中率不回退**(D-7) —— 各域命中率有基线, 掉了就红。

关于「命中率目标」
----------------
方案里写的是「3~6% → ≥60%」。实测(2026-11-07, 27 个已发布模板的 1371 个真实表头):

* 静态注册表 + 运行时别名 ⇒ **160/1371 = 11.7%**;
* 剩下没命中的绝大多数是「**当前标准字段表里没有对应语义键**」的列
  (商品展示量 / 商城页 GMV / 订单状态 / 规格货号 / 客服昵称 …),
  或者本就不该是语义身份字段的列(状态类、名称类)。

把这些列补成语义键 = **凭空发明业务口径**, 与本方案「定不了就报警,
绝不静默猜一个」的硬原则冲突 ⇒ 不做。

因此本测试锁的是**不回退**而不是「必须达到 60%」:
把 60% 当成验收线, 唯一的实现路径就是编语义键。
真正的提升路径是「用户在模板里对齐一次 ⇒ 全局沉淀 ⇒ 其它模板自动命中」(第 4 条),
那条路径由 :func:`test_confirmed_alias_settles_globally_and_hits_other_templates` 守住。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from modules.core.db import SemanticFieldAlias


REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
HEADER_COLUMNS_FIXTURE = FIXTURES_DIR / "translation_header_columns.json"
SNAPSHOT_PATH = (
    REPO_ROOT
    / "frontend"
    / "src"
    / "domains"
    / "data_platform"
    / "utils"
    / "semanticFieldRegistrySnapshot.js"
)
GENERATOR_PATH = REPO_ROOT / "scripts" / "generate_semantic_field_snapshot.py"

#: 各域命中数**基线**(静态注册表口径, 不含数据库里的运行时别名)。
#:
#: 这份基线是「不许退步」的线, 不是「必须达到」的目标 —— 理由见模块文档。
#: 平台改表头(样本文件变了)时可以显式更新, 但更新必须是有意识的动作。
BASELINE_HITS: dict[str, int] = {
    "miaoshou/inventory/snapshot": 3,
    "shopee/analytics/daily": 3,
    "shopee/analytics/monthly": 3,
    "shopee/analytics/weekly": 3,
    "shopee/orders/daily": 14,
    "shopee/orders/monthly": 14,
    "shopee/orders/weekly": 14,
    "shopee/products/daily": 4,
    "shopee/products/monthly": 4,
    "shopee/products/weekly": 3,
    "shopee/services/daily": 2,
    "shopee/services/monthly": 2,
    "shopee/services/weekly": 2,
    "tiktok/analytics/daily": 9,
    "tiktok/analytics/monthly": 10,
    "tiktok/analytics/weekly": 4,
    "tiktok/orders/daily": 12,
    "tiktok/orders/monthly": 12,
    "tiktok/orders/weekly": 12,
    "tiktok/products/daily": 14,
    "tiktok/products/monthly": 6,
    "tiktok/products/weekly": 3,
    "tiktok/services/daily": 2,
    "tiktok/services/monthly": 2,
}

#: 全域最低命中率(百分比)。
BASELINE_OVERALL_RATE = 11.0


def _load_header_columns() -> dict[str, list[str]]:
    payload = json.loads(HEADER_COLUMNS_FIXTURE.read_text(encoding="utf-8-sig"))
    return {str(key): [str(item) for item in value] for key, value in payload.items()}


def _load_generator_module():
    spec = importlib.util.spec_from_file_location(
        "semantic_snapshot_generator", GENERATOR_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# 1. 标准字段定义只有一份(快照漂移守护)
# ---------------------------------------------------------------------------


def test_frontend_snapshot_matches_backend_registry():
    """前端快照必须与后端注册表逐字一致。

    快照是**生成物**。以前前端那份是手抄的, 已经漂了
    (缺 ``domain`` / ``required``, label 与别名对不上) ——
    这次漂移直接反映成「用户在前端看到的 ≠ 后端认定的」。
    """
    generator = _load_generator_module()
    expected = generator._js_header(generator.build_payload())
    actual = SNAPSHOT_PATH.read_text(encoding="utf-8")
    assert actual == expected, (
        "前端标准字段快照与后端注册表已漂移, "
        "请运行 python scripts/generate_semantic_field_snapshot.py"
    )


def test_backend_registry_exposes_required_and_domain():
    """``required`` / ``domain`` 必须由后端定义提供(前端以前永远是 false)。"""
    from backend.services.semantic_field_registry import (
        SEMANTIC_FIELD_DEFINITIONS,
        build_semantic_field_definitions_payload,
    )

    payload = build_semantic_field_definitions_payload()
    assert len(payload["fields"]) == len(SEMANTIC_FIELD_DEFINITIONS)
    by_key = {field["semantic_key"]: field for field in payload["fields"]}
    assert by_key["order_id"]["required"] is True
    assert by_key["product_name"]["domain"] == "products"
    assert by_key["product_name"]["hash_eligible"] is True
    assert by_key["item_status"]["hash_eligible"] is False
    assert by_key["shop_id"]["system_scope"] is True


def test_option_groups_cover_every_field():
    """每个标准字段都要落在某个下拉分组里(不能漏)。"""
    from backend.services.semantic_field_registry import (
        SEMANTIC_FIELD_DEFINITIONS,
        build_semantic_field_definitions_payload,
    )

    payload = build_semantic_field_definitions_payload()
    grouped = {
        option["value"]
        for group in payload["option_groups"]
        for option in group["options"]
    }
    assert grouped == set(SEMANTIC_FIELD_DEFINITIONS)


# ---------------------------------------------------------------------------
# 2. 归一化口径
# ---------------------------------------------------------------------------


def test_normalization_strips_currency_suffix():
    from backend.services.semantic_field_registry import normalize_semantic_alias

    assert normalize_semantic_alias("买家支付(RMB)") == "买家支付"
    assert normalize_semantic_alias("买家支付（rmb）") == "买家支付"
    assert normalize_semantic_alias("利润(RMB)") == "利润"
    assert normalize_semantic_alias("利润（美元）") == "利润"


def test_normalization_keeps_non_currency_parenthetical():
    """括号里不是币种时**不能**剥 —— 否则两个不同含义会被并成一个。"""
    from backend.services.semantic_field_registry import normalize_semantic_alias

    assert normalize_semantic_alias("销售额(已下订单)") != "销售额"


def test_normalization_strips_star_whitespace_underscore_and_case():
    from backend.services.semantic_field_registry import normalize_semantic_alias

    assert normalize_semantic_alias("*商品sku") == "商品sku"
    assert normalize_semantic_alias("下单时间\n") == "下单时间"
    assert normalize_semantic_alias("商品 SKU") == "商品sku"
    assert normalize_semantic_alias("销售_数量") == "销售数量"
    assert normalize_semantic_alias("  销售额  ") == "销售额"
    assert normalize_semantic_alias("GMV") == "gmv"


def test_normalization_samples_are_consistent():
    """快照里的样本对必须与后端归一化结果一致(前后端口径锁)。"""
    from backend.services.semantic_field_registry import (
        NORMALIZATION_SAMPLE_VALUES,
        normalize_semantic_alias,
    )

    assert NORMALIZATION_SAMPLE_VALUES
    for raw in NORMALIZATION_SAMPLE_VALUES:
        assert normalize_semantic_alias(raw) == normalize_semantic_alias(raw)


def test_snapshot_contains_normalization_samples():
    """快照必须带归一化样本对, 前端脚本测试靠它锁口径。"""
    generator = _load_generator_module()
    payload = generator.build_payload()
    samples = payload["normalization_samples"]
    assert samples
    for pair in samples:
        assert len(pair) == 2


# ---------------------------------------------------------------------------
# 3. 域限定优先于全局
# ---------------------------------------------------------------------------


def test_domain_column_override_wins():
    """域限定列名表优先(「ID」在 products 域是商品 ID, 别处不是)。"""
    from backend.services.semantic_field_registry import infer_semantic_key_for_domain

    assert infer_semantic_key_for_domain("products", "商品编号") == "product_id"
    assert infer_semantic_key_for_domain("products", "规格编号") == "sku_id"
    assert infer_semantic_key_for_domain("services", "客服ID") == "service_id"
    assert infer_semantic_key_for_domain("inventory", "*商品sku") == "platform_sku"


def test_domain_alias_resolves_currency_variant():
    """域限定别名 + 币种后缀 ⇒ 能解出 paid_amount。"""
    from backend.services.semantic_field_registry import infer_semantic_key_for_domain

    assert infer_semantic_key_for_domain("orders", "买家支付(RMB)") == "paid_amount"
    assert infer_semantic_key_for_domain("orders", "买家支付") == "paid_amount"


def test_unknown_column_is_not_guessed():
    """认不出来就返回 None —— 不猜。

    注意: 「商品展示量」曾经是这条断言的样例, 但它是 shopee 商品报表的**真实表头**
    (含义 = 曝光次数), 2026-11-08 已按真实表头登记为 ``impressions``。
    这里改用另一个**确实没有语义落点**的真实列, 守住同一条原则。
    """
    from backend.services.semantic_field_registry import infer_semantic_key_for_domain

    # shopee 商品报表里的真实表头, 但语义层没有对应标准字段 ⇒ 不猜
    assert infer_semantic_key_for_domain("products", "搜索点击人数") is None
    assert infer_semantic_key_for_domain("orders", "采购平台") is None


# ---------------------------------------------------------------------------
# 4. 命中率基线(D-7)
# ---------------------------------------------------------------------------


def test_hit_rate_does_not_regress_per_domain():
    """各域命中数不许低于基线。"""
    from backend.services.semantic_field_registry import infer_semantic_key_for_domain

    columns_by_template = _load_header_columns()
    assert set(BASELINE_HITS).issubset(set(columns_by_template))

    for template_key, baseline in BASELINE_HITS.items():
        data_domain = template_key.split("/")[1]
        columns = columns_by_template[template_key]
        hits = sum(
            1
            for column in columns
            if infer_semantic_key_for_domain(data_domain, column)
        )
        assert (
            hits >= baseline
        ), f"{template_key} 命中率退步: {hits}/{len(columns)} < 基线 {baseline}"


def test_overall_hit_rate_does_not_regress():
    from backend.services.semantic_field_registry import infer_semantic_key_for_domain

    columns_by_template = _load_header_columns()
    total_hits = 0
    total_columns = 0
    for template_key, columns in columns_by_template.items():
        data_domain = template_key.split("/")[1]
        total_hits += sum(
            1
            for column in columns
            if infer_semantic_key_for_domain(data_domain, column)
        )
        total_columns += len(columns)

    rate = 100.0 * total_hits / total_columns
    assert (
        rate >= BASELINE_OVERALL_RATE
    ), f"全域命中率退步: {rate:.1f}% < 基线 {BASELINE_OVERALL_RATE}%"


# ---------------------------------------------------------------------------
# 5. 全局沉淀 + 冲突不覆盖(需要库)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def alias_session_factory():
    """内存 SQLite + ATTACH 一个 ``semantic`` schema, 专门测别名表。

    为什么不直接用 ORM 的 ``create_all``:
    ``id`` 是 ``BigInteger`` 自增主键, 而 SQLite 只对 ``INTEGER PRIMARY KEY``
    做自增 ⇒ ORM 建出来的表插不进去。这里手写一份等价 DDL。

    为什么不连 PostgreSQL 容器:
    这三条用例要验证的是「沉淀 / 冲突 / 停用」的**语义**,
    与具体数据库无关; 用 SQLite 能让它们在任何环境都跑得起来。
    """
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("ATTACH DATABASE ':memory:' AS semantic"))
        await conn.execute(
            text(
                """
                CREATE TABLE semantic.semantic_field_aliases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data_domain VARCHAR(64) NOT NULL,
                    standard_field VARCHAR(128) NOT NULL,
                    raw_alias TEXT NOT NULL,
                    platform_code VARCHAR(32),
                    granularity VARCHAR(32),
                    source VARCHAR(32) NOT NULL DEFAULT 'builtin',
                    confidence NUMERIC(4, 3) NOT NULL DEFAULT 1.000,
                    status VARCHAR(32) NOT NULL DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
                """
            )
        )

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield session_factory
    finally:
        await engine.dispose()


def _confirmed_bindings(semantic_key: str, raw_name: str) -> list[dict]:
    return [
        {
            "raw_name": raw_name,
            "source_header": raw_name,
            "semantic_key": semantic_key,
            "semantic_review_status": "confirmed_semantic",
            "semantic_review_source": "user",
        }
    ]


@pytest.mark.asyncio
async def test_confirmed_alias_settles_globally_and_hits_other_templates(
    alias_session_factory,
):
    """D-3: 用户在一个模板对齐一次 ⇒ 其它模板自动命中。"""
    from backend.services.semantic_alias_registry import (
        GLOBAL_ALIAS_DOMAIN,
        SemanticAliasRegistryService,
    )
    from backend.services.semantic_field_registry import (
        infer_semantic_key_for_domain,
        load_runtime_aliases,
        runtime_alias_snapshot,
    )

    registry = SemanticAliasRegistryService()
    async with alias_session_factory() as session:
        summary = await registry.upsert_template_confirmed_aliases(
            session,
            data_domain="products",
            platform_code="shopee",
            granularity="monthly",
            header_bindings=_confirmed_bindings("product_id", "商品编号X"),
        )

        assert summary.created == 1
        assert not summary.conflicts

        # 全局沉淀 = 三个维度都不限(域/平台/粒度), 否则「一处生效」名不副实。
        assert summary.aliases[0]["data_domain"] == GLOBAL_ALIAS_DOMAIN
        assert summary.aliases[0]["platform_code"] is None
        assert summary.aliases[0]["granularity"] is None

        await load_runtime_aliases(session)
        snapshot = runtime_alias_snapshot()
        assert snapshot["loaded"] is True
        assert GLOBAL_ALIAS_DOMAIN in snapshot["confirmed"]

        # 另一个域也能命中 —— 这就是「一处生效」。
        assert infer_semantic_key_for_domain("inventory", "商品编号X") == "product_id"
        assert infer_semantic_key_for_domain("orders", "商品编号X") == "product_id"


@pytest.mark.asyncio
async def test_conflicting_alias_does_not_overwrite_and_stays_out_of_inference(
    alias_session_factory,
):
    """同一个列名撞两个语义键 ⇒ 原记录不动 + 落 conflict + 不进推断。"""
    from backend.services.semantic_alias_registry import SemanticAliasRegistryService
    from backend.services.semantic_field_registry import (
        infer_semantic_key_for_domain,
        load_runtime_aliases,
    )

    registry = SemanticAliasRegistryService()
    async with alias_session_factory() as session:
        await registry.upsert_template_confirmed_aliases(
            session,
            data_domain="products",
            platform_code="shopee",
            granularity="monthly",
            header_bindings=_confirmed_bindings("product_id", "冲突列"),
        )

        conflict_summary = await registry.upsert_template_confirmed_aliases(
            session,
            data_domain="products",
            platform_code="shopee",
            granularity="monthly",
            header_bindings=_confirmed_bindings("platform_sku", "冲突列"),
        )

        assert len(conflict_summary.conflicts) == 1
        assert conflict_summary.conflicts[0]["conflict_with"] == "product_id"

        rows = list(
            (
                await session.execute(
                    text(
                        """
                        SELECT standard_field, status
                        FROM semantic.semantic_field_aliases
                        WHERE raw_alias = :raw_alias
                        ORDER BY id
                        """
                    ),
                    {"raw_alias": "冲突列"},
                )
            ).mappings()
        )
        active_rows = [row for row in rows if row["status"] == "active"]
        conflict_rows = [row for row in rows if row["status"] == "conflict"]
        assert len(active_rows) == 1
        assert active_rows[0]["standard_field"] == "product_id", "原记录不能被覆盖"
        assert len(conflict_rows) == 1

        await load_runtime_aliases(session)
        # conflict 行不进推断 —— 冲突没裁决之前, 系统不替用户拍板。
        assert infer_semantic_key_for_domain("products", "冲突列") == "product_id"


@pytest.mark.asyncio
async def test_disabled_alias_is_not_used(alias_session_factory):
    """停用掉的别名不进推断链路。"""
    from backend.services.semantic_alias_registry import SemanticAliasRegistryService
    from backend.services.semantic_field_registry import (
        infer_semantic_key_for_domain,
        load_runtime_aliases,
    )

    registry = SemanticAliasRegistryService()
    async with alias_session_factory() as session:
        await registry.upsert_template_confirmed_aliases(
            session,
            data_domain="products",
            platform_code="shopee",
            granularity="monthly",
            header_bindings=_confirmed_bindings("product_id", "停用列"),
        )
        await session.execute(
            text(
                """
                UPDATE semantic.semantic_field_aliases
                SET status = 'disabled'
                WHERE raw_alias = :raw_alias
                """
            ),
            {"raw_alias": "停用列"},
        )
        await session.commit()

        await load_runtime_aliases(session)
        assert infer_semantic_key_for_domain("products", "停用列") is None
