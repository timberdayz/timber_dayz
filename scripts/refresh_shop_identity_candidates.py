#!/usr/bin/env python3
"""批次 2 步骤 2.4：刷新店铺身份候选集物化副本，并做「副本 == 正本」内容指纹比对。

为什么是 **REFRESH** 而不是「DROP + 重建」
--------------------------------------------
副本资产 ``sql/semantic/shop_identity_resolution_candidates_v2_mv.sql`` 的刷新语义是
「存在则 REFRESH / 不存在则 CREATE」，**绝不 DROP ... CASCADE**（资产自己的注释与
``backend/tests/data_pipeline/test_identity_candidates_materialization.py`` 都在守这条）。

而 DROP 重建只在**口径变更**时才需要 —— 迁移
``current_migrations/versions/20261112_realign_identity_candidates_anchor.py`` 的说明写得很清楚：
「REFRESH 只重算**数据**, 不换**定义**；口径改了之后, 光 REFRESH 刷出来的还是旧口径」。
批次 2 只改 ``core.shop_accounts`` 的**数据**、口径一个字不动 ⇒ **REFRESH 即可**。

⚠ 而且不带 CASCADE 的 DROP 会直接失败：副本下游挂着
``semantic.fact_orders_atomic`` / ``fact_analytics_atomic`` /
``semantic.shop_identity_resolver``（都是 ``LANGUAGE sql``，依赖被跟踪），
要 DROP 就得先把这些对象的正文临时换成正本 —— 那是口径变更才需要的手术，
批次 2 不该做。

指纹比对沿用迁移 ``20261105_create_identity_candidates_mv.py`` 的口径：
行数 + 全量内容 md5（按行文本排序后拼接）。

用法::

    python scripts/refresh_shop_identity_candidates.py
    python scripts/refresh_shop_identity_candidates.py --check-only

退出码：``0`` 刷新成功且指纹一致 / ``1`` 指纹不一致 / ``2`` 执行失败。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

PROJECT_ROOT = Path(__file__).resolve().parents[1]

#: 候选集正本（普通视图）
CANDIDATES_VIEW = "semantic.shop_identity_resolution_candidates"
#: 候选集物化副本
CANDIDATES_MV = "semantic.shop_identity_resolution_candidates_v2_mv"
#: 副本资产（DO 块：存在则 REFRESH / 不存在则 CREATE）
CANDIDATES_MV_ASSET = "sql/semantic/shop_identity_resolution_candidates_v2_mv.sql"


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_env_files(project_root: Path) -> None:
    for name in (".env", ".env.local", ".env.collection.local"):
        _load_env_file(project_root / name)


def describe_connection(url: str) -> dict[str, Any]:
    parsed = make_url(url)
    return {
        "driver": parsed.drivername,
        "host": parsed.host,
        "port": parsed.port,
        "database": parsed.database,
    }


def fingerprint(conn, relation: str) -> tuple[int, str]:
    """关系的内容指纹：行数 + 全量内容 md5（按行文本排序后拼接）。

    与迁移 ``20261105_create_identity_candidates_mv.py`` 的 ``_fingerprint`` 同口径。
    """
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT count(*)::int AS row_count,
                   md5(coalesce(string_agg(row_json, '|' ORDER BY row_json), '')) AS digest
            FROM (
                SELECT row_to_json(t)::text AS row_json
                FROM {relation} t
            ) s
            """.format(
                relation=relation
            )
        )
        row = cursor.fetchone()
    return int(row[0]), str(row[1])


def refresh_materialized_copy(engine) -> None:
    """执行副本资产 —— DO 块内部是「存在则 REFRESH / 不存在则 CREATE」。

    用 psycopg2 的**简单查询协议**执行整份资产（它含 ``DO $$ ... $$`` 块，
    简单协议由数据库自己按分号切分，不会把 dollar-quoted 块切坏）。

    ⚠ ``engine.raw_connection()`` 返回的 ``_ConnectionFairy`` **不支持** ``with``
    （不是 context manager），必须显式 ``close()``。
    """
    asset_path = PROJECT_ROOT / CANDIDATES_MV_ASSET
    if not asset_path.is_file():
        raise RuntimeError(f"副本资产缺失: {CANDIDATES_MV_ASSET}")
    asset_sql = asset_path.read_text(encoding="utf-8")
    raw = engine.raw_connection()
    try:
        with raw.cursor() as cursor:
            cursor.execute(asset_sql)
        raw.commit()
    finally:
        raw.close()


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # pragma: no cover
        pass

    parser = argparse.ArgumentParser(
        description="刷新店铺身份候选集物化副本并做正本/副本指纹比对"
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="只比对指纹，不刷新",
    )
    args = parser.parse_args()

    load_env_files(PROJECT_ROOT)
    url = os.getenv("DATABASE_URL")
    if not url:
        print("[FAIL] DATABASE_URL is not configured")
        return 2

    engine = create_engine(url)
    try:
        if not args.check_only:
            print(f"[INFO] 刷新副本: {CANDIDATES_MV}")
            refresh_materialized_copy(engine)

        raw = engine.raw_connection()
        try:
            view_rows, view_digest = fingerprint(raw, CANDIDATES_VIEW)
            mv_rows, mv_digest = fingerprint(raw, CANDIDATES_MV)
        finally:
            raw.close()

        print(f"[INFO] 正本 {CANDIDATES_VIEW}: rows={view_rows} md5={view_digest}")
        print(f"[INFO] 副本 {CANDIDATES_MV}: rows={mv_rows} md5={mv_digest}")
        if (view_rows, view_digest) == (mv_rows, mv_digest):
            print("[OK] 副本与正本内容一致")
            return 0
        print("[FAIL] 副本与正本内容不一致 —— 拒绝继续，请人工核对")
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI 边界
        print(f"[FAIL] 执行失败: {type(exc).__name__}: {exc}")
        return 2
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
