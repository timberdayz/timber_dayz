"""SKU ↔ SPU **归属关系**的时态投影（2026-11-12）。

背景
----
``core.bridge_spu_sku`` 是一张**带生效区间**的关联表
（``effective_from`` / ``effective_to`` / ``binding_status``）——
「SKU 属于哪个 SPU」**不是 SKU 身上的一个字段**，
而是「一段归属关系在今天的落点」。

⇒ 换款 = 旧关系归档（``effective_to`` 落日期、状态转 historical）
  + 新关系生效（``effective_from`` 落日期）。
⇒ 只投影「今天的落点」而不带生效日，运营就看不到
  「这个货是什么时候挂到这个款上的」「换过几次款」。

本文件锁定：**归属的投影必须带生效日**，且投影逻辑只有一处定义
（律 1「真源只能一个」）。

⚠️ 判定「什么关系算当前有效」的口径也在本文件里定义一次：
   ``binding_status == 'active'`` 且 ``effective_to IS NULL``。
"""

from __future__ import annotations

import ast
from datetime import date
from types import SimpleNamespace

import pytest

from backend.services.product_spu_binding import (
    CURRENT_BINDING_CONDITION_DESCRIPTION,
    current_binding_condition,
    is_current_binding,
    project_current_binding,
)


def _binding(**overrides):
    base = {
        "id": 1,
        "spu": "XH-FASHION-001",
        "sku_id": 7,
        "effective_from": date(2026, 3, 15),
        "effective_to": None,
        "binding_status": "active",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


# ---------------------------------------------------------------------------
# ① 「当前有效」的判定
# ---------------------------------------------------------------------------


def test_current_binding_is_active_and_not_ended():
    assert is_current_binding(_binding()) is True


def test_historical_binding_is_not_current():
    assert is_current_binding(_binding(binding_status="historical")) is False


def test_inactive_binding_is_not_current():
    assert is_current_binding(_binding(binding_status="inactive")) is False


def test_ended_binding_is_not_current():
    assert is_current_binding(_binding(effective_to=date(2026, 6, 1))) is False


def test_current_binding_criterion_is_documented_once():
    """判定口径必须写在纸上 —— 免得各处口头相传。"""
    assert "active" in CURRENT_BINDING_CONDITION_DESCRIPTION
    assert "effective_to" in CURRENT_BINDING_CONDITION_DESCRIPTION


# ---------------------------------------------------------------------------
# ② 投影
# ---------------------------------------------------------------------------


def test_projection_carries_the_spu_and_the_effective_date():
    """投影必须同时给出「挂在哪个款」与「从哪天开始挂」。"""
    projected = project_current_binding(_binding())

    assert projected["spu"] == "XH-FASHION-001"
    assert projected["spu_effective_from"] == date(2026, 3, 15)


def test_projection_of_a_missing_binding_is_empty():
    """没有当前归属 ⇒ 两个字段都是空，而不是编一个出来。"""
    projected = project_current_binding(None)

    assert projected["spu"] is None
    assert projected["spu_effective_from"] is None


def test_projection_never_leaks_an_ended_or_historical_relation():
    """历史关系不得被当成当前归属投影出去。"""
    for binding in (
        _binding(binding_status="historical"),
        _binding(binding_status="inactive"),
        _binding(effective_to=date(2026, 6, 1)),
    ):
        projected = project_current_binding(binding)
        assert projected["spu"] is None
        assert projected["spu_effective_from"] is None


# ---------------------------------------------------------------------------
# ③ SQL 谓词：**同一口径**也必须只有一处定义
# ---------------------------------------------------------------------------


def _compiled_sql() -> str:
    """把真源给出的 SQL 条件渲染成可读的 SQL 文本。

    ⚠️ 必须用 ``literal_binds`` —— 否则状态值会渲染成绑定参数占位符
    （``%(binding_status_1)s``），看不到实际的值。
    """
    from sqlalchemy.dialects import postgresql

    dialect = postgresql.dialect()
    parts = [
        str(
            clause.compile(
                dialect=dialect, compile_kwargs={"literal_binds": True}
            )
        )
        for clause in current_binding_condition()
    ]
    return " ".join(parts)


def test_sql_condition_covers_status_and_effective_to():
    """SQL 条件必须同时含「状态是 active」与「没有到期日」两个语义。"""
    sql = _compiled_sql()

    assert "binding_status" in sql
    assert "effective_to" in sql
    assert "active" in sql
    assert "IS NULL" in sql.upper()


def test_sql_condition_matches_the_written_criterion():
    """SQL 条件与 :data:`CURRENT_BINDING_CONDITION_DESCRIPTION` 说的是同一件事。

    这是「写在纸上」的兑现：纸上那句话和代码里那句 SQL 必须对得上，
    否则纸就废了。
    """
    sql = _compiled_sql()

    assert "binding_status" in CURRENT_BINDING_CONDITION_DESCRIPTION
    assert "effective_to" in CURRENT_BINDING_CONDITION_DESCRIPTION
    # 纸上写的字段名，SQL 里必须都出现
    for token in ("binding_status", "effective_to"):
        assert token in sql


def test_sql_condition_is_reusable_as_where_args():
    """条件要能直接摊进 ``where(*...)`` —— 否则调用方就得再手抄一遍。"""
    clauses = current_binding_condition()

    assert isinstance(clauses, tuple)
    assert len(clauses) >= 2


# ---------------------------------------------------------------------------
# ④ 响应契约与接线
# ---------------------------------------------------------------------------


def test_sku_response_schema_exposes_the_binding_effective_date():
    """SKU 响应必须带 ``spu_effective_from`` —— 否则前端无从展示。"""
    from backend.schemas.product_center import SkuItem

    fields = SkuItem.model_fields

    assert "spu_effective_from" in fields
    assert fields["spu_effective_from"].is_required() is False


def test_router_projects_the_binding_through_the_true_source():
    """路由必须调用真源的投影函数，不能自己拼 ``spu`` 字段。"""
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2]
        / "backend/domains/business/routers/product_center.py"
    ).read_text(encoding="utf-8")

    assert (
        "from backend.services.product_spu_binding import" in source
    ), "路由必须从归属真源导入"
    assert "project_current_binding(" in source, "路由必须调用真源的投影函数"


