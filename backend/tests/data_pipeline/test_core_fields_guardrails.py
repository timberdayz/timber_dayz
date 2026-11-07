"""批次 E 护栏测试: 核心字段清单(``core_fields``)的口径护栏。

锁住四件事
----------

1. **迁移自包含且不漂移** —— 迁移里内嵌的规范语义键表必须是
   :mod:`backend.services.semantic_field_registry` 的**子集**(迁移不能 import backend,
   所以只能靠守护测试锁住漂移)。
2. **hash 键名口径** —— 清单推出的 hash 身份必须与旧口径
   ``deduplication_fields`` **逐字一致**(= ``raw_name`` 优先)。
   键名一变, hash 就变, 已入库的行全部变成「没见过的数据」。
3. **新旧分支 hash 等价** —— 同一行数据, 旧分支(``deduplication_fields``)
   与新分支(``core_fields``)算出的 ``data_hash`` 必须完全相同。
4. **``hash_participates`` 零引用**(规格 D2) —— 「参与去重」只由
   版本级核心字段清单的 ``in_hash`` 表达, 绑定级不再重复声明。

另加两条口径护栏:

* D1(指标可进 hash): 指标类 ``hash_eligible=True`` 但 ``default_hash=False``
  且必须带后果提示;
* 口径切换是**显式开关**: 默认关闭 ⇒ 不打开就不影响任何一行数据。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

import pytest

from backend.services.core_fields_service import (
    CORE_FIELD_KEYS,
    core_field_hash_identities,
    core_fields_hash_enabled,
    derive_core_fields,
    normalize_core_fields,
    resolve_core_field_value,
)
from backend.services.deduplication_service import DeduplicationService
from backend.services.semantic_field_registry import (
    SEMANTIC_FIELD_DEFINITIONS,
    get_semantic_requirements,
    is_canonical_semantic_key,
    is_hash_identity_semantic_key,
)

REPO_ROOT = Path(__file__).resolve().parents[3]

MIGRATION_PATH = (
    REPO_ROOT
    / "current_migrations"
    / "versions"
    / "20261125_template_versions_core_fields.py"
)


# ---------------------------------------------------------------------------
# 1) 迁移内嵌键表不漂移
# ---------------------------------------------------------------------------


def test_migration_embedded_canonical_keys_match_registry():
    """迁移内嵌的规范键表必须是**注册表的子集**。

    为什么不是「两边相等」
    ----------------------
    迁移 ``20261125`` 是 **执行过的一次性回填快照**, 按仓库规则
    「已执行迁移不可改」不能再动; 而注册表是**活的唯一事实源**, 之后新增了
    20 个标准字段(口径并列列 / 渠道维度 / 加购与点击类指标)。

    * **子集**(迁移 ⊆ 注册表) —— 这条守护必须留着:
      迁移引用的每个键都还在 ⇒ 回填逻辑没跑偏, 没有引用被删掉/改名的键;
    * **允许注册表变长** —— 新键由**运行期**接管:
      ``core_fields_service.derive_core_fields`` 走
      ``is_canonical_semantic_key``(活注册表), 新建/更新模板版本时直接带上新键。

    为什么**不做**「按新键重新回填存量行」
    ------------------------------------
    实测(开发库 xihong_erp, 55 个模板版本): 用当前注册表重新推导
    ``core_fields``, 与存量值有差异, 而差异**全部**来自 ``required`` 标志
    (域级契约在 20261127 之后把 order_id / metric_date 标成 required)
    与规范键表无关。
    重写存量行 ⇒ 给存量版本**新增 required** ⇒ 立刻变成新的口径漂移阻断源。
    ⇒ 存量行保持原样, 新键只对**运行期新建/更新**的版本生效。
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_mig_20261125", MIGRATION_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    embedded = set(module._CANONICAL_SEMANTIC_KEYS)
    registry = set(SEMANTIC_FIELD_DEFINITIONS.keys())

    dropped = sorted(embedded - registry)
    assert not dropped, (
        "迁移内嵌的规范语义键在注册表里没了(被删或改名): " f"{dropped}"
    )

    # 运行期推导必须认得迁移引用的每一个键
    for key in sorted(embedded):
        assert is_canonical_semantic_key(key), (
            f"运行期不再把 {key!r} 当规范语义键 —— 迁移回填与运行期推导会分叉"
        )

