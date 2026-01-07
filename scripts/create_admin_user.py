#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
创建管理员用户脚本

用于创建管理员账号，用于审批新用户注册。
"""

import sys
import asyncio
from pathlib import Path

# 添加项目根目录到 Python 路径
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from backend.models.database import AsyncSessionLocal
from modules.core.db import DimUser, DimRole
from backend.services.auth_service import auth_service
from modules.core.logger import get_logger

logger = get_logger(__name__)


async def create_admin_user(
    username="xihong",
    password="~!Qq1`1`",
    email="xihong@xihong.com",
    full_name="系统管理员"
):
    """创建管理员用户"""
    async with AsyncSessionLocal() as db:
        try:
            # 检查用户是否已存在
            result = await db.execute(select(DimUser).where(DimUser.username == username))
            existing_user = result.scalar_one_or_none()
            
            if existing_user:
                logger.info(f"[INFO] 用户 '{username}' 已存在，更新为管理员")
                # 重新加载用户和角色关系（在会话内）
                await db.refresh(existing_user, ["roles"])
                
                # 更新现有用户为管理员
                existing_user.password_hash = auth_service.hash_password(password)
                existing_user.email = email
                existing_user.full_name = full_name
                existing_user.status = "active"
                existing_user.is_active = True
                existing_user.is_superuser = True
                
                # 确保分配 admin 角色（使用 role_code 或 role_name 查找）
                result = await db.execute(
                    select(DimRole).where(
                        (DimRole.role_code == "admin") | (DimRole.role_name == "admin")
                    )
                )
                admin_role = result.scalar_one_or_none()
                
                # 如果 admin 角色不存在，创建它
                if not admin_role:
                    logger.info(f"[INFO] admin 角色不存在，创建 admin 角色")
                    admin_role = DimRole(
                        role_code="admin",
                        role_name="管理员",
                        description="系统管理员",
                        permissions="[]",
                        is_active=True,
                        is_system=True
                    )
                    db.add(admin_role)
                    await db.flush()
                
                # ⭐ 修复：直接操作关联表，避免懒加载问题
                from sqlalchemy import text
                result = await db.execute(
                    text("SELECT 1 FROM user_roles WHERE user_id = :user_id AND role_id = :role_id"),
                    {"user_id": existing_user.user_id, "role_id": admin_role.role_id}
                )
                if not result.scalar_one_or_none():
                    await db.execute(
                        text("INSERT INTO user_roles (user_id, role_id) VALUES (:user_id, :role_id)"),
                        {"user_id": existing_user.user_id, "role_id": admin_role.role_id}
                    )
                    logger.info(f"[INFO] 已分配 admin 角色")
                else:
                    logger.info(f"[INFO] 用户已拥有 admin 角色，跳过分配")
                
                await db.commit()
                await db.refresh(existing_user, ["roles"])
                
                # 在会话内访问关系
                roles_list = [role.role_name for role in existing_user.roles]
                
                logger.info(f"[SUCCESS] 用户 '{username}' 已更新为管理员")
                logger.info(f"  用户ID: {existing_user.user_id}")
                logger.info(f"  用户名: {existing_user.username}")
                logger.info(f"  邮箱: {existing_user.email}")
                logger.info(f"  状态: {existing_user.status}")
                logger.info(f"  是否激活: {existing_user.is_active}")
                logger.info(f"  是否超级用户: {existing_user.is_superuser}")
                logger.info(f"  角色: {roles_list}")
                
                return existing_user
            else:
                # 创建新用户
                user = DimUser(
                    username=username,
                    email=email,
                    password_hash=auth_service.hash_password(password),
                    full_name=full_name,
                    status="active",
                    is_active=True,
                    is_superuser=True
                )
                
                db.add(user)
                await db.flush()  # 获取用户ID
                
                # 分配 admin 角色（使用 role_code 或 role_name 查找）
                result = await db.execute(
                    select(DimRole).where(
                        (DimRole.role_code == "admin") | (DimRole.role_name == "admin")
                    )
                )
                admin_role = result.scalar_one_or_none()
                
                # 如果 admin 角色不存在，创建它
                if not admin_role:
                    logger.info(f"[INFO] admin 角色不存在，创建 admin 角色")
                    admin_role = DimRole(
                        role_code="admin",
                        role_name="管理员",
                        description="系统管理员",
                        permissions="[]",
                        is_active=True,
                        is_system=True
                    )
                    db.add(admin_role)
                    await db.flush()
                
                # ⭐ 修复：直接操作关联表，避免懒加载问题
                from sqlalchemy import text
                await db.execute(
                    text("INSERT INTO user_roles (user_id, role_id) VALUES (:user_id, :role_id) ON CONFLICT DO NOTHING"),
                    {"user_id": user.user_id, "role_id": admin_role.role_id}
                )
                logger.info(f"[INFO] 已分配 admin 角色")
                
                await db.commit()
                
                # 重新加载用户和角色关系（在会话内）
                await db.refresh(user, ["roles"])
                
                # 在会话内访问关系（现在 roles 已经加载）
                roles_list = [role.role_name for role in user.roles]
                
                logger.info(f"[SUCCESS] 管理员用户 '{username}' 创建成功")
                logger.info(f"  用户ID: {user.user_id}")
                logger.info(f"  用户名: {user.username}")
                logger.info(f"  邮箱: {user.email}")
                logger.info(f"  状态: {user.status}")
                logger.info(f"  是否激活: {user.is_active}")
                logger.info(f"  是否超级用户: {user.is_superuser}")
                logger.info(f"  角色: {roles_list}")
                
                return user
                
        except Exception as e:
            await db.rollback()
            logger.error(f"[ERROR] 创建管理员用户失败: {e}", exc_info=True)
            raise


async def main():
    """主函数"""
    print("=" * 70)
    print("  创建管理员用户")
    print("=" * 70)
    
    # 创建管理员用户
    try:
        user = await create_admin_user(
            username="xihong",
            password="~!Qq1`1`",
            email="xihong@xihong.com",
            full_name="系统管理员"
        )
        
        print("\n" + "=" * 70)
        print("  管理员用户创建/更新完成")
        print("=" * 70)
        print(f"用户名: {user.username}")
        print(f"密码: ~!Qq1`1`")
        print(f"邮箱: {user.email}")
        print(f"状态: {user.status}")
        print(f"是否激活: {user.is_active}")
        print(f"是否超级用户: {user.is_superuser}")
        print("\n[提示] 现在可以使用此账号登录系统并审批新用户")
        print("=" * 70)
        
        return True
        
    except Exception as e:
        print(f"\n[ERROR] 创建管理员用户失败: {e}")
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

