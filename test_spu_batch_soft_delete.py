# -*- coding: utf-8 -*-
"""Test SPU batch soft-delete (M2).

Scenario 1: All pass -> soft delete succeeds (reset at start of test).
Scenario 2: One fail -> full rollback, zero DB changes.
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
import asyncio
from datetime import date
from sqlalchemy import create_engine, text

from backend.models.database import get_async_db
from backend.domains.business.routers.product_center import batch_soft_delete_spus
from backend.schemas.product_center import BatchSpuSoftDeleteRequest
from modules.core.db import DimSpu


DB_URL = "postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp"
TEST_SPU_A = "XH-OFFICE-GNH"
TEST_SPU_B = "XH-OFFICE-GNH-2"


class FakeUser:
    user_id = 391
    username = "qaadmin"
    is_superuser = True


def reset_spu(spu, conn):
    """Restore one SPU from backup + clean audit."""
    conn.execute(text("""
        UPDATE core.dim_spu s SET
          active = b.active, biz_status = b.biz_status
        FROM core.dim_spu_backup_20260916 b
        WHERE s.spu = b.spu AND s.spu = :spu
    """), {"spu": spu})
    conn.execute(text("""
        UPDATE core.bridge_spu_sku SET binding_status='active', effective_to=NULL
        WHERE spu = :spu
    """), {"spu": spu})
    conn.execute(text(
        "DELETE FROM public.fact_audit_logs WHERE resource_id = :spu"
    ), {"spu": spu})


def initial_state(spu, conn):
    return conn.execute(text("""
        SELECT
          (SELECT active FROM core.dim_spu WHERE spu=:spu),
          (SELECT biz_status FROM core.dim_spu WHERE spu=:spu),
          (SELECT COUNT(*) FROM core.bridge_spu_sku
            WHERE spu=:spu AND binding_status='active' AND effective_to IS NULL)
    """), {"spu": spu}).first()


async def main():
    engine = create_engine(DB_URL)
    spus = [TEST_SPU_A, TEST_SPU_B]

    # 0. 重置 + 打印初始状态
    print("=" * 60)
    print("Reset 0: Restore both test SPUs + clean audit")
    print("=" * 60)
    with engine.begin() as conn:
        for s in spus:
            reset_spu(s, conn)
        for s in spus:
            r = initial_state(s, conn)
            print(f"  {s}: active={r[0]} biz_status={r[1]} active_bindings={r[2]}")
    print()

    # ---- 场景 1:全部 pass ----
    print("=" * 60)
    print("Scenario 1: Both SPUs cleared -> batch soft delete succeeds")
    print("=" * 60)
    async for db in get_async_db():
        # 1a. 停用两个 SPU 的所有 active binding
        await db.execute(
            text("""
                UPDATE core.bridge_spu_sku
                SET binding_status='inactive', effective_to=:d
                WHERE spu = ANY(:spus) AND binding_status='active' AND effective_to IS NULL
            """),
            {"d": date.today(), "spus": spus},
        )
        await db.commit()

        # 1b. 调批量 endpoint
        resp = await batch_soft_delete_spus(
            body=BatchSpuSoftDeleteRequest(
                spus=spus,
                confirm=True,
            ),
            db=db, _user=FakeUser(),
        )
        print(f"  total={resp.total} deleted={resp.deleted} blocked={resp.blocked} rolled_back={resp.rolled_back}")
        for item in resp.items:
            print(f"    [{item.status:7s}] {item.spu}: affected_bindings={item.affected_bindings} warns={len(item.warn_checks)}")
        assert resp.total == 2
        assert resp.deleted == 2
        assert resp.blocked == 0
        assert resp.rolled_back is False

        # 1c. 校验 DB 状态
        for s in spus:
            row = await db.get(DimSpu, s)
            print(f"  {s} after: active={row.active} biz_status={row.biz_status}")
            assert row.active is False
            assert row.biz_status == "retired"
        break

    # 1d. 校验 audit (sync engine,刚 commit 过)
    with engine.connect() as conn:
        audit_cnt = conn.execute(text(
            "SELECT COUNT(*) FROM public.fact_audit_logs "
            "WHERE action_type='batch_soft_delete' AND resource_id = ANY(:spus)"
        ), {"spus": spus}).scalar()
        print(f"  audit batch_soft_delete records: {audit_cnt}")
        assert audit_cnt == 2, f"expected 2 audit rows, got {audit_cnt}"
    print("  [OK] Scenario 1 verified\n")

    # 收尾:重置两个 SPU + 清理 audit
    with engine.begin() as conn:
        for s in spus:
            reset_spu(s, conn)

    # ---- 场景 2:任一 fail → 整体回滚 ----
    print("=" * 60)
    print("Scenario 2: One SPU has active binding -> full rollback")
    print("=" * 60)
    async for db in get_async_db():
        # 2a. 只停用 B 的 binding,A 保留(制造 A fail / B pass)
        await db.execute(
            text("""
                UPDATE core.bridge_spu_sku
                SET binding_status='inactive', effective_to=:d
                WHERE spu = :spu AND binding_status='active' AND effective_to IS NULL
            """),
            {"d": date.today(), "spu": TEST_SPU_B},
        )
        await db.commit()
        break

    async for db in get_async_db():
        resp = await batch_soft_delete_spus(
            body=BatchSpuSoftDeleteRequest(
                spus=spus,
                confirm=True,
            ),
            db=db, _user=FakeUser(),
        )
        print(f"  total={resp.total} deleted={resp.deleted} blocked={resp.blocked} rolled_back={resp.rolled_back}")
        for item in resp.items:
            print(f"    [{item.status:7s}] {item.spu}: blocked_reasons={item.blocked_reasons}")
        assert resp.total == 2
        assert resp.deleted == 0
        assert resp.blocked == 1
        assert resp.rolled_back is True
        break

    # 2b. 校验 A、B 都没被修改(rollback)
    with engine.connect() as conn:
        for s in spus:
            row = conn.execute(text(
                "SELECT active, biz_status FROM core.dim_spu WHERE spu = :spu"
            ), {"spu": s}).first()
            print(f"  {s} after: active={row[0]} biz_status={row[1]}")
            assert row[0] is True, f"{s} should still be active"
        # B 的 binding 应该是 inactive(2a 设置),A 应该是 active(没动)
        b_bind = conn.execute(text(
            "SELECT COUNT(*) FROM core.bridge_spu_sku "
            "WHERE spu=:spu AND binding_status='active' AND effective_to IS NULL"
        ), {"spu": TEST_SPU_B}).scalar()
        a_bind = conn.execute(text(
            "SELECT COUNT(*) FROM core.bridge_spu_sku "
            "WHERE spu=:spu AND binding_status='active' AND effective_to IS NULL"
        ), {"spu": TEST_SPU_A}).scalar()
        print(f"  active bindings: A={a_bind}, B={b_bind}")
        assert a_bind > 0, "A should still have active bindings"
        assert b_bind == 0, "B's binding was deactivated in 2a"

        # 2c. 校验没有新增 batch_soft_delete audit(整体回滚)
        audit_cnt = conn.execute(text(
            "SELECT COUNT(*) FROM public.fact_audit_logs "
            "WHERE action_type='batch_soft_delete' AND resource_id = ANY(:spus)"
        ), {"spus": spus}).scalar()
        print(f"  audit batch_soft_delete records (should be 0): {audit_cnt}")
        assert audit_cnt == 0, "rollback should leave no audit"

    print("  [OK] Scenario 2 verified: full rollback works\n")

    # ---- 收尾 ----
    with engine.begin() as conn:
        for s in spus:
            reset_spu(s, conn)

    print("=" * 60)
    print("ALL BATCH TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())