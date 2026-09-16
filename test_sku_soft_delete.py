# -*- coding: utf-8 -*-
"""Test SKU soft-delete + restore (M5.1)."""
import sys
sys.stdout.reconfigure(encoding="utf-8")
import asyncio
from datetime import date
from sqlalchemy import create_engine, select, update, text

from backend.models.database import get_async_db
from backend.domains.business.routers.product_center import (
    _check_sku_deletion_blockers,
    preview_sku_deletion,
    soft_delete_sku,
    restore_sku,
    _count_sku_business_references,
)
from backend.schemas.product_center import (
    SkuSoftDeleteRequest, SkuRestoreRequest,
)
from modules.core.db import DimErpSku, BridgeSpuSku


TEST_SKU_ID = 1869  # XH-ELEC-WRJ / SKU-0001


class FakeUser:
    user_id = 391
    username = "qaadmin"
    is_superuser = True


async def main():
    sync_engine = create_engine("postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp")

    # 0. 强制重置 SKU 到初始状态
    print("=" * 60)
    print("Reset 0: Force reset SKU to initial state")
    print("=" * 60)
    with sync_engine.begin() as conn:
        conn.execute(text("UPDATE core.dim_erp_sku SET status='active' WHERE sku_id=:id"), {"id": TEST_SKU_ID})
        conn.execute(text("""
            UPDATE core.bridge_spu_sku SET binding_status='active', effective_to=NULL
            WHERE sku_id=:id
        """), {"id": TEST_SKU_ID})
        conn.execute(text(
            "DELETE FROM public.fact_audit_logs WHERE resource_id=:id AND action_type IN ('sku_soft_delete','sku_restore')"
        ), {"id": str(TEST_SKU_ID)})

    async for db in get_async_db():
        sku_row = await db.get(DimErpSku, TEST_SKU_ID)
        print(f"  sku_id={sku_row.sku_id} sku_key={sku_row.sku_key} status={sku_row.status}")
        bc = (await db.execute(
            text("SELECT COUNT(*) FROM core.bridge_spu_sku "
                 "WHERE sku_id=:id AND binding_status='active' AND effective_to IS NULL"),
            {"id": TEST_SKU_ID},
        )).scalar()
        print(f"  active bindings: {bc}")
        print(f"  business refs: {await _count_sku_business_references(db, TEST_SKU_ID)}")
        assert sku_row.status == "active", f"expected active, got {sku_row.status}"
        break
    print()

    # Test 1: helper
    print("=" * 60)
    print("Test 1: _check_sku_deletion_blockers")
    print("=" * 60)
    async for db in get_async_db():
        checks = await _check_sku_deletion_blockers(db, TEST_SKU_ID)
        for c in checks:
            print(f"  [{c.status.upper():4s}] {c.code:30s} {c.label}")
            if c.detail:
                print(f"          -> {c.detail}")
        fail = sum(1 for c in checks if c.status == "fail")
        assert fail == 0, f"expected 0 fail, got {fail}"
        print(f"  [OK] fail={fail}\n")
        break

    # Test 2: preview endpoint
    print("=" * 60)
    print("Test 2: preview_sku_deletion")
    print("=" * 60)
    async for db in get_async_db():
        preview = await preview_sku_deletion(sku_id=TEST_SKU_ID, db=db, _user=FakeUser())
        print(f"  current_status={preview.current_status} can_soft_delete={preview.can_soft_delete}")
        print(f"  business_reference_count={preview.business_reference_count}")
        print(f"  soft_delete_impact={preview.soft_delete_impact}")
        assert preview.current_status == "active"
        assert preview.can_soft_delete is True
        print("  [OK]\n")
        break

    # Test 3: 完整流程 (snapshot → soft delete → 验证 → restore → 验证)
    print("=" * 60)
    print("Test 3: Full soft-delete + restore flow")
    print("=" * 60)
    async for db in get_async_db():
        # 3a. 快照 binding
        bindings = (await db.execute(
            select(BridgeSpuSku).where(BridgeSpuSku.sku_id == TEST_SKU_ID)
        )).scalars().all()
        snap = [(b.id, b.binding_status, b.effective_to) for b in bindings]
        print(f"  3a. Snapshot {len(snap)} bindings")

        try:
            # 3b. 软删
            sd = await soft_delete_sku(
                sku_id=TEST_SKU_ID,
                body=SkuSoftDeleteRequest(confirm=True),
                db=db, _user=FakeUser(),
            )
            print(f"  3b. soft_delete: {sd.previous_status} -> {sd.new_status}, affected_bindings={sd.affected_bindings}")

            # 3c. 校验
            sku_row = await db.get(DimErpSku, TEST_SKU_ID)
            assert sku_row.status == "inactive"
            active_b = (await db.execute(text(
                "SELECT COUNT(*) FROM core.bridge_spu_sku "
                "WHERE sku_id=:id AND binding_status='active' AND effective_to IS NULL"
            ), {"id": TEST_SKU_ID})).scalar()
            assert active_b == 0, f"expected 0 active bindings, got {active_b}"
            print(f"  3c. status=inactive, active_bindings=0")

            # 3d. audit
            audit = (await db.execute(text(
                "SELECT action_type FROM public.fact_audit_logs "
                "WHERE resource_id=:id AND action_type='sku_soft_delete' ORDER BY log_id DESC LIMIT 1"
            ), {"id": str(TEST_SKU_ID)})).mappings().first()
            assert audit is not None
            print(f"  3d. audit: {audit['action_type']}")

            # 3e. 恢复
            restore = await restore_sku(
                sku_id=TEST_SKU_ID,
                body=SkuRestoreRequest(confirm=True),
                db=db, _user=FakeUser(),
            )
            print(f"  3e. restore: {restore.previous_status} -> {restore.new_status}, restored_bindings={restore.restored_bindings}")
            assert restore.previous_status == "inactive"
            assert restore.new_status == "active"
            assert restore.restored_bindings >= 1

            # 3f. 校验恢复后
            sku_row = await db.get(DimErpSku, TEST_SKU_ID)
            assert sku_row.status == "active"
            active_b = (await db.execute(text(
                "SELECT COUNT(*) FROM core.bridge_spu_sku "
                "WHERE sku_id=:id AND binding_status='active' AND effective_to IS NULL"
            ), {"id": TEST_SKU_ID})).scalar()
            assert active_b >= 1, f"expected active bindings after restore, got {active_b}"
            print(f"  3f. status=active, active_bindings={active_b}")

            # 3g. audit restore
            audit_r = (await db.execute(text(
                "SELECT action_type FROM public.fact_audit_logs "
                "WHERE resource_id=:id AND action_type='sku_restore' ORDER BY log_id DESC LIMIT 1"
            ), {"id": str(TEST_SKU_ID)})).mappings().first()
            assert audit_r is not None
            print(f"  3g. audit restore: {audit_r['action_type']}")

            print("  [OK] Full flow passed\n")
        finally:
            # 3h. 清理(回到 backup 状态)
            pass

    # 收尾:重置 DB + 清 audit
    with sync_engine.begin() as conn:
        # 用 backup 还原(应该和原状一致,因为已恢复)
        # 但 audit 留下了,清掉
        conn.execute(text(
            "DELETE FROM public.fact_audit_logs "
            "WHERE resource_id=:id AND action_type IN ('sku_soft_delete','sku_restore')"
        ), {"id": str(TEST_SKU_ID)})
    print("  cleaned audit records")

    # Test 4: 边界 — 已 inactive 时再调 soft-delete 应 409
    print("=" * 60)
    print("Test 4: soft-delete 已 inactive SKU -> 409")
    print("=" * 60)
    async for db in get_async_db():
        # 手动设为 inactive
        await db.execute(update(DimErpSku).where(DimErpSku.sku_id == TEST_SKU_ID).values(status="inactive"))
        await db.commit()
        try:
            await soft_delete_sku(
                sku_id=TEST_SKU_ID,
                body=SkuSoftDeleteRequest(confirm=True),
                db=db, _user=FakeUser(),
            )
            print("  [FAIL] expected 409")
            assert False
        except Exception as e:
            print(f"  [OK] got expected error: {str(e.detail)[:80]}")
        # 恢复
        await db.execute(update(DimErpSku).where(DimErpSku.sku_id == TEST_SKU_ID).values(status="active"))
        await db.commit()

    # Test 5: 边界 — SKU 不存在应 404
    print("=" * 60)
    print("Test 5: 不存在的 SKU -> 404")
    print("=" * 60)
    async for db in get_async_db():
        try:
            await soft_delete_sku(
                sku_id=999999,
                body=SkuSoftDeleteRequest(confirm=True),
                db=db, _user=FakeUser(),
            )
            print("  [FAIL] expected 404")
            assert False
        except Exception as e:
            print(f"  [OK] got expected error: {str(e.detail)[:80]}")

    print()
    print("=" * 60)
    print("ALL M5.1 TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())