# -*- coding: utf-8 -*-
"""
回归测试：金额/数量解析约定（add-metabase-sql-retain-amount-sign）

验证 docs/AMOUNT_QUANTITY_PARSING_CONVENTION.md 约定：
- 负号保留：如 '-100' -> -100
- 畸形数据兜底为 NULL：如 '', '-', '~~~', '.', '--5' 等 -> NULL
- 不因单格解析失败抛错

使用与 Metabase 模型相同的「先清洗再校验再 ::numeric」逻辑在 PostgreSQL 中执行，
断言输出符号与 NULL 行为符合约定。
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _get_db_session():
    """获取同步 DB Session，失败返回 None（调用方可 skip）。"""
    try:
        from backend.models.database import get_db
        return next(get_db())
    except Exception:
        return None


# 与 Metabase 模型一致的「单列解析」SQL：清洗 + 合法数值正则 + 安全 ::numeric
# 输入为 raw_val（来自 VALUES），输出为 parsed（NUMERIC 或 NULL）
_CONVENTION_PARSE_SQL = """
WITH inp(raw_val) AS (
    SELECT * FROM (VALUES
        ('-100'),
        ('100'),
        (''),
        ('-'),
        ('~~~'),
        ('.'),
        ('--5'),
        ('123.45'),
        ('-0.5'),
        ('1,234.56'),
        ('  -42  ')
    ) AS t(raw_val)
),
cleaned AS (
    SELECT
        raw_val,
        REGEXP_REPLACE(
            REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(raw_val, ''), ',', ''), ' ', ''), CHR(8212), ''), CHR(8211), ''),
            $$[^0-9.-]$$, '', 'g'
        ) AS c
    FROM inp
)
SELECT
    raw_val,
    CASE
        WHEN c ~ '^-?([0-9]+\\.[0-9]*|[0-9]*\\.[0-9]+|[0-9]+)$'
         AND c IS NOT NULL AND c != '' AND c != '-' AND c != '.'
        THEN c::NUMERIC
        ELSE NULL
    END AS parsed
FROM cleaned
ORDER BY raw_val NULLS LAST
"""


def test_amount_parsing_retains_sign_and_null_for_malformed():
    """给定含负金额或畸形值的 raw 样本，断言解析后符号保留、畸形为 NULL。"""
    session = _get_db_session()
    if session is None:
        pytest.skip("DB unavailable (backend.models.database.get_db); run with PostgreSQL")
    try:
        from sqlalchemy import text
        rows = session.execute(text(_CONVENTION_PARSE_SQL)).fetchall()
    finally:
        session.close()

    # 构建 raw_val -> expected 映射（None 表示期望 NULL）
    expected = {
        "-100": -100,
        "100": 100,
        "": None,
        "-": None,
        "~~~": None,
        ".": None,
        "--5": None,  # 多负号经正则后仍非法，约定为 NULL
        "123.45": 123.45,
        "-0.5": -0.5,
        "1,234.56": 1234.56,
        "  -42  ": -42,
    }

    assert len(rows) == len(expected), "SQL 返回行数与用例数不一致"
    for raw_val, parsed in rows:
        raw_str = raw_val if raw_val is not None else ""
        exp = expected.get(raw_str)
        assert exp is not None or raw_str in ("", "-", "~~~", ".", "--5"), f"未定义用例: {raw_str!r}"
        if exp is None:
            assert parsed is None, f"raw={raw_str!r} 期望 NULL，得到 {parsed}"
        else:
            assert parsed is not None, f"raw={raw_str!r} 期望 {exp}，得到 NULL"
            assert float(parsed) == exp, f"raw={raw_str!r} 期望 {exp}，得到 {parsed}"


def test_amount_parsing_convention_doc_exists():
    """约定文档存在且包含关键策略说明。"""
    doc = ROOT / "docs" / "AMOUNT_QUANTITY_PARSING_CONVENTION.md"
    assert doc.exists(), "docs/AMOUNT_QUANTITY_PARSING_CONVENTION.md 不存在"
    text = doc.read_text(encoding="utf-8")
    assert "事实层保留负号" in text or "保留负号" in text
    assert "NULL" in text and ("畸形" in text or "无法解析" in text)
