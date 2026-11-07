"""迁移「错误页探测记录改判为探测失败」的守护测试。

守三件事
--------
1. **SQL 判据与 Python 判据逐字一致** —— 采集侧改完之后（``executor_v2``），
   迁移必须用**同一套**「哪些 URL 是错误页」口径，否则会出现
   「新记录判失败、旧记录判冲突」的两套标准；
2. **只改判、不删历史** —— 原状态与原探测值必须留在 ``raw_payload`` 里，
   且 downgrade 能原样改回；
3. **幂等** —— 重复跑不报错、不二次改写。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from sqlalchemy import text

from modules.apps.collection_center.executor_v2 import _is_platform_error_page


MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "current_migrations"
    / "versions"
    / "20261129_reclassify_error_page_shop_discoveries.py"
)

#: 一批覆盖各分支的 URL（错误页 / 登录页 / 正常业务页 / 边界）。
URL_CASES = [
    # 2026-11-07 事故现场
    "https://seller.shopee.cn/404?cnsc_shop_id=1391124228",
    "https://seller.shopee.cn/404",
    "https://seller.shopee.cn/404error?cnsc_shop_id=1",
    "https://seller.shopee.cn/error?cnsc_shop_id=1",
    "https://seller.shopee.cn/errorpage",
    "https://seller.shopee.cn/not-found",
    # 2026-04 历史 failed 记录命中的登录页
    "https://seller.shopee.cn/account/signin?next=%2Fportal%2Fhome",
    "https://seller.shopee.cn/login",
    # 正常业务页（不能被误判）
    "https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1227491331",
    "https://seller.shopee.cn/datacenter/error_report?cnsc_shop_id=1",
    "https://seller.shopee.cn/portal/home?cnsc_shop_id=1227491331",
    "https://seller.tiktokshopglobalselling.com/homepage?shop_region=MY",
    # 边界
    "",
    "https://seller.shopee.cn/",
]


def _load_migration():
    spec = importlib.util.spec_from_file_location("_mig_reclassify", MIGRATION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _disable_fk_triggers(pg_session) -> None:
    """探测记录有指向 ``core.main_accounts`` 的外键；本测试只关心改判逻辑。"""
    await pg_session.execute(
        text("SET session_replication_role = replica")
    )
    await pg_session.flush()


@pytest.mark.asyncio
async def test_sql_criteria_matches_python_error_page_detector(pg_session):
    """**迁移的 SQL 判据必须与 Python 逐条一致。**"""
    module = _load_migration()
    match_sql = module._error_page_match_sql("cases.url")

    payload = json.dumps(
        [{"id": index, "url": url} for index, url in enumerate(URL_CASES)],
        ensure_ascii=False,
    )
    rows = await pg_session.execute(
        text(
            f"""
            WITH cases AS (
                SELECT (item->>'id')::int AS id, item->>'url' AS url
                FROM jsonb_array_elements(CAST(:payload AS jsonb)) AS item
            )
            SELECT cases.id, ({match_sql}) AS is_error_page
            FROM cases
            ORDER BY cases.id
            """
        ),
        {"payload": payload},
    )
    results = {int(row[0]): bool(row[1]) for row in rows}

    assert len(results) == len(URL_CASES)
    for index, url in enumerate(URL_CASES):
        expected = _is_platform_error_page(url)
        assert results[index] is expected, (
            f"URL={url!r} SQL={results[index]} Python={expected}"
        )


@pytest.mark.asyncio
async def test_migration_reclassifies_error_page_rows_only(pg_session):
    module = _load_migration()
    await _disable_fk_triggers(pg_session)

    await pg_session.execute(
        text(
            """
            INSERT INTO core.platform_shop_discoveries
                (platform, main_account_id, detected_store_name,
                 detected_platform_shop_id, detected_region,
                 candidate_shop_account_ids, status, raw_payload)
            VALUES
                ('shopee', 'main_1', 'strawberries_store.sg', '1391124228', 'SG',
                 '["shopee_sg_hx_home_local"]'::jsonb, 'conflict_detected',
                 '{"current_url": "https://seller.shopee.cn/404?cnsc_shop_id=1391124228"}'::jsonb),
                ('shopee', 'main_1', 'chenewei666.sg', '1308200832', 'SG',
                 '["shopee_sg_hx_home_local"]'::jsonb, 'stale_url',
                 '{"current_url": "https://seller.shopee.cn/account/signin?next=%2Fportal%2Fhome"}'::jsonb),
                ('shopee', 'main_1', 'chenewei666.sg', '1308200832', 'SG',
                 '["shopee_my_xhkj1_local"]'::jsonb, 'detected_single_bound',
                 '{"current_url": "https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1308200832"}'::jsonb)
            """
        )
    )
    await pg_session.flush()

    stats = await pg_session.run_sync(module.apply_upgrade)
    await pg_session.flush()

    assert stats["reclassified"] == 2

    rows = (
        (
            await pg_session.execute(
                text(
                    """
                    SELECT status, detected_platform_shop_id, detected_store_name,
                           candidate_shop_account_ids, raw_payload
                    FROM core.platform_shop_discoveries
                    ORDER BY id
                    """
                )
            )
        )
        .mappings()
        .all()
    )
    assert len(rows) == 3

    # 404 页：改判为探测失败，探测值清空，原值留档
    row = rows[0]
    assert row["status"] == "failed"
    assert row["detected_platform_shop_id"] is None
    assert row["detected_store_name"] is None
    assert list(row["candidate_shop_account_ids"] or []) == []
    assert row["raw_payload"]["probe_failed"] is True
    assert row["raw_payload"]["reclassified_from_status"] == "conflict_detected"
    assert row["raw_payload"]["original_detected_platform_shop_id"] == "1391124228"
    assert list(row["raw_payload"]["original_candidate_shop_account_ids"]) == [
        "shopee_sg_hx_home_local"
    ]
    assert row["raw_payload"]["current_url"].endswith("/404?cnsc_shop_id=1391124228")

    # 登录页：同样改判
    assert rows[1]["status"] == "failed"
    assert rows[1]["raw_payload"]["reclassified_from_status"] == "stale_url"

    # 正常业务页：一行都不能动
    assert rows[2]["status"] == "detected_single_bound"
    assert rows[2]["detected_platform_shop_id"] == "1308200832"
    assert "probe_failed" not in (rows[2]["raw_payload"] or {})


@pytest.mark.asyncio
async def test_migration_is_idempotent(pg_session):
    module = _load_migration()
    await _disable_fk_triggers(pg_session)

    await pg_session.execute(
        text(
            """
            INSERT INTO core.platform_shop_discoveries
                (platform, main_account_id, status, raw_payload)
            VALUES ('shopee', 'main_1', 'conflict_detected',
                    '{"current_url": "https://seller.shopee.cn/404?cnsc_shop_id=1"}'::jsonb)
            """
        )
    )
    await pg_session.flush()

    first = await pg_session.run_sync(module.apply_upgrade)
    await pg_session.flush()
    second = await pg_session.run_sync(module.apply_upgrade)
    await pg_session.flush()

    assert first["reclassified"] == 1
    assert second["reclassified"] == 0

    row = (
        (
            await pg_session.execute(
                text(
                    """
                    SELECT status, raw_payload
                    FROM core.platform_shop_discoveries
                    ORDER BY id DESC
                    LIMIT 1
                    """
                )
            )
        )
        .mappings()
        .first()
    )
    assert row["status"] == "failed"
    # 第二次不得覆盖第一次留档的原值
    assert row["raw_payload"]["reclassified_from_status"] == "conflict_detected"


@pytest.mark.asyncio
async def test_migration_downgrade_restores_original_values(pg_session):
    module = _load_migration()
    await _disable_fk_triggers(pg_session)

    await pg_session.execute(
        text(
            """
            INSERT INTO core.platform_shop_discoveries
                (platform, main_account_id, detected_store_name,
                 detected_platform_shop_id, detected_region,
                 candidate_shop_account_ids, status, raw_payload)
            VALUES ('shopee', 'main_1', 'strawberries_store.sg', '1391124228', 'SG',
                    '["shopee_sg_hx_home_local"]'::jsonb, 'conflict_detected',
                    '{"current_url": "https://seller.shopee.cn/404?cnsc_shop_id=1391124228"}'::jsonb)
            """
        )
    )
    await pg_session.flush()

    await pg_session.run_sync(module.apply_upgrade)
    await pg_session.flush()
    await pg_session.run_sync(module.apply_downgrade)
    await pg_session.flush()

    row = (
        (
            await pg_session.execute(
                text(
                    """
                    SELECT status, detected_platform_shop_id, detected_store_name,
                           detected_region, candidate_shop_account_ids, raw_payload
                    FROM core.platform_shop_discoveries
                    ORDER BY id DESC
                    LIMIT 1
                    """
                )
            )
        )
        .mappings()
        .first()
    )
    assert row["status"] == "conflict_detected"
    assert row["detected_platform_shop_id"] == "1391124228"
    assert row["detected_store_name"] == "strawberries_store.sg"
    assert row["detected_region"] == "SG"
    assert list(row["candidate_shop_account_ids"] or []) == [
        "shopee_sg_hx_home_local"
    ]
    assert "probe_failed" not in (row["raw_payload"] or {})