def test_frontend_shows_the_binding_effective_date():
    """前端必须把「当前归属自哪天起」显示出来。"""
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2]
        / "frontend/src/domains/business/views/ProductCenter.vue"
    ).read_text(encoding="utf-8")

    assert "spu_effective_from" in source, "前端未展示归属生效日"


# ---------------------------------------------------------------------------
# ⑤ 全仓库收敛：不得再手抄「当前有效」的判定
# ---------------------------------------------------------------------------

#: **生产运行时代码**里不许把归属状态写死成字面量。
#:
#: ⚠️ 范围只含生产目录：测试 fixture 造数据、历史迁移（**已经落库**，
#:    改写会让迁移链与已落库的历史对不上）、根目录冒烟脚本都不在范围内。
#:    真正会**写坏库**的是运行时代码 ⇒ 守住那里就够。
_PRODUCTION_DIRS = (
    "backend/domains",
    "backend/services",
    "modules/core",
    "scripts",
)

#: 允许出现该字面量的文件（真源本身）。
_ALLOWED_HAND_COPIES = {
    "backend/services/product_spu_binding.py",  # 真源本身
}

#: 扫描时跳过的目录名。
#:
#: * ``.worktrees`` —— 其它分支的 git worktree，是**另一个代码副本**，
#:   由各自的分支负责收敛，不该让当前分支的守护测试替它们把关。
#: * ``.git`` / ``.venv`` / ``node_modules`` / ``__pycache__`` —— 非源码。
_SKIPPED_DIR_NAMES = {
    ".git",
    ".worktrees",
    ".venv",
    "node_modules",
    "__pycache__",
}


def _has_hardcoded_binding_status(source: str) -> bool:
    """扫 Python **代码**里把归属状态写死成字面量的地方。

    ⚠️ 用 :mod:`tokenize` 而不是正则 ——
       注释、文档字符串、raw SQL 片段里的 ``binding_status='active'``
       不该被当成「Python 层面的写死」
       （历史迁移里就有一份 raw SQL，那是**已落库**的既定事实，不能改）。
    """
    import io
    import tokenize

    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError):
        return False

    skip = (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.COMMENT)
    for index, token in enumerate(tokens):
        if token.type != tokenize.NAME or token.string != "binding_status":
            continue
        op_index = index + 1
        while op_index < len(tokens) and tokens[op_index].type in skip:
            op_index += 1
        if op_index >= len(tokens):
            continue
        op = tokens[op_index]
        if op.type != tokenize.OP or op.string not in ("=", "=="):
            continue
        literal_index = op_index + 1
        while literal_index < len(tokens) and tokens[literal_index].type in skip:
            literal_index += 1
        if literal_index >= len(tokens):
            continue
        literal = tokens[literal_index]
        if literal.type != tokenize.STRING:
            continue
        try:
            value = ast.literal_eval(literal.string)
        except (ValueError, SyntaxError):
            continue
        if value in {"active", "inactive", "historical"}:
            return True
    return False


def _scan_hand_copies():
    """扫出所有把归属状态写死成字面量的**生产**文件。

    ⇒ 只要有人绕过真源另写一份判定，这份清单就会变长 ⇒ 测试变红。
    """
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    hits = []
    for directory in _PRODUCTION_DIRS:
        for path in (repo_root / directory).rglob("*.py"):
            if any(part in _SKIPPED_DIR_NAMES for part in path.parts):
                continue
            relative = path.relative_to(repo_root).as_posix()
            if relative in _ALLOWED_HAND_COPIES:
                continue
            source = path.read_text(encoding="utf-8", errors="ignore")
            if _has_hardcoded_binding_status(source):
                hits.append(relative)
    return sorted(hits)


def test_no_runtime_module_hand_copies_the_binding_status():
    """生产代码里不得把归属状态写死 —— 只许真源定义一次。"""
    hits = _scan_hand_copies()

    assert hits == [], (
        "以下生产文件把归属状态写死成了字面量，请改用 "
        "backend.services.product_spu_binding 里的常量与判定函数："
        + ", ".join(hits)
    )


def test_orm_current_binding_index_predicate_comes_from_the_ssot():
    """「一个 SKU 只有一条当前归属」的部分索引谓词也必须从真源渲染。"""
    from modules.core.db import BridgeSpuSku

    from backend.services.product_spu_binding import (
        render_current_binding_index_predicate,
    )

    index = next(
        item
        for item in BridgeSpuSku.__table__.indexes
        if item.name == "uq_bridge_spu_sku_current"
    )
    predicate = str(index.dialect_options["postgresql"]["where"])

    assert predicate == render_current_binding_index_predicate()
