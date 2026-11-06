"""店铺身份候选集「锚点重锚」的契约测试（2026-11-06）。

背景
----
候选集的四路优先级原来是 ``platform_shop_id(1) → shop_account_id(2) → …``,
**最不稳的那个排在最前** —— ``platform_shop_id`` 会被采集器污染、平台换 ID 就失效,
而 ``shop_account_id`` 才是唯一正确锚点（改名不变、跨平台一致、采集器写不坏）。

本次改动三条:

1. ``shop_account_id`` 升为 priority 1、``platform_shop_id`` 降到 2;
2. 候选池只收「在营经营店」（``enabled IS TRUE`` + ``business_role='operating_store'``）;
3. 别名路不再认领任何账号的平台店铺编号（自别名 / 跨账号认领）。

这些用例守的是**五条**不变量:

A. 优先级确实倒过来了, 且正本与物化副本**两份都改了**（内容指纹守护）;
B. 候选池的过滤补上了（补的是系统其它环节都有的过滤, 不是新口径）;
C. 别名路不再认领平台店铺编号;
D. ⚠️ ``resolved_shop_id`` 的派生口径**没有被**倒置 ——
   语义层输出的 ``shop_id`` 取的是 ``COALESCE(canonical.platform_shop_id,
   resolved_shop_id)``, 看板显示名靠它跟 ``core.dim_shops.shop_id`` 对齐;
   一旦把 COALESCE 顺序也倒过来, dim_shops 的键与事实表的键就对不上,
   显示名会整片落空。**「锚点重锚」只动排序, 不动派生键。**
E. 口径改了必须**重建**物化副本（REFRESH 只重算数据, 不换定义）。

⚠️ 所有针对「SQL 文本」的断言都只看**可执行部分** ——
注释里出现同样的字样不算数（否则解释性注释会把断言带偏）。
"""

import importlib.util
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]

CANDIDATES_VIEW_ASSET = "sql/semantic/shop_identity_resolution_candidates.sql"
CANDIDATES_MV_ASSET = "sql/semantic/shop_identity_resolution_candidates_v2_mv.sql"
#: 原子层普通视图的资产 —— 开头带 ``DROP VIEW ... CASCADE``, 迁移必须把它剥掉
ANALYTICS_ATOMIC_ASSET = "sql/semantic/analytics_atomic.sql"
REALIGN_MIGRATION = (
    "current_migrations/versions/20261112_realign_identity_candidates_anchor.py"
)

#: 正本 + 物化副本 —— 两份都必须同步改（内容指纹守护会因此失败）
BOTH_CANDIDATE_ASSETS = (CANDIDATES_VIEW_ASSET, CANDIDATES_MV_ASSET)

#: 四条语义路径（候选计数写在这里, 不在候选集里）
SEMANTIC_PATHS = (
    "sql/semantic/orders_atomic.sql",
    "sql/semantic/analytics_atomic.sql",
    "sql/semantic/orders_monthly_atomic_mv.sql",
    "sql/semantic/analytics_monthly_atomic_mv.sql",
)


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def _strip_sql_comments(sql_text: str) -> str:
    """去掉 SQL 的 ``--`` 行注释 —— 断言要看的是**可执行 SQL**。"""
    kept: list[str] = []
    for line in sql_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        kept.append(line.split("--")[0])
    return "\n".join(kept)


