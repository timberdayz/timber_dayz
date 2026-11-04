# -*- coding: utf-8 -*-
"""
数据管道监控「存在性校验」契约测试。

背景：freshness 只记录「上一次刷新当时的结果」。对象后来被删除/改名时，
记录里的 status 仍然是 success，监控因此「假绿」——线上 9 个僵尸 target
就是这么被绿灯掩盖的。

v7.12.9 起：
- /api/data-pipeline/freshness 会实时核对对象是否还存在，
  把「已注册但对象已不存在」的目标标成 missing（并保留 recorded_status 便于追溯）。
- /api/data-pipeline/lineage 会给每条边标出目标/来源对象是否还存在。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


# --------------------------------------------------------------------------
# 单元测试：用假 session 验证判定逻辑，不需要数据库
# --------------------------------------------------------------------------
class _FakeRowsResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeMappingsResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    """按 SQL 内容分派结果，模拟 freshness / lineage / 存在性三类查询。"""

    def __init__(self, *, freshness_rows=(), lineage_rows=(), existing_objects=()):
        self.freshness_rows = list(freshness_rows)
        self.lineage_rows = list(lineage_rows)
        self.existing_objects = set(existing_objects)
        self.existence_params: list[dict] = []

    async def execute(self, statement, params=None):
        sql = str(statement)
        if "data_freshness_log" in sql:
            return _FakeMappingsResult(self.freshness_rows)
        if "data_lineage_registry" in sql:
            return _FakeMappingsResult(self.lineage_rows)
        if "pg_class" in sql:
            self.existence_params.append(dict(params or {}))
            targets = set((params or {}).get("targets") or [])
            return _FakeRowsResult(
                [(name,) for name in sorted(self.existing_objects & targets)]
            )
        raise AssertionError(f"unexpected SQL: {sql}")


@pytest.mark.asyncio
async def test_find_missing_targets_reports_only_objects_that_no_longer_exist():
    from backend.services.data_pipeline.refresh_validation import find_missing_targets

    session = _FakeSession(existing_objects={"api.present_module"})

    missing = await find_missing_targets(
        session,
        ["api.present_module", "api.gone_module", "no_schema_prefix"],
    )

    assert missing == {"api.gone_module"}
    # 不带 schema 前缀的名字不是数据库对象，不参与存在性核对
    assert session.existence_params[0]["targets"] == [
        "api.gone_module",
        "api.present_module",
    ]


@pytest.mark.asyncio
async def test_find_missing_targets_skips_query_when_no_schema_qualified_target():
    from backend.services.data_pipeline.refresh_validation import find_missing_targets

    session = _FakeSession()

    missing = await find_missing_targets(session, ["plain_target", "", None])

    assert missing == set()
    assert session.existence_params == []


@pytest.mark.asyncio
async def test_find_missing_targets_resolves_logical_target_to_its_real_object():
    from backend.services.data_pipeline.refresh_validation import find_missing_targets

    session = _FakeSession(existing_objects={"semantic.semantic_field_aliases"})

    missing = await find_missing_targets(session, ["semantic.alias_registry"])

    # 逻辑目标的代号本身不是数据库对象，必须按登记的真实对象名核对
    assert missing == set()
    assert session.existence_params[0]["targets"] == ["semantic.semantic_field_aliases"]


@pytest.mark.asyncio
async def test_pipeline_freshness_marks_targets_whose_object_is_missing():
    from backend.domains.data_platform.routers.data_pipeline import (
        get_pipeline_freshness,
    )

    session = _FakeSession(
        freshness_rows=[
            {
                "target_name": "api.present_module",
                "target_type": "view",
                "status": "success",
            },
            {
                "target_name": "api.gone_module",
                "target_type": "view",
                "status": "success",
            },
            {"target_name": "plain_target", "target_type": "task", "status": "success"},
        ],
        existing_objects={"api.present_module"},
    )

    response = await get_pipeline_freshness(db=session)
    body = json.loads(response.body.decode("utf-8"))
    targets = {row["target_name"]: row for row in body["data"]["targets"]}

    assert body["data"]["missing_targets"] == ["api.gone_module"]

    # 对象还在：状态保持不变
    assert targets["api.present_module"]["status"] == "success"
    assert targets["api.present_module"]["object_exists"] is True

    # 对象已删：不再显示 success，标成 missing，并保留原始状态便于追溯
    assert targets["api.gone_module"]["status"] == "missing"
    assert targets["api.gone_module"]["recorded_status"] == "success"
    assert targets["api.gone_module"]["object_exists"] is False

    # 非数据库对象无法核对存在性
    assert targets["plain_target"]["object_exists"] is None
    assert targets["plain_target"]["status"] == "success"


@pytest.mark.asyncio
async def test_pipeline_lineage_flags_edges_whose_object_is_missing():
    from backend.domains.data_platform.routers.data_pipeline import get_pipeline_lineage

    session = _FakeSession(
        lineage_rows=[
            {
                "target_name": "api.present_module",
                "source_name": "semantic.present_fact",
                "active": True,
            },
            {
                "target_name": "api.gone_module",
                "source_name": "semantic.gone_fact",
                "active": True,
            },
        ],
        existing_objects={"api.present_module", "semantic.present_fact"},
    )

    response = await get_pipeline_lineage(db=session)
    body = json.loads(response.body.decode("utf-8"))
    edges = {row["target_name"]: row for row in body["data"]["edges"]}

    assert body["data"]["missing_objects"] == ["api.gone_module", "semantic.gone_fact"]
    assert edges["api.present_module"]["target_object_exists"] is True
    assert edges["api.present_module"]["source_object_exists"] is True
    assert edges["api.gone_module"]["target_object_exists"] is False
    assert edges["api.gone_module"]["source_object_exists"] is False


# --------------------------------------------------------------------------
# 真库验证：确认存在性核对在真实 PostgreSQL 上成立
# --------------------------------------------------------------------------
_CREATE_OBJECT_RE = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:TEMP\s+|TEMPORARY\s+|UNLOGGED\s+)?"
    # FUNCTION 也要认：有些逻辑目标建的是函数（如共享的店铺身份解析函数），
    # 函数不在 pg_class 里，存在性核对走 pg_proc。
    r"(?:TABLE|VIEW|MATERIALIZED\s+VIEW|FUNCTION)\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"([A-Za-z_][\w$]*)\.([A-Za-z_][\w$]*)",
    re.IGNORECASE,
)


def test_every_logical_target_is_registered_with_its_real_object_name():
    """守护「逻辑目标 ↔ 真实对象名」的登记完整性。

    若某个目标的 SQL 建的对象名和目标代号不一致，必须登记在
    LOGICAL_TARGET_OBJECTS 里，否则存在性核对会把活着的目标误报成 missing。
    """
    from backend.services.data_pipeline.refresh_registry import SQL_TARGET_PATHS
    from backend.services.data_pipeline.refresh_validation import LOGICAL_TARGET_OBJECTS

    repo_root = Path(__file__).resolve().parents[3]
    mismatches: dict[str, set[str]] = {}

    for target, relative_path in SQL_TARGET_PATHS.items():
        sql_path = repo_root / relative_path
        assert sql_path.exists(), f"SQL 资产缺失: {relative_path}"
        sql_text = sql_path.read_text(encoding="utf-8", errors="replace")
        created = {
            f"{schema}.{name}" for schema, name in _CREATE_OBJECT_RE.findall(sql_text)
        }
        if target not in created:
            mismatches[target] = created

    # 每个名称不一致的目标都必须登记，且登记的对象名要真实存在
    for target, created in mismatches.items():
        assert target in LOGICAL_TARGET_OBJECTS, (
            f"逻辑目标 {target} 未登记到 LOGICAL_TARGET_OBJECTS，"
            f"存在性核对会把它误报成 missing；其 SQL 实际创建: {sorted(created)}"
        )
        assert LOGICAL_TARGET_OBJECTS[target] in created, (
            f"逻辑目标 {target} 登记的对象名 {LOGICAL_TARGET_OBJECTS[target]} "
            f"与 SQL 实际创建的对象不符: {sorted(created)}"
        )

    # 反向：登记表里不允许出现「其实同名」的目标（否则等于白白走别名）
    for target, object_name in LOGICAL_TARGET_OBJECTS.items():
        assert (
            target in mismatches
        ), f"{target} 的 SQL 实际创建同名对象 {object_name}，不需要登记为逻辑目标"


def _split_sql_statements(sql_text: str) -> list[str]:
    without_comments = re.sub(r"--[^\n]*", "", sql_text)
    return [part.strip() for part in without_comments.split(";") if part.strip()]


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_pipeline_freshness_marks_missing_object_against_real_postgres(
    pg_session,
):
    from sqlalchemy import text

    from backend.domains.data_platform.routers.data_pipeline import (
        get_pipeline_freshness,
    )

    ddl = Path("sql/ops/create_pipeline_tables.sql").read_text(encoding="utf-8")
    for statement in _split_sql_statements(ddl):
        await pg_session.execute(text(statement))

    await pg_session.execute(text("CREATE SCHEMA IF NOT EXISTS api"))
    await pg_session.execute(
        text("CREATE OR REPLACE VIEW api.freshness_probe_view AS SELECT 1 AS value")
    )
    await pg_session.execute(
        text(
            """
            INSERT INTO ops.data_freshness_log (target_name, target_type, last_succeeded_at, status)
            VALUES ('api.freshness_probe_view', 'view', NOW(), 'success')
            """
        )
    )
    await pg_session.execute(
        text(
            """
            INSERT INTO ops.data_freshness_log (target_name, target_type, last_succeeded_at, status)
            VALUES ('api.freshness_missing_view', 'view', NOW(), 'success')
            """
        )
    )

    response = await get_pipeline_freshness(db=pg_session)
    body = json.loads(response.body.decode("utf-8"))
    targets = {row["target_name"]: row for row in body["data"]["targets"]}

    assert targets["api.freshness_probe_view"]["status"] == "success"
    assert targets["api.freshness_probe_view"]["object_exists"] is True
    assert targets["api.freshness_missing_view"]["status"] == "missing"
    assert targets["api.freshness_missing_view"]["object_exists"] is False
    assert "api.freshness_missing_view" in body["data"]["missing_targets"]