# ---------------------------------------------------------------------------
# 2) hash 键名口径
# ---------------------------------------------------------------------------


def test_core_field_hash_identities_use_raw_name_first():
    """键名 = ``raw_name`` 优先(与旧口径逐字一致), 不是语义键优先。

    若改成语义键优先: 条目「商品编号」会被换成 ``product_id`` 写进 hash 载荷
    ⇒ 键变了 ⇒ hash 变了 ⇒ 已入库的行全部变成新数据。
    """
    core_fields = [
        {"semantic_key": "product_id", "raw_name": "商品编号", "required": False, "in_hash": True},
        {"semantic_key": "metric_date", "raw_name": None, "required": True, "in_hash": True},
        {"semantic_key": None, "raw_name": "*商品SKU", "required": False, "in_hash": True},
    ]

    assert core_field_hash_identities(core_fields) == ["商品编号", "metric_date", "*商品SKU"]


def test_core_fields_preserve_legacy_hash_keys_order():
    """清单的 ``raw_name`` 序列必须与 ``deduplication_fields`` **逐项同序**。

    这是 hash 等价的**结构不变量**: 清单推出的 hash 键名序列 =
    旧口径 ``deduplication_fields`` 序列 ⇒ 键不变 ⇒ hash 不变。

    (实测证据: ``scripts/replay_core_fields_hash.py`` 在 488 行真实数据上,
    切到清单口径后 hash 变化 0 行; 28/28 版本的键集合静态比对一致。)
    """
    dedup_fields = ["商品编号", "商品", "metric_date", "*商品SKU", "仓库"]
    core_fields = derive_core_fields(
        deduplication_fields=dedup_fields,
        header_bindings=[],
        data_domain="products",
    )

    assert core_field_hash_identities(core_fields) == [
        "商品编号",
        "商品",
        "metric_date",
        "*商品SKU",
        "仓库",
    ]


def test_core_fields_translation_requires_user_confirmed_binding():
    """清单里的 ``semantic_key`` 只认**用户确认过**的绑定。

    为什么不能用推断层(域限定列名表 / 全局别名表)
    ----------------------------------------------
    批次 D 的硬结论: 「只有用户确认过的绑定才允许被提升成语义身份」。
    推断出来的语义键(把中文「商品编号」推成 ``product_id``)一旦写进清单,
    就会与「真的写成 product_id 的模板」判成口径一致 ⇒ **假一致**。

    ⇒ 这条口径必须与迁移 ``20261125`` 的 SQL **一致**,
    否则「迁移回填的清单」与「运行时现推的清单」会给出不同答案。
    """
    pending_binding = {
        "raw_name": "商品编号",
        "source_header": "商品编号",
        "semantic_key": None,
        "semantic_review_status": "pending",
        "semantic_review_source": "inferred",
    }
    unconfirmed = derive_core_fields(
        deduplication_fields=["商品编号"],
        header_bindings=[pending_binding],
        data_domain="products",
    )
    assert unconfirmed[0]["semantic_key"] is None
    assert unconfirmed[0]["raw_name"] == "商品编号"

    confirmed_binding = {
        "raw_name": "商品编号",
        "source_header": "商品编号",
        "semantic_key": "product_id",
        "semantic_review_status": "confirmed_semantic",
        "semantic_review_source": "user",
    }
    confirmed = derive_core_fields(
        deduplication_fields=["商品编号"],
        header_bindings=[confirmed_binding],
        data_domain="products",
    )
    assert confirmed[0]["semantic_key"] == "product_id"
    assert confirmed[0]["raw_name"] == "商品编号"


def test_derive_core_fields_keeps_raw_name_and_semantic_key():
    """清单同时保留两种身份: 语义键(按标准含义取) + 原始列名(逐字兜底)。"""
    core_fields = derive_core_fields(
        deduplication_fields=["商品编号", "metric_date", "完全翻译不出的列"],
        header_bindings=[
            {
                "raw_name": "商品编号",
                "source_header": "商品编号",
                "semantic_key": "product_id",
                "semantic_review_status": "confirmed_semantic",
                "semantic_review_source": "user",
            }
        ],
        data_domain="products",
    )

    by_raw = {entry["raw_name"]: entry for entry in core_fields}

    assert by_raw["商品编号"]["semantic_key"] == "product_id"
    # 条目本身就是规范语义键 ⇒ raw_name 为空(键名就是语义键)
    assert by_raw[None]["semantic_key"] == "metric_date"
    # 翻译不出来 ⇒ 语义键为空, 逐字兜底
    assert by_raw["完全翻译不出的列"]["semantic_key"] is None


