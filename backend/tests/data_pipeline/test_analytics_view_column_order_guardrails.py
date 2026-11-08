"""analytics 视图列序自检的**回归守护**用例。

背景
----
2026-11-09 发现一个会**永久打断空库迁移链**的隐患:

* 迁移 ``20261209`` 的 fail-closed 自检断言的是「这 5 个 shopee 流量指标
  必须是视图的**最后 5 列**」;
* 迁移 ``20261210`` 在**后面**又追加了 13 个 tiktok 归因列
  ⇒ 视图末尾变成 18 列;
* ⇒ 再走一遍**空库链**时, 跑到 20261209 那一步, 断言必然失败
  ⇒ ``validate_migrations_fresh_db.py`` 与两个 rehearsal 用例全挂。

根因: 「必须是最后 N 列」这个断言把**历史迁移**和**未来迁移**绑死了。
视图列只能追加 ⇒ 后面再来 N 个迁移继续在末尾加列是**正常且正确**的,
历史迁移不该因此失效。

真正该守的不变量是「**新增列只能追加, 既有列一个都不能动**」,
它等价于:
  1. 期望列**一个都不能少**;
  2. 期望列的**相对顺序**不变;
  3. 期望列**连续成块**(中间插别的列 = 破坏列序契约);
  4. 整块**追加在锚点列之后**(锚点之前的老列一个都不许挪到块后面)。

本文件把这条新语义钉死, 并**加强式**覆盖 6 类失败场景。
"""

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_20261209 = (
    REPO_ROOT
    / "current_migrations"
    / "versions"
    / "20261209_semantic_analytics_shopee_traffic_fields.py"
)
MIGRATION_20261210 = (
    REPO_ROOT
    / "current_migrations"
    / "versions"
    / "20261210_semantic_analytics_tiktok_attribution.py"
)

#: 列序锚点 —— analytics 域新增的列一律追加在它之后。
ANCHOR = "identity_candidates"

#: 20261209 追加的 5 个 shopee 流量指标(相对顺序固定)。
SHOPEE_BLOCK = (
    "new_visitor_count",
    "returning_visitor_count",
    "new_follower_count",
    "avg_session_duration_seconds",
    "avg_page_views_per_visitor",
)

#: 20261210 追加的 13 个 tiktok 归因列(相对顺序固定)。
TIKTOK_BLOCK = (
    "product_card_gmv",
    "live_gmv",
    "live_indirect_gmv",
    "video_gmv",
    "video_indirect_gmv",
    "bound_account_live_attributed_gmv",
    "bound_account_video_attributed_gmv",
    "affiliate_video_attributed_gmv",
    "creator_live_gmv",
    "creator_live_attributed_gmv",
    "creator_live_indirect_gmv",
    "creator_video_gmv",
    "creator_video_indirect_gmv",
)


