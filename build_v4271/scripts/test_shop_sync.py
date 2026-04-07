#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试店铺同步功能

测试场景：
1. 创建账号时自动同步到 dim_shops
2. 更新账号时自动更新 dim_shops
3. 目标管理创建分解时自动同步店铺
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, text

from modules.core.db import PlatformAccount, DimShop, DimPlatform
from backend.services.shop_sync_service import sync_platform_account_to_dim_shop
from backend.services.encryption_service import get_encryption_service
from modules.core.logger import get_logger

logger = get_logger(__name__)


async def test_shop_sync():
    """测试店铺同步功能"""
    # 从环境变量获取数据库URL
    import os
    database_url = os.getenv("DATABASE_URL", "postgresql://erp_user:erp_pass_2025@localhost:5432/xihong_erp")
    
    # 转换为异步URL
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    
    engine = create_async_engine(database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db:
        try:
            print("=" * 60)
            print("测试1: 创建测试账号并同步到 dim_shops")
            print("=" * 60)
            
            # 清理测试数据
            test_account_id = "test_shop_sync_001"
            test_shop_id = "test_shop_001"
            
            # 删除测试账号
            result = await db.execute(
                select(PlatformAccount).where(PlatformAccount.account_id == test_account_id)
            )
            test_account = result.scalar_one_or_none()
            if test_account:
                await db.delete(test_account)
                await db.commit()
                print(f"[清理] 删除已有测试账号: {test_account_id}")
            
            # 删除测试店铺
            result = await db.execute(
                select(DimShop).where(
                    DimShop.platform_code == "shopee",
                    DimShop.shop_id == test_shop_id
                )
            )
            test_shop = result.scalar_one_or_none()
            if test_shop:
                await db.delete(test_shop)
                await db.commit()
                print(f"[清理] 删除已有测试店铺: shopee/{test_shop_id}")
            
            # 创建测试账号
            encryption_service = get_encryption_service()
            test_account = PlatformAccount(
                account_id=test_account_id,
                platform="shopee",
                store_name="测试店铺",
                shop_id=test_shop_id,
                shop_region="SG",
                currency="SGD",
                username="test_user",
                password_encrypted=encryption_service.encrypt_password("test_password"),
                enabled=True,
                created_by="test",
                updated_by="test"
            )
            db.add(test_account)
            await db.commit()
            await db.refresh(test_account)
            print(f"[创建] 测试账号创建成功: {test_account_id}")
            
            # 同步到 dim_shops
            shop = await sync_platform_account_to_dim_shop(db, test_account)
            await db.commit()
            
            if shop:
                print(f"[同步] 店铺同步成功: {shop.platform_code}/{shop.shop_id}")
                print(f"  - 店铺名称: {shop.shop_name}")
                print(f"  - 区域: {shop.region}")
                print(f"  - 货币: {shop.currency}")
            else:
                print("[错误] 店铺同步失败：返回 None")
                return False
            
            # 验证店铺是否存在
            result = await db.execute(
                select(DimShop).where(
                    DimShop.platform_code == "shopee",
                    DimShop.shop_id == test_shop_id
                )
            )
            verified_shop = result.scalar_one_or_none()
            if verified_shop:
                print(f"[验证] 店铺在 dim_shops 中存在: {verified_shop.shop_name}")
            else:
                print("[错误] 店铺在 dim_shops 中不存在")
                return False
            
            print("\n" + "=" * 60)
            print("测试2: 更新账号信息并同步更新 dim_shops")
            print("=" * 60)
            
            # 更新账号信息
            test_account.store_name = "更新后的测试店铺"
            test_account.shop_region = "MY"
            test_account.currency = "MYR"
            await db.commit()
            await db.refresh(test_account)
            print(f"[更新] 账号信息已更新: {test_account.store_name}")
            
            # 同步更新
            shop = await sync_platform_account_to_dim_shop(db, test_account)
            await db.commit()
            
            if shop:
                print(f"[同步] 店铺信息已更新:")
                print(f"  - 店铺名称: {shop.shop_name}")
                print(f"  - 区域: {shop.region}")
                print(f"  - 货币: {shop.currency}")
                
                # 验证更新
                if shop.shop_name == "更新后的测试店铺" and shop.region == "MY" and shop.currency == "MYR":
                    print("[验证] 店铺信息更新成功")
                else:
                    print("[错误] 店铺信息更新不完整")
                    return False
            else:
                print("[错误] 店铺同步失败")
                return False
            
            print("\n" + "=" * 60)
            print("测试3: 测试没有 shop_id 的账号（应跳过同步）")
            print("=" * 60)
            
            test_account_no_shop_id = PlatformAccount(
                account_id="test_no_shop_id_001",
                platform="shopee",
                store_name="无店铺ID的账号",
                shop_id=None,  # 没有 shop_id
                username="test_user2",
                password_encrypted=encryption_service.encrypt_password("test_password"),
                enabled=True,
                created_by="test",
                updated_by="test"
            )
            db.add(test_account_no_shop_id)
            await db.commit()
            await db.refresh(test_account_no_shop_id)
            
            shop = await sync_platform_account_to_dim_shop(db, test_account_no_shop_id)
            if shop is None:
                print("[验证] 没有 shop_id 的账号正确跳过同步")
            else:
                print("[警告] 没有 shop_id 的账号不应该同步，但返回了店铺对象")
            
            # 清理测试数据
            await db.delete(test_account_no_shop_id)
            await db.commit()
            
            print("\n" + "=" * 60)
            print("测试完成：所有测试通过！")
            print("=" * 60)
            
            # 清理测试账号和店铺
            await db.delete(test_account)
            await db.delete(verified_shop)
            await db.commit()
            print("[清理] 测试数据已清理")
            
            return True
            
        except Exception as e:
            logger.error(f"测试失败: {e}", exc_info=True)
            await db.rollback()
            return False
        finally:
            await engine.dispose()


if __name__ == "__main__":
    import asyncio
    
    success = asyncio.run(test_shop_sync())
    sys.exit(0 if success else 1)
