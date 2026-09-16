# -*- coding: utf-8 -*-
"""Test SPU restore (M3 最简版):spu soft-delete 后一键复活。

场景:
1. happy path: 软删 → restore → active=true + biz_status=promoted + binding 复活 + audit
2. already-active 409:对 active SPU 调 restore
3. not-exist 404:对不存在 SPU 调 restore
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
import asyncio
from datetime import date
from sqlalchemy import create_engine, select, text

from backend.models.database import get_async_db
from backend.domains.business.routers.product_center import (
    restore_spu,
    soft_delete_spu,
)
from backend.schemas.product_center import SpuRestoreRequest, SpuSoftDeleteRequest
from modules.core.db import DimSpu, BridgeSpuSku


TEST_SPU = "XH-OFFICE-GNH"


class FakeUser:
    user_id = 391
    username = "qaadmin"
    is_superuser = True


def reset_spu_sync(spu: str):
    """同步引擎:从 backup 恢复 SPU + binding + 清 audit。"""
    eng = create_engine("postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp")
    with eng.begin() as conn:
        conn.execute(text("""
            UPDATE core.dim_spu s SET active = b.active, biz_status = b.biz_status
            FROM core.dim_spu_backup_20260916 b
            WHERE s.spu = b.spu AND s.spu = :spu
        """), {"spu": spu})
        conn.execute(text("""
            UPDATE core.bridge_spu_sku SET binding_status='active', effective_to=NULL
            WHERE spu = :spu
        """), {"spu": spu})
        conn.execute(text("DELETE FROM public.fact_audit_logs WHERE resource_id = :spu"), {"spu": spu})


async def main():
    print("=" * 60)
    print("Reset 0: Restore XH-OFFICE-GNH to clean state")
    print("=" * 60)
    reset_spu_sync(TEST_SPU)
    print("  [OK]\n")

    # ---- Test 1: already-active 409 ----
    print("=" * 60)
    print("Test 1: restore already-active SPU -> 409")
    print("=" * 60)
    async for db in get_async_db():
        try:
            await restore_spu(
                spu=TEST_SPU,
                body=SpuRestoreRequest(confirm=True),
                db=db, _user=FakeUser(),
            )
            print("  [FAIL] expected HTTPException, got success")
            assert False
        except Exception as e:
            assert "已是启用状态" in str(e.detail) or "409" in str(e.status_code)
            print(f"  [OK] rejected: status={e.status_code} detail={e.detail}\n")
        break

    # ---- Test 2: not-exist 404 ----
    print("=" * 60)
    print("Test 2: restore non-existent SPU -> 404")
    print("=" * 60)
    async for db in get_async_db():
        try:
            await restore_spu(
                spu="XH-NOT-EXIST-9999",
                body=SpuRestoreRequest(confirm=True),
                db=db, _user=FakeUser(),
            )
            print("  [FAIL] expected HTTPException, got success")
            assert False
        except Exception as e:
            assert "not found" in str(e.detail).lower() or "404" in str(e.status_code)
            print(f"  [OK] rejected: status={e.status_code} detail={e.detail}\n")
        break

    # ---- Test 3: happy path 软删 → restore → 复活 + audit ----
    print("=" * 60)
    print("Test 3: soft delete -> restore -> active=true + biz_status=promoted + binding 复活")
    print("=" * 60)
    async for db in get_async_db():
        # 3a. 准备:让所有 active binding inactive(soft-delete 前置)
        await db.execute(
            text("""
                UPDATE core.bridge_spu_sku
                SET binding_status='inactive', effective_to=:d
                WHERE spu = :spu AND binding_status='active' AND effective_to IS NULL
            """),
            {"d": date.today(), "spu": TEST_SPU},
        )
        await db.commit()
        print("  3a. Inactivated all active bindings")

        # 3b. 软删
        sd = await soft_delete_spu(
            spu=TEST_SPU,
            body=SpuSoftDeleteRequest(confirm=True),
            db=db, _user=FakeUser(),
        )
        assert sd.audit_recorded is True
        print(f"  3b. soft_delete: biz_status={sd.biz_status} affected_bindings={sd.affected_bindings}")

        # 3c. 校验软删状态
        spu_row = await db.get(DimSpu, TEST_SPU)
        assert spu_row.active is False and spu_row.biz_status == "retired"
        print(f"  3c. dim_spu after soft-delete: active={spu_row.active} biz_status={spu_row.biz_status}")

        # 3d. 记录最早的 inactive binding id(预期会被复活)
        earliest_id = (await db.execute(
            select(BridgeSpuSku.id)
            .where(
                BridgeSpuSku.spu == TEST_SPU,
                BridgeSpuSku.binding_status == "inactive",
            )
            .order_by(BridgeSpuSku.effective_to.asc())
            .limit(1)
        )).scalar_one_or_none()
        print(f"  3d. earliest inactive binding id={earliest_id}")

        # 3e. restore
        resp = await restore_spu(
            spu=TEST_SPU,
            body=SpuRestoreRequest(confirm=True),
            db=db, _user=FakeUser(),
        )
        assert resp.audit_recorded is True
        assert resp.previous_biz_status == "retired"
        assert resp.new_biz_status == "promoted"
        assert resp.restored_bindings == 1
        print(f"  3e. restore response: {resp.previous_biz_status} → {resp.new_biz_status} restored_bindings={resp.restored_bindings}")

        # 3f. 校验 dim_spu 状态
        spu_row = await db.get(DimSpu, TEST_SPU)
        assert spu_row.active is True and spu_row.biz_status == "promoted"
        print(f"  3f. dim_spu after restore: active={spu_row.active} biz_status={spu_row.biz_status}")

        # 3g. 校验最早的 binding 已复活
        earliest = await db.get(BridgeSpuSku, earliest_id)
        assert earliest.binding_status == "active" and earliest.effective_to is None
        print(f"  3g. earliest binding复活: binding_status={earliest.binding_status} effective_to={earliest.effective_to}")

        # 3h. 校验 audit 有 spu_restore
        audit = (await db.execute(text(
            "SELECT action_type FROM public.fact_audit_logs "
            "WHERE resource_id=:spu AND action_type='spu_restore' ORDER BY log_id DESC LIMIT 1"
        ), {"spu": TEST_SPU})).mappings().first()
        assert audit is not None and audit["action_type"] == "spu_restore"
        print(f"  3h. audit record: {audit['action_type']}")

        print("  [OK] Test 3 passed\n")
        break

    # 收尾
    reset_spu_sync(TEST_SPU)
    print("=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())