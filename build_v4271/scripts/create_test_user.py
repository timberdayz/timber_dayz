#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
创建测试用户脚本

用于创建测试用户，方便进行 API 测试。
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
from modules.core.db import DimUser, DimRole
from backend.services.auth_service import auth_service
from modules.core.logger import get_logger

logger = get_logger(__name__)


async def create_test_user(username="admin", password="admin", email="admin@test.com", full_name="测试管理员"):
    """创建测试用户"""
    async with AsyncSessionLocal() as db:
        try:
            # 检查用户是否已存在
            result = await db.execute(select(DimUser).where(DimUser.username == username))
            existing_user = result.scalar_one_or_none()
            
            if existing_user:
                logger.info(f"[INFO] 用户 '{username}' 已存在，跳过创建")
                return existing_user
            
            # 创建新用户
            user = DimUser(
                username=username,
                email=email,
                password_hash=auth_service.hash_password(password),
                full_name=full_name,
                is_active=True
            )
            
            db.add(user)
            await db.flush()  # 获取用户ID
            
            # 分配 admin 角色
            result = await db.execute(select(DimRole).where(DimRole.role_name == "admin"))
            admin_role = result.scalar_one_or_none()
            
            if admin_role:
                user.roles.append(admin_role)
                logger.info(f"[INFO] 已分配 admin 角色")
            else:
                logger.warning(f"[WARN] admin 角色不存在，用户创建成功但未分配角色")
            
            await db.commit()
            
            # 重新加载用户和角色关系（在会话内）
            await db.refresh(user)
            # 在会话内访问关系，避免异步问题
            roles_list = []
            for role in user.roles:
                roles_list.append(role.role_name)
            
            logger.info(f"[SUCCESS] 用户 '{username}' 创建成功")
            logger.info(f"  用户ID: {user.user_id}")
            logger.info(f"  用户名: {user.username}")
            logger.info(f"  邮箱: {user.email}")
            logger.info(f"  角色: {roles_list}")
            
            return user
            
        except Exception as e:
            await db.rollback()
            logger.error(f"[ERROR] 创建用户失败: {e}", exc_info=True)
            raise


async def main():
    """主函数"""
    print("=" * 70)
    print("  创建测试用户")
    print("=" * 70)
    
    # 创建默认测试用户
    try:
        user = await create_test_user(
            username="admin",
            password="admin",
            email="admin@test.com",
            full_name="测试管理员"
        )
        
        print("\n" + "=" * 70)
        print("  测试用户创建完成")
        print("=" * 70)
        print(f"用户名: {user.username}")
        print(f"密码: admin")
        print(f"邮箱: {user.email}")
        # 注意：在会话外访问关系可能有问题，这里只显示基本信息
        print(f"角色: 已创建（如需查看角色，请查询数据库）")
        print("\n[提示] 现在可以使用此账号进行 API 测试")
        print("=" * 70)
        
        return True
        
    except Exception as e:
        print(f"\n[ERROR] 创建用户失败: {e}")
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

