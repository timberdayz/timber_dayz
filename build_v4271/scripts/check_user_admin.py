#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查指定用户的管理员权限
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
from modules.core.logger import get_logger

logger = get_logger(__name__)


async def check_user_admin(username: str = "xihong"):
    """检查指定用户的管理员权限"""
    async with AsyncSessionLocal() as db:
        try:
            # 查询用户
            result = await db.execute(
                select(DimUser)
                .options(selectinload(DimUser.roles))
                .where(DimUser.username == username)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                print(f"[ERROR] 用户 '{username}' 不存在")
                return False
            
            # 刷新角色关系
            await db.refresh(user, ["roles"])
            
            print("=" * 70)
            print(f"  检查用户 '{username}' 的管理员权限")
            print("=" * 70)
            print(f"\n[用户信息]")
            print(f"  用户ID: {user.user_id}")
            print(f"  用户名: {user.username}")
            print(f"  邮箱: {user.email}")
            print(f"  姓名: {user.full_name or '未设置'}")
            print(f"  状态: {user.status}")
            print(f"  是否激活: {user.is_active}")
            print(f"  是否超级用户: {user.is_superuser}")
            
            # 检查角色
            roles_list = [role for role in user.roles]
            print(f"\n[角色信息]")
            if roles_list:
                for role in roles_list:
                    print(f"  - {role.role_name} (role_code: {role.role_code})")
            else:
                print("  未分配角色")
            
            # 检查管理员权限
            print(f"\n[权限检查]")
            is_admin = False
            
            # 1. 检查 is_superuser 标志
            if user.is_superuser:
                print("  [OK] 用户是超级用户 (is_superuser = True)")
                is_admin = True
            else:
                print("  [X] 用户不是超级用户 (is_superuser = False)")
            
            # 2. 检查是否有 admin 角色
            has_admin_role = any(
                (hasattr(role, "role_code") and role.role_code == "admin") or
                (hasattr(role, "role_name") and role.role_name == "admin")
                for role in user.roles
            )
            
            if has_admin_role:
                print("  [OK] 用户拥有管理员角色 (role_code='admin' 或 role_name='admin')")
                is_admin = True
            else:
                print("  [X] 用户没有管理员角色")
            
            # 总结
            print(f"\n[结论]")
            if is_admin:
                print(f"  [OK] 用户 '{username}' 具有管理员权限")
                print(f"  [提示] 可以访问系统管理模块的所有功能")
            else:
                print(f"  [X] 用户 '{username}' 不具有管理员权限")
                print(f"  [提示] 无法访问需要管理员权限的功能")
                print(f"  [建议] 如果需要管理员权限，请:")
                print(f"    1. 设置 is_superuser = True")
                print(f"    2. 或分配 role_code='admin' 的角色")
            
            print("\n" + "=" * 70)
            
            return is_admin
            
        except Exception as e:
            logger.error(f"[ERROR] 检查用户权限失败: {e}", exc_info=True)
            print(f"\n[ERROR] 检查失败: {e}")
            import traceback
            traceback.print_exc()
            return False


async def main():
    """主函数"""
    try:
        username = sys.argv[1] if len(sys.argv) > 1 else "xihong"
        is_admin = await check_user_admin(username)
        return is_admin
    except Exception as e:
        print(f"\n[ERROR] 发生错误: {e}")
        import traceback
        traceback.print_exc()
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