def test_derive_core_fields_keeps_raw_name_for_domain_mapped_placeholder():
    """未确认的占位符列名(``*商品SKU``)保留 ``raw_name``, 语义键留空。

    规格 §6.1 说这类「占位符列名」须「降级为逐字匹配并明确告警」。
    现实是: ``*商品SKU`` 确实是 inventory 域的真实列名。

    ⇒ 语义键**只认用户确认过的绑定**(见
    :func:`test_core_fields_translation_requires_user_confirmed_binding`),
    未确认时留空;
    ⇒ 但 ``raw_name`` 必须保留 —— 它是 hash 载荷的**键名**,
    键名变了 hash 就变了。
    """
    core_fields = derive_core_fields(
        deduplication_fields=["*商品SKU"],
        header_bindings=[],
        data_domain="inventory",
    )

    entry = core_fields[0]
    assert entry["semantic_key"] is None
    assert entry["raw_name"] == "*商品SKU"
    # 键名 = raw_name(旧口径的键) ⇒ hash 载荷的键不变
    assert core_field_hash_identities(core_fields) == ["*商品SKU"]


# ---------------------------------------------------------------------------
# 3) 新旧分支 hash 等价
# ---------------------------------------------------------------------------


_EQUIVALENCE_CASES: List[Dict[str, Any]] = [
    {
        "name": "规范语义键条目",
        "data_domain": "orders",
        "deduplication_fields": ["product_id", "platform_sku", "order_id"],
        "bindings": [
            {
                "raw_name": "product_id",
                "source_header": "product_id",
                "semantic_key": "product_id",
                "semantic_review_status": "confirmed_semantic",
                "semantic_review_source": "user",
            }
        ],
        "row": {"product_id": "P-1", "platform_sku": "SKU-1", "order_id": "SO-1", "qty": 3},
    },
    {
        "name": "物理列名条目(翻译得出)",
        "data_domain": "products",
        "deduplication_fields": ["商品编号", "规格编号"],
        "bindings": [
            {
                "raw_name": "商品编号",
                "source_header": "商品编号",
                "semantic_key": "product_id",
                "semantic_review_status": "confirmed_semantic",
                "semantic_review_source": "user",
            },
            {
                "raw_name": "规格编号",
                "source_header": "规格编号",
                "semantic_key": "sku_id",
                "semantic_review_status": "confirmed_semantic",
                "semantic_review_source": "user",
            },
        ],
        "row": {"商品编号": "P-1", "规格编号": "S-1", "商品名称": "测试"},
    },
    {
        "name": "物理列名条目(翻译不出)",
        "data_domain": "inventory",
        "deduplication_fields": ["*商品SKU", "仓库"],
        "bindings": [],
        "row": {"*商品SKU": "X-1", "仓库": "华东仓"},
    },
    {
        "name": "混合 + 大小写差异",
        "data_domain": "products",
        "deduplication_fields": ["商品编号", "Order ID"],
        "bindings": [
            {
                "raw_name": "商品编号",
                "source_header": "商品编号",
                "semantic_key": "product_id",
                "semantic_review_status": "confirmed_semantic",
                "semantic_review_source": "user",
            }
        ],
        "row": {"商品编号": "P-1", "Order ID": "SO-9"},
    },
]


