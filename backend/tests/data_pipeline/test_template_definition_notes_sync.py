# -*- coding: utf-8 -*-
"""决策资产投影时 ``notes`` 必须跟着进库 —— 守护测试。

背景
----
2026-11-14 生产实跑(库存维度投影到 v4)后发现: 投影后 ``--check`` 守卫仍然报差异,
而且**只差 ``notes`` 一项**::

    [DIFF] miaoshou/inventory/snapshot/-/-
            - notes: 定义="... 2026-11-14 业务拍板: ..."  库内="DSS架构重构(v4.6.0)+ ..."

根因
----
:meth:`FieldMappingTemplateService.save_template` **不写 ``notes`` 列**
(它的参数里压根没有 ``notes``) ⇒ 投影完库里的 notes 仍是旧版本的内容。

而 ``notes`` 在 :data:`scripts.template_definitions.DECISION_FIELDS` 里**参与比对**
⇒ 设计意图就是「notes 也要镜像」, 只是发布服务漏了这个参数。

⇒ 后果: 定义守卫 ``--check`` 永远红 ⇒ 「仓库定义 ↔ 库内实例」这条闭环断的。

本文件锁住三件事:

1. ``changed_decision_fields`` 能区分「只差 notes」与「真的变了口径」;
2. 投影路径必须**同步 notes**;
3. 差异只有 notes 时**不发布新版本**(避免版本号无意义地膨胀)。
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFINITIONS_DIR = REPO_ROOT / "templates" / "definitions"
APPLY_SCRIPT_PATH = REPO_ROOT / "scripts" / "apply_template_definitions.py"


def _load_apply_script():
    """按文件路径加载投影脚本(它是运维脚本, 不是包)。"""
    spec = importlib.util.spec_from_file_location(
        "apply_template_definitions", APPLY_SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# 1. 字段级差异接口
# ---------------------------------------------------------------------------


def test_changed_decision_fields_detects_notes_only_difference():
    """只改 ``notes`` 时, 差异字段必须**只有** ``notes``。"""
    from scripts.template_definitions import changed_decision_fields

    base: Dict[str, Any] = {
        "platform": "miaoshou",
        "data_domain": "inventory",
        "granularity": "snapshot",
        "header_columns": ["*商品SKU", "仓库"],
        "deduplication_fields": ["*商品SKU", "仓库"],
        "core_fields": [{"raw_name": "*商品SKU", "required": True, "in_hash": True}],
        "notes": "库里的旧说明",
    }
    changed = dict(base, notes="仓库里的新说明")

    assert changed_decision_fields(changed, base) == ["notes"]
    assert changed_decision_fields(base, base) == []


def test_changed_decision_fields_detects_real_caliber_change():
    """改去重字段表时, 差异字段里**必须有** ``deduplication_fields``。"""
    from scripts.template_definitions import changed_decision_fields

    base: Dict[str, Any] = {
        "platform": "miaoshou",
        "data_domain": "inventory",
        "granularity": "snapshot",
        "deduplication_fields": ["*商品SKU", "仓库"],
        "notes": "同一句话",
    }
    changed = dict(base, deduplication_fields=["*商品SKU"])

    fields = changed_decision_fields(changed, base)
    assert "deduplication_fields" in fields
    assert "notes" not in fields


# ---------------------------------------------------------------------------
# 2. 投影必须同步 notes
# ---------------------------------------------------------------------------


class _FakeDb:
    """最小 AsyncSession 替身: 只记 execute/commit。"""

    def __init__(self) -> None:
        self.statements: List[str] = []
        self.params: List[Dict[str, Any]] = []
        self.commits = 0

    async def execute(self, statement: Any, params: Any = None) -> None:
        self.statements.append(str(statement))
        self.params.append(dict(params or {}))

    async def commit(self) -> None:
        self.commits += 1


def test_sync_notes_writes_notes_column_and_commits():
    """``_sync_notes`` 必须 UPDATE notes 列并提交。"""
    module = _load_apply_script()
    db = _FakeDb()

    asyncio.run(module._sync_notes(db, 367, "新的说明文字"))

    assert len(db.statements) == 1, "应当只执行一条 UPDATE"
    statement = db.statements[0]
    assert "UPDATE" in statement.upper()
    assert "core.field_mapping_templates" in statement
    assert "notes" in statement
    assert db.params[0]["notes"] == "新的说明文字"
    assert db.params[0]["id"] == 367
    assert db.commits == 1, "notes 写完必须提交"


def test_sync_notes_skips_when_definition_has_no_notes():
    """定义里没写 notes ⇒ **不动**库里的 notes(不抹掉运维备注)。"""
    module = _load_apply_script()
    db = _FakeDb()

    asyncio.run(module._sync_notes(db, 367, None))

    assert db.statements == [], "定义没写 notes 时不应执行任何写操作"
    assert db.commits == 0


def test_apply_path_syncs_notes_after_publish():
    """投影路径必须调用 ``_sync_notes``(静态检查: 防止以后被人删掉)。"""
    text = APPLY_SCRIPT_PATH.read_text(encoding="utf-8")
    assert "_sync_notes(" in text, "投影路径没有同步 notes"
    assert (
        'await _sync_notes(db, int(result["template_id"])' in text
    ), "发布新版本后必须同步新版本的 notes"


def test_notes_only_difference_does_not_publish_new_version():
    """差异只有 notes 时, 必须**原地补**, 不发新版本。"""
    text = APPLY_SCRIPT_PATH.read_text(encoding="utf-8")
    assert '== ["notes"]' in text, "缺少「只差 notes」的判定分支"
    assert "未发布新版本" in text, "notes-only 分支应明确不发布新版本"


def test_save_template_really_has_no_notes_parameter():
    """记录这个约束: 发布服务的参数里**没有** notes ⇒ 必须单独补。

    如果将来 ``save_template`` 真的加了 notes 参数, 这条会失败 ——
    那时应该改成直接把 notes 传进去, 而不是继续走独立 UPDATE。
    """
    text = (
        REPO_ROOT / "backend" / "services" / "field_mapping_template_service.py"
    ).read_text(encoding="utf-8")
    start = text.index("async def save_template(")
    signature = text[start : text.index(") -> Dict[str, Any]:", start)]
    assert "notes" not in signature, (
        "save_template 已经有 notes 参数了 —— 可以直接传参, "
        "不必再走独立的 UPDATE 补丁"
    )


# ---------------------------------------------------------------------------
# 3. 定义文件里每个维度都得有 notes
# ---------------------------------------------------------------------------


def test_every_definition_has_notes():
    """所有维度都必须写 notes。

    为什么
    ------
    镜像语义是「仓库定义是 SSOT」⇒ 定义里没写 notes 时, 投影脚本会**保持库内原值**
    ⇒ 守卫会一直报 notes 差异 ⇒ 闭环断的。

    ⇒ 定义侧必须每份都写 notes(哪怕只是「本维度无特殊说明」)。
    """
    missing: List[str] = []
    for path in sorted(DEFINITIONS_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not str(payload.get("notes") or "").strip():
            missing.append(path.name)

    assert not missing, f"这些维度没写 notes: {missing}"
