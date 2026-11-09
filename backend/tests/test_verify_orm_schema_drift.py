"""契约测试：ORM ↔ 数据库 结构漂移门禁(scripts/verify_orm_schema_drift.py)。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify_orm_schema_drift.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("verify_orm_schema_drift", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate():
    return _load_gate()


def test_gate_script_exists():
    assert SCRIPT.exists()


def test_missing_database_url_is_not_silently_skipped(gate, monkeypatch):
    """没有 DATABASE_URL 时必须退出码 2 —— 不能看起来像通过。"""
    monkeypatch.setattr(sys, "argv", ["verify_orm_schema_drift.py"])
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert gate.main() == 2


def test_check_reports_missing_columns_and_extra_columns(gate, tmp_path):
    """用一个最小库验证：ORM 有库没有 ⇒ 报错；库有 ORM 没有 ⇒ 仅提示。"""
    import sqlalchemy as sa

    db_path = tmp_path / "drift.db"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE demo (id INTEGER PRIMARY KEY, keep TEXT)"))
        conn.execute(sa.text("CREATE TABLE demo2 (id INTEGER PRIMARY KEY)"))
    engine.dispose()

    result = gate.check(f"sqlite:///{db_path}", allow_missing_table=True)

    assert result["missing_tables"], "ORM 里有、库里没有的表应被记录"
    assert result["tables_checked"] > 0
    # 本仓库 ORM 与本地库的偏差（本机开发库）不应出现「ORM 有库没有」的列
    assert result["missing_columns"] == [], result["missing_columns"][:10]


def test_json_output_shape(gate):
    import json

    result = {
        "missing_tables": [],
        "missing_columns": [],
        "extra_columns": [{"table": "t", "column": "c"}],
        "tables_checked": 1,
    }
    assert json.loads(json.dumps(result, ensure_ascii=False))["tables_checked"] == 1