def _load(path: Path, alias: str):
    """把迁移文件当模块加载(迁移文件不是可导入包)。"""
    spec = importlib.util.spec_from_file_location(alias, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mig_20261209():
    return _load(MIGRATION_20261209, "_mig_20261209_columns")


@pytest.fixture(scope="module")
def mig_20261210():
    return _load(MIGRATION_20261210, "_mig_20261210_columns")


# ── 一、迁移文件里必须真的换成新语义 ────────────────────────────────────


def test_both_migrations_expose_the_new_column_block_check(mig_20261209, mig_20261210):
    """两个迁移都必须用同一个「存在 + 顺序 + 连续 + 锚点」检查。"""
    for module in (mig_20261209, mig_20261210):
        assert hasattr(
            module, "_check_column_block"
        ), "{0} 缺 _check_column_block".format(module.__name__)
        assert hasattr(
            module, "TRAFFIC_COLUMN_ANCHOR"
        ), "{0} 缺 TRAFFIC_COLUMN_ANCHOR".format(module.__name__)
        assert module.TRAFFIC_COLUMN_ANCHOR == ANCHOR


def test_migrations_no_longer_assert_absolute_tail(mig_20261209, mig_20261210):
    """⚠ **不许再用「必须是最后 N 列」这种绝对末尾断言**。

    它把历史迁移和未来迁移绑死 ⇒ 后面任何一次追加列都会让**空库链断裂**
    (2026-11-09 实际发生过: 20261210 落地后 20261209 的自检永久失败)。
    """
    for module in (mig_20261209, mig_20261210):
        source = Path(module.__file__).read_text(encoding="utf-8", errors="replace")
        assert (
            "columns[-len(" not in source
        ), "{0} 还在用绝对末尾断言(columns[-len(...)])".format(module.__name__)


# ── 二、新语义的行为(加强式: 6 类失败场景都要拦住) ───────────────────────


def test_column_block_check_accepts_exact_block(mig_20261210):
    """基线: 列齐全 + 顺序正确 + 连续 + 追加在锚点之后 ⇒ 通过。"""
    columns = ["gmv", ANCHOR] + list(TIKTOK_BLOCK)
    mig_20261210._check_column_block("v", columns, TIKTOK_BLOCK, ANCHOR)


def test_column_block_check_accepts_later_appended_columns(mig_20261209, mig_20261210):
    """⚠⚠ **回归本体**: 后面再来一个迁移继续在末尾追加列 ⇒ **必须照样通过**。

    这正是 20261209 在 20261210 落地后失效的那个场景。
    """
    columns = ["gmv", ANCHOR] + list(TIKTOK_BLOCK) + ["future_col_a", "future_col_b"]
    mig_20261210._check_column_block("v", columns, TIKTOK_BLOCK, ANCHOR)

    # 20261209 的 5 列同理: 后面追加 13 列也不能让它失效。
    columns_09 = ["gmv", ANCHOR] + list(SHOPEE_BLOCK) + list(TIKTOK_BLOCK)
    mig_20261209._check_column_block("v", columns_09, SHOPEE_BLOCK, ANCHOR)


def test_column_block_check_rejects_missing_column(mig_20261210):
    """少一列 ⇒ 报错(= 字典登记了但没真正接进语义层)。"""
    columns = ["gmv", ANCHOR] + list(TIKTOK_BLOCK[:-1])
    with pytest.raises(RuntimeError) as excinfo:
        mig_20261210._check_column_block("v", columns, TIKTOK_BLOCK, ANCHOR)
    assert "缺少新登记" in str(excinfo.value)


def test_column_block_check_rejects_wrong_relative_order(mig_20261210):
    """相对顺序变了 ⇒ 报错(列序是下游取数的契约)。"""
    swapped = list(TIKTOK_BLOCK)
    swapped[0], swapped[1] = swapped[1], swapped[0]
    columns = ["gmv", ANCHOR] + swapped
    with pytest.raises(RuntimeError) as excinfo:
        mig_20261210._check_column_block("v", columns, TIKTOK_BLOCK, ANCHOR)
    assert "相对顺序变了" in str(excinfo.value)


def test_column_block_check_rejects_non_contiguous_block(mig_20261210):
    """块中间插进别的列 ⇒ 报错(破坏了「整块追加」的契约)。"""
    columns = (
        ["gmv", ANCHOR] + list(TIKTOK_BLOCK[:3]) + ["intruder"] + list(TIKTOK_BLOCK[3:])
    )
    with pytest.raises(RuntimeError) as excinfo:
        mig_20261210._check_column_block("v", columns, TIKTOK_BLOCK, ANCHOR)
    assert "不是连续的一块" in str(excinfo.value)


def test_column_block_check_rejects_missing_anchor(mig_20261210):
    """锚点列不在 ⇒ 无法确认新列是追加的 ⇒ 报错(不许静默放过)。"""
    columns = ["gmv"] + list(TIKTOK_BLOCK)
    with pytest.raises(RuntimeError) as excinfo:
        mig_20261210._check_column_block("v", columns, TIKTOK_BLOCK, ANCHOR)
    assert "缺少锚点列" in str(excinfo.value)


def test_column_block_check_rejects_block_before_anchor(mig_20261210):
    """新列被挪到锚点之前 ⇒ 报错(老列被重排 = 列序契约被破坏)。"""
    columns = list(TIKTOK_BLOCK) + ["gmv", ANCHOR]
    with pytest.raises(RuntimeError) as excinfo:
        mig_20261210._check_column_block("v", columns, TIKTOK_BLOCK, ANCHOR)
    assert "没有追加在锚点列" in str(excinfo.value)


def test_column_block_check_rejects_empty_view(mig_20261210):
    """视图不存在 / 没有可见列 ⇒ 报错(不许当成「通过」)。"""
    with pytest.raises(RuntimeError) as excinfo:
        mig_20261210._check_column_block("v", [], TIKTOK_BLOCK, ANCHOR)
    assert "没有可见列" in str(excinfo.value)