@pytest.mark.parametrize("case", _EQUIVALENCE_CASES, ids=lambda c: c["name"])
def test_core_fields_branch_hash_equals_legacy_branch_hash(case):
    """同一行数据, 新旧两个分支算出的 ``data_hash`` 必须**完全相同**。

    这是批次 E 最关键的一条护栏: 口径切换不得改任何一行的 hash
    (规格 §6.1「回填必须先行」的前提就是「不用回填」)。
    """
    service = DeduplicationService(db=None)
    scope_values = {
        "platform_code": "shopee",
        "shop_id": "shop-a",
        "data_domain": case["data_domain"],
        "granularity": "daily",
    }

    core_fields = derive_core_fields(
        deduplication_fields=case["deduplication_fields"],
        header_bindings=case["bindings"],
        data_domain=case["data_domain"],
    )

    old_hash = service.calculate_data_hash(
        case["row"],
        deduplication_fields=case["deduplication_fields"],
        header_bindings=case["bindings"],
        scope_values=scope_values,
    )
    new_hash = service.calculate_data_hash(
        case["row"],
        deduplication_fields=case["deduplication_fields"],
        header_bindings=case["bindings"],
        scope_values=scope_values,
        core_fields=core_fields,
    )

    assert new_hash == old_hash


def test_core_fields_branch_keeps_system_identity_fields():
    """新分支必须保留系统身份字段(platform_code / shop_id / 日期身份)。

    少了任何一个 ⇒ hash 的作用域变了 ⇒ 跨店铺/跨日期的行会互相覆盖。
    """
    service = DeduplicationService(db=None)
    scope_values = {
        "platform_code": "shopee",
        "shop_id": "shop-a",
        "data_domain": "analytics",
        "granularity": "daily",
    }
    core_fields = derive_core_fields(
        deduplication_fields=["metric_date"],
        header_bindings=[],
        data_domain="analytics",
    )

    base = service.calculate_data_hash(
        {"日期": "2026-06-08", "访客数": 100},
        deduplication_fields=["metric_date"],
        scope_values=scope_values,
    )
    with_core_fields = service.calculate_data_hash(
        {"日期": "2026-06-08", "访客数": 100},
        deduplication_fields=["metric_date"],
        scope_values=scope_values,
        core_fields=core_fields,
    )
    other_shop = service.calculate_data_hash(
        {"日期": "2026-06-08", "访客数": 100},
        deduplication_fields=["metric_date"],
        scope_values={**scope_values, "shop_id": "shop-b"},
        core_fields=core_fields,
    )

    assert with_core_fields == base
    assert other_shop != base


def test_core_fields_branch_recovers_field_on_column_rename():
    """列名漂移时: 旧口径会**丢掉**这个字段, 新口径按标准含义救回来。

    这是规格 §1.3「按标准含义取」带来的**能力**, 不是回归 ——
    旧口径本来就取不到, 所以不存在「与旧口径等价」的约束。
    """
    service = DeduplicationService(db=None)
    bindings = [
        {
            "raw_name": "商品编号",
            "source_header": "商品编号",
            "semantic_key": "product_id",
            "semantic_review_status": "confirmed_semantic",
            "semantic_review_source": "user",
            "aliases": ["商品编号", "商品ID"],
        }
    ]
    core_fields = derive_core_fields(
        deduplication_fields=["商品编号"],
        header_bindings=bindings,
        data_domain="products",
    )
    renamed_row = {"商品ID": "P-1"}

    old_hash = service.calculate_data_hash(
        renamed_row,
        deduplication_fields=["商品编号"],
        header_bindings=bindings,
    )
    new_hash = service.calculate_data_hash(
        renamed_row,
        deduplication_fields=["商品编号"],
        header_bindings=bindings,
        core_fields=core_fields,
    )

    assert old_hash != new_hash


def test_resolve_core_field_value_prefers_literal_then_semantic():
    """取值顺序: 逐字优先(保等价), 未命中才语义兜底(抗漂移)。"""
    bindings = [
        {
            "raw_name": "商品编号",
            "source_header": "商品编号",
            "semantic_key": "product_id",
            "semantic_review_status": "confirmed_semantic",
            "semantic_review_source": "user",
        }
    ]
    entry = {
        "semantic_key": "product_id",
        "raw_name": "商品编号",
        "required": False,
        "in_hash": True,
    }

    # 逐字命中 ⇒ 载荷键 = 实际列名, 不降级
    value, key, degraded = resolve_core_field_value(
        {"商品编号": "P-1"}, entry, header_bindings=bindings
    )
    assert value == "P-1"
    assert key == "商品编号"
    assert degraded is False

    # 逐字未命中 ⇒ 语义兜底, 载荷键仍是清单里的键名
    value, key, degraded = resolve_core_field_value(
        {"商品ID": "P-2"}, entry, header_bindings=bindings
    )
    assert value == "P-2"
    assert key == "商品编号"
    assert degraded is True


