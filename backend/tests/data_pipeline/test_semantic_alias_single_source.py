"""语义别名单一事实源的契约测试 —— 2026-11-08。

背景
----
「列名 → 标准字段」的映射以前散落在 4 个载体里(DB seed / Python builtin /
字典 / 入库前改名归一), 而且**已经漂移**。本文件把「单一事实源」这件事
**锁死**: 事实源是 :mod:`backend.services.semantic_field_registry` 的字典,
其余载体全部由它派生。

本文件锁死的不变量:

1. :data:`BUILTIN_ALIASES` 里**每一条**都能在字典里找到来源
   (不接受手写条目);
2. products 域的**真实表头**都在派生结果里;
3. paid 与 placed 两套口径**不会**落到同一个标准字段(口径不许混);
4. 生成器的 ``--check`` 能正确检出「生成结果 ↔ SQL 资产」的差异;
5. 归一化形态生成正确(币种后缀 / Excel 重名序号)。

⚠️ 关于第 4 条: 当前 ``sql/semantic/semantic_alias_registry.sql`` 里**还没有**
新的 products 域别名(那是迁移那条线的工作), 所以 ``--check`` **应该**报告
「有差异」。本文件断言的是「它正确地检测到了差异」, 而不是「没有差异」。
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Dict, List, Set, Tuple

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
GENERATOR_PATH = REPO_ROOT / "scripts" / "generate_semantic_alias_seed.py"
SQL_ASSET = REPO_ROOT / "sql" / "semantic" / "semantic_alias_registry.sql"

#: products 域的关键真实表头(来自 shopee / tiktok 商品报表的真实表头)。
REQUIRED_PRODUCT_HEADERS: Tuple[Tuple[str, str], ...] = (
    ("商品编号", "product_id"),
    ("已付款订单", "order_count"),
    ("销售额（已付款订单）", "sales_amount"),
    ("件数（已付款订单）", "sales_volume"),
    ("转化率（已付款订单）", "conversion_rate"),
)

#: 口径配对: (已付款口径的标准字段, 已下单口径的标准字段)。
CALIBER_PAIRS: Tuple[Tuple[str, str], ...] = (
    ("order_count", "order_count_placed"),
    ("sales_amount", "sales_amount_placed"),
    ("sales_volume", "sales_volume_placed"),
    ("conversion_rate", "conversion_rate_placed"),
    ("order_conversion_rate", "order_conversion_rate_placed"),
    ("buyer_count", "buyer_count_placed"),
    ("aov", "aov_placed"),
)

#: 只属于其它域的别名 —— 它们**不许**出现在 products 的派生结果里
#: (跨域污染: 同一个列名在不同域含义不同)。
OTHER_DOMAIN_ONLY_ALIASES: Tuple[str, ...] = (
    # orders 域
    "买家支付",
    "出库数量",
    "预估回款金额",
    "结算时间",
    "成本利润率",
    # analytics 域
    "uv",
    "访问用户数",
    "支付订单数",
    "成交订单数",
    "成交金额",
    "交易额",
)


def _load_generator() -> ModuleType:
    """按文件路径加载生成器脚本(它不在包里, 但要被契约测试直接调用)。"""
    spec = importlib.util.spec_from_file_location(
        "generate_semantic_alias_seed", GENERATOR_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def generator() -> ModuleType:
    return _load_generator()


@pytest.fixture(scope="module")
def builtin_aliases() -> List[Dict[str, str]]:
    from backend.services.semantic_alias_registry import BUILTIN_ALIASES

    return list(BUILTIN_ALIASES)


# ---------------------------------------------------------------------------
# 1. 每一条派生别名都能在字典里找到来源
# ---------------------------------------------------------------------------


def test_every_builtin_alias_comes_from_the_dictionary(builtin_aliases):
    """``BUILTIN_ALIASES`` 不许有手写条目 —— 每条都要能追溯到字典。"""
    from backend.services.semantic_field_registry import (
        DOMAIN_SEMANTIC_ALIASES,
        SEMANTIC_FIELD_ALIASES,
    )

    # 允许的来源: 全局别名表(标准字段的 key + 它的 aliases)+ 域限定别名表。
    allowed: Dict[str, Set[str]] = {
        key: set(aliases) for key, aliases in SEMANTIC_FIELD_ALIASES.items()
    }
    for semantic_key, aliases in DOMAIN_SEMANTIC_ALIASES.get("products", {}).items():
        allowed.setdefault(semantic_key, set()).update(aliases)

    assert builtin_aliases, "派生结果不能为空"

    unknown: List[str] = []
    for record in builtin_aliases:
        standard_field = str(record.get("standard_field") or "")
        raw_alias = str(record.get("raw_alias") or "")
        assert (
            record.get("data_domain") == "products"
        ), f"products 域的派生结果里出现了别的域: {record}"
        if raw_alias not in allowed.get(standard_field, set()):
            unknown.append(f"{standard_field} <- {raw_alias}")

    assert not unknown, f"以下别名在字典里找不到来源(疑似手写): {unknown}"


def test_builtin_alias_shape_is_unchanged(builtin_aliases):
    """既有构造器依赖的形状: list[dict] + 三个键。"""
    for record in builtin_aliases:
        assert isinstance(record, dict)
        assert set(record) == {"data_domain", "standard_field", "raw_alias"}


def test_builtin_alias_has_no_duplicate_column(builtin_aliases):
    """同一个列名只认一个标准字段 —— 否则 PG 侧解析结果不确定。"""
    owners: Dict[str, Set[str]] = {}
    for record in builtin_aliases:
        raw_alias = str(record["raw_alias"])
        owners.setdefault(raw_alias, set()).add(str(record["standard_field"]))

    conflicts = {
        alias: sorted(fields) for alias, fields in owners.items() if len(fields) > 1
    }
    assert not conflicts, f"同一个列名被多个标准字段认领: {conflicts}"


# ---------------------------------------------------------------------------
# 2. products 域的真实表头都在派生结果里
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("raw_alias", "standard_field"), REQUIRED_PRODUCT_HEADERS)
def test_required_product_headers_are_derived(
    builtin_aliases, raw_alias, standard_field
):
    """真实表头必须被认领, 且落到正确的标准字段上。"""
    matched = [
        record
        for record in builtin_aliases
        if record["raw_alias"] == raw_alias and record["data_domain"] == "products"
    ]
    assert matched, f"真实表头 {raw_alias!r} 没被派生出来"
    assert str(matched[0]["standard_field"]) == standard_field


def test_products_real_headers_cover_caliber_variants(builtin_aliases):
    """下单口径的真实表头也要在派生结果里, 且落在 *_placed 字段上。"""
    placed_headers = (
        "已下订单",
        "销售额（已下订单）",
        "件数（已下订单）",
        "转化率（已下订单）",
        "订单转化率（已下订单）",
        "买家数（已下订单）",
        "每笔订单销售额（已下订单）",
    )
    mapping = {
        str(record["raw_alias"]): str(record["standard_field"])
        for record in builtin_aliases
    }
    for header in placed_headers:
        assert header in mapping, f"下单口径表头 {header!r} 没被派生出来"
        assert mapping[header].endswith(
            "_placed"
        ), f"{header!r} 落到了 {mapping[header]}, 应当落在 *_placed 字段上"


def test_other_domain_aliases_do_not_leak_into_products(builtin_aliases):
    """别的域的别名不许混进 products(跨域污染)。"""
    raw_aliases = {str(record["raw_alias"]) for record in builtin_aliases}
    leaked = sorted(raw_aliases & set(OTHER_DOMAIN_ONLY_ALIASES))
    assert not leaked, f"跨域污染: {leaked}"


# ---------------------------------------------------------------------------
# 3. 口径不许混
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("paid_field", "placed_field"), CALIBER_PAIRS)
def test_caliber_pairs_use_distinct_standard_fields(
    builtin_aliases, paid_field, placed_field
):
    """已付款口径与已下单口径必须落在**不同**的标准字段上。"""
    mapping = {
        str(record["raw_alias"]): str(record["standard_field"])
        for record in builtin_aliases
    }
    paid_headers = [
        alias
        for alias, field in mapping.items()
        if field == paid_field and "已付款" in alias
    ]
    placed_headers = [
        alias
        for alias, field in mapping.items()
        if field == placed_field and "已下" in alias
    ]
    assert paid_headers, f"{paid_field} 没有已付款口径的别名"
    assert placed_headers, f"{placed_field} 没有已下单口径的别名"

    for paid_header in paid_headers:
        for placed_header in placed_headers:
            assert (
                mapping[paid_header] != mapping[placed_header]
            ), f"{paid_header} 与 {placed_header} 落到了同一个标准字段"


def test_no_column_maps_to_two_calibers(builtin_aliases):
    """同一个列名不许同时被 paid 与 placed 两个口径认领。"""
    from backend.services.semantic_field_registry import (
        CALIBER_PAID,
        CALIBER_PLACED,
        SEMANTIC_FIELD_DEFINITIONS,
    )

    owners: Dict[str, Set[str]] = {}
    for record in builtin_aliases:
        raw_alias = str(record["raw_alias"])
        owners.setdefault(raw_alias, set()).add(str(record["standard_field"]))

    mixed: List[str] = []
    for raw_alias, fields in owners.items():
        calibers = {
            SEMANTIC_FIELD_DEFINITIONS.get(field, {}).get("caliber") for field in fields
        }
        if CALIBER_PAID in calibers and CALIBER_PLACED in calibers:
            mixed.append(raw_alias)

    assert not mixed, f"同一列名同时被两套口径认领: {mixed}"


# ---------------------------------------------------------------------------
# 4. 生成器 --check 能正确检出差异
# ---------------------------------------------------------------------------


def test_generator_check_detects_difference_and_does_not_write(tmp_path):
    """``--check`` 报告差异 + 非零退出码 + 不写文件。

    做法: 拿当前资产造一份**删掉一行**的副本, 让 --check 比对时必然有差异。
    （不能依赖"仓库里的资产正好是旧的" —— 资产是持续更新的,
    那样这条测试会随资产同步而失效。）
    """
    asset_text = SQL_ASSET.read_text(encoding="utf-8")
    rows = [
        line
        for line in asset_text.split("\n")
        if line.strip().startswith("('products'")
    ]
    assert rows, "资产里没有 products seed 行"
    dropped = rows[0]
    broken_text = asset_text.replace(dropped + "\n", "", 1)
    assert broken_text != asset_text, "没能造出有差异的资产副本"

    broken_asset = tmp_path / "semantic_alias_registry_broken.sql"
    broken_asset.write_text(broken_text, encoding="utf-8", newline="\n")
    before = broken_asset.read_bytes()

    result = subprocess.run(
        [
            sys.executable,
            str(GENERATOR_PATH),
            "--check",
            "--sql-asset",
            str(broken_asset),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert result.returncode != 0, (
        "生成结果与 SQL 资产不一致时 --check 必须返回非零退出码\n"
        f"stdout:\n{result.stdout}"
    )
    assert (
        "缺失" in result.stdout
    ), f"--check 必须打印差异明细\nstdout:\n{result.stdout}"
    assert broken_asset.read_bytes() == before, "--check 模式不许写文件"


def test_generator_check_passes_when_asset_is_in_sync():
    """资产与字典一致时 --check 必须返回 0(否则 CI 会一直红)。"""
    result = subprocess.run(
        [sys.executable, str(GENERATOR_PATH), "--check"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, (
        "别名资产与字典已经一致, --check 必须返回 0\n" f"stdout:\n{result.stdout}"
    )


def test_generator_stdout_is_compatible_with_sql_asset_shape(generator):
    """生成的 seed 段与现有 SQL 资产的 INSERT 段同形(同样的列 + ON CONFLICT)。"""
    sql_text = generator.render_seed_sql(
        generator.build_domain_alias_records("products")
    )

    assert "INSERT INTO semantic.semantic_field_aliases" in sql_text
    assert (
        "    (data_domain, standard_field, raw_alias, normalized_alias, "
        "source, confidence, status)" in sql_text
    )
    assert "ON CONFLICT (" in sql_text
    assert "COALESCE(platform_code, '')" in sql_text
    assert "COALESCE(granularity, '')" in sql_text
    # ON CONFLICT 必须把 **confidence** 一起更新 ——
    # 沿革旧词(如「已确定订单」)的置信度要低于当前措辞,
    # 重新 seed 时必须能把旧行的置信度降下来, 否则同表新旧两列并存时
    # resolve_alias 选谁是随机的。
    assert "DO UPDATE SET updated_at = NOW()" in sql_text
    assert "confidence = EXCLUDED.confidence" in sql_text
    assert "status = EXCLUDED.status" in sql_text
    # normalized_alias 也必须跟着更新 ——
    # PG 侧的 semantic.resolve_alias_normalized() 是按这一列匹配的,
    # 新别名落库时它是 NULL ⇒ 归一化解析看不见这些行(实测漏了 6 条)。
    assert "normalized_alias = EXCLUDED.normalized_alias" in sql_text


def test_generator_seed_rows_are_parseable_and_round_trip(generator):
    """生成 → 解析 → 比对, 必须完全一致(自洽)。"""
    rows = generator.build_domain_alias_records("products")
    sql_text = generator.render_seed_sql(rows)
    parsed = generator.parse_seed_rows(sql_text)
    missing, extra = generator.diff_seed_rows(rows, parsed)
    assert (
        not missing and not extra
    ), f"生成结果与自身解析结果不一致: 缺失 {missing}, 多余 {extra}"


def test_generator_and_builtin_share_the_same_source(generator, builtin_aliases):
    """生成器与 ``BUILTIN_ALIASES`` 必须来自同一份字典(不得分叉)。"""
    rows = generator.build_domain_alias_records("products")
    generated = {
        (str(row["data_domain"]), str(row["standard_field"]), str(row["raw_alias"]))
        for row in rows
    }
    builtin = {
        (str(row["data_domain"]), str(row["standard_field"]), str(row["raw_alias"]))
        for row in builtin_aliases
    }
    assert generated == builtin, (
        "生成器与 BUILTIN_ALIASES 不一致\n"
        f"仅生成器有: {sorted(generated - builtin)}\n"
        f"仅 builtin 有: {sorted(builtin - generated)}"
    )


# ---------------------------------------------------------------------------
# 5. 归一化形态
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("商品曝光次数.1", "商品曝光次数"),
        ("销售额（已付款订单） (SGD)", "销售额(已付款订单)"),
        ("加购次数（直播）", "加购次数(直播)"),
        ("  商品曝光次数  ", "商品曝光次数"),
    ],
)
def test_normalized_alias_generation(generator, raw, expected):
    """归一化形态: 币种后缀 / Excel 重名序号 / 全角标点都要收敛。"""
    assert generator.normalize_alias(raw) == expected


def test_normalized_alias_is_reported_for_every_seed_row(generator):
    """每一行都要带归一化形态(供 PG 侧归一化匹配用)。"""
    rows = generator.build_domain_alias_records("products")
    assert rows
    for row in rows:
        assert row.get("normalized_alias"), f"缺归一化形态: {row}"
        assert row["normalized_alias"] == row["normalized_alias"].strip().lower()


def test_caliber_history_variant_is_reported(generator):
    """口径沿革的等价形态要一并产出(shopee「已确定订单」→「已下单」)。"""
    rows = {
        (str(row["standard_field"]), str(row["raw_alias"])): row
        for row in generator.build_domain_alias_records("products")
    }
    row = rows[("order_count_placed", "已确定订单")]
    assert row["normalized_alias"] == "已确定订单"
    assert "已下单" in str(row["normalized_alias_history"])

    # 未登记沿革的平台不折算
    assert (
        generator.normalize_alias("已确定订单", platform_code="tiktok") == "已确定订单"
    )
