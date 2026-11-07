import re
from pathlib import Path


def _compact(text: str) -> str:
    """去掉全部空白。

    契约断言关心的是代码结构，不是 black 的换行/缩进排版；压成单行后
    纯格式化改动不会打断断言。
    """
    return re.sub(r"\s+", "", text)


def test_raw_data_importer_dynamic_column_update_deduplicates_normalized_assignments():
    source = Path("backend/services/raw_data_importer.py").read_text(encoding="utf-8")
    compact = _compact(source)

    # 一个规范化列名可能对应多个原始列名 ⇒ 必须成组收集，逐个取值
    assert (
        "column_mapping.setdefault(normalized_col,[]).append(original_col)" in compact
    )
    assert re.search(
        r"for\s*\(\s*normalized_col,\s*original_columns,?\s*\)\s*in\s*column_mapping\.items\(\)\s*:",
        source,
    )
    assert "set_clauses.append(f'\"{normalized_col}\"=:{normalized_col}')" in compact
    # 反向遍历（一个原始列对应一个规范化列）会把同名列写坏
    assert "fororiginal_col,normalized_colincolumn_mapping.items()" not in compact


def test_raw_data_importer_does_not_treat_upsert_updates_as_data_loss():
    source = Path("backend/services/raw_data_importer.py").read_text(encoding="utf-8")

    assert "if expected_inserted > 0 and not is_upsert:" in source
