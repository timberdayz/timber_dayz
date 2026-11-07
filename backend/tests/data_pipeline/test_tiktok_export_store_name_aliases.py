"""TikTok「导出店名」别名补录的契约测试（2026-11-13）。

背景
----
TikTok 有一批导出的「店铺」列写的是**英文商场名**（``DAONE Mall`` 这种）,
而店铺账号档案里存的是「品牌 + 地区」（``FIORO SG``）⇒ 身份解析匹配不上。

实测(live 开发库): 2026-02 ~ 2026-05 的 **720 行** TikTok 流量
(108,764 UV) 全部落 ``unmatched_shop_label`` —— 看板上看不见。
补 6 条别名即可把这批行归位。

这些用例守的是**四条**不变量:

A. **归一化规则只有一个真源** —— 迁移里硬编码的别名键、迁移在 SQL 里现算的键、
   以及 ``normalize_alias_key`` 三者必须一致。任一漂移 ⇒ 「认领了却匹配不上」
   (候选集只按 ``alias_normalized`` 匹配, SQL 侧不做第二次规范化)。
B. **只补别名, 不动账号档案** —— 账号档案里的 ``store_name`` 是看板显示名的来源,
   改它会动到所有历史行的显示口径。
C. **别名键必须干净** —— 不能已经被别的账号认领(会让候选数变 2 ⇒ 整片落 unknown),
   也不能撞上某个账号的平台店铺编号(会被候选集的 ``NOT EXISTS`` 守护静默排除)。
D. **迁移后必须刷的物化视图不能漏** —— 别名表是实时的, 副本与原子层是快照;
   只插别名不刷 ⇒ 新别名不生效。

⚠️ 所有针对「SQL 文本」的断言都只看**可执行部分** —— 注释里出现同样的字样
不算数(否则解释性注释会把断言带偏)。
"""

import importlib.util
import re
from pathlib import Path

from backend.utils.text_normalization import normalize_alias_key


REPO_ROOT = Path(__file__).resolve().parents[3]

ALIAS_MIGRATION = (
    "current_migrations/versions/20261116_add_tiktok_export_store_name_aliases.py"
)

#: 迁移里那 6 条别名的期望映射 —— 与迁移模块的数据保持一致。
EXPECTED_ALIASES = (
    ("DAONE Mall", "daonemall", "tiktok_sg_daone_mall_local", "SG"),
    ("DAWIE Mall", "dawiemall", "tiktok_my_dawie_mall_local", "MY"),
    ("Explorers Mall", "explorersmall", "tiktok_ph_explorers_mall_local", "PH"),
    ("Malaysia(Flora Mall)", "malaysiafloramall", "tiktok_my_flora_mall_local", "MY"),
    (
        "Philippines(DAJU Mall)",
        "philippinesdajumall",
        "tiktok_ph_daju_mall_local",
        "PH",
    ),
    ("Singapore(HX Home)", "singaporehxhome", "tiktok_sg_hx_home_local", "SG"),
)

