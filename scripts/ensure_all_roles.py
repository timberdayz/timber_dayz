#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
确保所有必需角色存在

根据2026-01-08讨论的权限矩阵，确保以下角色存在：
1. 管理员 (admin) - 系统管理员
2. 主管 (manager) - 部门主管
3. 操作员 (operator) - 日常操作人员（将"运营人员"重命名为"操作员"）
4. 财务 (finance) - 财务人员

执行方式:
    python scripts/ensure_all_roles.py
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, text
from backend.utils.config import get_settings
from modules.core.logger import get_logger

logger = get_logger(__name__)

# 角色定义（根据2026-01-08讨论的权限矩阵）
REQUIRED_ROLES = [
    {
        'role_code': 'admin',
        'role_name': '管理员',
        'description': '系统管理员，拥有所有系统权限，包括用户审批、系统配置、数据管理等',
        'is_system': True
    },
    {
        'role_code': 'manager',
        'role_name': '主管',
        'description': '部门主管，拥有业务管理、审批和配置权限，可管理账号、目标、采购、报表等',
        'is_system': False
    },
    {
        'role_code': 'operator',
        'role_name': '操作员',  # 统一使用"操作员"而不是"运营人员"
        'description': '日常操作人员，拥有基础业务操作权限，可进行数据同步、订单处理等日常操作',
        'is_system': False
    },
    {
        'role_code': 'finance',
        'role_name': '财务',
        'description': '财务人员，拥有财务和销售数据查看权限，可进行财务管理和报表查看',
        'is_system': False
    }
]

def safe_print(text):
    """安全打印（处理Windows GBK编码）"""
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        try:
            safe_text = text.encode('gbk', errors='ignore').decode('gbk')
            print(safe_text, flush=True)
        except:
            safe_text = text.encode('ascii', errors='ignore').decode('ascii')
            print(safe_text, flush=True)

def ensure_all_roles():
    """确保所有必需角色存在"""
    try:
        settings = get_settings()
        engine = create_engine(settings.DATABASE_URL)
        
        with engine.connect() as conn:
            trans = conn.begin()
            try:
                safe_print("开始检查并创建必需角色...")
                
                created_count = 0
                updated_count = 0
                
                for role_def in REQUIRED_ROLES:
                    # 检查角色是否存在（按role_code）
                    result = conn.execute(text("""
                        SELECT role_id, role_name, role_code, description, is_system
                        FROM dim_roles 
                        WHERE role_code = :role_code
                    """), {"role_code": role_def['role_code']})
                    existing_role = result.fetchone()
                    
                    if existing_role:
                        # 角色已存在，检查是否需要更新
                        role_id, role_name, role_code, description, is_system = existing_role
                        needs_update = False
                        update_fields = []
                        update_params = {}
                        
                        # 检查角色名称是否需要更新
                        if role_name != role_def['role_name']:
                            # 特殊处理：如果现有角色是"运营人员"，更新为"操作员"
                            if role_code == 'operator' and role_name == '运营人员':
                                update_fields.append("role_name = :role_name")
                                update_params['role_name'] = role_def['role_name']
                                needs_update = True
                                safe_print(f"[更新] 将角色 '{role_name}' 重命名为 '{role_def['role_name']}'")
                        
                        # 检查描述是否需要更新
                        if description != role_def['description']:
                            update_fields.append("description = :description")
                            update_params['description'] = role_def['description']
                            needs_update = True
                        
                        # 检查is_system是否需要更新
                        if is_system != role_def['is_system']:
                            update_fields.append(f"is_system = {role_def['is_system']}")
                            needs_update = True
                        
                        if needs_update:
                            # 构建更新SQL
                            update_fields.append("updated_at = NOW()")
                            update_params['role_code'] = role_def['role_code']
                            
                            update_sql = f"""
                                UPDATE dim_roles 
                                SET {', '.join(update_fields)}
                                WHERE role_code = :role_code
                            """
                            conn.execute(text(update_sql), update_params)
                            updated_count += 1
                            safe_print(f"[更新] 角色 '{role_def['role_name']}' (role_code: {role_code})")
                        else:
                            safe_print(f"[跳过] 角色 '{role_def['role_name']}' (role_code: {role_code}) 已存在且无需更新")
                    else:
                        # 角色不存在，创建它
                        conn.execute(text("""
                            INSERT INTO dim_roles (role_code, role_name, description, is_active, permissions, data_scope, is_system)
                            VALUES (:role_code, :role_name, :description, true, '[]', 'all', :is_system)
                        """), {
                            "role_code": role_def['role_code'],
                            "role_name": role_def['role_name'],
                            "description": role_def['description'],
                            "is_system": role_def['is_system']
                        })
                        created_count += 1
                        safe_print(f"[创建] 角色 '{role_def['role_name']}' (role_code: {role_def['role_code']})")
                
                trans.commit()
                
                safe_print("=" * 70)
                safe_print(f"[完成] 角色检查完成")
                safe_print(f"  创建: {created_count} 个角色")
                safe_print(f"  更新: {updated_count} 个角色")
                safe_print("=" * 70)
                
                # 验证结果
                safe_print("\n[验证] 当前数据库中的角色列表:")
                result = conn.execute(text("""
                    SELECT role_id, role_code, role_name, description, is_system, created_at
                    FROM dim_roles 
                    ORDER BY role_id
                """))
                roles = result.fetchall()
                for role in roles:
                    safe_print(f"  - {role[2]} (role_code: {role[1]}, is_system: {role[4]})")
                    safe_print(f"    描述: {role[3]}")
                
                return True
                    
            except Exception as e:
                trans.rollback()
                safe_print(f"[ERROR] 操作失败: {e}")
                import traceback
                traceback.print_exc()
                return False
                
    except Exception as e:
        safe_print(f"[ERROR] 数据库连接失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    safe_print("开始确保所有必需角色存在...")
    success = ensure_all_roles()
    if success:
        safe_print("[完成] 所有必需角色已确保存在")
        sys.exit(0)
    else:
        safe_print("[失败] 角色创建/更新失败")
        sys.exit(1)
