"""前后端标准字段口径**一致性**守护。

[*] 批次 D 之后, 口径发生了根本变化:
    前端**不再手抄**一份标准字段字典, 改成「接口为权威 + 生成快照兜底」。

⇒ 所以这个测试断言的不再是「两份手抄字典逐字相同」(那份副本已经删了),
    而是新口径下真正要守住的三条:

    1. 前端**不得再出现**手抄的标准字段副本(否则又变成两份口径);
    2. 前端注册表**必须从接口取**(API-1);
    3. 兜底快照是**生成物**, 它的字段键集合与后端注册表一致。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from backend.services.semantic_field_registry import SEMANTIC_FIELD_META

FRONTEND_UTILS = (
    Path(__file__).resolve().parents[2]
    / "frontend"
    / "src"
    / "domains"
    / "data_platform"
    / "utils"
)


def _snapshot_fields() -> dict[str, dict]:
    """从生成快照里读出「字段键 -> 字段定义」。"""
    source = (FRONTEND_UTILS / "semanticFieldRegistrySnapshot.js").read_text(
        encoding="utf-8"
    )
    match = re.search(
        r"export const SEMANTIC_FIELD_REGISTRY_SNAPSHOT = (?P<body>\{.*?\n\})",
        source,
        re.S,
    )
    assert match, "前端标准字段快照 export 未找到"
    payload = json.loads(match.group("body"))
    fields = payload.get("fields")
    assert isinstance(fields, list) and fields, "前端快照里没有 fields 列表"
    return {str(item["semantic_key"]): item for item in fields}


def test_frontend_has_no_handwritten_standard_field_copy():
    """前端**不得**再手抄一份标准字段字典(批次 D 的核心整改之一)。"""
    header_bindings = (FRONTEND_UTILS / "headerBindings.js").read_text(encoding="utf-8")
    assert not re.search(
        r"export const SEMANTIC_FIELD_META\s*=",
        header_bindings,
    ), "headerBindings.js 不应再导出 SEMANTIC_FIELD_META(前端只保留一份口径)"

    for path in FRONTEND_UTILS.glob("*.js"):
        source = path.read_text(encoding="utf-8")
        if path.name == "semanticFieldRegistrySnapshot.js":
            continue
        assert not re.search(
            r"export const SEMANTIC_FIELD_META\s*=",
            source,
        ), f"{path.name} 不应再导出 SEMANTIC_FIELD_META"


def test_frontend_registry_is_loaded_from_api():
    """标准字段注册表必须**从接口取**(API-1), 快照只作兜底。"""
    loader = (FRONTEND_UTILS / "semanticFieldRegistryApi.js").read_text(
        encoding="utf-8"
    )
    assert "getSemanticFieldDefinitions" in loader, "前端注册表应通过 API-1 接口加载"
    assert "hydrateSemanticFieldRegistry" in loader, "接口数据应灌进前端注册表"
    assert "source: 'api'" in loader, "接口来源必须被标记出来(快照只是兜底)"


def test_frontend_snapshot_keys_match_backend_contract():
    """兜底快照(生成物)的字段键集合 == 后端注册表的键集合。"""
    snapshot_fields = _snapshot_fields()
    assert set(snapshot_fields) == set(SEMANTIC_FIELD_META)
