#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复测试用户密码脚本

用于更新测试用户的密码，确保密码正确。
"""

import sys
import asyncio
from pathlib import Path

# 添加项目根目录到 Python 路径
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models.database import AsyncSessionLocal
from modules.core.db import DimUser
from backend.services.auth_service import auth_service
from modules.core.logger import get_logger

logger = get_logger(__name__)


async def fix_user_password(username="admin", password="admin"):
    """修复用户密码"""
    async with AsyncSessionLocal() as db:
        try:
            # 查找用户
            result = await db.execute(select(DimUser).where(DimUser.username == username))
            user = result.scalar_one_or_none()
            
            if not user:
                logger.error(f"[ERROR] 用户 '{username}' 不存在")
                return False
            
            # 更新密码
            user.password_hash = auth_service.hash_password(password)
            user.is_active = True
            
            await db.commit()
            
            logger.info(f"[SUCCESS] 用户 '{username}' 密码已更新")
            logger.info(f"  用户ID: {user.user_id}")
            logger.info(f"  用户名: {user.username}")
            logger.info(f"  邮箱: {user.email}")
            logger.info(f"  是否激活: {user.is_active}")
            
            return True
            
        except Exception as e:
            await db.rollback()
            logger.error(f"[ERROR] 更新密码失败: {e}", exc_info=True)
            raise


async def main():
    """主函数"""
    print("=" * 70)
    print("  修复测试用户密码")
    print("=" * 70)
    
    try:
        success = await fix_user_password(
            username="admin",
            password="admin"
        )
        
        if success:
            print("\n" + "=" * 70)
            print("  密码修复完成")
            print("=" * 70)
            print("用户名: admin")
            print("密码: admin")
            print("\n[提示] 现在可以使用此账号进行 API 测试")
            print("=" * 70)
        
        return success
        
    except Exception as e:
        print(f"\n[ERROR] 修复失败: {e}")
        return False


if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n[INFO] 操作被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] 发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

