# -*- coding: utf-8 -*-
"""Test SPU soft-delete M1 implementation end-to-end."""
import sys
sys.stdout.reconfigure(encoding="utf-8")
import asyncio
from datetime import date
from sqlalchemy import create_engine, select, update, text

from backend.models.database import get_async_db
from backend.domains.business.routers.product_center import (
    _check_spu_deletion_blockers,
    preview_spu_deletion,
    soft_delete_spu,
)
from backend.schemas.product_center import SpuSoftDeleteRequest
from modules.core.db import DimSpu, BridgeSpuSku


TEST_SPU = "XH-OFFICE-GNH"


class FakeUser:
    user_id = 391
    username = "qaadmin"
    is_superuser = True


async def main():
    print("=" * 60)
    print("Reset 0: Restore XH-OFFICE-GNH from backup")
    print("=" * 60)
    sync_engine = create_engine("postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp")
    with sync_engine.begin() as conn:
        r = conn.execute(text("""
            UPDATE core.dim_spu s SET active = b.active, biz_status = b.biz_status
            FROM core.dim_spu_backup_20260916 b
            WHERE s.spu = b.spu AND s.spu = :spu
            RETURNING s.active, s.biz_status
        """), {"spu": TEST_SPU}).first()
        print(f"  dim_spu: active={r[0]} biz_status={r[1]}")
        conn.execute(text("""
            UPDATE core.bridge_spu_sku SET binding_status='active', effective_to=NULL
            WHERE spu = :spu
        """), {"spu": TEST_SPU})
        conn.execute(text("DELETE FROM public.fact_audit_logs WHERE resource_id = :spu"), {"spu": TEST_SPU})
    print()

    # Test 1: helper
    print("=" * 60)
    print("Test 1: _check_spu_deletion_blockers")
    print("=" * 60)
    async for db in get_async_db():
        checks = await _check_spu_deletion_blockers(db, TEST_SPU)
        for c in checks:
            print(f"  [{c.status.upper():4s}] {c.code:30s} {c.label}")
            if c.detail:
                print(f"          -> {c.detail}")
        fail = sum(1 for c in checks if c.status == "fail")
        assert fail >= 1, "expected at least 1 fail"
        print(f"  fail={fail} -> [OK]\n")
        break

    # Test 2: preview endpoint direct call
    print("=" * 60)
    print("Test 2: preview_spu_deletion direct call (blocked)")
    print("=" * 60)
    async for db in get_async_db():
        result = await preview_spu_deletion(spu=TEST_SPU, db=db, _user=FakeUser())
        print(f"  can_soft_delete={result.can_soft_delete}")
        print(f"  blocked_reasons={result.blocked_reasons}")
        assert result.can_soft_delete is False
        assert len(result.blocked_reasons) > 0
        print("  [OK]\n")
        break

    # Test 3: full flow (inactivate -> soft delete -> audit -> rollback)
    print("=" * 60)
    print("Test 3: Full soft-delete flow")
    print("=" * 60)
    async for db in get_async_db():
        snapshot = (await db.execute(select(BridgeSpuSku).where(BridgeSpuSku.spu == TEST_SPU))).scalars().all()
        snapshot_data = [{"id": b.id, "binding_status": b.binding_status, "effective_to": b.effective_to} for b in snapshot]
        print(f"  3a. Snapshot {len(snapshot_data)} bindings")

        await db.execute(
            update(BridgeSpuSku)
            .where(BridgeSpuSku.spu == TEST_SPU, BridgeSpuSku.binding_status == "active")
            .values(binding_status="inactive", effective_to=date.today())
        )
        await db.commit()
        print(f"  3b. Inactivated all active bindings")

        try:
            preview = await preview_spu_deletion(spu=TEST_SPU, db=db, _user=FakeUser())
            assert preview.can_soft_delete is True
            print(f"  3c. Preview after inactivating: can_soft_delete=True")

            sd_resp = await soft_delete_spu(
                spu=TEST_SPU,
                body=SpuSoftDeleteRequest(confirm=True),
                db=db, _user=FakeUser(),
            )
            print(f"  3d. soft_delete_spu response: spu={sd_resp.spu} biz_status={sd_resp.biz_status} audit_recorded={sd_resp.audit_recorded}")

            spu_row = await db.get(DimSpu, TEST_SPU)
            assert spu_row.active is False and spu_row.biz_status == "retired"
            print(f"  3e. dim_spu: active={spu_row.active} biz_status={spu_row.biz_status}")

            audit = (await db.execute(text(
                "SELECT action_type FROM public.fact_audit_logs "
                "WHERE resource_id=:spu AND action_type='soft_delete' ORDER BY log_id DESC LIMIT 1"
            ), {"spu": TEST_SPU})).mappings().first()
            assert audit is not None and audit["action_type"] == "soft_delete"
            print(f"  3f. audit record: {audit['action_type']}")
            print("  [OK] Test 3 passed\n")

        finally:
            for b in snapshot_data:
                await db.execute(
                    update(BridgeSpuSku).where(BridgeSpuSku.id == b["id"]).values(
                        binding_status=b["binding_status"], effective_to=b["effective_to"],
                    )
                )
            await db.execute(
                update(DimSpu).where(DimSpu.spu == TEST_SPU).values(active=True, biz_status="candidate")
            )
            await db.commit()
            with sync_engine.begin() as c:
                c.execute(text("DELETE FROM public.fact_audit_logs WHERE resource_id = :spu"), {"spu": TEST_SPU})
            print(f"  3g. Restored state")

    print("=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())