def _load_migration_module():
    """把迁移当成普通模块导入 —— 这样可以直接调用它的纯函数做**行为**断言。"""
    path = REPO_ROOT / REALIGN_MIGRATION
    spec = importlib.util.spec_from_file_location(
        "realign_identity_candidates_anchor_migration", path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _branch_priority(sql_text: str, method: str) -> int:
    """取出某一路候选的 ``resolution_priority``。

    只认「紧跟在 ``resolution_method`` 后面」的 priority —— 否则正文里别的
    ``N AS resolution_priority`` 会把断言带偏。
    """
    pattern = (
        r"'" + method + r"'::varchar\s+AS\s+resolution_method\s*,\s*"
        r"(\d+)\s+AS\s+resolution_priority"
    )
    match = re.search(pattern, sql_text, re.S)
    assert match, "候选集里找不到 {method} 这一路".format(method=method)
    return int(match.group(1))


# ---------------------------------------------------------------------------
# A. 锚点优先级倒置
# ---------------------------------------------------------------------------


def test_shop_account_id_is_the_top_priority_anchor_in_both_assets():
    """``shop_account_id`` 必须是 priority 1 —— 最稳的锚点说了算。"""
    for rel in BOTH_CANDIDATE_ASSETS:
        text = _strip_sql_comments(_read(rel))
        assert _branch_priority(text, "shop_account_id") == 1, rel


def test_platform_shop_id_is_demoted_to_second_priority_in_both_assets():
    """``platform_shop_id`` 降到 priority 2 —— 它会被污染, 不能排第一。"""
    for rel in BOTH_CANDIDATE_ASSETS:
        text = _strip_sql_comments(_read(rel))
        assert _branch_priority(text, "platform_shop_id") == 2, rel


def test_alias_and_store_name_priorities_are_unchanged():
    """别名路 / 店名路仍是垫底的 3、4 —— 别名是订单「店铺」中文列的唯一救命路。"""
    for rel in BOTH_CANDIDATE_ASSETS:
        text = _strip_sql_comments(_read(rel))
        assert _branch_priority(text, "alias_match") == 3, rel
        assert _branch_priority(text, "store_name_match") == 4, rel


def test_candidate_count_formula_is_not_touched():
    """⚠️ 计数口径**一个字都不能动**。

    把计数改成「按优先级分层」会把歧义行判成唯一, 然后选中被污染的那个 ——
    那就是静默错配。候选数必须仍然是「去重后的店铺数」, 而且只存在于
    **四条语义路径**里, 不在候选集里。
    """
    for rel in BOTH_CANDIDATE_ASSETS:
        text = _strip_sql_comments(_read(rel))
        assert "count(DISTINCT" not in text, rel

    for rel in SEMANTIC_PATHS:
        text = _strip_sql_comments(_read(rel))
        assert "count(DISTINCT c.resolved_shop_id)" in text, rel
        assert "OVER ()" not in text, rel


# ---------------------------------------------------------------------------
# B. 候选池过滤
# ---------------------------------------------------------------------------


def test_candidate_pool_only_contains_enabled_operating_stores():
    """候选池只收在营经营店。

    这一条是**补漏抄的过滤** —— 系统其它每个环节（采集挑账号 / 员工绩效 /
    探测匹配 / 数据同步清理）都已经过滤了 enabled 与 business_role,
    只有语义层候选池漏了。
    """
    for rel in BOTH_CANDIDATE_ASSETS:
        text = _strip_sql_comments(_read(rel))
        assert "sa.enabled IS TRUE" in text, rel
        assert "sa.business_role = 'operating_store'" in text, rel


# ---------------------------------------------------------------------------
# C. 别名路不再认领平台店铺编号
# ---------------------------------------------------------------------------


def test_alias_branch_refuses_to_claim_a_platform_shop_id():
    """自别名 / 跨账号认领会让同一串身份值指向两个账号 ⇒ 整行落 unknown。"""
    for rel in BOTH_CANDIDATE_ASSETS:
        text = _strip_sql_comments(_read(rel))
        assert "NOT EXISTS" in text, rel
        assert "alias_owner.platform_shop_id" in text, rel
        assert "alias_owner.enabled IS TRUE" in text, rel


# ---------------------------------------------------------------------------
# D. 派生键不许跟着倒 —— 看板显示名 JOIN 靠它
# ---------------------------------------------------------------------------


def test_resolved_shop_id_derivation_stays_platform_first():
    """``resolved_shop_id`` 的派生顺序**保持** platform_shop_id > shop_account_id > id。

    语义层输出的 ``shop_id`` = ``COALESCE(canonical.platform_shop_id, resolved_shop_id)``,
    看板显示名的 JOIN 拿它跟 ``core.dim_shops.shop_id`` 对齐。
    一旦把这里的 COALESCE 顺序也倒过来, dim_shops 的键与事实表的键就对不上。
    """
    for rel in BOTH_CANDIDATE_ASSETS:
        text = _strip_sql_comments(_read(rel))
        derived = re.search(
            r"COALESCE\(\s*NULLIF\(TRIM\(COALESCE\(sa\.platform_shop_id, ''\)\), ''\),\s*"
            r"NULLIF\(TRIM\(COALESCE\(sa\.shop_account_id, ''\)\), ''\),\s*"
            r"sa\.id::text\s*\) AS resolved_shop_id",
            text,
            re.S,
        )
        assert derived is not None, rel


def test_dim_shop_id_derivation_matches_the_semantic_layer():
    """``resolve_dim_shop_id`` 必须与候选集的派生口径**逐字一致**。

    不一致 ⇒ 看板显示名的 JOIN 永远落空 ⇒ 维度表等于没有。
    """
    from backend.services.shop_sync_service import resolve_dim_shop_id

    class _Account:
        def __init__(self, platform_shop_id=None, shop_account_id=None, id=7):
            self.platform_shop_id = platform_shop_id
            self.shop_account_id = shop_account_id
            self.id = id

    assert resolve_dim_shop_id(_Account("1308200825", "sa_1")) == "1308200825"
    assert resolve_dim_shop_id(_Account(None, "sa_1")) == "sa_1"
    assert resolve_dim_shop_id(_Account("  ", "  ")) == "7"


# ---------------------------------------------------------------------------
# E. 部署: 口径改了必须**重建**物化副本, 光 REFRESH 不够
# ---------------------------------------------------------------------------


def test_realign_migration_exists_and_is_chained_to_the_head():
    text = _read(REALIGN_MIGRATION)
    assert 'revision = "current_schema_20261112_realign_identity_candidates_anchor"' in text
    assert (
        'down_revision = "current_schema_20261111_add_refresh_queue_domain_and_retry"' in text
    )


def test_realign_migration_rebuilds_the_materialized_copy():
    """副本的刷新语义是「存在则 REFRESH / 不存在则 CREATE」——
    REFRESH 只重算**数据**, 不换**定义** ⇒ 口径改了必须 DROP 重建。"""
    text = _read(REALIGN_MIGRATION)
    assert "DROP MATERIALIZED VIEW" in text
    assert CANDIDATES_MV_ASSET in text


def test_realign_migration_never_drops_cascade():
    """迁移**真正执行**的 SQL 里不得出现 CASCADE。

    断言看的是「会被执行的语句」, 而不是源码里出现的字样 ——
    注释与 docstring 里解释「为什么要避开 CASCADE」是正常叙述, 不是执行。
    """
    module = _load_migration_module()
    source = _read(REALIGN_MIGRATION)

    # ① 迁移里唯一的 DROP: 删副本的物化视图 —— 必须不带 CASCADE
    drop_statements = re.findall(r'_exec_sql\(\s*"([^"]*)"', source)
    assert drop_statements, "没找到删副本的 DROP 语句 —— 断言失效, 需要同步维护"
    for statement in drop_statements:
        assert "CASCADE" not in statement.upper(), statement

    # ② 原子层资产里的 DROP VIEW ... CASCADE 必须被剥掉
    stripped = module._strip_cascade_drop(_read(ANALYTICS_ATOMIC_ASSET))
    assert "DROP VIEW" not in stripped.upper()
    assert "CASCADE" not in stripped.upper()


def test_realign_migration_repoints_the_sql_function_before_dropping_the_copy():
    """解析函数是 ``LANGUAGE sql`` ⇒ 它对副本的依赖**被跟踪** ⇒ 必须先「让开」。

    让开的做法是**把函数体里的副本引用换成正本**(口径等价, 函数照常可用),
    而不是 ``DROP FUNCTION`` —— 后者会被
    ``semantic.fact_inventory_snapshot`` / ``fact_products_atomic`` /
    ``semantic.fact_services_atomic`` 这些依赖它的视图挡住, 直接报
    ``DependentObjectsStillExist``(live 开发库实测)。
    """
    text = _read(REALIGN_MIGRATION)
    assert "DROP FUNCTION" not in text, "别用 DROP FUNCTION —— 它有下游视图依赖"
    assert "to_source_view" in text
    assert "shop_identity_resolution_candidates_v2_mv" in text

    upgrade_body = text[text.index("def upgrade()") : text.index("def downgrade()")]
    assert upgrade_body.index("to_source_view=True") < upgrade_body.index(
        "DROP MATERIALIZED VIEW"
    ), "让开(改成读正本)必须发生在 DROP 副本之前"


def test_realign_migration_does_not_cascade_drop_the_atomic_views():
    """⚠️ ``analytics_atomic.sql`` 开头的 ``DROP VIEW ... CASCADE`` 会**连带删掉 10 个对象**。

    live 开发库实测: ``DROP VIEW IF EXISTS semantic.fact_analytics_atomic CASCADE``
    会 cascade 到物化视图 ``semantic.fact_analytics_atomic_mv`` + 4 个 ``mart.*``
    视图 + 5 个 ``api.business_overview_*`` 视图。

    本迁移只换引用、不改列 ⇒ 必须用 ``CREATE OR REPLACE VIEW``(保持视图 OID),
    并把资产里那句 DROP 去掉。

    这里断言的是**行为**: 把真实资产喂给迁移的剥除函数, 看结果里还有没有
    ``DROP VIEW`` / ``CASCADE`` —— 而不是去源码里找字符串。
    """
    module = _load_migration_module()
    asset = _read(ANALYTICS_ATOMIC_ASSET)
    assert "DROP VIEW" in asset.upper(), "资产里本来就没有 DROP VIEW —— 本用例的前提变了"

    stripped = module._strip_cascade_drop(asset)
    assert "DROP VIEW" not in stripped.upper(), "DROP VIEW ... CASCADE 没被剥掉"
    assert "CASCADE" not in stripped.upper()

    # 迁移必须真的走这个剥除逻辑（而不是另写一份）
    assert "_strip_cascade_drop" in _read(REALIGN_MIGRATION)


def test_realign_migration_guards_content_fingerprint():
    """迁移必须做「副本 == 正本」的内容指纹比对, 不一致就回滚。"""
    text = _read(REALIGN_MIGRATION)
    assert "_fingerprint" in text
    assert "md5(" in text
    assert "拒绝继续" in text