#: 归一化规则的探针值 —— 除了 6 条真实别名, 还要带上**会被前缀/分隔符影响**的边角。
PROBE_VALUES = (
    "DAONE Mall",
    "DAWIE Mall",
    "Explorers Mall",
    "Malaysia(Flora Mall)",
    "Philippines(DAJU Mall)",
    "Singapore(HX Home)",
    "  DAONE Mall  ",
    "tiktok shop DAONE Mall",
    "TikTok Shop DAONE Mall",
    "TK新加坡1店",
    "Shopee3C店",
    "Malaysia/Flora Mall",
    "Malaysia_Flora-Mall",
    "Shopee Malaysia(Flora Mall)",
    "daone mall",
)


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def _load_migration_module():
    """把迁移当成普通模块导入 —— 这样可以直接调用它的纯函数做**行为**断言。"""
    path = REPO_ROOT / ALIAS_MIGRATION
    spec = importlib.util.spec_from_file_location(
        "add_tiktok_export_store_name_aliases_migration", path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sql_regex_literals(sql_text: str) -> dict[str, str]:
    """取出 SQL 里的两条正则规则。

    只取**成对出现**的「看起来像正则」的字面量: 含 ``^`` / ``[`` / ``+`` 之一。
    这样不会把 ``'tiktok'`` 这种普通字符串也当成规则。
    """
    literals = re.findall(r"'([^']*)'", sql_text)
    prefix = [literal for literal in literals if literal.startswith("^")]
    separator = [
        literal
        for literal in literals
        if "[" in literal and "+" in literal and not literal.startswith("^")
    ]
    assert len(prefix) == 1, "迁移里应当有且只有一条平台前缀规则，实际：{0}".format(
        prefix
    )
    assert len(separator) == 1, "迁移里应当有且只有一条分隔符规则，实际：{0}".format(
        separator
    )
    return {"prefix": prefix[0], "separator": separator[0]}


def _to_python_regex(literal: str) -> str:
    """把 SQL 正则字面量转成 Python 正则。

    PostgreSQL 的 POSIX 字符类 ``[:space:]`` ≡ Python 的 ``\\s`` —— 这里做等价替换。
    （不替换的话 Python 会把 ``[[:space:]_()/-]`` 当成「嵌套集」, 静默丢掉空白。）
    """
    return re.sub(r"\[:space:\]", r"\\s", literal)


def _sql_normalize(sql_text: str, value: str) -> str:
    """按迁移里那套 SQL 规则在 Python 侧**模拟**一次归一化。

    做法: 把 SQL 的两个正则字面量取出来, 转成 Python 正则, 按迁移 SQL 的顺序
    (剥前缀 → 小写 → 删分隔符 → 去空白)套一遍。
    """
    literals = _sql_regex_literals(sql_text)
    prefix_pattern = _to_python_regex(literals["prefix"])
    separator_pattern = _to_python_regex(literals["separator"])

    text = value.strip()
    text = re.sub(prefix_pattern, "", text, count=1, flags=re.IGNORECASE)
    text = text.strip().lower()
    text = re.sub(separator_pattern, "", text)
    return text.strip()


# ---------------------------------------------------------------------------
# A. 归一化规则只有一个真源
# ---------------------------------------------------------------------------


def test_migration_alias_keys_match_the_python_normalizer():
    """迁移里硬编码的别名键必须等于 ``normalize_alias_key(alias_value)``。

    归一化的唯一真源是 ``backend/utils/text_normalization.py::normalize_alias_key``;
    候选集只按存好的 ``alias_normalized`` 匹配, **SQL 侧不做第二次规范化** ⇒
    两边不一致就是「认领了却匹配不上」。
    """
    module = _load_migration_module()
    for alias_value, alias_normalized, _sid, _region in module._TIKTOK_EXPORT_ALIASES:
        assert normalize_alias_key(alias_value) == alias_normalized, alias_value


def test_migration_sql_normalization_matches_the_python_normalizer():
    """迁移里那套 **SQL 归一化规则**必须与 Python 侧逐条一致。

    这是跨层校验的第二道: 光对齐硬编码值不够 —— SQL 表达式本身也可能漂移
    (比如有人把分隔符类改窄了), 那会导致「存的是 A、算出来是 B」。
    """
    module = _load_migration_module()
    sql_text = module._NORMALIZE_SQL
    for probe in PROBE_VALUES:
        assert _sql_normalize(sql_text, probe) == normalize_alias_key(probe), probe


def test_migration_declares_the_expected_alias_rows():
    """迁移里那 6 条别名必须与本用例锁定的映射完全一致。"""
    module = _load_migration_module()
    assert tuple(module._TIKTOK_EXPORT_ALIASES) == EXPECTED_ALIASES


def test_alias_values_are_the_raw_export_labels():
    """``alias_value`` 必须存**导出里的原样标签**。

    存原样的理由: 出问题时能直接拿它去导出文件里搜。归一化键存在
    ``alias_normalized`` 那一列, 不污染可读列。
    """
    module = _load_migration_module()
    for alias_value, _normalized, _sid, _region in module._TIKTOK_EXPORT_ALIASES:
        assert alias_value == alias_value.strip()
        assert normalize_alias_key(alias_value) != alias_value or alias_value.islower()


# ---------------------------------------------------------------------------
# B. 只补别名, 不动账号档案
# ---------------------------------------------------------------------------


def test_migration_never_writes_to_shop_accounts():
    """迁移**不得**写 ``core.shop_accounts``。

    账号档案里的 ``store_name`` 是看板显示名的来源(``core.dim_shops.shop_name``),
    改它会动到所有历史行的显示口径 —— 本次只补别名。
    """
    source = _read(ALIAS_MIGRATION)
    executable = "\n".join(
        line for line in source.splitlines() if not line.strip().startswith("#")
    )
    for statement in re.findall(r"INSERT INTO\s+([\w.]+)", executable, re.IGNORECASE):
        assert statement.lower() == "core.shop_account_aliases", statement
    assert "UPDATE core.shop_accounts" not in executable
    assert "DELETE FROM core.shop_accounts" not in executable


def test_alias_type_is_claimed_not_former_name():
    """别名类型用 ``claimed`` —— 不是 ``former_name``。

    ``former_name`` 表示「曾用名」(改名流程写的), 语义不对: 这里不是店改名了,
    而是**导出文件里的叫法**与账号档案里的叫法不同。
    """
    module = _load_migration_module()
    assert module.ALIAS_TYPE == "claimed"
    assert module.ALIAS_TYPE != "former_name"


# ---------------------------------------------------------------------------
# C. 别名键必须干净
# ---------------------------------------------------------------------------


def test_migration_fails_closed_on_alias_key_conflicts():
    """迁移必须**在写之前**挡住「别名键会引发歧义」的两种情况。

    ① 同一串键已经被别的账号认领 —— 候选集按 ``platform_code`` +
       ``identity_value_normalized`` 匹配, **不看区域** ⇒ 两家共用一串键
       ⇒ 候选数变 2 ⇒ 整片行落 unknown;
    ② 撞上某个账号的平台店铺编号 —— 候选集的别名路有 ``NOT EXISTS`` 守护,
       撞上了这条别名会被**静默排除** ⇒ 认领了却匹配不上。
    """
    module = _load_migration_module()
    assert hasattr(module, "_alias_key_conflicts")
    assert hasattr(module, "_assert_targets_resolvable")
    source = _read(ALIAS_MIGRATION)
    assert "_alias_key_conflicts()" in source
    assert "拒绝继续" in source


def test_migration_insert_is_idempotent():
    """插入必须幂等 —— 重跑迁移不能报唯一约束冲突, 也不能插重复行。"""
    source = _read(ALIAS_MIGRATION)
    executable = "\n".join(
        line for line in source.splitlines() if not line.strip().startswith("#")
    )
    assert "ON CONFLICT DO NOTHING" in executable.upper()


def test_downgrade_only_removes_the_rows_this_migration_inserted():
    """回滚必须**只删本次插进去的行**。

    靠 ``source`` 标记 + 精确的别名键定位 ⇒ 不会误伤运维手工加的别名。
    """
    module = _load_migration_module()
    source = _read(ALIAS_MIGRATION)
    downgrade_body = source[source.index("def downgrade()") :]
    assert "source = :source" in downgrade_body
    assert module.ALIAS_SOURCE in source


# ---------------------------------------------------------------------------
# D. 迁移后必须刷的物化视图不能漏
# ---------------------------------------------------------------------------


def test_required_refresh_targets_cover_the_snapshot_chain():
    """别名表是实时的, 但副本与原子层是**快照** ⇒ 必须列出要刷的目标。

    漏一个 ⇒ 那条链路还在用建库时的旧快照, 新别名对它不生效。
    """
    module = _load_migration_module()
    targets = set(module._REQUIRED_REFRESH_TARGETS)
    required = {
        "semantic.shop_identity_resolution_candidates_v2_mv",
        "semantic.fact_analytics_atomic_mv",
        "semantic.fact_analytics_monthly_atomic_mv",
        "semantic.fact_orders_atomic_mv",
        "semantic.fact_orders_monthly_atomic_mv",
        "semantic.fact_products_atomic_mv",
    }
    assert required <= targets, required - targets


def test_required_refresh_targets_exist_in_the_refresh_registry():
    """要刷的目标必须**在刷新注册表里登记过** —— 否则刷新管道根本不认它。

    这里用「注册表里的依赖关系」反推该链的完整集合, 避免本用例与注册表脱节。
    """
    from backend.services.data_pipeline.refresh_registry import SQL_TARGET_PATHS

    module = _load_migration_module()
    for target in module._REQUIRED_REFRESH_TARGETS:
        assert target in SQL_TARGET_PATHS, target


# ---------------------------------------------------------------------------
# E. 迁移链
# ---------------------------------------------------------------------------


def test_migration_is_chained_to_the_head():
    """迁移必须接在上一条 current_schema 迁移之后。

    ⚠️ ``down_revision`` 指向的是**当时** main 上的链尾；别的会话会往链上追加迁移，
    所以合并前必须**重新对一次 main 的链尾**（否则 alembic 会出现两个头，
    ``run_current_schema_migrations.py`` 的 ``walk_revisions(head="heads")`` 会出问题）。
    """
    module = _load_migration_module()
    assert (
        module.revision
        == "current_schema_20261116_add_tiktok_export_store_name_aliases"
    )
    assert module.down_revision.startswith("current_schema_")
