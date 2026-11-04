"""契约测试：语义层的数值转换必须带「合法性校验」。

背景
----
`NULLIF(REGEXP_REPLACE(x, '[^0-9.-]', '', 'g'), '')::numeric` 这套写法，
对平台导出里的「无数据」占位符（`'--'`）会得到 `'--'` —— 非空 ⇒ 走进 ::numeric ⇒
`invalid input syntax for type numeric: "--"` ⇒ **整条查询直接报错**。

analytics 层在 v7.13.2 补过正则校验，但 products / services / inventory 三层**都还没补**。

实测
----
`b_class.fact_tiktok_services_agent_monthly` 有 137 行满意度是 `'--'`
⇒ `SELECT sum(satisfaction) FROM semantic.fact_services_atomic` 直接炸。

⚠️ PG 的列裁剪会掩盖它：`SELECT count(*)` 正常（469 行），一读数值列才炸
⇒ **「count(*) 通过」不代表视图健康**。
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

# 三层以前没做校验的语义视图
GUARDED_ASSETS = (
    "sql/semantic/products_atomic.sql",
    "sql/semantic/services_atomic.sql",
    "sql/semantic/inventory_snapshot.sql",
)

VALID_NUMERIC_RE = r"^-?(?:\d+(?:\.\d*)?|\.\d+)$"


def _read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


@pytest.mark.parametrize("relative", GUARDED_ASSETS)
def test_numeric_conversion_has_validity_guard(relative: str) -> None:
    """每处 ::numeric 之前都必须先过一次正则合法性校验。"""
    body = _read(relative)
    assert VALID_NUMERIC_RE in body, f"{relative} 缺少数值合法性校验正则"

    # 每个 ::numeric 都必须由一个带 ~ 校验的 WHEN 守卫
    cast_count = body.count("::numeric")
    guard_count = body.count(f"~ '{VALID_NUMERIC_RE}'")
    assert cast_count > 0, f"{relative} 没有数值转换"
    assert guard_count >= cast_count, (
        f"{relative} 有 {cast_count} 处 ::numeric 但只有 {guard_count} 处校验 —— "
        "存在裸 ::numeric，脏值一进来就崩"
    )


def _case_blocks(body: str) -> list[str]:
    """把文件切成一个个 CASE ... END 块（按大写关键字扫，够用即可）。"""
    blocks: list[str] = []
    index = 0
    length = len(body)
    while True:
        start = body.find("CASE", index)
        if start < 0:
            break
        depth = 0
        i = start
        while i < length:
            if body.startswith("CASE", i) and (i == 0 or not body[i - 1].isalnum()):
                depth += 1
                i += 4
                continue
            if body.startswith("END", i) and (i == 0 or not body[i - 1].isalnum()):
                depth -= 1
                i += 3
                if depth == 0:
                    break
                continue
            i += 1
        blocks.append(body[start:i])
        index = i + 3
    return blocks


@pytest.mark.parametrize("relative", GUARDED_ASSETS)
def test_no_bare_numeric_cast_without_guard(relative: str) -> None:
    """不允许出现「守卫之后又单独 ::numeric」之外的裸转换。

    守卫写法固定为：
        WHEN NULLIF(<cleaned>, '') ~ '<regex>' THEN NULLIF(<cleaned>, '')::numeric
    """
    body = _read(relative)
    guarded_blocks = 0
    for block in _case_blocks(body):
        if "::numeric" not in block:
            continue
        assert f"~ '{VALID_NUMERIC_RE}'" in block, (
            f"{relative} 有一个带 ::numeric 的 CASE 块没有合法性校验 —— "
            "脏值（如 '--'）一进来就崩"
        )
        guarded_blocks += 1
    assert guarded_blocks > 0, f"{relative} 没有找到数值转换块"


@pytest.mark.parametrize("relative", GUARDED_ASSETS)
def test_invalid_value_falls_to_null_not_zero(relative: str) -> None:
    """非法值必须落 NULL（不是 0）：「取不到」和「真的是零」必须可区分。"""
    body = _read(relative)
    assert "ELSE NULL" in body
    # ELSE 分支不能是 0
    assert "ELSE 0" not in body


def test_services_satisfaction_is_guarded() -> None:
    """服务层的满意度是这次崩溃的现场，必须被守住。"""
    body = _read("sql/semantic/services_atomic.sql")
    assert "AS satisfaction" in body
    case_start = body.rfind("CASE", 0, body.index("satisfaction_raw IS NULL"))
    window = body[case_start:]
    window = window[: window.index("END AS satisfaction")]
    assert f"~ '{VALID_NUMERIC_RE}'" in window