# ---------------------------------------------------------------------------
# 4) 清单结构与开关
# ---------------------------------------------------------------------------


def test_normalize_core_fields_keeps_four_keys():
    """清单项固定四个键(semantic_key / raw_name / required / in_hash)。"""
    normalized = normalize_core_fields(
        [
            {"semantic_key": "product_id", "raw_name": "商品编号"},
            "metric_date",
        ]
    )

    assert normalized
    for entry in normalized:
        assert set(entry.keys()) == set(CORE_FIELD_KEYS)

    by_key = {entry["semantic_key"] or entry["raw_name"]: entry for entry in normalized}
    assert by_key["product_id"]["in_hash"] is True
    assert by_key["metric_date"]["semantic_key"] == "metric_date"
    assert by_key["metric_date"]["raw_name"] is None


def test_core_fields_hash_switch_defaults_to_off(monkeypatch):
    """口径切换是显式开关, 默认关闭 ⇒ 不打开就不影响任何一行数据。"""
    monkeypatch.delenv("SYNC_CORE_FIELDS_HASH_ENABLED", raising=False)
    assert core_fields_hash_enabled() is False

    monkeypatch.setenv("SYNC_CORE_FIELDS_HASH_ENABLED", "1")
    assert core_fields_hash_enabled() is True

    monkeypatch.setenv("SYNC_CORE_FIELDS_HASH_ENABLED", "off")
    assert core_fields_hash_enabled() is False


# ---------------------------------------------------------------------------
# 5) D2: hash_participates 零引用 / D1: 指标可进 hash
# ---------------------------------------------------------------------------


def test_semantic_requirements_no_longer_expose_hash_participates():
    """绑定级不再声明「参与去重」—— 同一事实只由核心字段清单表达。"""
    requirements = get_semantic_requirements("product_id")

    assert "hash_participates" not in requirements
    assert requirements["required"] is False


def test_hash_participates_has_no_live_code_reference():
    """``hash_participates`` 在**活代码**里零引用(规格 D2 验收标准)。

    只扫「真正的代码引用」—— 字符串字面量 / 属性访问 / 字典键 / 关键字参数,
    **不扫注释**: 注释里写「``hash_participates`` 已下线」是必要的说明文字,
    不是引用。

    允许出现的位置: 历史迁移(不可改)、本次迁移的说明与数据清理、
    文档、以及本测试文件本身。
    """
    import re

    allowed_prefixes = (
        "current_migrations/",
        "docs/",
        "backend/tests/",
        "scripts/",
        "temp/",
    )
    banned_suffixes = (".py", ".js", ".mjs", ".vue", ".ts")
    scan_roots = ("backend/services", "backend/domains", "backend/schemas", "frontend/src")

    reference_re = re.compile(
        r"""["']hash_participates["']      # 字符串字面量(字典键 / 传参)
          | \.hash_participates\b           # 属性访问
          | \bhash_participates\s*[:=]      # 标识符形式的字典键 / 关键字参数
        """,
        re.VERBOSE,
    )

    offenders: List[str] = []
    for root in scan_roots:
        base = REPO_ROOT / root
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.suffix not in banned_suffixes or not path.is_file():
                continue
            relative = path.relative_to(REPO_ROOT).as_posix()
            if relative.startswith(allowed_prefixes):
                continue
            for lineno, line in enumerate(
                path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
            ):
                if reference_re.search(line):
                    offenders.append(f"{relative}:{lineno}: {line.strip()[:120]}")

    assert not offenders, (
        "hash_participates 在活代码里还有引用(应已下线):\n" + "\n".join(offenders)
    )


def test_metric_fields_are_hash_eligible_but_not_default():
    """D1: 指标类不再硬性禁止进 hash, 但不默认参与, 且必须带后果提示。"""
    for metric_key in ["page_views", "gmv", "live_attributed_gmv"]:
        meta = SEMANTIC_FIELD_DEFINITIONS[metric_key]
        assert meta["kind"] == "metric"
        assert meta["hash_eligible"] is True
        assert meta["default_hash"] is False
        assert meta.get("hash_warning")
        assert is_hash_identity_semantic_key(metric_key) is True
